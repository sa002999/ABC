from fastapi import APIRouter, Depends
from uuid import UUID
from typing import Literal
from pydantic import ConfigDict, Field
from app.core.database import get_connection
from app.core.schemas import CamelModel
from app.modules.bookings.schemas import Guest, DraftInput
from app.modules.bookings.service import validate_draft, validate_rental_hours
from app.modules.catalog.rules import pricing_lines
from app.modules.catalog.schemas import City
from datetime import date, datetime, time, timedelta
from fastapi import HTTPException
from app.core.errors import error
from app.modules.bookings.queries import match_inventory, inventory_candidates
from app.modules.bookings.rules import TOKYO, in_window, utcnow

router = APIRouter(tags=['搭配探索'])


class PublicGuest(CamelModel):
    model_config = ConfigDict(extra='forbid')
    guest_type: Literal['ADULT_FEMALE', 'ADULT_MALE']
    plan_id: UUID
    kimono_id: UUID


class OutfitInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    city: City
    guests: list[PublicGuest] = Field(min_length=1, max_length=3)


class AvailabilityInput(OutfitInput):
    store_id: UUID
    from_date: date = Field(alias='from')
    to_date: date = Field(alias='to')


@router.post('/api/catalog/party-availability')
def party_availability(body: AvailabilityInput, connection=Depends(get_connection)):
    if body.to_date == date.max or body.to_date < body.from_date or (body.to_date-body.from_date).days > 30:
        error(422, 'INVALID_DATE_RANGE', '每次請查詢 1～31 天的場次。')
    store = connection.execute('SELECT id,name,city,is_demo FROM stores WHERE id=%s AND active AND city=%s',
                               (body.store_id, body.city)).fetchone()
    if not store:
        error(422, 'PLAN_STORE_MISMATCH', '請選擇目前城市的共同適用門市。')
    draft = DraftInput(store_id=body.store_id, guests=[Guest.model_validate(g.model_dump()) for g in body.guests])
    settings, _, plans = validate_draft(connection, draft, None)
    now = utcnow()
    rows = connection.execute('''SELECT s.*, GREATEST(0,s.capacity_total-COALESCE((
        SELECT sum(h.party_size) FROM availability_holds h WHERE h.slot_id=s.id
        AND ((h.status='HELD' AND h.expires_at>now()) OR h.status IN ('PAYMENT_PENDING','RESERVED'))),0)) AS remaining
        FROM availability_slots s WHERE store_id=%s
        AND starts_at>=%s AND starts_at<%s ORDER BY starts_at''',
        (body.store_id, datetime.combine(body.from_date, time.min, TOKYO),
         datetime.combine(body.to_date+timedelta(days=1), time.min, TOKYO))).fetchall()
    candidates = inventory_candidates(connection, body.store_id,
        [slot for slot in rows if slot['status']=='OPEN' and in_window(slot['starts_at'], now) and slot['remaining']>=len(draft.guests)],
        draft.guests, plans, settings)
    slots = []
    for slot in rows:
        remaining = slot['remaining']
        reason = ('SLOT_CLOSED' if slot['status'] != 'OPEN' else
                  'OUTSIDE_BOOKING_WINDOW' if not in_window(slot['starts_at'], now) else
                  'SLOT_FULL' if remaining < len(draft.guests) else None)
        checked = False
        if not reason:
            # Reuse the booking rules, without creating a draft, quote or hold.
            try:
                validate_rental_hours(slot, settings, plans)
                match_inventory(connection, body.store_id, slot, draft.guests, plans, settings, candidates=candidates)
                checked = True
            except HTTPException as exc:
                code = exc.detail.get('code') if isinstance(exc.detail, dict) else None
                if code not in ('RENTAL_AFTER_CLOSING', 'INVENTORY_UNAVAILABLE', 'SLOT_UNAVAILABLE'):
                    raise
                reason = code
                checked = code == 'INVENTORY_UNAVAILABLE'
        slots.append({'slotId': slot['id'], 'startsAt': slot['starts_at'], 'endsAt': slot['ends_at'],
                      'remaining': remaining, 'available': reason is None, 'reason': reason,
                      'inventoryChecked': checked, 'isDemo': slot['is_demo'],
                      'rentalEndsAt': [(slot['starts_at']+timedelta(minutes=p['duration_minutes'])) for p in plans]})
    return {'view': 'partyAvailability', **body.model_dump(mode='json', by_alias=True),
            'store': {'id': store['id'], 'name': store['name']}, 'slots': slots,
            'timezone': 'Asia/Tokyo', 'serverTime': now, 'availabilityChecked': True,
            'inventoryReserved': False, 'bookingCreated': False,
            'isDemo': store['is_demo'] or settings['settings_demo'] or any(p['is_demo'] for p in plans) or any(s['isDemo'] for s in slots),
            'notice': '日本時間。已檢查全員接待名額、租借與整備期間的和服庫存；結果僅供查詢當下參考，未保留庫存、未建立預約。無可用時段時可保留搭配改查其他日期。'}


@router.post('/api/catalog/outfit-summary')
def summary(body: OutfitInput, connection=Depends(get_connection)):
    draft = DraftInput(guests=[Guest.model_validate(g.model_dump()) for g in body.guests])
    _, _, plans = validate_draft(connection, draft, None)
    lines = pricing_lines(draft.guests, plans)
    common = None
    for guest in draft.guests:
        stores = connection.execute('''SELECT s.id,s.name,s.city FROM stores s JOIN plan_stores ps ON ps.store_id=s.id
            WHERE s.active AND s.city=%s AND ps.plan_id=%s AND EXISTS
            (SELECT 1 FROM inventory_items i WHERE i.store_id=s.id AND i.kimono_id=%s)
            ORDER BY s.slug''', (body.city, guest.plan_id, guest.kimono_id)).fetchall()
        ids = {s['id'] for s in stores}
        common = ids if common is None else common & ids
    stores = [s for s in stores if s['id'] in common]
    return {'view': 'outfitSummary', 'city': body.city, 'guests': body.model_dump(mode='json', by_alias=True)['guests'],
            'lineItems': lines, 'estimatedTotal': sum(line['total'] for line in lines), 'currency': 'TWD',
            'commonStores': stores, 'isDemo': any(p['is_demo'] for p in plans),
            'availabilityChecked': False, 'bookingCreated': False,
            'notice': '估計金額依目前後端規則計算；未檢查日期、全員庫存及接待名額，未保留或建立預約。' if stores else
                      '目前搭配沒有共同適用門市，請調整款式或方案。選擇已保留，未建立預約。'}
