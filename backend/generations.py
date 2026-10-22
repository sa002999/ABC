"""Durable website try-on queue, owner-only results and Tokyo daily quota."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import ConfigDict, StrictBool

from catalog import CamelModel
from database import connect, get_connection
from looks import LookSelection, Member, validate_selection
from person_sources import owned_session, require_consent
from photo_checks import MAX_BYTES
from photo_storage import ensure_private_storage, private_bucket, remove_key
from storage import read_product_image, s3_client
from vertex_try_on import GenerationError, configuration, generate

router = APIRouter(prefix='/api', tags=['AI 試穿'])
Connection = Annotated[psycopg.Connection, Depends(get_connection, scope='function')]
TOKYO = ZoneInfo('Asia/Tokyo')
ACTIVE = ('QUEUED','VALIDATING','GENERATING')
FAILURES = {
    'VERTEX_NOT_CONFIGURED':'AI 服務設定尚未完成，請聯絡管理者。',
    'VERTEX_CREDENTIALS':'AI 服務憑證無法使用，請聯絡管理者。',
    'VERTEX_PERMISSION':'Google Cloud 尚未開通此模型所需權限或服務，請聯絡管理者。',
    'VERTEX_MODEL_UNAVAILABLE':'目前設定的地區或模型無法使用，請聯絡管理者。',
    'PROVIDER_REJECTED':'AI 服務未產生可用圖片，請調整人物或服裝圖片後重新確認生成。',
    'PROVIDER_BUSY':'AI 服務目前額度不足或忙碌，請稍後重新確認生成。',
    'PROVIDER_TIMEOUT':'AI 服務回應逾時，未自動重送；重試須重新確認並使用新的 1 次額度。',
    'PROVIDER_UNAVAILABLE':'AI 服務暫時無法使用，未自動重新生成。',
    'INVALID_RESULT':'AI 服務回傳的圖片無法使用，請稍後重新確認生成。',
    'SOURCE_UNAVAILABLE':'人物照片、同意、商品或帳號已變更，請重新選擇來源。',
    'STORAGE_UNAVAILABLE':'圖片儲存服務暫時無法使用，請稍後重新確認生成。',
    'WORKER_INTERRUPTED':'生成處理中斷，未自動重送；請重新確認後再試。',
    'INTERNAL_ERROR':'生成處理失敗，未自動重送，請稍後再試。',
}


class GenerationInput(LookSelection):
    model_config = ConfigDict(extra='forbid')
    photo_id: UUID | None = None
    model_id: UUID | None = None
    confirmed: StrictBool


def fail(status, code, message):
    raise HTTPException(status, {'code':code,'message':message})


def day_bounds(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(TOKYO)
    return local.date(), datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),TOKYO)


def result_url(row):
    if row['status']!='SUCCEEDED' or not row['expires_at'] or row['expires_at']<=datetime.now(timezone.utc):
        return None
    ttl = min(120,int((row['expires_at']-datetime.now(timezone.utc)).total_seconds()))
    if ttl<1: return None
    return s3_client().generate_presigned_url('get_object',Params={'Bucket':private_bucket(),
        'Key':row['result_key'],'ResponseCacheControl':'no-store','ResponseContentType':'image/jpeg'},ExpiresIn=ttl)


def job_data(row):
    status = row['status']
    if status=='SUCCEEDED' and row['expires_at']<=datetime.now(timezone.utc): status='EXPIRED'
    url=result_url(row)
    return {'jobId':row['id'],'generationId':row['id'] if status=='SUCCEEDED' else None,
        'sessionId':row['session_id'],'status':status,'source':row['source'],'kind':row['kind'],
        'planId':row['plan_id'],'kimonoId':row['kimono_id'],
        'photoId':row['photo_id'],'modelId':row['model_id'],
        'createdAt':row['created_at'],'completedAt':row['completed_at'],'expiresAt':row['expires_at'],
        'imageUrl':url,'imageUrlExpiresIn':max(0,min(120,int((row['expires_at']-datetime.now(timezone.utc)).total_seconds()))) if url else None,
        'failure':{'code':row['failure_code'],'message':FAILURES.get(row['failure_code'],FAILURES['INTERNAL_ERROR'])} if row['failure_code'] else None,
        'qualityStatus':'NOT_CHECKED' if row['photo_id'] else 'STORE_REVIEWED'}


@router.get('/account/generation-usage')
def usage(member: Member, connection: Connection):
    day, reset = day_bounds()
    rows = connection.execute('SELECT source,used FROM generation_usage WHERE user_id=%s AND day=%s',(member,day)).fetchall()
    used = {row['source']:row['used'] for row in rows}
    return {'timezone':'Asia/Tokyo','day':day,'resetsAt':reset,
        'website':{'limit':5,'used':used.get('WEBSITE',0),'remaining':max(0,5-used.get('WEBSITE',0))},
        'mcp':{'limit':3,'used':used.get('MCP',0),'remaining':max(0,3-used.get('MCP',0))}}


def source_row(session, connection, photo_id, model_id):
    if session['source']=='SELF':
        require_consent(session)
        if model_id or not photo_id or session['current_photo_id']!=photo_id:
            fail(409,'SOURCE_CHANGED','本人照片已變更，請重新確認。')
        row = connection.execute("SELECT * FROM person_photos WHERE id=%s AND user_id=%s AND session_id=%s AND status IN ('FILE_READY','READY')",
            (photo_id,session['user_id'],session['id'])).fetchone()
    else:
        if photo_id or not model_id or session['model_id']!=model_id:
            fail(409,'SOURCE_CHANGED','模特兒已變更，請重新確認。')
        row = connection.execute('SELECT * FROM store_models WHERE id=%s AND active',(model_id,)).fetchone()
    if not row: fail(409,'SOURCE_UNAVAILABLE',FAILURES['SOURCE_UNAVAILABLE'])
    return row


@router.post('/try-on/sessions/{session_id}/generations', status_code=202)
def create_job(session_id: UUID, body: GenerationInput, member: Member, connection: Connection, response: Response,
               idempotency_key: Annotated[UUID, Header(alias='Idempotency-Key')]):
    if not body.confirmed: fail(403,'GENERATION_CONFIRMATION_REQUIRED','請先明確確認這次 AI 試穿。')
    fingerprint = hashlib.sha256(json.dumps({'session':str(session_id),**body.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
    # Serialize member quota checks and retries across tabs and API processes.
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(member,)).fetchone()
    old = connection.execute('SELECT * FROM generation_jobs WHERE user_id=%s AND idempotency_key=%s',(member,idempotency_key)).fetchone()
    if old:
        if old['request_hash']!=fingerprint: fail(409,'IDEMPOTENCY_CONFLICT','同一生成請求的內容不一致，請重新確認。')
        response.status_code=200
        return job_data(old)
    session = owned_session(session_id,member,connection,True)
    if (session['plan_id'],session['kimono_id'])!=(body.plan_id,body.kimono_id):
        fail(409,'OUTFIT_CHANGED','搭配已變更，請重新載入並確認。')
    validate_selection(body,connection)
    source_row(session,connection,body.photo_id,body.model_id)
    try: _,location,model=configuration()
    except GenerationError as error: fail(503,error.code,FAILURES[error.code])
    if connection.execute("SELECT 1 FROM generation_jobs WHERE user_id=%s AND status IN ('QUEUED','VALIDATING','GENERATING') LIMIT 1",(member,)).fetchone():
        fail(409,'GENERATION_IN_PROGRESS','已有試穿任務處理中，請先等待結果。')
    day,_ = day_bounds()
    connection.execute("INSERT INTO generation_usage(user_id,source,day) VALUES (%s,'WEBSITE',%s) ON CONFLICT DO NOTHING",(member,day))
    counted = connection.execute("UPDATE generation_usage SET used=used+1 WHERE user_id=%s AND source='WEBSITE' AND day=%s AND used<5 RETURNING used",(member,day)).fetchone()
    if not counted: fail(429,'GENERATION_QUOTA_EXCEEDED','今日網站生成額度已用完，將於日本時間午夜重設。')
    job_id=uuid4()
    row=connection.execute('''INSERT INTO generation_jobs
        (id,user_id,session_id,plan_id,kimono_id,photo_id,model_id,status,idempotency_key,request_hash,usage_day,provider_model,provider_location,result_key)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s,%s,%s,%s,%s) RETURNING *''',
        (job_id,member,session_id,body.plan_id,body.kimono_id,body.photo_id,body.model_id,idempotency_key,fingerprint,day,model,location,
         f'private/try-on/generations/{member}/{job_id}/result.jpg')).fetchone()
    return job_data(row)


@router.get('/try-on/jobs/{job_id}')
def get_job(job_id: UUID, member: Member, connection: Connection):
    row=connection.execute('SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s',(job_id,member)).fetchone()
    if not row: fail(404,'JOB_NOT_FOUND','找不到這個試穿任務。')
    return job_data(row)


@router.get('/try-on/generations')
def list_jobs(member: Member, connection: Connection, page: int=Query(0,ge=0,le=100000),
              page_size: int=Query(12,alias='pageSize',ge=1,le=50),source: Literal['WEBSITE','MCP'] | None=None):
    rows=connection.execute('SELECT * FROM generation_jobs WHERE user_id=%s'+(' AND source=%s' if source else '')+' ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s',
                           (member,*([source] if source else []),page_size+1,page*page_size)).fetchall()
    return {'data':[job_data(row) for row in rows[:page_size]],'nextPage':page+1 if len(rows)>page_size else None}


@router.delete('/try-on/generations/{generation_id}',status_code=202)
def delete_generation(generation_id: UUID, member: Member, connection: Connection):
    row=connection.execute('SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s FOR UPDATE',(generation_id,member)).fetchone()
    if not row: fail(404,'JOB_NOT_FOUND','找不到這張試穿圖。')
    if row['status'] in ACTIVE: fail(409,'GENERATION_IN_PROGRESS','任務仍在處理中，請等待完成後再刪除。')
    connection.execute("UPDATE generation_jobs SET status='DELETED',deleted_at=COALESCE(deleted_at,now()),cleanup_pending=true WHERE id=%s",(generation_id,))
    return {'ok':True,'deletionStatus':'QUEUED'}


def read_source(client,key):
    if not key or not key.startswith('private/try-on/'):
        raise GenerationError('SOURCE_UNAVAILABLE')
    stream=client.get_object(Bucket=private_bucket(),Key=key)['Body']
    try: data=stream.read(MAX_BYTES+1)
    finally: stream.close()
    if len(data)>MAX_BYTES: raise GenerationError('SOURCE_UNAVAILABLE')
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
            validate_selection(LookSelection(plan_id=job['plan_id'],kimono_id=job['kimono_id']),connection)
            source=source_row(session,connection,job['photo_id'],job['model_id'])
            asset=connection.execute("SELECT image_key FROM product_assets WHERE kimono_id=%s AND kind='PRODUCT' AND active ORDER BY sort_order,id LIMIT 1",(job['kimono_id'],)).fetchone()
            if not asset: raise GenerationError('SOURCE_UNAVAILABLE')
            person=read_source(client,source['source_key'])
            # Vertex accepts JPEG/PNG. Catalog's WebP remains a display asset.
            from PIL import Image
            from io import BytesIO
            product=BytesIO()
            with Image.open(BytesIO(read_product_image(asset['image_key']))) as image: image.convert('RGB').save(product,'JPEG',quality=95)
        def before_call():
            with connect() as connection:
                # Recheck consent immediately before transmitting the private photo.
                session=owned_session(job['session_id'],job['user_id'],connection)
                source_row(session,connection,job['photo_id'],job['model_id'])
                active=connection.execute('SELECT active FROM users WHERE id=%s',(job['user_id'],)).fetchone()
                if not active or not active['active']: raise GenerationError('SOURCE_UNAVAILABLE')
                marked=connection.execute("UPDATE generation_jobs SET status='GENERATING',provider_calls=provider_calls+1 WHERE id=%s AND status='VALIDATING' RETURNING id",(job['id'],)).fetchone()
                if not marked: raise GenerationError('WORKER_INTERRUPTED')
        image=generate(person,product.getvalue(),job['provider_location'],job['provider_model'],before_call)
        client.put_object(Bucket=private_bucket(),Key=job['result_key'],Body=image,ContentType='image/jpeg',CacheControl='no-store')
        with connect() as connection:
            completed=connection.execute("UPDATE generation_jobs SET status='SUCCEEDED',completed_at=now(),expires_at=now()+interval '7 days' WHERE id=%s AND status='GENERATING' RETURNING id",(job['id'],)).fetchone()
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
            from bookings import cleanup_booking_holds
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
