from app.core.config import PHOTO_MAX_BYTES as MAX_BYTES
from app.core.database import connect
from app.integrations.s3 import ensure_private_storage, private_bucket, remove_key, s3_client
from app.integrations.vertex import GenerationError, generate, generate_scene
from app.modules.try_on.scenes import parent_source
from app.modules.try_on.outfits import outfit_source
from app.modules.catalog.rules import validate_selection
from app.modules.catalog.schemas import LookSelection
from app.modules.try_on.queries import owned_session
from app.modules.try_on.service import source_row
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
import psycopg
import time


def read_source(client,key,max_bytes=MAX_BYTES):
    if not key or not key.startswith('private/try-on/'):
        raise GenerationError('SOURCE_UNAVAILABLE')
    stream=client.get_object(Bucket=private_bucket(),Key=key)['Body']
    try: data=stream.read(max_bytes+1)
    finally: stream.close()
    if len(data)>max_bytes: raise GenerationError('SOURCE_UNAVAILABLE')
    return data


def process_job(job):
    """No transaction spans the provider request, and no failed prediction is retried."""
    try:
        ensure_private_storage()
        client=s3_client()
        with connect() as connection:
            session=owned_session(job['session_id'],job['user_id'],connection)
            account=connection.execute('SELECT active FROM users WHERE id=%s',(job['user_id'],)).fetchone()
            if not account or not account['active']: raise GenerationError('SOURCE_UNAVAILABLE')
            if job['kind']=='TRY_ON':
                validate_selection(LookSelection(plan_id=job['plan_id'],kimono_id=job['kimono_id']),connection)
            source=source_row(session,connection,job['photo_id'],job['model_id'],job['kimono_id'])
            if job['kind']=='SCENE':
                parent=parent_source(connection,job['parent_job_id'],job['user_id'])
                person=read_source(client,parent['result_key'],20*1024*1024)
            else:
                outfit=outfit_source(connection,job['kimono_id'],job.get('belt_id'))
                if job.get('outfit_sha256') and (outfit['sha256']!=job['outfit_sha256'] or outfit['key']!=job['outfit_key']
                        or source['source_key']!=job['person_source_key']):
                    raise GenerationError('SOURCE_UNAVAILABLE')
                person=read_source(client,source['source_key'])
        def before_call():
            with connect() as connection:
                # Recheck consent immediately before transmitting the private photo.
                session=owned_session(job['session_id'],job['user_id'],connection)
                current_source=source_row(session,connection,job['photo_id'],job['model_id'],job['kimono_id'])
                if current_source['source_key']!=source['source_key']: raise GenerationError('SOURCE_UNAVAILABLE')
                if job['kind']=='SCENE':
                    current_parent=parent_source(connection,job['parent_job_id'],job['user_id'])
                    if current_parent['result_key']!=parent['result_key']: raise GenerationError('SOURCE_UNAVAILABLE')
                active=connection.execute('SELECT active FROM users WHERE id=%s',(job['user_id'],)).fetchone()
                if not active or not active['active']: raise GenerationError('SOURCE_UNAVAILABLE')
                marked=connection.execute("UPDATE generation_jobs SET status='GENERATING',provider_calls=provider_calls+1 WHERE id=%s AND status='VALIDATING' RETURNING id",(job['id'],)).fetchone()
                if not marked: raise GenerationError('WORKER_INTERRUPTED')
        image=(generate_scene(person,job['scene_prompt'],job['provider_location'],job['provider_model'],before_call)
            if job['kind']=='SCENE' else generate(person,outfit['content'],job['provider_location'],job['provider_model'],before_call))
        client.put_object(Bucket=private_bucket(),Key=job['result_key'],Body=image,ContentType='image/jpeg',CacheControl='no-store')
        with connect() as connection:
            completed=connection.execute("""UPDATE generation_jobs SET status='SUCCEEDED',completed_at=now(),
                expires_at=CASE WHEN source='MCP' THEN
                    (date_trunc('day',now() AT TIME ZONE 'Asia/Tokyo')+interval '1 day') AT TIME ZONE 'Asia/Tokyo'
                    ELSE now()+interval '7 days' END
                WHERE id=%s AND status='GENERATING' RETURNING id""",(job['id'],)).fetchone()
            if not completed: connection.execute('UPDATE generation_jobs SET cleanup_pending=true WHERE id=%s',(job['id'],))
    except Exception as error:
        # Provider errors can contain images, tokens or PII; persist only known codes.
        if isinstance(error,GenerationError): code=error.code
        elif isinstance(error,HTTPException): code='STORAGE_UNAVAILABLE' if error.status_code>=500 else 'SOURCE_UNAVAILABLE'
        elif isinstance(error,(ClientError,BotoCoreError)): code='STORAGE_UNAVAILABLE'
        else: code='INTERNAL_ERROR'
        with connect() as connection:
            connection.execute("UPDATE generation_jobs SET status='FAILED',failure_code=%s,completed_at=now(),cleanup_pending=true WHERE id=%s AND status IN ('VALIDATING','GENERATING')",(code,job['id']))


def cleanup_results():
    with connect() as connection:
        connection.execute("UPDATE generation_jobs SET status='FAILED',failure_code='WORKER_INTERRUPTED',completed_at=now(),cleanup_pending=true WHERE status IN ('VALIDATING','GENERATING') AND started_at<now()-interval '15 minutes'")
        connection.execute("UPDATE generation_jobs SET status='EXPIRED',cleanup_pending=true WHERE status='SUCCEEDED' AND expires_at<=now()")
        rows=connection.execute('SELECT id,result_key FROM generation_jobs WHERE cleanup_pending ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED').fetchall()
        if rows:
            versioned=ensure_private_storage()
            client=s3_client()
            for row in rows:
                remove_key(client,row['result_key'],versioned)
                connection.execute('UPDATE generation_jobs SET cleanup_pending=false WHERE id=%s',(row['id'],))


def worker(once=False):
    print('Try-on worker started. Paid requests run only for explicitly confirmed queued jobs.',flush=True)
    while True:
        try:
            from app.modules.bookings.service import cleanup_booking_holds
            cleanup_booking_holds()
            cleanup_results()
            with connect() as connection:
                job=connection.execute("SELECT * FROM generation_jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
                if job: connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(job['id'],))
            if job:
                process_job(job)
                print('Try-on job processed: '+str(job['id']),flush=True)
        except (psycopg.Error,ClientError,BotoCoreError,HTTPException):
            print('Worker services temporarily unavailable; queued jobs are preserved.',flush=True)
        if once: return
        time.sleep(3)
