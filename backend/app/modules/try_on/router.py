from app.core.database import get_connection
from app.modules.accounts.dependencies import Member
from app.modules.catalog.schemas import LookSelection
from app.modules.try_on import photos as photos, service as service
from app.modules.try_on.schemas import GenerationInput, SessionInput, UploadInput, ValidateInput, SceneInput
from app.modules.try_on.scenes import SCENES, create_scene
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from typing import Annotated, Literal
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection, scope='function')]
photos_router = APIRouter(prefix='/api', tags=['人物來源與照片'])
generations_router = APIRouter(prefix='/api', tags=['AI 試穿'])

@generations_router.get('/scenes')
def scenes():
    return {'data':[{'id':key,'name':value[0]} for key,value in SCENES.items()]}

@generations_router.post('/try-on/jobs/{job_id}/scene-generations',status_code=202)
def scene_generation(job_id: UUID, body: SceneInput, member: Member, connection: Connection, response: Response, idempotency_key: Annotated[UUID,Header(alias='Idempotency-Key')]):
    return create_scene(job_id,body,member,connection,response,idempotency_key)

@generations_router.get('/account/generation-usage')
def usage(member: Member, connection: Connection):
    return service.usage(member=member, connection=connection)

@generations_router.post('/try-on/sessions/{session_id}/generations', status_code=202)
def create_job(session_id: UUID, body: GenerationInput, member: Member, connection: Connection, response: Response, idempotency_key: Annotated[UUID, Header(alias='Idempotency-Key')]):
    return service.create_job(session_id=session_id, body=body, member=member, connection=connection, response=response, idempotency_key=idempotency_key)

@generations_router.get('/try-on/jobs/{job_id}')
def get_job(job_id: UUID, member: Member, connection: Connection):
    return service.get_job(job_id=job_id, member=member, connection=connection)

@generations_router.get('/try-on/generations')
def list_jobs(member: Member, connection: Connection, page: int=Query(0, ge=0, le=100000), page_size: int=Query(12, alias='pageSize', ge=1, le=50), source: Literal['WEBSITE', 'MCP'] | None=None):
    return service.list_jobs(member=member, connection=connection, page=page, page_size=page_size, source=source)

@generations_router.delete('/try-on/generations/{generation_id}', status_code=202)
def delete_generation(generation_id: UUID, member: Member, connection: Connection):
    return service.delete_generation(generation_id=generation_id, member=member, connection=connection)

@photos_router.get('/try-on/consent')
def consent():
    return photos.consent()

@photos_router.get('/models')
def models(connection: Connection):
    return photos.models(connection=connection)

@photos_router.get('/models/{model_id}/preview', include_in_schema=False)
def model_preview(model_id: UUID, connection: Connection):
    return photos.model_preview(model_id=model_id, connection=connection)

@photos_router.get('/try-on/photos')
def list_photos(member: Member, connection: Connection):
    return photos.list_photos(member=member,connection=connection)

@photos_router.delete('/try-on/photos/{photo_id}', status_code=202)
def delete_library_photo(photo_id: UUID, member: Member, connection: Connection, tasks: BackgroundTasks):
    return photos.delete_library_photo(photo_id=photo_id,member=member,connection=connection,tasks=tasks)

@photos_router.post('/try-on/sessions', status_code=201)
def create_session(body: SessionInput, member: Member, connection: Connection):
    return photos.create_session(body=body, member=member, connection=connection)

@photos_router.get('/try-on/sessions')
def list_sessions(member: Member, connection: Connection, page: int=Query(0, ge=0), page_size: int=Query(12, alias='pageSize', ge=1, le=50)):
    return photos.list_sessions(member=member, connection=connection, page=page, page_size=page_size)

@photos_router.get('/try-on/sessions/{session_id}')
def get_session(session_id: UUID, member: Member, connection: Connection):
    return photos.get_session(session_id=session_id, member=member, connection=connection)

@photos_router.patch('/try-on/sessions/{session_id}')
def update_session(session_id: UUID, body: LookSelection, member: Member, connection: Connection):
    return photos.update_session(session_id=session_id, body=body, member=member, connection=connection)

@photos_router.post('/try-on/sessions/{session_id}/upload-url')
def upload_url(session_id: UUID, body: UploadInput, request: Request, member: Member, connection: Connection, tasks: BackgroundTasks):
    return photos.upload_url(session_id=session_id, body=body, request=request, member=member, connection=connection, tasks=tasks)

@photos_router.put('/try-on/sessions/{session_id}/uploads/{photo_id}')
async def transfer_photo(session_id: UUID, photo_id: UUID, request: Request, member: Member, connection: Connection):
    return await photos.transfer_photo(session_id=session_id, photo_id=photo_id, request=request, member=member, connection=connection)

@photos_router.post('/try-on/sessions/{session_id}/validate')
def validate_photo(session_id: UUID, body: ValidateInput, member: Member, connection: Connection, tasks: BackgroundTasks):
    return photos.validate_photo(session_id=session_id, body=body, member=member, connection=connection, tasks=tasks)

@photos_router.delete('/try-on/sessions/{session_id}/photo', status_code=202)
def delete_photo(session_id: UUID, member: Member, connection: Connection, tasks: BackgroundTasks, withdraw_consent: bool=Query(False, alias='withdrawConsent')):
    return photos.delete_photo(session_id=session_id, member=member, connection=connection, tasks=tasks, withdraw_consent=withdraw_consent)
router = APIRouter()
router.include_router(photos_router)
router.include_router(generations_router)
