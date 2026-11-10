"""One durable payment attempt per hold, including timeouts and retries."""
import os
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.core.errors import error
from app.core.database import connect
from app.integrations import tappay_service as tappay
from app.modules.bookings.contact import require_contact
from app.modules.bookings.queries import lock_member
from app.modules.bookings.rules import utcnow

POLICY_VERSION = 'cancellation-7days-v1'


def label(value):
    return value.get('zh-Hant',next(iter(value.values()),'')) if isinstance(value,dict) else value


def order_data(connection, row):
    booking = connection.execute('SELECT booking_no FROM bookings WHERE order_no=%s', (row['order_no'],)).fetchone()
    return {'orderNo':row['order_no'], 'holdId':row['hold_id'], 'paymentStatus':row['status'],
            'bookingNo':booking['booking_no'] if booking else None, 'total':row['total'], 'currency':'TWD', 'environment':'sandbox'}


def owned_order(connection, order_no, member):
    row=connection.execute('SELECT * FROM payment_orders WHERE order_no=%s AND user_id=%s', (order_no,member)).fetchone()
    if not row: error(404,'ORDER_NOT_FOUND','找不到本人訂單。')
    return row


def submit(connection, member, identity, body, key):
    if not identity.get('email_verified'): error(403,'EMAIL_VERIFICATION_REQUIRED','請先完成 Email 驗證。')
    if not tappay.configured(): error(503,'PAYMENT_UNAVAILABLE','Sandbox 金流設定尚未完成。')
    lock_member(connection,member)
    previous=connection.execute('SELECT * FROM payment_orders WHERE user_id=%s AND idempotency_key=%s',(member,key)).fetchone()
    if previous:
        if previous['hold_id']!=body.hold_id or previous['quote_id']!=body.quote_token:
            error(409,'IDEMPOTENCY_CONFLICT','付款識別碼已用於其他內容。')
        return order_data(connection,previous)
    hold=connection.execute('SELECT * FROM availability_holds WHERE id=%s AND user_id=%s FOR UPDATE',(body.hold_id,member)).fetchone()
    if not hold: error(404,'HOLD_NOT_FOUND','找不到本人暫留。')
    previous=connection.execute('SELECT * FROM payment_orders WHERE hold_id=%s',(body.hold_id,)).fetchone()
    if previous:
        if previous['quote_id']!=body.quote_token: error(409,'QUOTE_MISMATCH','報價與原付款不符。')
        return order_data(connection,previous)
    if body.policy_version!=POLICY_VERSION or not body.accepted_policy: error(422,'POLICY_REQUIRED','請確認目前取消政策。')
    if hold['status']!='HELD' or hold['expires_at']<=utcnow(): error(409,'HOLD_EXPIRED','暫留已失效，請重新報價。')
    if hold['quote_id']!=body.quote_token: error(409,'QUOTE_MISMATCH','報價與暫留不符。')
    if hold['total']<=0: error(422,'INVALID_AMOUNT','付款金額須大於零。')
    draft=connection.execute('SELECT * FROM booking_drafts WHERE id=%s',(hold['draft_id'],)).fetchone()
    require_contact(connection,draft)
    data=draft['data']
    contact={'name':data['contactName'],'email':data['contactEmail'],'phone_number':data['contactPhone']}
    if len(contact['name'])>40 or len(contact['email'])>40 or len(contact['phone_number'])>16:
        error(422,'CONTACT_TOO_LONG','付款姓名與 Email 最多 40 字，電話最多 16 字，請釋放暫留後修正。')
    guests=[]
    for guest in data['guests']:
        garment=connection.execute('SELECT name FROM kimonos WHERE id=%s',(guest['kimonoId'],)).fetchone()
        belt=connection.execute('SELECT name FROM accessories WHERE id=%s',(guest['accessoryIds'][0],)).fetchone() if guest.get('accessoryIds') else None
        guests.append({**guest,'kimonoName':label(garment['name']) if garment else '和服','beltName':label(belt['name']) if belt else None})
    snapshot={**hold['snapshot'],'guests':guests}
    order_no='KT'+uuid4().hex.upper();bank_id=uuid4().hex[:19].upper()
    row=connection.execute('''INSERT INTO payment_orders
        (order_no,user_id,hold_id,idempotency_key,quote_id,total,merchant_id,bank_transaction_id,policy_version,contact,snapshot)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (order_no,member,hold['id'],key,hold['quote_id'],hold['total'],os.environ['TAPPAY_MERCHANT_ID'],bank_id,
         POLICY_VERSION,Jsonb(contact),Jsonb(snapshot))).fetchone()
    connection.execute("UPDATE availability_holds SET status='PAYMENT_PENDING' WHERE id=%s",(hold['id'],))
    # Commit before any external side effect, so a crashed request can always be recovered.
    connection.commit()
    try: result=tappay.pay_by_prime(body.prime,order_no,row['total'],contact,bank_id)
    except (tappay.TapPayRequestError,tappay.TapPayConfigurationError): return order_data(connection,row)
    trade_id=result.get('rec_trade_id')
    if isinstance(trade_id,str) and 0<len(trade_id)<=30:
        connection.execute('UPDATE payment_orders SET rec_trade_id=%s WHERE order_no=%s',(trade_id,order_no))
    connection.commit()
    reconcile(connection,order_no)
    return order_data(connection,owned_order(connection,order_no,member))


def verified_status(order, record):
    expected={'merchant_id':order['merchant_id'],'bank_transaction_id':order['bank_transaction_id'],'currency':'TWD','amount':order['total']}
    if any(record.get(k)!=v for k,v in expected.items()): return 'REVIEW_REQUIRED'
    if record.get('order_number',order['order_no'])!=order['order_no']: return 'REVIEW_REQUIRED'
    if not isinstance(record.get('rec_trade_id'),str) or not record['rec_trade_id']: return 'REVIEW_REQUIRED'
    if order['rec_trade_id'] and record['rec_trade_id']!=order['rec_trade_id']: return 'REVIEW_REQUIRED'
    return {0:'AUTHORIZED',1:'PAID',-1:'FAILED',5:'FAILED',4:'PAYMENT_PENDING'}.get(record.get('record_status'),'REVIEW_REQUIRED')


def reconcile(connection, order_no):
    row=connection.execute('''UPDATE payment_orders SET checked_at=now() WHERE order_no=%s
        AND status IN ('PAYMENT_PENDING','AUTHORIZED') AND
        (checked_at IS NULL OR checked_at<now()-interval '45 seconds') RETURNING *''',(order_no,)).fetchone()
    connection.commit()
    if not row: return
    try: result=tappay.records(row)
    except (tappay.TapPayRequestError,tappay.TapPayConfigurationError): return
    records=result.get('trade_records')
    if result.get('status') not in (0,2) or not isinstance(records,list) or not records: return
    status=verified_status(row,records[0]) if len(records)==1 and isinstance(records[0],dict) else 'REVIEW_REQUIRED'
    lock_member(connection,row['user_id'])
    held=connection.execute('SELECT * FROM availability_holds WHERE id=%s',(row['hold_id'],)).fetchone()
    connection.execute('SELECT id FROM stores WHERE id=%s FOR UPDATE',(held['store_id'],))
    held=connection.execute('SELECT * FROM availability_holds WHERE id=%s FOR UPDATE',(row['hold_id'],)).fetchone()
    current=connection.execute('SELECT * FROM payment_orders WHERE order_no=%s FOR UPDATE',(order_no,)).fetchone()
    if current['status'] not in ('PAYMENT_PENDING','AUTHORIZED'): return
    if current['status']=='AUTHORIZED' and status in ('FAILED','PAYMENT_PENDING'): status='REVIEW_REQUIRED'
    if status in ('AUTHORIZED','PAID'):
        count=connection.execute("SELECT count(*) AS n FROM inventory_allocations WHERE hold_id=%s AND status IN ('HELD','RESERVED')",(held['id'],)).fetchone()['n']
        if held['status'] not in ('PAYMENT_PENDING','RESERVED') or count!=held['party_size']: status='REFUND_REQUIRED'
        else:
            connection.execute("UPDATE availability_holds SET status='RESERVED' WHERE id=%s",(held['id'],))
            connection.execute("UPDATE inventory_allocations SET status='RESERVED' WHERE hold_id=%s",(held['id'],))
            connection.execute('INSERT INTO bookings(booking_no,order_no,user_id) VALUES (%s,%s,%s) ON CONFLICT(order_no) DO NOTHING',('KB'+uuid4().hex.upper(),order_no,row['user_id']))
    elif status=='FAILED':
        connection.execute("UPDATE availability_holds SET status='RELEASED' WHERE id=%s AND status='PAYMENT_PENDING'",(held['id'],))
        connection.execute("UPDATE inventory_allocations SET status='RELEASED' WHERE hold_id=%s AND status='HELD'",(held['id'],))
    rec=records[0].get('rec_trade_id') if len(records)==1 and isinstance(records[0],dict) else None
    connection.execute('UPDATE payment_orders SET status=%s,rec_trade_id=COALESCE(rec_trade_id,%s),updated_at=now() WHERE order_no=%s',(status,rec if status!='REVIEW_REQUIRED' else None,order_no))
    connection.commit()


def booking_data(row):
    s=row['snapshot']
    return {'bookingNo':row['booking_no'],'orderNo':row['order_no'],'status':row['status'],
            'paymentStatus':row['payment_status'],'total':row['total'],'currency':'TWD','environment':'sandbox',
            'storeName':s['storeName'],'startTime':s['startsAt'],'date':s['startsAt'],
            'lineItems':s['lineItems'],'contact':row['contact'],
            'guests':[{'role':'MALE' if g['guestType']=='ADULT_MALE' else 'FEMALE',
                       'kimonoName':g['kimonoName'],'beltName':g.get('beltName')}
                      for g in s['guests']]}


def bookings(connection,member,booking_no=None,page=0):
    rows=connection.execute('''SELECT b.*,o.status AS payment_status,o.total,o.snapshot,o.contact FROM bookings b
        JOIN payment_orders o USING(order_no) WHERE b.user_id=%s'''+(' AND b.booking_no=%s' if booking_no else '')+
        ' ORDER BY b.created_at DESC LIMIT 12 OFFSET %s',(member,booking_no,page*12) if booking_no else (member,page*12)).fetchall()
    if booking_no:
        if not rows: error(404,'BOOKING_NOT_FOUND','找不到本人預約。')
        return booking_data(rows[0])
    return {'data':[booking_data(r) for r in rows]}


def reconcile_batch():
    with connect() as connection:
        rows=connection.execute("SELECT order_no FROM payment_orders WHERE status IN ('PAYMENT_PENDING','AUTHORIZED') AND (checked_at IS NULL OR checked_at<now()-interval '45 seconds') ORDER BY checked_at NULLS FIRST LIMIT 20").fetchall()
    for row in rows:
        with connect() as connection: reconcile(connection,row['order_no'])
