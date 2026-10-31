from pillow_heif import register_heif_opener
from PIL import Image, ImageOps, UnidentifiedImageError
from app.core.config import DATA_DIR, PHOTO_MAX_BYTES as MAX_BYTES
from app.core.database import connect
from app.integrations.s3 import check_upload_cors, ensure_private_storage, preview_url, private_bucket, remove_key, s3_client
from app.modules.catalog.rules import validate_selection
from app.modules.try_on.queries import owned_session
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.responses import FileResponse
from io import BytesIO
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from uuid import uuid4
from app.modules.try_on.pose_check import POSE_MESSAGES, pose_issue
import os
import psycopg
import warnings


CONSENT_VERSION = 'photo-consent-2026-10-24-pose'
VALID_CONSENT_VERSIONS = ['photo-consent-2026-10-17', 'photo-consent-2026-10-23', 'photo-consent-2026-10-23-scenes', CONSENT_VERSION]
MAX_MEMBER_PHOTOS = 3


CONSENT_TEXT = ('我確認已取得照片當事人同意，有權上傳此人物照片，並同意本站以 AWS 私有儲存與圖片檔案檢查處理照片。'
    '新增或替換照片時，本站會在後端以 MediaPipe 檢查單人人物及肩膀至腳踝的身體範圍，不會為此將照片傳至 Google 雲端辨識 API。'
    '只有在我另行確認生成時，才將照片送至 Google Cloud Vertex AI 進行試穿或背景場景變換；兩種生成均會另外確認。'
    '每個會員最多保存三張人物照片，照片保留至我指定刪除、替換或刪除帳號；撤回同意會停止使用並刪除對應照片。'
    '原圖、生成圖與收藏分開管理，刪除原圖不會連動刪除已保存的生成圖或收藏。')


def require_consent(row):
    if row['source'] != 'SELF' or row['consent_version'] not in VALID_CONSENT_VERSIONS or row['consent_revoked_at']:
        raise HTTPException(403, {'code': 'PHOTO_CONSENT_REQUIRED', 'message': '請先重新確認本人照片處理同意。'})


def lock_photo_library(connection, member):
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (member,)).fetchone()


def owned_photo(photo_id, member, connection):
    photo = connection.execute('''SELECT p.*,s.consent_version AS photo_consent_version,s.consented_at AS photo_consented_at
        FROM person_photos p JOIN try_on_sessions s ON s.id=p.session_id
        WHERE p.id=%s AND p.user_id=%s AND s.user_id=p.user_id AND s.source='SELF'
          AND p.status IN ('FILE_READY','READY') AND s.current_photo_id=p.id
          AND s.consent_version=ANY(%s) AND s.consent_revoked_at IS NULL''', (photo_id,member,VALID_CONSENT_VERSIONS)).fetchone()
    if not photo:
        raise HTTPException(404, {'code':'PHOTO_NOT_FOUND','message':'找不到可使用的人物照片，請重新選擇。'})
    return photo


def library_count(connection, member, exclude=None):
    return connection.execute('''SELECT count(*) AS count FROM person_photos p
        WHERE p.user_id=%s AND (%s::uuid IS NULL OR p.id<>%s) AND (
            p.status IN ('FILE_READY','READY') OR
            (p.status='PENDING' AND p.upload_expires_at>now() AND p.replaces_photo_id IS NULL))''',
        (member,exclude,exclude)).fetchone()['count']


def require_photo_capacity(connection, member, exclude=None):
    if library_count(connection, member, exclude) < MAX_MEMBER_PHOTOS:
        return
    counts = connection.execute('''SELECT
        count(*) FILTER (WHERE status IN ('FILE_READY','READY')) AS saved,
        count(*) FILTER (WHERE status='PENDING' AND upload_expires_at>now()
            AND replaces_photo_id IS NULL) AS pending,
        ceil(extract(epoch FROM min(upload_expires_at) FILTER (WHERE status='PENDING'
            AND upload_expires_at>now() AND replaces_photo_id IS NULL)-now())) AS retry_seconds
        FROM person_photos WHERE user_id=%s AND (%s::uuid IS NULL OR id<>%s)''',
        (member, exclude, exclude)).fetchone()
    if counts['saved'] >= MAX_MEMBER_PHOTOS:
        raise HTTPException(409, {'code':'PHOTO_LIMIT_REACHED',
            'message':'照片庫已有三張人物照片，請先到官網管理照片庫。'})
    seconds = max(1, int(counts['retry_seconds'] or 1))
    raise HTTPException(409, {'code':'PHOTO_UPLOAD_PENDING',
        'message':f"照片庫目前有 {counts['saved']} 張照片，另有 {counts['pending']} 筆未完成上傳暫占名額（失敗上傳也可能占用）。請回原介面重試本次上傳，或約 {seconds} 秒後再按上傳；不需要刪除已有照片。"})


def list_photos(member, connection):
    rows = connection.execute('''SELECT p.* FROM person_photos p JOIN try_on_sessions s ON s.id=p.session_id
        WHERE p.user_id=%s AND p.status IN ('FILE_READY','READY') AND s.user_id=p.user_id
          AND s.current_photo_id=p.id AND s.source='SELF' AND s.consent_version=ANY(%s) AND s.consent_revoked_at IS NULL
        ORDER BY p.created_at DESC,p.id DESC LIMIT 3''', (member,VALID_CONSENT_VERSIONS)).fetchall()
    return {'data':[photo_data(p) for p in rows],'maxPhotos':MAX_MEMBER_PHOTOS}


def delete_library_photo(photo_id, member, connection, tasks):
    lock_photo_library(connection, member)
    photo = owned_photo(photo_id, member, connection)
    session = owned_session(photo['session_id'], member, connection, True)
    connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=now(),cleanup_pending=true WHERE id=%s", (photo_id,))
    connection.execute('UPDATE try_on_sessions SET current_photo_id=NULL WHERE user_id=%s AND current_photo_id=%s', (member,photo_id))
    audit(connection,session,'DELETED',photo_id)
    tasks.add_task(cleanup_photos,[photo_id])
    return {'ok':True,'deletionStatus':'QUEUED'}


def audit(connection, session, action, photo_id=None):
    connection.execute('''INSERT INTO photo_audit_events (id,user_id,session_id,photo_id,action,consent_version)
        VALUES (%s,%s,%s,%s,%s,%s)''', (uuid4(), session['user_id'], session['id'], photo_id, action, session['consent_version']))


def photo_data(photo):
    return {'photoId': photo['id'], 'status': photo['status'], 'issues': photo['issues'],
            'width': photo['width'], 'height': photo['height'], 'qualityStatus': 'PASSED' if photo['status'] == 'READY' else 'PENDING',
            'previewUrl': preview_url(photo['preview_key']) if photo['status'] in ('FILE_READY', 'READY') else None,
            'previewExpiresIn': 120 if photo['status'] in ('FILE_READY', 'READY') else None}


def session_data(row, connection):
    if 'photo' in row:
        photo, model, pending = row['photo'], row['model'], row['pending']
    else:
        photo = connection.execute('SELECT * FROM person_photos WHERE id=%s AND user_id=%s',
                                   (row['current_photo_id'], row['user_id'])).fetchone() if row['current_photo_id'] else None
        model = connection.execute('SELECT id,name,warning,active FROM store_models WHERE id=%s', (row['model_id'],)).fetchone() if row['model_id'] else None
        pending = connection.execute('''SELECT EXISTS (SELECT 1 FROM person_photos
            WHERE session_id=%s AND status='DELETED' AND cleanup_pending) AS pending''', (row['id'],)).fetchone()['pending']
    return {'sessionId': row['id'], 'source': row['source'], 'planId': row['plan_id'], 'kimonoId': row['kimono_id'],
        'modelId': row['model_id'], 'modelName': model['name'] if model else None,
        'consentStatus': 'NOT_REQUIRED' if row['source'] == 'MODEL' else ('GRANTED' if row['consent_version'] in VALID_CONSENT_VERSIONS and not row['consent_revoked_at'] else 'REVOKED'),
        'status': ('MODEL_SELECTED' if model and model['active'] else 'SOURCE_UNAVAILABLE') if row['source'] == 'MODEL' else ('PHOTO_READY' if photo and photo['status'] == 'READY' else 'PHOTO_PENDING_QUALITY' if photo and photo['status'] == 'FILE_READY' else 'NEEDS_PHOTO'),
        'photo': photo_data(photo) if photo else None, 'deletionPending': pending, 'createdAt': row['created_at']}


def consent():
    return {'version': CONSENT_VERSION, 'text': CONSENT_TEXT, 'maxBytes': MAX_BYTES,
            'minLongEdge': 1200, 'maxLongEdge': 6000, 'formats': ['JPEG', 'PNG', 'HEIC']}


def models(connection):
    rows = connection.execute("SELECT id,name,role,warning FROM store_models WHERE active ORDER BY role,name->>'zh-Hant',id").fetchall()
    return {'data': [{'id': row['id'], 'name': row['name'], 'role':row['role'], 'warning': row['warning'],
                      'previewUrl': '/api/models/' + str(row['id']) + '/preview'} for row in rows]}


def model_preview(model_id, connection):
    row = connection.execute('SELECT preview_path FROM store_models WHERE id=%s AND active', (model_id,)).fetchone()
    if row:
        directory = (DATA_DIR / 'model-previews').resolve()
        path = (directory / row['preview_path']).resolve()
        if path.is_relative_to(directory) and path.suffix == '.webp' and path.is_file():
            return FileResponse(path, media_type='image/webp', headers={'Cache-Control': 'public, max-age=300'})
    raise HTTPException(404, {'code': 'MODEL_NOT_FOUND', 'message': '找不到模特兒預覽。'})


def create_session(body, member, connection):
    validate_selection(body, connection)
    selected_photo = None
    if body.source == 'MODEL':
        model = connection.execute('SELECT id,role FROM store_models WHERE id=%s AND active', (body.model_id,)).fetchone() if body.model_id else None
        if body.photo_id or not model:
            raise HTTPException(422, {'code': 'MODEL_NOT_FOUND', 'message': '請選擇可用的預設模特兒。'})
        garment = connection.execute('SELECT gender FROM kimonos WHERE id=%s', (body.kimono_id,)).fetchone()
        if model['role']!=garment['gender']:
            raise HTTPException(422, {'code':'MODEL_ROLE_MISMATCH','message':'請選擇適用此和服角色的商店模特兒。'})
    else:
        if body.model_id:
            raise HTTPException(422, {'code':'INVALID_SOURCE','message':'人物照片與商店模特兒只能選擇一種來源。'})
        if body.photo_id:
            selected_photo = owned_photo(body.photo_id,member,connection)
        elif not body.consent_accepted or body.consent_version != CONSENT_VERSION:
            raise HTTPException(403, {'code': 'PHOTO_CONSENT_REQUIRED', 'message': '請先明確同意目前的人物照片處理說明。'})
    row = connection.execute('''INSERT INTO try_on_sessions
        (id,user_id,plan_id,kimono_id,source,model_id,consent_version,consented_at,current_photo_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (uuid4(), member, body.plan_id, body.kimono_id, body.source, body.model_id,
         selected_photo['photo_consent_version'] if selected_photo else CONSENT_VERSION if body.source == 'SELF' else None,
         selected_photo['photo_consented_at'] if selected_photo else datetime.now(timezone.utc) if body.source == 'SELF' else None,
         selected_photo['id'] if selected_photo else None)).fetchone()
    if body.source == 'SELF' and not selected_photo:
        audit(connection, row, 'CONSENT')
    return session_data(row, connection)


def list_sessions(member, connection, page, page_size):
    rows = connection.execute('''SELECT s.*,
        CASE WHEN p.id IS NOT NULL THEN jsonb_build_object('id',p.id,'status',p.status,
            'issues',p.issues,'width',p.width,'height',p.height,'preview_key',p.preview_key) END AS photo,
        CASE WHEN m.id IS NOT NULL THEN jsonb_build_object('name',m.name,'active',m.active) END AS model,
        EXISTS (SELECT 1 FROM person_photos deleted WHERE deleted.session_id=s.id
            AND deleted.status='DELETED' AND deleted.cleanup_pending) AS pending
        FROM try_on_sessions s
        LEFT JOIN person_photos p ON p.id=s.current_photo_id AND p.user_id=s.user_id
        LEFT JOIN store_models m ON m.id=s.model_id
        WHERE s.user_id=%s ORDER BY s.created_at DESC,s.id DESC LIMIT %s OFFSET %s''',
                              (member, page_size + 1, page * page_size)).fetchall()
    return {'data': [session_data(row, connection) for row in rows[:page_size]], 'nextPage': page + 1 if len(rows) > page_size else None}


def get_session(session_id, member, connection):
    return session_data(owned_session(session_id, member, connection), connection)


def update_session(session_id, body, member, connection):
    owned_session(session_id, member, connection, True)
    validate_selection(body, connection)
    row = connection.execute('UPDATE try_on_sessions SET plan_id=%s,kimono_id=%s WHERE id=%s RETURNING *',
                             (body.plan_id, body.kimono_id, session_id)).fetchone()
    return session_data(row, connection)


def upload_url(session_id, body, request, member, connection, tasks, direct_post=False):
    lock_photo_library(connection,member)
    session = owned_session(session_id, member, connection, True)
    require_consent(session)
    if session['consent_version']!=CONSENT_VERSION:
        raise HTTPException(403, {'code':'PHOTO_CONSENT_REQUIRED','message':'新增或替換照片前，請先確認目前的人物照片處理說明。'})
    replacement = body.replace_photo_id or session['current_photo_id']
    if replacement:
        owned_photo(replacement,member,connection)
    ensure_private_storage()
    # Preserve direct S3 uploads where CORS is configured. Local Vite can use
    # an authenticated API transfer when bucket CORS cannot be administered.
    api_transfer = False
    if not direct_post:
        try:
            check_upload_cors(request.headers.get('origin') or os.getenv('PUBLIC_ORIGIN'))
        except HTTPException as error:
            if not isinstance(error.detail, dict) or error.detail.get('code') != 'PHOTO_CORS_UNAVAILABLE':
                raise
            api_transfer = True
    # MCP uses a signed simple POST with an opaque response. Completion must be
    # verified through validate_photo; no bucket CORS or public access is changed.
    old = connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=now(),cleanup_pending=true WHERE session_id=%s AND status='PENDING' RETURNING id", (session_id,)).fetchall()
    if old:
        tasks.add_task(cleanup_photos, [row['id'] for row in old])
    if not replacement:
        require_photo_capacity(connection, member)
    photo_id = uuid4()
    base = 'private/try-on/photos/' + str(member) + '/' + str(photo_id)
    raw_key = 'private/try-on/uploads/' + str(member) + '/' + str(photo_id) + '/' + uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(seconds=300)
    connection.execute('''INSERT INTO person_photos (id,session_id,user_id,raw_key,source_key,preview_key,content_type,expected_size,status,upload_expires_at,replaces_photo_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,%s)''',
        (photo_id, session_id, member, raw_key, base + '/source.jpg', base + '/preview.webp', body.content_type, body.size, expires,replacement))
    if api_transfer:
        return {'photoId':photo_id,'uploadUrl':f'/api/try-on/sessions/{session_id}/uploads/{photo_id}',
                'method':'PUT','transport':'API','expiresAt':expires}
    upload = s3_client().generate_presigned_post(Bucket=private_bucket(), Key=raw_key,
        Fields={'Content-Type': body.content_type, 'Cache-Control': 'no-store'},
        Conditions=[{'Content-Type': body.content_type}, {'Cache-Control': 'no-store'}, ['content-length-range', 1, MAX_BYTES]], ExpiresIn=300)
    return {'photoId': photo_id, 'uploadUrl': upload['url'], 'method': 'POST', 'fields': upload['fields'], 'expiresAt': expires}


async def transfer_photo(session_id, photo_id, request, member, connection):
    session=owned_session(session_id,member,connection,True)
    require_consent(session)
    photo=connection.execute('SELECT * FROM person_photos WHERE id=%s AND session_id=%s AND user_id=%s FOR UPDATE',
        (photo_id,session_id,member)).fetchone()
    if not photo or photo['status']!='PENDING' or photo['upload_expires_at']<=datetime.now(timezone.utc):
        raise HTTPException(409,{'code':'UPLOAD_EXPIRED','message':'這次上傳已到期或已完成，請重新上傳。'})
    if request.headers.get('content-type','').split(';')[0]!=photo['content_type']:
        raise HTTPException(422,{'code':'PHOTO_TYPE_MISMATCH','message':'照片類型與原上傳請求不符。'})
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>min(MAX_BYTES,photo['expected_size']):
            raise HTTPException(413,{'code':'FILE_TOO_LARGE','message':'照片超過這次上傳允許的大小。'})
        content.extend(chunk)
    if len(content)!=photo['expected_size']:
        raise HTTPException(422,{'code':'FILE_SIZE_MISMATCH','message':'照片長度不符，請重新上傳。'})
    ensure_private_storage()
    await run_in_threadpool(s3_client().put_object,Bucket=private_bucket(),Key=photo['raw_key'],Body=bytes(content),
        ContentType=photo['content_type'],CacheControl='no-store')
    return {'photoId':photo_id,'uploaded':True}


def validate_photo(session_id, body, member, connection, tasks):
    lock_photo_library(connection,member)
    session = owned_session(session_id, member, connection, True)
    require_consent(session)
    photo = connection.execute('SELECT * FROM person_photos WHERE id=%s AND session_id=%s AND user_id=%s FOR UPDATE',
                               (body.photo_id, session_id, member)).fetchone()
    if not photo:
        raise HTTPException(404, {'code': 'PHOTO_NOT_FOUND', 'message': '找不到這次上傳的照片。'})
    if photo['status'] != 'PENDING':
        return photo_data(photo)
    if photo['replaces_photo_id']:
        owned_photo(photo['replaces_photo_id'],member,connection)
    else:
        require_photo_capacity(connection, member, exclude=photo['id'])
    ensure_private_storage()
    client, bucket = s3_client(), private_bucket()
    try:
        if datetime.now(timezone.utc) >= photo['upload_expires_at']:
            raise InvalidPhoto('UPLOAD_EXPIRED')
        try:
            metadata = client.head_object(Bucket=bucket, Key=photo['raw_key'])
        except ClientError as error:
            if error.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound'):
                raise HTTPException(409, {'code': 'PHOTO_UPLOAD_MISSING', 'message': '尚未收到這次上傳的照片，請先完成上傳。'}) from None
            raise
        if metadata['ContentLength'] > MAX_BYTES:
            raise InvalidPhoto('FILE_TOO_LARGE')
        if metadata['ContentLength'] != photo['expected_size']:
            raise InvalidPhoto('FILE_SIZE_MISMATCH')
        args = {'Bucket': bucket, 'Key': photo['raw_key']}
        if metadata.get('VersionId'):
            args['VersionId'] = metadata['VersionId']
        stream = client.get_object(**args)['Body']
        try:
            content = stream.read(MAX_BYTES + 1)
        finally:
            stream.close()
        image, normalized = normalize_photo(content, photo['content_type'])
        try:
            pose_code = pose_issue(image)
        except Exception:
            # A model/dependency/inference failure is not a rejection of the user's photo.
            raise HTTPException(503, {'code': 'PHOTO_VALIDATION_UNAVAILABLE',
                'message': '人物與姿勢驗證服務暫時無法使用，請稍後重試；原照片仍保留。'}) from None
        if pose_code:
            raise InvalidPhoto(pose_code)
    except InvalidPhoto as error:
        issues = issue_list(error.codes)
        photo = connection.execute("UPDATE person_photos SET status='REJECTED',issues=%s,cleanup_pending=true WHERE id=%s RETURNING *", (Jsonb(issues), photo['id'])).fetchone()
        audit(connection, session, 'REJECTED', photo['id'])
        tasks.add_task(cleanup_photos, [photo['id']])
        return photo_data(photo)
    client.put_object(Bucket=bucket, Key=photo['source_key'], Body=normalized, ContentType='image/jpeg', CacheControl='no-store')
    client.put_object(Bucket=bucket, Key=photo['preview_key'], Body=preview_bytes(image), ContentType='image/webp', CacheControl='no-store')
    clean_ids = [photo['id']]
    if photo['replaces_photo_id']:
        old = photo['replaces_photo_id']
        connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=now(),cleanup_pending=true WHERE id=%s AND user_id=%s", (old, member))
        audit(connection, session, 'REPLACED', old)
        clean_ids.append(old)
        connection.execute('UPDATE try_on_sessions SET current_photo_id=NULL WHERE user_id=%s AND current_photo_id=%s', (member,old))
    photo = connection.execute("UPDATE person_photos SET status='READY',width=%s,height=%s,cleanup_pending=true WHERE id=%s RETURNING *", (image.width, image.height, photo['id'])).fetchone()
    connection.execute('UPDATE try_on_sessions SET current_photo_id=%s WHERE id=%s', (photo['id'], session_id))
    tasks.add_task(cleanup_photos, clean_ids)
    return photo_data(photo)


def delete_photo(session_id, member, connection, tasks, withdraw_consent):
    lock_photo_library(connection,member)
    session = owned_session(session_id, member, connection, True)
    if session['source'] != 'SELF':
        raise HTTPException(409, {'code': 'NOT_MEMBER_PHOTO', 'message': '預設模特兒不是會員原圖，無法在此刪除。'})
    current = session['current_photo_id']
    rows = connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=COALESCE(deleted_at,now()),cleanup_pending=true WHERE (id=%s OR (session_id=%s AND status='PENDING')) AND user_id=%s RETURNING id", (current,session_id, member)).fetchall()
    if current:
        connection.execute('UPDATE try_on_sessions SET current_photo_id=NULL WHERE user_id=%s AND current_photo_id=%s', (member,current))
    connection.execute('UPDATE try_on_sessions SET current_photo_id=NULL,consent_revoked_at=CASE WHEN %s THEN now() ELSE consent_revoked_at END WHERE id=%s', (withdraw_consent, session_id))
    audit(connection, session, 'WITHDRAWN' if withdraw_consent else 'DELETED', session['current_photo_id'])
    tasks.add_task(cleanup_photos, [row['id'] for row in rows])
    return {'ok': True, 'deletionStatus': 'QUEUED'}


def cleanup_photos(photo_ids=None):
    """Persisted flags survive process restarts. CLI retries failures and late POST replays."""
    try:
        versioned = ensure_private_storage()
        client = s3_client()
        with connect() as connection:
            rows = connection.execute('''SELECT * FROM person_photos WHERE
                (cleanup_pending OR (NOT raw_finalized AND upload_expires_at < now()))
                AND (status <> 'PENDING' OR upload_expires_at < now())
                AND (%s::uuid[] IS NULL OR id=ANY(%s)) ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED''',
                (photo_ids, photo_ids)).fetchall()
            for row in rows:
                keys = [row['raw_key']] if row['status'] in ('FILE_READY', 'READY') else [row['raw_key'], row['source_key'], row['preview_key']]
                for key in keys:
                    if key:
                        remove_key(client, key, versioned)
                connection.execute("""UPDATE person_photos SET cleanup_pending=false,
                    raw_finalized=(upload_expires_at < now()),status=CASE WHEN status='PENDING' THEN 'EXPIRED' ELSE status END WHERE id=%s""", (row['id'],))
    except (psycopg.Error, BotoCoreError, ClientError, HTTPException):
        # Keep cleanup flags for explicit retry; never log private keys or signed URLs.
        return False
    return True


ISSUES = {
    'UNSUPPORTED_FILE': '請使用可正常開啟的單張 JPEG、PNG 或 HEIC 照片。',
    'FILE_TOO_LARGE': '單張照片不可超過 10 MB。',
    'LOW_RESOLUTION': '照片長邊至少需要 1200 像素，請使用較清晰的原始照片。',
    'HIGH_RESOLUTION': '照片長邊不可超過 6000 像素，請先縮小圖片。',
    **POSE_MESSAGES,
    'NOT_FRONTAL': '請面向鏡頭站立，避免側身或背對鏡頭。',
    'LOW_LIGHT': '照片中的人物過暗，請在光線充足處重新拍攝。',
    'UPLOAD_EXPIRED': '這次上傳已逾時，請重新選擇照片。',
    'FILE_SIZE_MISMATCH': '實際上傳大小與這次申請不一致，請重新選擇照片。',
}


class InvalidPhoto(Exception):
    def __init__(self, *codes):
        self.codes = list(codes)


def issue_list(codes):
    return [{'code': code, 'message': ISSUES[code]} for code in codes]


def normalize_photo(content, content_type=None):
    if len(content) > MAX_BYTES:
        raise InvalidPhoto('FILE_TOO_LARGE')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                allowed = {'JPEG': ['image/jpeg'], 'PNG': ['image/png'], 'HEIF': ['image/heic', 'image/heif']}
                if image.format not in allowed or (content_type and content_type not in allowed[image.format]):
                    raise InvalidPhoto('UNSUPPORTED_FILE')
                if getattr(image, 'n_frames', 1) != 1:
                    raise InvalidPhoto('UNSUPPORTED_FILE')
                if max(image.size) > 6000:
                    raise InvalidPhoto('HIGH_RESOLUTION')
                if max(image.size) < 1200:
                    raise InvalidPhoto('LOW_RESOLUTION')
                upright = ImageOps.exif_transpose(image).convert('RGBA')
                clean = Image.new('RGB', upright.size, 'white')
                clean.paste(upright, mask=upright.getchannel('A'))
                clean.thumbnail((2400, 2400))
                # New pixel canvas intentionally carries no EXIF, XMP or source filename.
                result = BytesIO()
                clean.save(result, 'JPEG', quality=92, optimize=True)
                return clean, result.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InvalidPhoto('UNSUPPORTED_FILE') from None


def preview_bytes(image, format='WEBP'):
    small = image.copy()
    small.thumbnail((480, 720))
    output = BytesIO()
    small.save(output, format, quality=82)
    return output.getvalue()

register_heif_opener(thumbnails=False, aux_images=False)
