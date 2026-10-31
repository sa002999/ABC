"""MCP-only routes derive the member and quota channel from trusted dependencies."""
import os
import hashlib
import logging
from urllib.parse import urlsplit
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import ConfigDict, Field, StrictBool
from psycopg.types.json import Jsonb
from app.core.database import get_connection
from app.core.schemas import CamelModel
from app.modules.accounts.mcp import mcp_member
from app.modules.catalog.queries import plan_detail, kimono_detail
from app.modules.try_on import photos, service
from app.modules.try_on.schemas import SessionInput, GenerationInput, UploadInput, ValidateInput
from app.integrations.s3 import private_bucket, s3_client

router = APIRouter(prefix='/api/mcp/try-on', tags=['MCP AI 試穿'])
logger = logging.getLogger('uvicorn.error')
Member = Annotated[UUID, Depends(mcp_member)]
Connection = Annotated[object, Depends(get_connection, scope='function')]


class Outfit(CamelModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: UUID
    kimono_id: UUID
    conversation_id: UUID = Field(default_factory=uuid4)


class Prepare(Outfit):
    source: Literal['MODEL', 'SELF']
    model_id: UUID | None = None
    photo_id: UUID | None = None


class Confirm(CamelModel):
    model_config = ConfigDict(extra='forbid')
    review_id: UUID
    confirmed: StrictBool


class PhotoUpload(Outfit):
    consent_accepted: StrictBool
    consent_version: str = Field(min_length=1, max_length=100)
    content_type: Literal['image/jpeg', 'image/png', 'image/heic', 'image/heif']
    size: int = Field(strict=True, gt=0, le=photos.MAX_BYTES)


class CompletePhoto(CamelModel):
    model_config = ConfigDict(extra='forbid')
    session_id: UUID
    photo_id: UUID


def selection(body, connection):
    plan = plan_detail(body.plan_id, connection)
    kimono = kimono_detail(body.kimono_id, connection)
    if not connection.execute('SELECT 1 FROM plan_kimonos WHERE plan_id=%s AND kimono_id=%s', (body.plan_id, body.kimono_id)).fetchone():
        service.fail(422, 'INVALID_OUTFIT', '所選和服不適用此方案。')
    return plan, kimono


def jobs(member, connection, conversation_id=None):
    rows = connection.execute('''SELECT j.*,k.name AS kimono_name FROM generation_jobs j JOIN kimonos k ON k.id=j.kimono_id WHERE j.user_id=%s AND j.source='MCP'
        AND j.deleted_at IS NULL AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM mcp_try_on_reviews r
        WHERE r.user_id=j.user_id AND r.job_id=j.id AND r.conversation_id=%s))
        ORDER BY j.created_at DESC,j.id DESC LIMIT 12''', (member, conversation_id, conversation_id)).fetchall()
    return [job_data(row) for row in rows]


def job_data(row):
    return {**service.job_data(row), 'kimonoName': row.get('kimono_name')}


def material_version(person, outfit):
    return hashlib.sha256((person['source_key'] + ':' + outfit['sha256']).encode()).hexdigest()


@router.get('/media-config')
def media_config():
    bucket = private_bucket()
    region = os.getenv('AWS_REGION', 'ap-northeast-1')
    return {'imageOrigins': [f'https://{bucket}.s3.{region}.amazonaws.com', f'https://{bucket}.s3.amazonaws.com']}


@router.get('/photo-consent')
def photo_consent(member: Member):
    return {'view': 'photoConsent', **photos.consent(), 'maxPhotos': photos.MAX_MEMBER_PHOTOS}


@router.post('/photo-uploads', status_code=201)
def create_photo_upload(body: PhotoUpload, request: Request, member: Member, connection: Connection, tasks: BackgroundTasks):
    if not body.consent_accepted or body.consent_version != photos.CONSENT_VERSION:
        service.fail(403, 'PHOTO_CONSENT_REQUIRED', '請先閱讀並勾選目前的本人照片處理同意。')
    photos.lock_photo_library(connection, member)
    photos.require_photo_capacity(connection, member)
    session = photos.create_session(SessionInput(plan_id=body.plan_id, kimono_id=body.kimono_id,
        source='SELF', consent_accepted=True, consent_version=body.consent_version), member, connection)
    upload = photos.upload_url(session['sessionId'], UploadInput(content_type=body.content_type,
        size=body.size, file_name='photo'), request, member, connection, tasks, direct_post=True)
    logger.info('MCP photo upload prepared photoId=%s host=%s expiresAt=%s',
                upload['photoId'], urlsplit(upload['uploadUrl']).hostname, upload['expiresAt'])
    return {'view': 'photoUpload', 'sessionId': session['sessionId'], 'photoId': upload['photoId'],
            'expiresAt': upload['expiresAt'], 'upload': upload}


@router.post('/photo-uploads/complete')
def complete_photo_upload(body: CompletePhoto, member: Member, connection: Connection, tasks: BackgroundTasks):
    logger.info('MCP photo upload completion requested photoId=%s', body.photo_id)
    photo = photos.validate_photo(body.session_id, ValidateInput(photo_id=body.photo_id), member, connection, tasks)
    return {'view': 'photoUploaded', 'photo': photo}


@router.post('/sources')
def sources(body: Outfit, member: Member, connection: Connection):
    plan, kimono = selection(body, connection)
    models = [m for m in photos.models(connection)['data'] if m['role'] == kimono['gender']]
    # Use short-lived HTTPS images in external host iframes, avoiding browser access to the local API.
    for model in models:
        person = connection.execute('SELECT source_key FROM store_models WHERE id=%s AND active', (model['id'],)).fetchone()
        model['previewUrl'] = s3_client().generate_presigned_url('get_object', Params={
            'Bucket': private_bucket(), 'Key': person['source_key'], 'ResponseCacheControl': 'no-store'}, ExpiresIn=120)
    active = connection.execute("SELECT j.*,k.name AS kimono_name FROM generation_jobs j JOIN kimonos k ON k.id=j.kimono_id WHERE j.user_id=%s AND j.source='MCP' AND j.status IN ('QUEUED','VALIDATING','GENERATING') ORDER BY j.created_at DESC LIMIT 1", (member,)).fetchone()
    return {'view': 'tryOnSources', 'conversationId': body.conversation_id,
            'planId': body.plan_id, 'planName': plan['name'], 'kimonoId': body.kimono_id, 'kimonoName': kimono['name'],
            'isDemo': plan['is_demo'] or kimono['is_demo'], 'models': models, 'photos': photos.list_photos(member, connection)['data'],
            'usage': service.usage(member, connection), 'jobs': jobs(member, connection, body.conversation_id),
            'activeJob': job_data(active) if active else None,
            'uploadPageUrl': os.getenv('PUBLIC_ORIGIN', 'http://127.0.0.1:8000').rstrip('/') + '/try-on?plan=' + str(body.plan_id),
            'notice': '每位旅客可選擇試穿或略過。可在介面新增本人照片並完成同意；不支援上傳時使用官網備援。生成每次另行確認；AI 圖僅為示意，不保證實際合身度。'}


@router.post('/prepare', status_code=201)
def prepare(body: Prepare, member: Member, connection: Connection):
    plan, kimono = selection(body, connection)
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (member,))
    session = photos.create_session(SessionInput(plan_id=body.plan_id, kimono_id=body.kimono_id,
        source=body.source, model_id=body.model_id, photo_id=body.photo_id), member, connection)
    if body.source == 'SELF' and not body.photo_id:
        service.fail(403, 'PHOTO_CONSENT_REQUIRED', '請先上傳照片並完成同意，再選取照片庫中的照片。')
    value = GenerationInput(plan_id=body.plan_id, kimono_id=body.kimono_id,
        model_id=body.model_id, photo_id=body.photo_id, confirmed=True)
    row = connection.execute('SELECT * FROM try_on_sessions WHERE id=%s', (session['sessionId'],)).fetchone()
    person = service.source_row(row, connection, body.photo_id, body.model_id)
    outfit = service.outfit_source(connection, body.kimono_id)
    review = connection.execute('''INSERT INTO mcp_try_on_reviews(id,user_id,conversation_id,session_id,selection,usage_day,material_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id,expires_at''',
        (uuid4(), member, body.conversation_id, row['id'], Jsonb(value.model_dump(mode='json', by_alias=True)), service.day_bounds()[0], material_version(person, outfit))).fetchone()
    return {'view': 'tryOnReview', 'reviewId': review['id'], 'conversationId': body.conversation_id,
            'reviewExpiresAt': review['expires_at'], 'planId': body.plan_id, 'planName': plan['name'],
            'kimonoId': body.kimono_id, 'kimonoName': kimono['name'], 'source': body.source,
            'photoId': body.photo_id, 'modelId': body.model_id, 'modelName': person.get('name'),
            'usage': service.usage(member, connection), 'isDemo': plan['is_demo'] or kimono['is_demo'],
            'notice': '尚未生成或扣額度。確認後最多使用 1 次 MCP 額度；相同有效結果會重用且不重扣。圖片於完成當日日本午夜到期，不加入網站生成圖收藏。跨午夜完成的任務以完成當日計算圖片到期，額度仍計入送出當日。失敗不自動重送；重試須重新確認並使用額度。'}


@router.post('/confirm', status_code=202)
def confirm(body: Confirm, member: Member, connection: Connection, response: Response):
    if not body.confirmed:
        service.fail(403, 'GENERATION_CONFIRMATION_REQUIRED', '請明確確認這一次生成。')
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (member,))
    review = connection.execute('SELECT * FROM mcp_try_on_reviews WHERE id=%s AND user_id=%s FOR UPDATE', (body.review_id, member)).fetchone()
    if not review:
        service.fail(404, 'REVIEW_NOT_FOUND', '找不到本人的生成確認內容。')
    if review['job_id']:
        response.status_code = 200
        return {**job(review['job_id'], member, connection), 'usage': service.usage(member, connection)}
    if review['expires_at'] <= datetime.now(timezone.utc) or review['usage_day'] != service.day_bounds()[0]:
        service.fail(409, 'REVIEW_EXPIRED', '確認內容已到期或已跨日本午夜，請重新查看來源、款式與額度。')
    value = GenerationInput.model_validate(review['selection'])
    selection(value, connection)
    session = service.owned_session(review['session_id'], member, connection)
    person = service.source_row(session, connection, value.photo_id, value.model_id)
    if material_version(person, service.outfit_source(connection, value.kimono_id)) != review['material_version']:
        service.fail(409, 'SOURCE_CHANGED', '人物或服裝素材已變更，請重新查看並確認生成。')
    result = service.create_job(review['session_id'], value, member,
                                connection, response, review['id'], source='MCP')
    connection.execute('UPDATE mcp_try_on_reviews SET job_id=%s WHERE id=%s', (result['jobId'], review['id']))
    return {**job(result['jobId'], member, connection), 'conversationId': review['conversation_id'], 'usage': service.usage(member, connection)}


@router.get('/jobs')
def history(member: Member, connection: Connection, conversation_id: UUID | None = None):
    return {'view': 'tryOnJobs', 'jobs': jobs(member, connection, conversation_id),
            'notice': '僅查本人 MCP 任務；失效圖片不再提供網址。每個有效圖片網址最多 120 秒，可重新查詢更新。'}


@router.get('/jobs/{job_id}')
def job(job_id: UUID, member: Member, connection: Connection):
    row = connection.execute("SELECT j.*,k.name AS kimono_name FROM generation_jobs j JOIN kimonos k ON k.id=j.kimono_id WHERE j.id=%s AND j.user_id=%s AND j.source='MCP'", (job_id, member)).fetchone()
    if not row:
        service.fail(404, 'JOB_NOT_FOUND', '找不到本人的 MCP 試穿任務。')
    return {'view': 'tryOnJob', **job_data(row)}
