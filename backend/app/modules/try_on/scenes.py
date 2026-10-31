import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from app.integrations.vertex import GenerationError, scene_configuration
from app.modules.try_on.queries import owned_session
from app.modules.try_on.service import FAILURES, fail, job_data, reserve_quota, source_row


SCENES = {
    'CHERRY_BLOSSOM': ('櫻花', 'a peaceful Japanese cherry blossom walkway in full bloom, with soft natural daylight'),
    'TEMPLE': ('寺廟', 'a traditional Japanese Buddhist temple courtyard, wooden temple architecture and a serene garden, with soft natural daylight'),
}


def scene_prompt(scene_id):
    return ('Edit the background of this photograph only. Place the existing person in ' + SCENES[scene_id][1]
        + '. Preserve exactly the same person, face, identity, hair, expression, body, pose, kimono, obi belt, patterns, colors and accessories. '
        'Do not restyle or replace any clothing. Keep the full person and original composition and aspect ratio. '
        'Only adjust environmental lighting and contact shadows as needed for a realistic photograph. '
        'No added people, text, watermarks, logos or framing. Return one edited image.')


def parent_source(connection, job_id, member):
    parent=connection.execute("""SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s
        AND source='WEBSITE' AND kind='TRY_ON' AND status='SUCCEEDED' AND expires_at>now()
        AND deleted_at IS NULL AND NOT cleanup_pending FOR SHARE""",(job_id,member)).fetchone()
    if not parent: fail(422,'SCENE_SOURCE_UNAVAILABLE','請先完成並選用仍有效的原始試穿圖；場景圖不能作為場景生成來源。')
    session=owned_session(parent['session_id'],member,connection)
    source=source_row(session,connection,parent['photo_id'],parent['model_id'],parent['kimono_id'])
    if parent['person_source_key'] and source['source_key']!=parent['person_source_key']:
        fail(409,'SOURCE_CHANGED','原始人物來源已變更，請重新試穿。')
    return parent


def create_scene(job_id,body,member,connection,response,idempotency_key):
    if not body.confirmed: fail(403,'GENERATION_CONFIRMATION_REQUIRED','請先明確確認這次場景生成。')
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(member,)).fetchone()
    parent=parent_source(connection,job_id,member)
    prompt=scene_prompt(body.scene_id)
    cache_key=hashlib.sha256(json.dumps([str(parent['id']),parent['result_key'],body.scene_id,prompt,
        os.getenv('VERTEX_SCENE_MODEL','gemini-nano-banana-2.1')]).encode()).hexdigest()
    fingerprint=hashlib.sha256(json.dumps([str(job_id),body.model_dump(mode='json')],sort_keys=True).encode()).hexdigest()
    old=connection.execute('SELECT * FROM generation_jobs WHERE user_id=%s AND idempotency_key=%s',(member,idempotency_key)).fetchone()
    if old:
        if old['request_hash']!=fingerprint or old['reuse_key']!=cache_key:
            fail(409,'IDEMPOTENCY_CONFLICT','同一次場景請求的來源或場景已變更，請重新確認。')
        response.status_code=200
        return job_data(old,reused=old['status']=='SUCCEEDED' and bool(old['expires_at']) and old['expires_at']>datetime.now(timezone.utc))
    previous=connection.execute("""SELECT * FROM generation_jobs WHERE user_id=%s AND reuse_key=%s AND kind='SCENE'
        AND source='WEBSITE' AND deleted_at IS NULL AND NOT cleanup_pending
        AND ((status='SUCCEEDED' AND expires_at>now()) OR status IN ('QUEUED','VALIDATING','GENERATING'))
        ORDER BY completed_at DESC NULLS LAST,created_at DESC LIMIT 1""",(member,cache_key)).fetchone()
    if previous:
        response.status_code=200
        return job_data(previous,reused=previous['status']=='SUCCEEDED')
    try: _,location,model=scene_configuration()
    except GenerationError as error: fail(503,error.code,FAILURES[error.code])
    day=reserve_quota(connection,member)
    identity=uuid4()
    row=connection.execute('''INSERT INTO generation_jobs
        (id,user_id,session_id,plan_id,kimono_id,photo_id,model_id,belt_id,kind,parent_job_id,scene_id,scene_prompt,
         person_source_key,reuse_key,status,idempotency_key,request_hash,usage_day,provider_model,provider_location,result_key)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'SCENE',%s,%s,%s,%s,%s,'QUEUED',%s,%s,%s,%s,%s,%s) RETURNING *''',
        (identity,member,parent['session_id'],parent['plan_id'],parent['kimono_id'],parent['photo_id'],parent['model_id'],parent['belt_id'],
         parent['id'],body.scene_id,prompt,parent['person_source_key'],cache_key,idempotency_key,fingerprint,day,model,location,
         f'private/try-on/generations/{member}/{identity}/result.jpg')).fetchone()
    return job_data(row)
