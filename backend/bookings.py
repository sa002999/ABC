"""Member drafts, authoritative TWD quotes and atomic inventory holds; no payment."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal, NoReturn
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import ConfigDict, Field, ValidationError, model_validator
from psycopg.types.json import Jsonb

from auth import current_identity
from catalog import CamelModel
from database import connect, get_connection
from looks import Member

router=APIRouter(prefix='/api',tags=['預約與即時庫存'])
Connection=Annotated[psycopg.Connection,Depends(get_connection,scope='function')]
TOKYO=ZoneInfo('Asia/Tokyo')


def error(status,code,message) -> NoReturn:
    raise HTTPException(status,{'code':code,'message':message})


class Guest(CamelModel):
    model_config=ConfigDict(extra='forbid')
    display_name: str=Field('',max_length=60)
    guest_type: Literal['ADULT_FEMALE','ADULT_MALE']='ADULT_FEMALE'
    plan_id: UUID | None=None
    kimono_id: UUID | None=None
    saved_look_id: UUID | None=None
    generation_id: UUID | None=None
    accessory_ids: list[UUID]=Field(default_factory=list,max_length=1)

    @model_validator(mode='after')
    def adult_accessories(self):
        if self.guest_type=='ADULT_MALE' and self.accessory_ids:
            error(422,'INVALID_ACCESSORY','男生不可選配件。')
        return self



class DraftInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    store_id: UUID | None=None
    slot_id: UUID | None=None
    guests: list[Guest]=Field(min_length=1,max_length=3)
    party_size: int | None=Field(None,ge=1,le=3)
    contact_name: str=Field('',max_length=100)
    contact_email: str=Field('',max_length=254)
    contact_phone: str=Field('',max_length=30)
    locale: Literal['zh-Hant','en','ja']='zh-Hant'
    add_on_ids: list[UUID]=Field(default_factory=list,max_length=20)
    photography_id: UUID | None=None

    @model_validator(mode='after')
    def guest_count(self):
        if self.party_size is not None and self.party_size!=len(self.guests):
            error(422,'INVALID_GUEST_COUNT','每筆預約限 1～3 人，旅客清單須與人數一致。')
        if self.add_on_ids or self.photography_id:
            error(422,'ADDONS_UNAVAILABLE','攝影與其他加購尚未開放。')
        return self


class DraftUpdate(DraftInput):
    version: int=Field(ge=1)


class QuoteInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    draft_id: UUID
    version: int=Field(ge=1)


class HoldInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    draft_id: UUID
    quote_token: UUID


def utcnow(): return datetime.now(timezone.utc)


def in_window(starts_at,now=None):
    delta=starts_at-(now or utcnow())
    return timedelta(hours=24)<=delta<=timedelta(days=90)


def lock_member(connection,member):
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(member,)).fetchone()


def current_draft(connection,member,lock=False):
    return connection.execute('''SELECT d.* FROM booking_drafts d WHERE d.id=(
        SELECT candidate.id FROM booking_drafts candidate WHERE candidate.user_id=%s
        ORDER BY (candidate.expires_at>now() AND EXISTS (SELECT 1 FROM availability_holds h WHERE h.draft_id=candidate.id
            AND ((h.status='HELD' AND h.expires_at>now()) OR h.status='PAYMENT_PENDING'))) DESC,
        candidate.updated_at DESC,candidate.id DESC LIMIT 1) AND d.expires_at>now()
        AND NOT EXISTS (SELECT 1 FROM availability_holds h WHERE h.draft_id=d.id AND h.status='RESERVED')
        '''+(' FOR UPDATE OF d' if lock else ''),(member,)).fetchone()


def owned_draft(connection,draft_id,member,lock=False):
    row=current_draft(connection,member,lock)
    if not row or row['id']!=draft_id: error(404,'DRAFT_NOT_FOUND','找不到目前草稿，或草稿已到期、已成立預約。請從會員中心恢復目前草稿。')
    return row


def draft_input(row):
    if not 1<=len(row['data'].get('guests',[]))<=3:
        error(422,'INVALID_GUEST_COUNT','每筆預約限 1～3 人，請修正原草稿，不會自動刪減旅客。')
    try: return DraftInput.model_validate(row['data'])
    except ValidationError: error(422,'INVALID_DRAFT','草稿有已失效或不完整的欄位，請重新確認。')


def draft_json(body):
    return body.model_dump(mode='json',by_alias=True,exclude={'version'})


def effective_hold(row):
    return 'EXPIRED' if row['status']=='HELD' and row['expires_at']<=utcnow() else row['status']


def active_hold(connection,draft_id):
    return connection.execute("""SELECT * FROM availability_holds WHERE draft_id=%s AND
        ((status='HELD' AND expires_at>now()) OR status IN ('PAYMENT_PENDING','RESERVED')) ORDER BY created_at DESC LIMIT 1""",(draft_id,)).fetchone()


def hold_data(row):
    return {'holdId':row['id'],'draftId':row['draft_id'],'status':effective_hold(row),'expiresAt':row['expires_at'],
        'serverTime':utcnow(),'currency':'TWD','total':row['total'],'partySize':row['party_size'],
        'snapshot':row['snapshot'],'paymentAvailable':False,'bookingConfirmed':False}


def draft_data(row,connection):
    held=active_hold(connection,row['id'])
    slot=connection.execute('SELECT id,starts_at,ends_at,is_demo FROM availability_slots WHERE id=%s',(row['data'].get('slotId'),)).fetchone() if row['data'].get('slotId') else None
    issues=[] if 1<=len(row['data'].get('guests',[]))<=3 else [{'code':'INVALID_GUEST_COUNT','message':'每筆預約限 1～3 人，請修正旅客清單。'}]
    return {'draftId':row['id'],'status':'DRAFT','version':row['version'],'expiresAt':row['expires_at'],
        'updatedAt':row['updated_at'],'data':row['data'],'validationIssues':issues,
        'slot':{'slotId':slot['id'],'startsAt':slot['starts_at'],'endsAt':slot['ends_at'],'isDemo':slot['is_demo']} if slot else None,
        'activeHold':hold_data(held) if held else None}


def store_settings(connection,store_id,lock=False):
    row=connection.execute('''SELECT s.id,s.name,s.is_demo,b.cleaning_minutes,b.closes_at,b.is_demo AS settings_demo
        FROM stores s JOIN store_booking_settings b ON b.store_id=s.id WHERE s.id=%s AND s.active'''+(' FOR SHARE OF s,b' if lock else ''),(store_id,)).fetchone()
    if not row: error(409,'STORE_UNAVAILABLE','門市尚未開放預約，請選擇其他門市。')
    return row


def selected_slot(connection,store_id,slot_id,lock=False):
    row=connection.execute('SELECT * FROM availability_slots WHERE id=%s AND store_id=%s'+(' FOR UPDATE' if lock else ''),(slot_id,store_id)).fetchone()
    if not row or row['status']!='OPEN' or not in_window(row['starts_at']):
        error(409,'SLOT_UNAVAILABLE','時段已關閉，或不在開始前 24 小時至未來 90 天的預約範圍，請重新選擇。')
    return row


def validate_draft(connection,body,member,complete=False,lock_prices=False):
    settings=store_settings(connection,body.store_id,lock_prices) if body.store_id else None
    if body.slot_id and not body.store_id: error(422,'STORE_REQUIRED','請先選擇門市。')
    slot=selected_slot(connection,body.store_id,body.slot_id,lock_prices) if body.slot_id else None
    if complete and (not settings or not slot): error(422,'INCOMPLETE_DRAFT','請先完成門市與場次選擇。')
    plans=[]
    for guest in body.guests:
        if not guest.plan_id:
            if guest.kimono_id or complete: error(422,'INCOMPLETE_OUTFIT','請為每位旅客選擇完整方案。')
            plans.append(None);continue
        row=connection.execute('''SELECT p.id,p.kimono_id,p.name,p.base_price,p.duration_minutes,p.is_demo,p.kind,p.additional_guest_price
            FROM plans p JOIN kimonos k ON k.id=p.kimono_id WHERE p.id=%s AND p.active AND k.active'''+(' FOR SHARE OF p,k' if lock_prices else ''),(guest.plan_id,)).fetchone()
        if not row:
            error(422,'INVALID_OUTFIT','方案或和服已無法選用，請重新選擇。')
        if settings and not connection.execute('SELECT 1 FROM plan_stores WHERE plan_id=%s AND store_id=%s',(guest.plan_id,body.store_id)).fetchone():
            error(422,'PLAN_STORE_MISMATCH','有旅客的方案不適用目前門市，請明確更換方案。')
        from commerce import selected_belts
        if not guest.kimono_id and not complete:
            plans.append(row);continue
        garment=connection.execute('SELECT id,gender FROM kimonos WHERE id=%s AND active',(guest.kimono_id,)).fetchone()
        expected='FEMALE' if guest.guest_type=='ADULT_FEMALE' else 'MALE'
        if not garment or garment['gender']!=expected:
            error(422,'INVALID_OUTFIT','和服與旅客角色不符。')
        if settings and not connection.execute('SELECT 1 FROM inventory_items WHERE kimono_id=%s AND store_id=%s',(guest.kimono_id,body.store_id)).fetchone():
            error(422,'PLAN_STORE_MISMATCH','所選和服不屬於目前門市。')
        row={**row,'kimono_id':guest.kimono_id,'belts':selected_belts(connection,expected,guest.accessory_ids)}
        if guest.saved_look_id:
            look=connection.execute('SELECT plan_id,kimono_id FROM looks WHERE id=%s AND user_id=%s',(guest.saved_look_id,member)).fetchone()
            if not look or (look['plan_id'],look['kimono_id'])!=(guest.plan_id,guest.kimono_id):
                error(422,'INVALID_SAVED_LOOK','收藏不存在、非本人所有，或與搭配不符。')
        if guest.generation_id:
            generated=connection.execute('SELECT plan_id,kimono_id FROM generation_jobs WHERE id=%s AND user_id=%s AND source=\'WEBSITE\'',(guest.generation_id,member)).fetchone()
            if not generated or (generated['plan_id'],generated['kimono_id'])!=(guest.plan_id,guest.kimono_id):
                error(422,'INVALID_GENERATION','試穿紀錄非本人所有，或與搭配不符。')
        if slot and settings:
            rental_end=slot['starts_at']+timedelta(minutes=row['duration_minutes'])
            close=datetime.combine(slot['starts_at'].astimezone(TOKYO).date(),settings['closes_at'],TOKYO)
            if rental_end>close: error(409,'RENTAL_AFTER_CLOSING','此方案的歸還時間超過門市當日收件時間，請改選較早場次。')
        plans.append(row)
    from commerce import validate_packages
    validate_packages(body.guests,plans)
    if complete:
        import re
        if not body.contact_name.strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',body.contact_email) or not re.fullmatch(r'[+0-9() .-]{6,30}',body.contact_phone):
            error(422,'CONTACT_REQUIRED','請填寫聯絡姓名、有效 Email 與電話。')
    return settings,slot,plans


def remaining_capacity(connection,slot):
    used=connection.execute("""SELECT COALESCE(sum(party_size),0) AS used FROM availability_holds
        WHERE slot_id=%s AND ((status='HELD' AND expires_at>now()) OR status IN ('PAYMENT_PENDING','RESERVED'))""",(slot['id'],)).fetchone()['used']
    return max(0,slot['capacity_total']-used)


def match_inventory(connection,store_id,slot,guests,plans,settings,lock=False):
    used=[];allocations=[]
    for index,(guest,plan) in enumerate(zip(guests,plans)):
        rental_end=slot['starts_at']+timedelta(minutes=plan['duration_minutes'])
        cleaning_end=rental_end+timedelta(minutes=settings['cleaning_minutes'])
        row=connection.execute('''SELECT i.id FROM inventory_items i WHERE i.store_id=%s AND i.kimono_id=%s
            AND i.status='AVAILABLE' AND NOT(i.id=ANY(%s::uuid[])) AND NOT EXISTS
            (SELECT 1 FROM inventory_allocations a JOIN availability_holds h ON h.id=a.hold_id
                WHERE a.inventory_id=i.id AND a.status IN ('HELD','RESERVED')
                AND ((h.status='HELD' AND h.expires_at>now()) OR h.status IN ('PAYMENT_PENDING','RESERVED'))
                AND a.rental_starts_at<%s AND a.cleaning_ends_at>%s)
            ORDER BY i.code LIMIT 1'''+(' FOR UPDATE OF i' if lock else ''),
            (store_id,guest.kimono_id,used,cleaning_end,slot['starts_at'])).fetchone()
        if not row: error(409,'INVENTORY_UNAVAILABLE',f'旅客 {index+1} 的和服在租借與整備期間內庫存不足，整筆未暫留。')
        used.append(row['id']);allocations.append((index,row['id'],slot['starts_at'],rental_end,cleaning_end))
    return allocations


def price_snapshot(body,settings,slot,plans):
    from commerce import pricing_lines
    lines=pricing_lines(body.guests,plans)
    for line in lines:
        i=line['guestIndex']
        line['rentalEndsAt']=(slot['starts_at']+timedelta(minutes=plans[i]['duration_minutes'])).isoformat()
    total=sum(line['total'] for line in lines)
    snapshot={'storeId':str(settings['id']),'storeName':settings['name'],'slotId':str(slot['id']),
        'startsAt':slot['starts_at'].isoformat(),'slotVersion':slot['version'],'cleaningMinutes':settings['cleaning_minutes'],
        'closesAt':str(settings['closes_at']),'lineItems':lines,'subtotal':total,
        'discount':0,'total':total,'currency':'TWD',
        'isDemo':settings['is_demo'] or settings['settings_demo'] or slot['is_demo'] or any(p['is_demo'] for p in plans)}
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    return snapshot,digest


@router.get('/stores/{store_id}/availability')
def availability(store_id: UUID,connection: Connection,start: date=Query(alias='from'),end: date=Query(alias='to'),
                 party_size: int=Query(1,alias='partySize',ge=1,le=3),plan_id: UUID | None=Query(None,alias='planId')):
    if end<start or (end-start).days>30: error(422,'INVALID_DATE_RANGE','每次請查詢 1～31 天的場次。')
    settings=store_settings(connection,store_id)
    plan_ref=None
    if plan_id:
        plan_ref=connection.execute('SELECT kimono_id,kind FROM plans WHERE id=%s AND active',(plan_id,)).fetchone()
        if not plan_ref: error(422,'INVALID_OUTFIT','找不到此方案。')
    rows=connection.execute('SELECT * FROM availability_slots WHERE store_id=%s AND starts_at>=%s AND starts_at<%s ORDER BY starts_at',
        (store_id,datetime.combine(start,time.min,TOKYO),datetime.combine(end+timedelta(days=1),time.min,TOKYO))).fetchall()
    result=[]
    for row in rows:
        remaining=remaining_capacity(connection,row)
        reason='SLOT_CLOSED' if row['status']!='OPEN' else 'OUTSIDE_BOOKING_WINDOW' if not in_window(row['starts_at']) else 'SLOT_FULL' if remaining<party_size else None
        checked=False
        if not reason and plan_id and plan_ref['kind']!='COUPLE':
            body=DraftInput(store_id=store_id,slot_id=row['id'],guests=[Guest(plan_id=plan_id,kimono_id=plan_ref['kimono_id']) for _ in range(party_size)],party_size=party_size,contact_name='',contact_email='',contact_phone='')
            try:
                _,_,plans=validate_draft(connection,body,None)
                match_inventory(connection,store_id,row,body.guests,plans,settings)
            except HTTPException as exc:
                if exc.status_code==422: raise
                reason=exc.detail['code'] if isinstance(exc.detail,dict) else 'INVENTORY_UNAVAILABLE'
            checked=True
        result.append({'slotId':row['id'],'startsAt':row['starts_at'],'endsAt':row['ends_at'],'status':row['status'],
            'capacityTotal':row['capacity_total'],'remaining':remaining,'partySize':party_size,'available':reason is None,
            'reason':reason,'inventoryChecked':checked,'isDemo':row['is_demo'] or settings['settings_demo']})
    return {'data':result,'timezone':'Asia/Tokyo','serverTime':utcnow()}


@router.post('/booking-drafts',status_code=201)
def create_draft(body: DraftInput,member: Member,connection: Connection,response: Response):
    lock_member(connection,member)
    row=current_draft(connection,member,True)
    if row:
        response.status_code=200
        return draft_data(row,connection)
    validate_draft(connection,body,member)
    row=connection.execute('INSERT INTO booking_drafts(id,user_id,data) VALUES (%s,%s,%s) RETURNING *',(uuid4(),member,Jsonb(draft_json(body)))).fetchone()
    return draft_data(row,connection)


@router.get('/booking-drafts')
def list_drafts(member: Member,connection: Connection,page: int=Query(0,ge=0,le=100000)):
    row=current_draft(connection,member) if page==0 else None
    return {'data':[draft_data(row,connection)] if row else [],'nextPage':None}


@router.get('/booking-drafts/{draft_id}')
def get_draft(draft_id: UUID,member: Member,connection: Connection):
    return draft_data(owned_draft(connection,draft_id,member),connection)


@router.patch('/booking-drafts/{draft_id}')
def update_draft(draft_id: UUID,body: DraftUpdate,member: Member,connection: Connection):
    lock_member(connection,member)
    row=owned_draft(connection,draft_id,member,True)
    if row['version']!=body.version: error(409,'DRAFT_CONFLICT','草稿已在其他頁面更新，請重新載入再修改。')
    if active_hold(connection,draft_id): error(409,'DRAFT_HELD','草稿已有暫留或付款處理中，請先釋放可取消的暫留。')
    validate_draft(connection,body,member)
    row=connection.execute('UPDATE booking_drafts SET data=%s,version=version+1,updated_at=now() WHERE id=%s RETURNING *',(Jsonb(draft_json(body)),draft_id)).fetchone()
    return draft_data(row,connection)


@router.post('/pricing/quote')
def quote(body: QuoteInput,member: Member,connection: Connection):
    row=owned_draft(connection,body.draft_id,member)
    if row['version']!=body.version: error(409,'DRAFT_CONFLICT','草稿已更新，請重新載入後報價。')
    data=draft_input(row)
    settings,slot,plans=validate_draft(connection,data,member,True)
    if data.store_id is None or settings is None or slot is None:
        error(422,'INCOMPLETE_DRAFT','請先完成門市與場次選擇。')
    if remaining_capacity(connection,slot)<len(data.guests): error(409,'SLOT_FULL','接待名額不足以容納全員，請更換場次。')
    match_inventory(connection,data.store_id,slot,data.guests,plans,settings)
    snapshot,digest=price_snapshot(data,settings,slot,plans)
    saved=connection.execute('''INSERT INTO booking_quotes(id,user_id,draft_id,draft_version,pricing_hash,line_items,total)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(uuid4(),member,row['id'],row['version'],digest,Jsonb(snapshot),snapshot['total'])).fetchone()
    assert saved is not None
    return {'quoteToken':saved['id'],'draftId':row['id'],'version':row['version'],'expiresAt':saved['expires_at'],
        'serverTime':utcnow(),**snapshot,'inventoryReserved':False}


def expire_holds(connection,store_id=None):
    if store_id:
        stores=[{'id':store_id}]
    else:
        stores=connection.execute("SELECT id FROM stores WHERE id IN (SELECT store_id FROM availability_holds WHERE status='HELD' AND expires_at<=now()) ORDER BY id FOR UPDATE").fetchall()
    for store in stores:
        expired=connection.execute("UPDATE availability_holds SET status='EXPIRED' WHERE store_id=%s AND status='HELD' AND expires_at<=now() RETURNING id",(store['id'],)).fetchall()
        if expired: connection.execute("UPDATE inventory_allocations SET status='RELEASED' WHERE hold_id=ANY(%s) AND status='HELD'",([r['id'] for r in expired],))


def cleanup_booking_holds():
    with connect() as connection:
        expire_holds(connection)
        connection.execute("DELETE FROM inventory_allocations WHERE hold_id IN (SELECT id FROM availability_holds WHERE status IN ('EXPIRED','RELEASED') AND created_at<now()-interval '7 days')")
        connection.execute("DELETE FROM availability_holds WHERE status IN ('EXPIRED','RELEASED') AND created_at<now()-interval '7 days'")
        connection.execute('DELETE FROM booking_quotes q WHERE expires_at<now() AND NOT EXISTS(SELECT 1 FROM availability_holds h WHERE h.quote_id=q.id)')
        connection.execute('''DELETE FROM booking_drafts d WHERE expires_at<now()
            AND NOT EXISTS(SELECT 1 FROM availability_holds h WHERE h.draft_id=d.id)
            AND NOT EXISTS(SELECT 1 FROM booking_quotes q WHERE q.draft_id=d.id)''')


@router.post('/availability/holds',status_code=201)
def create_hold(body: HoldInput,member: Member,connection: Connection,response: Response,
                idempotency_key: Annotated[UUID,Header(alias='Idempotency-Key')],identity=Depends(current_identity)):
    if not identity.get('email_verified'): error(403,'EMAIL_VERIFICATION_REQUIRED','請先完成 Email 驗證並重新整理登入狀態。')
    lock_member(connection,member)
    digest=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    old=connection.execute('SELECT * FROM availability_holds WHERE user_id=%s AND idempotency_key=%s',(member,idempotency_key)).fetchone()
    if old:
        if old['request_hash']!=digest: error(409,'IDEMPOTENCY_CONFLICT','同一次暫留請求內容不同，請重新確認。')
        response.status_code=200;return hold_data(old)
    row=owned_draft(connection,body.draft_id,member)
    data=draft_input(row)
    if not data.store_id: error(422,'INCOMPLETE_DRAFT','請先完成門市選擇。')
    connection.execute('SELECT id FROM stores WHERE id=%s FOR UPDATE',(data.store_id,)).fetchone()
    row=owned_draft(connection,body.draft_id,member,True)
    if active_hold(connection,row['id']): error(409,'DRAFT_HELD','這份草稿已有有效暫留，請恢復原暫留。')
    expire_holds(connection,data.store_id)
    quoted=connection.execute('SELECT * FROM booking_quotes WHERE id=%s AND user_id=%s AND draft_id=%s FOR SHARE',(body.quote_token,member,row['id'])).fetchone()
    if not quoted or quoted['expires_at']<=utcnow() or quoted['draft_version']!=row['version']:
        error(409,'QUOTE_EXPIRED','報價已到期或草稿已變更，請重新報價。')
    settings,slot,plans=validate_draft(connection,data,member,True,True)
    snapshot,pricing_hash=price_snapshot(data,settings,slot,plans)
    if pricing_hash!=quoted['pricing_hash']: error(409,'PRICE_CHANGED','價格或租借規則已變更，請重新查看報價再確認。')
    if remaining_capacity(connection,slot)<len(data.guests): error(409,'SLOT_FULL','接待名額不足以容納全員，整筆未暫留。')
    allocations=match_inventory(connection,data.store_id,slot,data.guests,plans,settings,True)
    held=connection.execute('''INSERT INTO availability_holds
        (id,user_id,draft_id,draft_version,quote_id,store_id,slot_id,party_size,idempotency_key,request_hash,total,snapshot)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (uuid4(),member,row['id'],row['version'],quoted['id'],data.store_id,slot['id'],len(data.guests),idempotency_key,digest,snapshot['total'],Jsonb(snapshot))).fetchone()
    for index,inventory_id,start,rental_end,cleaning_end in allocations:
        connection.execute('''INSERT INTO inventory_allocations(id,inventory_id,hold_id,guest_index,rental_starts_at,rental_ends_at,cleaning_ends_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',(uuid4(),inventory_id,held['id'],index,start,rental_end,cleaning_end))
    return hold_data(held)


@router.get('/availability/holds/{hold_id}')
def get_hold(hold_id: UUID,member: Member,connection: Connection):
    row=connection.execute('SELECT * FROM availability_holds WHERE id=%s AND user_id=%s',(hold_id,member)).fetchone()
    if not row: error(404,'HOLD_NOT_FOUND','找不到這筆暫留。')
    return hold_data(row)


@router.delete('/availability/holds/{hold_id}')
def release_hold(hold_id: UUID,member: Member,connection: Connection):
    lock_member(connection,member)
    row=connection.execute('SELECT * FROM availability_holds WHERE id=%s AND user_id=%s',(hold_id,member)).fetchone()
    if not row: error(404,'HOLD_NOT_FOUND','找不到這筆暫留。')
    connection.execute('SELECT id FROM stores WHERE id=%s FOR UPDATE',(row['store_id'],)).fetchone()
    row=connection.execute('SELECT * FROM availability_holds WHERE id=%s FOR UPDATE',(hold_id,)).fetchone()
    if row['status'] in ('PAYMENT_PENDING','RESERVED'): error(409,'PAYMENT_IN_PROGRESS','付款待確認或正式保留不可由此釋放。')
    connection.execute("UPDATE availability_holds SET status=CASE WHEN status='HELD' THEN 'RELEASED' ELSE status END WHERE id=%s",(hold_id,))
    connection.execute("UPDATE inventory_allocations SET status='RELEASED' WHERE hold_id=%s AND status='HELD'",(hold_id,))
    return {'ok':True,'bookingConfirmed':False}
