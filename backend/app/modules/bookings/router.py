from app.core.database import get_connection
from app.modules.accounts.dependencies import Member, current_identity
from app.modules.bookings import service as service
from app.modules.bookings.schemas import DraftInput, DraftUpdate, HoldInput, QuoteInput
from datetime import date
from fastapi import APIRouter, Depends, Header, Query, Response
from typing import Annotated
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection, scope='function')]
router = APIRouter(prefix='/api', tags=['預約與即時庫存'])

@router.get('/stores/{store_id}/availability')
def availability(store_id: UUID, connection: Connection, start: date=Query(alias='from'), end: date=Query(alias='to'), party_size: int=Query(1, alias='partySize', ge=1, le=3), plan_id: UUID | None=Query(None, alias='planId')):
    return service.availability(store_id=store_id, connection=connection, start=start, end=end, party_size=party_size, plan_id=plan_id)

@router.post('/booking-drafts', status_code=201)
def create_draft(body: DraftInput, member: Member, connection: Connection, response: Response):
    return service.create_draft(body=body, member=member, connection=connection, response=response)

@router.get('/booking-drafts')
def list_drafts(member: Member, connection: Connection, page: int=Query(0, ge=0, le=100000)):
    return service.list_drafts(member=member, connection=connection, page=page)

@router.get('/booking-drafts/{draft_id}')
def get_draft(draft_id: UUID, member: Member, connection: Connection):
    return service.get_draft(draft_id=draft_id, member=member, connection=connection)

@router.patch('/booking-drafts/{draft_id}')
def update_draft(draft_id: UUID, body: DraftUpdate, member: Member, connection: Connection):
    return service.update_draft(draft_id=draft_id, body=body, member=member, connection=connection)

@router.post('/pricing/quote')
def quote(body: QuoteInput, member: Member, connection: Connection):
    return service.quote(body=body, member=member, connection=connection)

@router.post('/availability/holds', status_code=201)
def create_hold(body: HoldInput, member: Member, connection: Connection, response: Response, idempotency_key: Annotated[UUID, Header(alias='Idempotency-Key')], identity=Depends(current_identity)):
    return service.create_hold(body=body, member=member, connection=connection, response=response, idempotency_key=idempotency_key, identity=identity)

@router.get('/availability/holds/{hold_id}')
def get_hold(hold_id: UUID, member: Member, connection: Connection):
    return service.get_hold(hold_id=hold_id, member=member, connection=connection)

@router.delete('/availability/holds/{hold_id}')
def release_hold(hold_id: UUID, member: Member, connection: Connection):
    return service.release_hold(hold_id=hold_id, member=member, connection=connection)
