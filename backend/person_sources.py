import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4, uuid5

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import ConfigDict, Field
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from catalog import CamelModel
from database import BACKEND_DIR, connect, get_connection
from looks import LookSelection, Member, validate_selection
from photo_checks import MAX_BYTES, InvalidPhoto, issue_list, normalize_photo, preview_bytes
from photo_storage import check_upload_cors, ensure_private_storage, preview_url, private_bucket, remove_key
from storage import s3_client

router = APIRouter(prefix='/api', tags=['人物來源與照片'])
# Commit photo state before deletion background tasks open their own connections.
Connection = Annotated[psycopg.Connection, Depends(get_connection, scope='function')]
CONSENT_VERSION = 'photo-consent-2026-10-17'
CONSENT_TEXT = ('我確認有權使用此本人照片，同意本站以 AWS 私有儲存與圖片檔案檢查處理照片。'
    '只有在我另行確認生成時，才將照片送至 Google Cloud Vertex AI 進行試穿。'
    '照片保留至我刪除、替換或刪除帳號；撤回同意會停止使用並刪除本工作階段的照片。'
    '原圖、生成圖與收藏分開管理，刪除原圖不會連動刪除已保存的生成圖或收藏。')


class SessionInput(LookSelection):
    source: Literal['SELF', 'MODEL']
    model_id: UUID | None = None
    consent_accepted: bool = False
    consent_version: str | None = Field(None, max_length=100)


class UploadInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    content_type: Literal['image/jpeg', 'image/png', 'image/heic', 'image/heif']
    size: int = Field(gt=0, le=MAX_BYTES)
    file_name: str = Field(min_length=1, max_length=255)


class ValidateInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    photo_id: UUID


def missing_session():
    raise HTTPException(404, {'code': 'SESSION_NOT_FOUND', 'message': '找不到這個試穿工作階段。'})


def owned_session(session_id, member, connection, lock=False):
    row = connection.execute('SELECT * FROM try_on_sessions WHERE id=%s AND user_id=%s' + (' FOR UPDATE' if lock else ''),
                             (session_id, member)).fetchone()
    if not row:
        missing_session()
    return row


def require_consent(row):
    if row['source'] != 'SELF' or row['consent_version'] != CONSENT_VERSION or row['consent_revoked_at']:
        raise HTTPException(403, {'code': 'PHOTO_CONSENT_REQUIRED', 'message': '請先重新確認本人照片處理同意。'})


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
        'consentStatus': 'NOT_REQUIRED' if row['source'] == 'MODEL' else ('GRANTED' if row['consent_version'] == CONSENT_VERSION and not row['consent_revoked_at'] else 'REVOKED'),
        'status': ('MODEL_SELECTED' if model and model['active'] else 'SOURCE_UNAVAILABLE') if row['source'] == 'MODEL' else ('PHOTO_READY' if photo and photo['status'] == 'READY' else 'PHOTO_PENDING_QUALITY' if photo and photo['status'] == 'FILE_READY' else 'NEEDS_PHOTO'),
        'photo': photo_data(photo) if photo else None, 'deletionPending': pending, 'createdAt': row['created_at']}


@router.get('/try-on/consent')
def consent():
    return {'version': CONSENT_VERSION, 'text': CONSENT_TEXT, 'maxBytes': MAX_BYTES,
            'minLongEdge': 1200, 'maxLongEdge': 6000, 'formats': ['JPEG', 'PNG', 'HEIC']}


@router.get('/models')
def models(connection: Connection):
    rows = connection.execute("SELECT id,name,warning FROM store_models WHERE active ORDER BY name->>'zh-Hant',id").fetchall()
    return {'data': [{'id': row['id'], 'name': row['name'], 'warning': row['warning'],
                      'previewUrl': '/api/models/' + str(row['id']) + '/preview'} for row in rows]}


@router.get('/models/{model_id}/preview', include_in_schema=False)
def model_preview(model_id: UUID, connection: Connection):
    row = connection.execute('SELECT preview_path FROM store_models WHERE id=%s AND active', (model_id,)).fetchone()
    if row:
        directory = (BACKEND_DIR / 'model-previews').resolve()
        path = (directory / row['preview_path']).resolve()
        if path.is_relative_to(directory) and path.suffix == '.webp' and path.is_file():
            return FileResponse(path, media_type='image/webp', headers={'Cache-Control': 'public, max-age=300'})
    raise HTTPException(404, {'code': 'MODEL_NOT_FOUND', 'message': '找不到模特兒預覽。'})


@router.post('/try-on/sessions', status_code=201)
def create_session(body: SessionInput, member: Member, connection: Connection):
    validate_selection(body, connection)
    if body.source == 'MODEL':
        if not body.model_id or not connection.execute('SELECT id FROM store_models WHERE id=%s AND active', (body.model_id,)).fetchone():
            raise HTTPException(422, {'code': 'MODEL_NOT_FOUND', 'message': '請選擇可用的預設模特兒。'})
    elif body.model_id or not body.consent_accepted or body.consent_version != CONSENT_VERSION:
        raise HTTPException(403, {'code': 'PHOTO_CONSENT_REQUIRED', 'message': '請先明確同意目前的本人照片處理說明。'})
    row = connection.execute('''INSERT INTO try_on_sessions
        (id,user_id,plan_id,kimono_id,source,model_id,consent_version,consented_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (uuid4(), member, body.plan_id, body.kimono_id, body.source, body.model_id,
         CONSENT_VERSION if body.source == 'SELF' else None, datetime.now(timezone.utc) if body.source == 'SELF' else None)).fetchone()
    if body.source == 'SELF':
        audit(connection, row, 'CONSENT')
    return session_data(row, connection)


@router.get('/try-on/sessions')
def list_sessions(member: Member, connection: Connection, page: int = Query(0, ge=0), page_size: int = Query(12, alias='pageSize', ge=1, le=50)):
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


@router.get('/try-on/sessions/{session_id}')
def get_session(session_id: UUID, member: Member, connection: Connection):
    return session_data(owned_session(session_id, member, connection), connection)


@router.patch('/try-on/sessions/{session_id}')
def update_session(session_id: UUID, body: LookSelection, member: Member, connection: Connection):
    owned_session(session_id, member, connection, True)
    validate_selection(body, connection)
    row = connection.execute('UPDATE try_on_sessions SET plan_id=%s,kimono_id=%s WHERE id=%s RETURNING *',
                             (body.plan_id, body.kimono_id, session_id)).fetchone()
    return session_data(row, connection)


@router.post('/try-on/sessions/{session_id}/upload-url')
def upload_url(session_id: UUID, body: UploadInput, request: Request, member: Member, connection: Connection, tasks: BackgroundTasks):
    session = owned_session(session_id, member, connection, True)
    require_consent(session)
    ensure_private_storage()
    # Preserve direct S3 uploads where CORS is configured. Local Vite can use
    # an authenticated API transfer when bucket CORS cannot be administered.
    api_transfer = False
    try:
        check_upload_cors(request.headers.get('origin') or os.getenv('PUBLIC_ORIGIN'))
    except HTTPException as error:
        if not isinstance(error.detail, dict) or error.detail.get('code') != 'PHOTO_CORS_UNAVAILABLE':
            raise
        api_transfer = True
    old = connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=now(),cleanup_pending=true WHERE session_id=%s AND status='PENDING' RETURNING id", (session_id,)).fetchall()
    if old:
        tasks.add_task(cleanup_photos, [row['id'] for row in old])
    photo_id = uuid4()
    base = 'private/try-on/photos/' + str(member) + '/' + str(photo_id)
    raw_key = 'private/try-on/uploads/' + str(member) + '/' + str(photo_id) + '/' + uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(seconds=300)
    connection.execute('''INSERT INTO person_photos (id,session_id,user_id,raw_key,source_key,preview_key,content_type,expected_size,status,upload_expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)''',
        (photo_id, session_id, member, raw_key, base + '/source.jpg', base + '/preview.webp', body.content_type, body.size, expires))
    if api_transfer:
        return {'photoId':photo_id,'uploadUrl':f'/api/try-on/sessions/{session_id}/uploads/{photo_id}',
                'method':'PUT','transport':'API','expiresAt':expires}
    upload = s3_client().generate_presigned_post(Bucket=private_bucket(), Key=raw_key,
        Fields={'Content-Type': body.content_type, 'Cache-Control': 'no-store'},
        Conditions=[{'Content-Type': body.content_type}, {'Cache-Control': 'no-store'}, ['content-length-range', 1, MAX_BYTES]], ExpiresIn=300)
    return {'photoId': photo_id, 'uploadUrl': upload['url'], 'method': 'POST', 'fields': upload['fields'], 'expiresAt': expires}


@router.put('/try-on/sessions/{session_id}/uploads/{photo_id}')
async def transfer_photo(session_id: UUID, photo_id: UUID, request: Request, member: Member, connection: Connection):
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


@router.post('/try-on/sessions/{session_id}/validate')
def validate_photo(session_id: UUID, body: ValidateInput, member: Member, connection: Connection, tasks: BackgroundTasks):
    session = owned_session(session_id, member, connection, True)
    require_consent(session)
    photo = connection.execute('SELECT * FROM person_photos WHERE id=%s AND session_id=%s AND user_id=%s FOR UPDATE',
                               (body.photo_id, session_id, member)).fetchone()
    if not photo:
        raise HTTPException(404, {'code': 'PHOTO_NOT_FOUND', 'message': '找不到這次上傳的照片。'})
    if photo['status'] != 'PENDING':
        return photo_data(photo)
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
    except InvalidPhoto as error:
        issues = issue_list(error.codes)
        photo = connection.execute("UPDATE person_photos SET status='REJECTED',issues=%s,cleanup_pending=true WHERE id=%s RETURNING *", (Jsonb(issues), photo['id'])).fetchone()
        audit(connection, session, 'REJECTED', photo['id'])
        tasks.add_task(cleanup_photos, [photo['id']])
        return photo_data(photo)
    client.put_object(Bucket=bucket, Key=photo['source_key'], Body=normalized, ContentType='image/jpeg', CacheControl='no-store')
    client.put_object(Bucket=bucket, Key=photo['preview_key'], Body=preview_bytes(image), ContentType='image/webp', CacheControl='no-store')
    clean_ids = [photo['id']]
    if session['current_photo_id']:
        old = session['current_photo_id']
        connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=now(),cleanup_pending=true WHERE id=%s AND user_id=%s", (old, member))
        audit(connection, session, 'REPLACED', old)
        clean_ids.append(old)
    photo = connection.execute("UPDATE person_photos SET status='FILE_READY',width=%s,height=%s,cleanup_pending=true WHERE id=%s RETURNING *", (image.width, image.height, photo['id'])).fetchone()
    connection.execute('UPDATE try_on_sessions SET current_photo_id=%s WHERE id=%s', (photo['id'], session_id))
    tasks.add_task(cleanup_photos, clean_ids)
    return photo_data(photo)


@router.delete('/try-on/sessions/{session_id}/photo', status_code=202)
def delete_photo(session_id: UUID, member: Member, connection: Connection, tasks: BackgroundTasks,
                 withdraw_consent: bool = Query(False, alias='withdrawConsent')):
    session = owned_session(session_id, member, connection, True)
    if session['source'] != 'SELF':
        raise HTTPException(409, {'code': 'NOT_MEMBER_PHOTO', 'message': '預設模特兒不是會員原圖，無法在此刪除。'})
    rows = connection.execute("UPDATE person_photos SET status='DELETED',deleted_at=COALESCE(deleted_at,now()),cleanup_pending=true WHERE session_id=%s AND user_id=%s RETURNING id", (session_id, member)).fetchall()
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


def seed_models():
    ensure_private_storage()
    client, bucket = s3_client(), private_bucket()
    folder = BACKEND_DIR / 'model-previews'
    folder.mkdir(exist_ok=True)
    with connect() as connection:
        for index in (1, 2, 3):
            path = BACKEND_DIR / 'assets' / 'default models' / f'person-{index}.jpg'
            image, content = normalize_photo(path.read_bytes(), 'image/jpeg')
            model_id = uuid5(UUID('5281aa4b-3ca8-40f9-b231-3a1362f97aa2'), 'person-model:' + str(index))
            key = 'private/try-on/models/' + str(model_id) + '/' + hashlib.sha256(content).hexdigest() + '.jpg'
            client.put_object(Bucket=bucket, Key=key, Body=content, ContentType='image/jpeg', CacheControl='no-store')
            preview_path = str(model_id) + '.webp'
            (folder / preview_path).write_bytes(preview_bytes(image))
            warning = '照片中有狗，腿部局部遮擋可能影響試穿效果。' if index == 3 else None
            connection.execute('''INSERT INTO store_models (id,name,source_key,preview_path,warning)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET source_key=EXCLUDED.source_key,
                preview_path=EXCLUDED.preview_path,warning=EXCLUDED.warning,reviewed_at=now()''',
                (model_id, Jsonb({'zh-Hant': '預設模特兒 ' + str(index)}), key, preview_path, warning))
    print('3 reviewed model sources imported privately; public previews contain no EXIF.')
