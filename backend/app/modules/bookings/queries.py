from app.core.errors import error
from app.modules.bookings.rules import in_window
from datetime import timedelta


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


def active_hold(connection,draft_id):
    return connection.execute("""SELECT * FROM availability_holds WHERE draft_id=%s AND
        ((status='HELD' AND expires_at>now()) OR status IN ('PAYMENT_PENDING','RESERVED')) ORDER BY created_at DESC LIMIT 1""",(draft_id,)).fetchone()


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


def remaining_capacity(connection,slot):
    used=connection.execute("""SELECT COALESCE(sum(party_size),0) AS used FROM availability_holds
        WHERE slot_id=%s AND ((status='HELD' AND expires_at>now()) OR status IN ('PAYMENT_PENDING','RESERVED'))""",(slot['id'],)).fetchone()['used']
    return max(0,slot['capacity_total']-used)


AVAILABLE_INVENTORY = '''i.status='AVAILABLE' AND NOT EXISTS
    (SELECT 1 FROM inventory_allocations a JOIN availability_holds h ON h.id=a.hold_id
        WHERE a.inventory_id=i.id AND a.status IN ('HELD','RESERVED')
        AND ((h.status='HELD' AND h.expires_at>now()) OR h.status IN ('PAYMENT_PENDING','RESERVED'))
        AND a.rental_starts_at<r.cleaning_end AND a.cleaning_ends_at>r.starts_at)'''


def inventory_candidates(connection, store_id, slots, guests, plans, settings):
    requests = [(slot['id'], index, guest.kimono_id, slot['starts_at'],
                 slot['starts_at']+timedelta(minutes=plan['duration_minutes']+settings['cleaning_minutes']))
                for slot in slots for index, (guest, plan) in enumerate(zip(guests, plans))]
    if not requests:
        return {}
    values = ','.join(['(%s::uuid,%s::int,%s::uuid,%s::timestamptz,%s::timestamptz)']*len(requests))
    rows = connection.execute(f'''SELECT r.slot_id,r.guest_index,i.id FROM (VALUES {values})
        AS r(slot_id,guest_index,kimono_id,starts_at,cleaning_end)
        JOIN inventory_items i ON i.store_id=%s AND i.kimono_id=r.kimono_id
        WHERE {AVAILABLE_INVENTORY} ORDER BY i.code''',
        [value for request in requests for value in request]+[store_id]).fetchall()
    candidates = {}
    for row in rows:
        candidates.setdefault((row['slot_id'], row['guest_index']), []).append(row['id'])
    return candidates


def match_inventory(connection,store_id,slot,guests,plans,settings,lock=False,candidates=None):
    if not lock and candidates is None:
        candidates = inventory_candidates(connection, store_id, [slot], guests, plans, settings)
    used=[];allocations=[]
    for index,(guest,plan) in enumerate(zip(guests,plans)):
        rental_end=slot['starts_at']+timedelta(minutes=plan['duration_minutes'])
        cleaning_end=rental_end+timedelta(minutes=settings['cleaning_minutes'])
        if lock:
            row=connection.execute(f'''SELECT i.id FROM inventory_items i
                CROSS JOIN (SELECT %s::timestamptz AS starts_at,%s::timestamptz AS cleaning_end) r
                WHERE i.store_id=%s AND i.kimono_id=%s AND NOT(i.id=ANY(%s::uuid[]))
                AND {AVAILABLE_INVENTORY} ORDER BY i.code LIMIT 1 FOR UPDATE OF i''',
                (slot['starts_at'],cleaning_end,store_id,guest.kimono_id,used)).fetchone()
        else:
            inventory_id = next((value for value in candidates.get((slot['id'], index), []) if value not in used), None)
            row = {'id': inventory_id} if inventory_id else None
        if not row: error(409,'INVENTORY_UNAVAILABLE',f'旅客 {index+1} 的和服在租借與整備期間內庫存不足，整筆未暫留。')
        used.append(row['id']);allocations.append((index,row['id'],slot['starts_at'],rental_end,cleaning_end))
    return allocations


def expire_holds(connection,store_id=None):
    if store_id:
        stores=[{'id':store_id}]
    else:
        stores=connection.execute("SELECT id FROM stores WHERE id IN (SELECT store_id FROM availability_holds WHERE status='HELD' AND expires_at<=now()) ORDER BY id FOR UPDATE").fetchall()
    for store in stores:
        expired=connection.execute("UPDATE availability_holds SET status='EXPIRED' WHERE store_id=%s AND status='HELD' AND expires_at<=now() RETURNING id",(store['id'],)).fetchall()
        if expired: connection.execute("UPDATE inventory_allocations SET status='RELEASED' WHERE hold_id=ANY(%s) AND status='HELD'",([r['id'] for r in expired],))
