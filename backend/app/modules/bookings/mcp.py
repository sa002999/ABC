"""Member-only handoff from MCP selection to website payment."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import ConfigDict, Field

from app.core.errors import error
from app.core.schemas import CamelModel
from app.integrations.tappay_service import configured
from app.modules.accounts.mcp import mcp_member
from app.modules.bookings import service
from app.modules.bookings.queries import lock_member
from app.modules.bookings.router import Connection, require_booking_profile
from app.modules.bookings.schemas import DraftInput, DraftUpdate, HoldInput, QuoteInput

McpMember = Annotated[UUID, Depends(mcp_member)]
router = APIRouter(prefix='/api/mcp/booking', tags=['MCP booking'])


class SelectionGuest(CamelModel):
    model_config = ConfigDict(extra='forbid')
    guest_type: Literal['ADULT_FEMALE', 'ADULT_MALE']
    plan_id: UUID
    kimono_id: UUID


class Selection(CamelModel):
    model_config = ConfigDict(extra='forbid')
    store_id: UUID
    slot_id: UUID
    guests: list[SelectionGuest] = Field(min_length=1, max_length=3)
    replace_draft_id: UUID | None = None
    replace_version: int | None = Field(None, ge=1)


class ConfirmHold(HoldInput):
    confirmed: Literal[True]


@router.post('/prepare')
def prepare(body: Selection, member: McpMember, connection: Connection, response: Response):
    lock_member(connection, member)
    profile = require_booking_profile(member, connection)
    name, email, phone = profile['display_name'].strip(), profile['email'], profile['phone_number']
    if len(name) > 40 or len(email) > 40:
        error(422, 'CONTACT_TOO_LONG', '付款姓名與 Email 最多 40 字，請至官網確認聯絡資料。')
    draft = DraftInput.model_validate({
        **body.model_dump(exclude={'replace_draft_id', 'replace_version'}), 'contact_name': name, 'contact_email': email,
        'contact_phone': phone, 'contact_mode': 'member',
    })
    saved = service.create_draft(draft, member, connection, response)
    if saved['activeHold']:
        error(409, 'DRAFT_HELD', '已有暫留或付款處理中，請至官網繼續。')
    if saved['data'] != service.draft_json(draft):
        if body.replace_draft_id != saved['draftId'] or body.replace_version != saved['version']:
            return {'draftConflict': True, 'draftId': saved['draftId'], 'version': saved['version']}
        update = DraftUpdate.model_validate({**draft.model_dump(), 'version': saved['version']})
        saved = service.update_draft(saved['draftId'], update, member, connection)
    quote = service.quote(QuoteInput(draft_id=saved['draftId'], version=saved['version']), member, connection)
    return {**quote, 'paymentAvailable': configured()}


@router.post('/hold', status_code=201)
def hold(body: ConfirmHold, member: McpMember, connection: Connection, response: Response):
    lock_member(connection, member)
    require_booking_profile(member, connection)
    if not configured():
        error(503, 'PAYMENT_UNAVAILABLE', '官網 Sandbox 付款尚未設定，無法建立付款暫留。')
    request = HoldInput(draft_id=body.draft_id, quote_token=body.quote_token)
    return service.create_hold(request, member, connection, response, body.quote_token, {'email_verified': True})
