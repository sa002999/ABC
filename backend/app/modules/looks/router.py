from app.core.database import get_connection
from app.modules.accounts.dependencies import Member
from app.modules.catalog.schemas import LookSelection
from app.modules.looks import service as service
from app.modules.looks.schemas import CompareInput, Look, LookList, LookUpdate
from fastapi import APIRouter, Depends, Header, Query, Response
from typing import Annotated
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection)]
router = APIRouter(prefix='/api', tags=['我的造型收藏'])

@router.post('/looks', response_model=Look, status_code=201)
def create_look(selection: LookSelection, member: Member, connection: Connection, response: Response, idempotency_key: Annotated[UUID | None, Header(alias='Idempotency-Key')]=None):
    return service.create_look(selection=selection, member=member, connection=connection, response=response, idempotency_key=idempotency_key)

@router.get('/looks', response_model=LookList)
def list_looks(member: Member, connection: Connection, page: int=Query(0, ge=0, le=100000), page_size: int=Query(12, alias='pageSize', ge=1, le=50), plan_id: UUID | None=Query(None, alias='planId')):
    return service.list_looks(member=member, connection=connection, page=page, page_size=page_size, plan_id=plan_id)

@router.get('/looks/{look_id}', response_model=Look)
def get_look(look_id: UUID, member: Member, connection: Connection):
    return service.get_look(look_id=look_id, member=member, connection=connection)

@router.patch('/looks/{look_id}', response_model=Look)
def update_look(look_id: UUID, selection: LookUpdate, member: Member, connection: Connection):
    return service.update_look(look_id=look_id, selection=selection, member=member, connection=connection)

@router.delete('/looks/{look_id}')
def delete_look(look_id: UUID, member: Member, connection: Connection):
    return service.delete_look(look_id=look_id, member=member, connection=connection)

@router.post('/plans/compare', response_model=list[Look])
def compare_looks(selection: CompareInput, member: Member, connection: Connection):
    return service.compare_looks(selection=selection, member=member, connection=connection)
