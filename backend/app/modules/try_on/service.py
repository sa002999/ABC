from app.integrations.s3 import private_bucket, s3_client
from app.integrations.vertex import GenerationError, configuration
from app.modules.catalog.rules import validate_selection
from app.modules.try_on.photos import require_consent, owned_photo
from app.modules.try_on.queries import owned_session
from app.modules.try_on.outfits import outfit_source, reuse_key
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from uuid import uuid4
from zoneinfo import ZoneInfo
import hashlib
import json


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


def job_data(row, reused=False):
    status = row['status']
    if status=='SUCCEEDED' and row['expires_at']<=datetime.now(timezone.utc): status='EXPIRED'
    url=result_url(row)
    return {'jobId':row['id'],'generationId':row['id'] if status=='SUCCEEDED' else None,
        'sessionId':row['session_id'],'status':status,'source':row['source'],'kind':row['kind'],
        'planId':row['plan_id'],'kimonoId':row['kimono_id'],'beltId':row.get('belt_id'),
        'parentJobId':row.get('parent_job_id'),'sceneId':row.get('scene_id'),
        'reused':reused,
        'photoId':row['photo_id'],'modelId':row['model_id'],
        'createdAt':row['created_at'],'completedAt':row['completed_at'],'expiresAt':row['expires_at'],
        'imageUrl':url,'imageUrlExpiresIn':max(0,min(120,int((row['expires_at']-datetime.now(timezone.utc)).total_seconds()))) if url else None,
        'failure':{'code':row['failure_code'],'message':FAILURES.get(row['failure_code'],FAILURES['INTERNAL_ERROR'])} if row['failure_code'] else None,
        'qualityStatus':'NOT_CHECKED' if row['photo_id'] else 'STORE_REVIEWED'}


def usage(member, connection):
    day, reset = day_bounds()
    rows = connection.execute('SELECT source,used FROM generation_usage WHERE user_id=%s AND day=%s',(member,day)).fetchall()
    used = {row['source']:row['used'] for row in rows}
    return {'timezone':'Asia/Tokyo','day':day,'resetsAt':reset,
        'website':{'limit':5,'used':used.get('WEBSITE',0),'remaining':max(0,5-used.get('WEBSITE',0))},
        'mcp':{'limit':3,'used':used.get('MCP',0),'remaining':max(0,3-used.get('MCP',0))}}


def source_row(session, connection, photo_id, model_id, kimono_id=None):
    if session['source']=='SELF':
        require_consent(session)
        if model_id or not photo_id or session['current_photo_id']!=photo_id:
            fail(409,'SOURCE_CHANGED','本人照片已變更，請重新確認。')
        row = owned_photo(photo_id,session['user_id'],connection)
    else:
        if photo_id or not model_id or session['model_id']!=model_id:
            fail(409,'SOURCE_CHANGED','模特兒已變更，請重新確認。')
        row = connection.execute('SELECT * FROM store_models WHERE id=%s AND active',(model_id,)).fetchone()
        garment = connection.execute('SELECT gender FROM kimonos WHERE id=%s', (kimono_id or session['kimono_id'],)).fetchone()
        if row and (not garment or row['role']!=garment['gender']):
            fail(422,'MODEL_ROLE_MISMATCH','請選擇適用此和服角色的商店模特兒。')
    if not row: fail(409,'SOURCE_UNAVAILABLE',FAILURES['SOURCE_UNAVAILABLE'])
    return row


def create_job(session_id, body, member, connection, response, idempotency_key, source='WEBSITE'):
    if source not in ('WEBSITE', 'MCP'): raise ValueError('Invalid trusted generation channel')
    if not body.confirmed: fail(403,'GENERATION_CONFIRMATION_REQUIRED','請先明確確認這次 AI 試穿。')
    fingerprint = hashlib.sha256(json.dumps({'session':str(session_id),**({'channel':source} if source=='MCP' else {}),**body.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
    # Serialize member quota checks and retries across tabs and API processes.
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(member,)).fetchone()
    session = owned_session(session_id,member,connection,True)
    if (session['plan_id'],session['kimono_id'])!=(body.plan_id,body.kimono_id):
        fail(409,'OUTFIT_CHANGED','搭配已變更，請重新載入並確認。')
    validate_selection(body,connection)
    person = source_row(session,connection,body.photo_id,body.model_id)
    outfit = outfit_source(connection,body.kimono_id,body.belt_id)
    cache_key = reuse_key(body.kimono_id,body.belt_id,body.photo_id,body.model_id,person['source_key'],outfit['sha256'])
    old = connection.execute('SELECT * FROM generation_jobs WHERE user_id=%s AND idempotency_key=%s',(member,idempotency_key)).fetchone()
    if old:
        if old['source']!=source or old['request_hash']!=fingerprint or old.get('reuse_key')!=cache_key:
            fail(409,'IDEMPOTENCY_CONFLICT','同一生成請求的內容或素材已變更，請重新確認。')
        response.status_code=200
        return job_data(old,reused=old['status']=='SUCCEEDED' and bool(old['expires_at']) and old['expires_at']>datetime.now(timezone.utc))
    previous = connection.execute("""SELECT * FROM generation_jobs WHERE user_id=%s AND reuse_key=%s
        AND source=%s AND kind='TRY_ON' AND deleted_at IS NULL AND NOT cleanup_pending
        AND ((status='SUCCEEDED' AND expires_at>now()) OR status IN ('QUEUED','VALIDATING','GENERATING'))
        ORDER BY completed_at DESC NULLS LAST,created_at DESC,id DESC LIMIT 1""", (member,cache_key,source)).fetchone()
    if previous:
        response.status_code=200
        return job_data(previous,reused=previous['status']=='SUCCEEDED')
    try: _,location,model=configuration()
    except GenerationError as error: fail(503,error.code,FAILURES[error.code])
    day=reserve_quota(connection,member,source)
    job_id=uuid4()
    row=connection.execute('''INSERT INTO generation_jobs
        (id,user_id,session_id,plan_id,kimono_id,photo_id,model_id,belt_id,outfit_key,outfit_sha256,person_source_key,reuse_key,
         status,idempotency_key,request_hash,usage_day,provider_model,provider_location,result_key,source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (job_id,member,session_id,body.plan_id,body.kimono_id,body.photo_id,body.model_id,body.belt_id,
         outfit['key'],outfit['sha256'],person['source_key'],cache_key,idempotency_key,fingerprint,day,model,location,
         f'private/try-on/generations/{member}/{job_id}/result.jpg',source)).fetchone()
    return job_data(row)


def reserve_quota(connection,member,source='WEBSITE'):
    if source not in ('WEBSITE', 'MCP'): raise ValueError('Invalid trusted generation channel')
    # Callers hold the member row lock, shared by try-on and scene requests.
    if connection.execute("SELECT 1 FROM generation_jobs WHERE user_id=%s AND status IN ('QUEUED','VALIDATING','GENERATING') LIMIT 1",(member,)).fetchone():
        fail(409,'GENERATION_IN_PROGRESS','已有生成任務處理中，請先等待結果。')
    day,_=day_bounds()
    connection.execute('INSERT INTO generation_usage(user_id,source,day) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(member,source,day))
    limit=3 if source=='MCP' else 5
    if not connection.execute('UPDATE generation_usage SET used=used+1 WHERE user_id=%s AND source=%s AND day=%s AND used<%s RETURNING used',(member,source,day,limit)).fetchone():
        fail(429,'GENERATION_QUOTA_EXCEEDED',f'今日 {source} 生成額度已用完，將於日本時間午夜重設。')
    return day


def get_job(job_id, member, connection):
    row=connection.execute('SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s',(job_id,member)).fetchone()
    if not row: fail(404,'JOB_NOT_FOUND','找不到這個試穿任務。')
    return job_data(row)


def list_jobs(member, connection, page, page_size, source):
    source = source or 'WEBSITE'
    rows=connection.execute('SELECT * FROM generation_jobs WHERE user_id=%s'+(' AND source=%s' if source else '')+' ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s',
                           (member,*([source] if source else []),page_size+1,page*page_size)).fetchall()
    return {'data':[job_data(row) for row in rows[:page_size]],'nextPage':page+1 if len(rows)>page_size else None}


def delete_generation(generation_id, member, connection):
    row=connection.execute('SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s FOR UPDATE',(generation_id,member)).fetchone()
    if not row: fail(404,'JOB_NOT_FOUND','找不到這張試穿圖。')
    if row['status'] in ACTIVE: fail(409,'GENERATION_IN_PROGRESS','任務仍在處理中，請等待完成後再刪除。')
    connection.execute("UPDATE generation_jobs SET status='DELETED',deleted_at=COALESCE(deleted_at,now()),cleanup_pending=true WHERE id=%s",(generation_id,))
    return {'ok':True,'deletionStatus':'QUEUED'}
