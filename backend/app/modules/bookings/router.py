from app.modules.bookings import contact
from app.core.errors import error
from app.core.database import get_connection
from app.modules.accounts.dependencies import Member, current_identity
from app.modules.bookings import service as service
from app.modules.bookings.schemas import ContactEmailCode, ContactPhoneProof, ContactVersion, DraftInput, DraftUpdate, HoldInput, QuoteInput
from app.modules.bookings.schemas import PaymentInput
from app.modules.bookings import payments
from datetime import date
from fastapi import APIRouter, Depends, Header, Query, Response
from typing import Annotated
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection, scope='function')]
router = APIRouter(prefix='/api', tags=['預約與即時庫存'])

def require_booking_profile(member, connection):
    profile = connection.execute(
        'SELECT display_name,email,phone_number,phone_verified_at FROM users WHERE id=%s', (member,)
    ).fetchone()
    if profile is None:
        error(403, "BOOKING_PROFILE_REQUIRED", "請先到會員中心完成會員資料。")
    missing = []
    if not (profile['display_name'] or '').strip():
        missing.append('填寫會員姓名')
    if not (profile['phone_number'] or '').strip() or not profile['phone_verified_at']:
        missing.append('完成會員手機驗證')
    if missing:
        error(403, 'BOOKING_PROFILE_REQUIRED', '請先到會員中心' + '、'.join(missing) + '，再開始預約。')
    return profile


def booking_member(_identity=Depends(contact.verified_identity), *, member: Member, connection: Connection):
    require_booking_profile(member, connection)
    return member


BookingMember = Annotated[UUID, Depends(booking_member, scope='function')]


@router.get('/stores/{store_id}/availability')
def availability(store_id: UUID, connection: Connection, start: date=Query(alias='from'), end: date=Query(alias='to'), party_size: int=Query(1, alias='partySize', ge=1, le=3), plan_id: UUID | None=Query(None, alias='planId')):
    return service.availability(store_id=store_id, connection=connection, start=start, end=end, party_size=party_size, plan_id=plan_id)

@router.post('/booking-drafts', status_code=201)
def create_draft(body: DraftInput, member: BookingMember, connection: Connection, response: Response):
    return service.create_draft(body=body, member=member, connection=connection, response=response)

@router.get('/booking-drafts')
def list_drafts(member: BookingMember, connection: Connection, page: int=Query(0, ge=0, le=100000)):
    return service.list_drafts(member=member, connection=connection, page=page)

@router.get('/booking-drafts/{draft_id}')
def get_draft(draft_id: UUID, member: BookingMember, connection: Connection):
    return service.get_draft(draft_id=draft_id, member=member, connection=connection)

@router.patch('/booking-drafts/{draft_id}')
def update_draft(draft_id: UUID, body: DraftUpdate, member: BookingMember, connection: Connection):
    return service.update_draft(draft_id=draft_id, body=body, member=member, connection=connection)

@router.post('/booking-drafts/{draft_id}/contact/email')
def send_contact_email(draft_id: UUID, body: ContactVersion, member: BookingMember, connection: Connection):
    contact.send_email(connection,draft_id,member,body.version)
    return {'ok':True}


@router.post('/booking-drafts/{draft_id}/contact/email/confirm')
def confirm_contact_email(draft_id: UUID, body: ContactEmailCode, member: BookingMember, connection: Connection):
    if not contact.confirm_email(connection,draft_id,member,body.version,body.code):
        error(422,'INVALID_CONTACT_CODE','驗證碼不正確、已到期或嘗試次數過多。')
    return {'ok':True}


@router.post('/booking-drafts/{draft_id}/contact/phone')
def confirm_contact_phone(draft_id: UUID, body: ContactPhoneProof, member: BookingMember, connection: Connection,
                          identity=Depends(contact.verified_identity)):
    contact.confirm_phone(connection,draft_id,member,body.version,identity,body.phone_token)
    return {'ok':True}


@router.post('/pricing/quote')
def quote(body: QuoteInput, member: BookingMember, connection: Connection):
    return service.quote(body=body, member=member, connection=connection)

@router.post('/availability/holds', status_code=201)
def create_hold(body: HoldInput, member: BookingMember, connection: Connection, response: Response, idempotency_key: Annotated[UUID, Header(alias='Idempotency-Key')], identity=Depends(current_identity)):
    return service.create_hold(body=body, member=member, connection=connection, response=response, idempotency_key=idempotency_key, identity=identity)

@router.get('/availability/holds/{hold_id}')
def get_hold(hold_id: UUID, member: Member, connection: Connection):
    return service.get_hold(hold_id=hold_id, member=member, connection=connection)

@router.delete('/availability/holds/{hold_id}')
def release_hold(hold_id: UUID, member: Member, connection: Connection):
    return service.release_hold(hold_id=hold_id, member=member, connection=connection)


@router.post('/bookings')
def submit_payment(body: PaymentInput, member: Member, connection: Connection, response: Response,
                   idempotency_key: Annotated[UUID, Header(alias='Idempotency-Key')], identity=Depends(current_identity)):
    result=payments.submit(connection,member,identity,body,idempotency_key)
    response.status_code=202 if result['paymentStatus']=='PAYMENT_PENDING' else 200
    return result


@router.get('/orders/{order_no}')
def get_order(order_no: str, member: Member, connection: Connection):
    payments.owned_order(connection,order_no,member)
    payments.reconcile(connection,order_no)
    return payments.order_data(connection,payments.owned_order(connection,order_no,member))


@router.get('/orders')
def list_orders(member: Member, connection: Connection):
    rows=connection.execute("SELECT * FROM payment_orders WHERE user_id=%s AND status IN ('PAYMENT_PENDING','REVIEW_REQUIRED','REFUND_REQUIRED') ORDER BY created_at DESC LIMIT 20",(member,)).fetchall()
    return {'data':[payments.order_data(connection,r) for r in rows]}


@router.get('/bookings')
def list_bookings(member: Member, connection: Connection, page: int=Query(0,ge=0,le=100000)):
    return payments.bookings(connection,member,page=page)


@router.get('/bookings/{booking_no}')
def get_booking(booking_no: str, member: Member, connection: Connection):
    return payments.bookings(connection,member,booking_no)
