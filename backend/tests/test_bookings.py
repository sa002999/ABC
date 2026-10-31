import os
import unittest
from datetime import datetime,timedelta,timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.modules.accounts.dependencies import current_identity
from app.modules.bookings.queries import expire_holds
from app.modules.bookings.rules import in_window
from app.core.database import connect, get_connection
from commands.seeds.catalog import identifier


class BookingInputTests(unittest.TestCase):
    def test_time_boundaries_and_private_routes(self):
        now=datetime(2026,10,17,tzinfo=timezone.utc)
        for delta,expected in [(timedelta(hours=24),True),(timedelta(hours=24,seconds=-1),False),(timedelta(days=90),True),(timedelta(days=90,seconds=1),False)]:
            self.assertEqual(in_window(now+delta,now),expected)
        with TestClient(app) as client:
            for method,path in [('GET','/api/booking-drafts'),('POST','/api/booking-drafts'),('GET','/api/booking-drafts/'+str(uuid4())),
                ('POST','/api/pricing/quote'),('POST','/api/availability/holds'),('GET','/api/availability/holds/'+str(uuid4()))]:
                response=client.request(method,path,json={} if method=='POST' else None)
                self.assertEqual(response.status_code,401)
                self.assertEqual(response.headers['cache-control'],'no-store')


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class BookingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection=connect();self.transaction=self.connection.transaction(force_rollback=True);self.transaction.__enter__()
        app.dependency_overrides[get_connection]=lambda:self.connection
        self.identity={'uid':'booking-test-'+str(uuid4()),'email':'booking-test@example.com','email_verified':True}
        app.dependency_overrides[current_identity]=lambda:self.identity
        self.client=TestClient(app);self.client.put('/api/account',json={}).raise_for_status()
        self.store=self.connection.execute("SELECT id FROM stores WHERE slug='demo-kyoto'").fetchone()['id']
        self.slot=self.connection.execute("SELECT * FROM availability_slots WHERE store_id=%s AND starts_at>now()+interval '30 days' AND status='OPEN' ORDER BY starts_at LIMIT 1",(self.store,)).fetchone()
        self.assertIsNotNone(self.slot,'Run seed-booking-demo first')

    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.transaction.__exit__(None,None,None);self.connection.close()

    def body(self,count=1,slot=None):
        return {'storeId':str(self.store),'slotId':str(slot or self.slot['id']),
            'guests':[{'guestType':'ADULT_FEMALE','planId':'30000000-0000-4000-8000-000000000013' if count>1 else '30000000-0000-4000-8000-000000000011','kimonoId':str(identifier('kimono','RKH0002'))} for _ in range(count)],
            'contactName':'測試聯絡人','contactEmail':'test@example.com','contactPhone':'+886912345678'}

    def draft(self,body=None):
        response=self.client.post('/api/booking-drafts',json=body or self.body());self.assertIn(response.status_code,(200,201),response.text);return response.json()

    def test_single_draft_reused_without_overwriting_or_extending_expiry(self):
        first=self.draft()
        resumed=self.draft({**self.body(),'contactName':'不可覆蓋原草稿'})
        self.assertEqual(resumed['draftId'],first['draftId'])
        self.assertEqual(resumed['data'],first['data'])
        self.assertEqual(resumed['expiresAt'],first['expiresAt'])
        self.assertEqual(len(self.client.get('/api/booking-drafts').json()['data']),1)
        self.connection.execute("UPDATE booking_drafts SET expires_at=now()-interval '1 second' WHERE id=%s",(first['draftId'],))
        self.assertEqual(self.client.get('/api/booking-drafts').json()['data'],[])
        self.assertEqual(self.client.get('/api/booking-drafts/'+first['draftId']).status_code,404)
        self.assertNotEqual(self.draft()['draftId'],first['draftId'])

    def quote(self,draft):
        return self.client.post('/api/pricing/quote',json={'draftId':draft['draftId'],'version':draft['version']})

    def hold(self,draft,quote,key=None):
        return self.client.post('/api/availability/holds',json={'draftId':draft['draftId'],'quoteToken':quote['quoteToken']},headers={'Idempotency-Key':key or str(uuid4())})

    def test_guest_count_contacts_versions_and_owner(self):
        for count in [0,4]:
            body=self.body();body['guests']=[body['guests'][0]]*count
            result=self.client.post('/api/booking-drafts',json=body)
            self.assertEqual(result.status_code,422);self.assertEqual(result.json()['error']['code'],'INVALID_GUEST_COUNT')
        self.assertEqual(self.client.post('/api/booking-drafts',json={**self.body(),'partySize':2}).status_code,422)
        self.assertEqual(self.client.post('/api/booking-drafts',json={**self.body(),'total':1}).status_code,422)
        draft=self.draft();path='/api/booking-drafts/'+draft['draftId']
        updated=self.client.patch(path,json={**draft['data'],'version':draft['version'],'contactName':'已更新'})
        self.assertEqual(updated.status_code,200,updated.text)
        self.assertEqual(self.client.patch(path,json={**draft['data'],'version':draft['version']}).status_code,409)
        self.identity['uid']='other-booking-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.quote(draft).status_code,404)
        self.assertEqual(self.client.get('/api/booking-drafts').json()['data'],[])

    def test_quote_and_hold_atomicity_replay_and_database_overlap(self):
        first=self.draft();second=self.draft()
        self.assertEqual(first['draftId'],second['draftId'])
        q1=self.quote(first);q2=self.quote(second)
        self.assertEqual(q1.status_code,200,q1.text);self.assertEqual(q2.status_code,200,q2.text)
        self.assertEqual(q1.json()['total'],1500);self.assertFalse(q1.json()['inventoryReserved'])
        count=self.connection.execute('SELECT count(*) AS n FROM inventory_allocations WHERE hold_id IN (SELECT id FROM availability_holds WHERE draft_id=%s)',(first['draftId'],)).fetchone()['n']
        self.assertEqual(count,0)
        key=str(uuid4());held=self.hold(first,q1.json(),key)
        self.assertEqual(held.status_code,201,held.text)
        replay=self.hold(first,q1.json(),key)
        self.assertEqual(replay.status_code,200);self.assertEqual(replay.json()['holdId'],held.json()['holdId']);self.assertEqual(replay.json()['expiresAt'],held.json()['expiresAt'])
        blocked=self.hold(second,q2.json());self.assertEqual(blocked.status_code,409,blocked.text)
        self.assertEqual(blocked.json()['error']['code'],'DRAFT_HELD')
        self.assertEqual(self.client.patch('/api/booking-drafts/'+first['draftId'],json={**first['data'],'version':first['version']}).status_code,409)
        row=self.connection.execute('SELECT * FROM inventory_allocations WHERE hold_id=%s',(held.json()['holdId'],)).fetchone()
        with self.assertRaises(psycopg.errors.ExclusionViolation):
            with self.connection.transaction():
                self.connection.execute('''INSERT INTO inventory_allocations(id,inventory_id,hold_id,guest_index,rental_starts_at,rental_ends_at,cleaning_ends_at)
                    VALUES (%s,%s,%s,1,%s,%s,%s)''',(uuid4(),row['inventory_id'],row['hold_id'],row['rental_starts_at'],row['rental_ends_at'],row['cleaning_ends_at']))
        self.assertFalse(held.json()['bookingConfirmed']);self.assertFalse(held.json()['paymentAvailable'])

    def test_whole_party_capacity_and_inventory(self):
        self.connection.execute("UPDATE inventory_items SET status='MAINTENANCE' WHERE kimono_id=%s AND code<>%s",(identifier('kimono','RKH0002'),'DEMO-RKH0002-001'))
        bad=self.draft(self.body(2))
        self.assertEqual(self.quote(bad).status_code,409)
        self.connection.execute("UPDATE inventory_items SET status='AVAILABLE' WHERE kimono_id=%s",(identifier('kimono','RKH0002'),))
        updated=self.client.patch('/api/booking-drafts/'+bad['draftId'],json={**self.body(3),'version':bad['version']})
        self.assertEqual(updated.status_code,200,updated.text);good=updated.json()
        quoted=self.quote(good);self.assertEqual(quoted.status_code,200,quoted.text)
        self.assertEqual(quoted.json()['total'],4200)
        self.connection.execute('UPDATE availability_slots SET capacity_total=2 WHERE id=%s',(self.slot['id'],))
        self.assertEqual(self.hold(good,quoted.json()).status_code,409)
        self.assertEqual(self.connection.execute('SELECT count(*) AS n FROM availability_holds WHERE draft_id=%s',(good['draftId'],)).fetchone()['n'],0)

    def test_expiry_release_and_pending_payment_protection(self):
        first=self.draft();quoted=self.quote(first).json();held=self.hold(first,quoted).json()
        self.connection.execute("UPDATE availability_holds SET expires_at=now()-interval '1 second' WHERE id=%s",(held['holdId'],))
        self.assertEqual(self.client.get('/api/availability/holds/'+held['holdId']).json()['status'],'EXPIRED')
        second=self.draft();q2=self.quote(second);self.assertEqual(q2.status_code,200,q2.text)
        h2=self.hold(second,q2.json());self.assertEqual(h2.status_code,201,h2.text)
        self.connection.execute("UPDATE availability_holds SET status='PAYMENT_PENDING',expires_at=now()-interval '1 second' WHERE id=%s",(h2.json()['holdId'],))
        expire_holds(self.connection,self.store)
        self.assertEqual(self.client.get('/api/availability/holds/'+h2.json()['holdId']).json()['status'],'PAYMENT_PENDING')
        self.assertEqual(self.client.delete('/api/availability/holds/'+h2.json()['holdId']).status_code,409)
        third=self.draft();self.assertEqual(self.hold(third,self.quote(third).json()).status_code,409)

    def test_price_change_email_and_release(self):
        draft=self.draft();quoted=self.quote(draft).json()
        self.identity['email_verified']=False
        self.assertEqual(self.hold(draft,quoted).status_code,403)
        self.identity['email_verified']=True
        self.connection.execute('UPDATE plans SET base_price=base_price+100 WHERE id=%s',(UUID('30000000-0000-4000-8000-000000000011'),))
        changed=self.hold(draft,quoted);self.assertEqual(changed.status_code,409);self.assertEqual(changed.json()['error']['code'],'PRICE_CHANGED')
        q2=self.quote(draft).json();self.assertEqual(q2['total'],1600)
        held=self.hold(draft,q2).json()
        self.assertEqual(self.client.delete('/api/availability/holds/'+held['holdId']).status_code,200)
        self.assertEqual(self.client.get('/api/availability/holds/'+held['holdId']).json()['status'],'RELEASED')

    def test_cleaning_period_blocks_later_rentals(self):
        self.connection.execute("UPDATE inventory_items SET status='MAINTENANCE' WHERE kimono_id=%s AND code<>%s",(identifier('kimono','RKH0002'),'DEMO-RKH0002-001'))
        self.connection.execute('UPDATE plans SET duration_minutes=60 WHERE id=%s',(UUID('30000000-0000-4000-8000-000000000011'),))
        start=self.slot['starts_at']
        ids=[]
        for hours in (2,3):
            slot_id=uuid4();ids.append(slot_id)
            self.connection.execute('INSERT INTO availability_slots(id,store_id,starts_at,ends_at,capacity_total,is_demo) VALUES (%s,%s,%s,%s,3,true)',(slot_id,self.store,start+timedelta(hours=hours),start+timedelta(hours=hours,minutes=30)))
        first=self.draft();held=self.hold(first,self.quote(first).json());self.assertEqual(held.status_code,201,held.text)
        self.identity['uid']='other-cleaning-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        overlapping=self.draft(self.body(slot=ids[0]));self.assertEqual(self.quote(overlapping).status_code,409)
        updated=self.client.patch('/api/booking-drafts/'+overlapping['draftId'],json={**self.body(slot=ids[1]),'version':overlapping['version']})
        self.assertEqual(updated.status_code,200,updated.text);boundary=updated.json();q=self.quote(boundary);self.assertEqual(q.status_code,200,q.text)
        self.assertEqual(self.hold(boundary,q.json()).status_code,201)


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class BookingConcurrencyTests(unittest.TestCase):
    def test_two_members_cannot_hold_the_same_physical_item(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from fastapi import Request
        store,kimono,plan,slot,inventory=[uuid4() for _ in range(5)]
        tag=uuid4().hex
        identities={key:{'uid':'booking-race-'+tag+'-'+key,'email':'race@example.com','email_verified':True} for key in ('first','second')}
        start=datetime.now(ZoneInfo('Asia/Tokyo')).replace(hour=9,minute=0,second=0,microsecond=0)+timedelta(days=30)
        def identity(request: Request): return identities[request.headers['x-test-member']]
        try:
            with connect() as c:
                c.execute("INSERT INTO stores(id,slug,city,name,is_demo) VALUES (%s,%s,'KYOTO','{\"zh-Hant\":\"並行測試門市（自動清除）\"}',true)",(store,'test-'+tag))
                c.execute("INSERT INTO store_booking_settings(store_id,cleaning_minutes,closes_at,is_demo) VALUES (%s,120,'19:00',true)",(store,))
                c.execute("INSERT INTO kimonos(id,sku,name,kimono_type,is_demo) VALUES (%s,%s,'{\"zh-Hant\":\"測試和服\"}','KIMONO',true)",(kimono,'TEST-'+tag))
                c.execute("INSERT INTO plans(id,slug,kimono_id,name,summary,description,audience,duration_minutes,base_price,is_demo) VALUES (%s,%s,%s,'{\"zh-Hant\":\"測試方案\"}','{}','{}',ARRAY['SOLO'],60,1000,true)",(plan,'test-'+tag,kimono))
                c.execute('INSERT INTO plan_stores(plan_id,store_id) VALUES (%s,%s)',(plan,store))
                c.execute('INSERT INTO plan_kimonos(plan_id,kimono_id) VALUES (%s,%s)',(plan,kimono))
                c.execute('INSERT INTO availability_slots(id,store_id,starts_at,ends_at,capacity_total,is_demo) VALUES (%s,%s,%s,%s,2,true)',(slot,store,start,start+timedelta(minutes=30)))
                c.execute("INSERT INTO inventory_items(id,code,store_id,kimono_id,is_demo) VALUES (%s,%s,%s,%s,true)",(inventory,'TEST-'+tag,store,kimono))
            app.dependency_overrides[current_identity]=identity
            requests=[]
            with TestClient(app) as client:
                for key in identities:
                    headers={'x-test-member':key}
                    client.put('/api/account',json={},headers=headers).raise_for_status()
                    body={'storeId':str(store),'slotId':str(slot),'guests':[{'planId':str(plan),'kimonoId':str(kimono)}],
                        'contactName':'測試','contactEmail':'race@example.com','contactPhone':'0912345678'}
                    draft=client.post('/api/booking-drafts',json=body,headers=headers);draft.raise_for_status()
                    quoted=client.post('/api/pricing/quote',json={'draftId':draft.json()['draftId'],'version':draft.json()['version']},headers=headers);quoted.raise_for_status()
                    requests.append((headers,{'draftId':draft.json()['draftId'],'quoteToken':quoted.json()['quoteToken']}))
            barrier=Barrier(2)
            def reserve(request):
                headers,body=request
                with TestClient(app) as client:
                    barrier.wait(timeout=15)
                    return client.post('/api/availability/holds',json=body,headers={**headers,'Idempotency-Key':str(uuid4())})
            with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(reserve,requests))
            self.assertEqual(sorted(r.status_code for r in responses),[201,409],[r.text for r in responses])
            with connect() as c:
                self.assertEqual(c.execute("SELECT count(*) AS n FROM inventory_allocations WHERE inventory_id=%s AND status='HELD'",(inventory,)).fetchone()['n'],1)
        finally:
            app.dependency_overrides.clear()
            with connect() as c:
                uids=[v['uid'] for v in identities.values()]
                c.execute('DELETE FROM inventory_allocations WHERE inventory_id=%s',(inventory,))
                c.execute('DELETE FROM availability_holds WHERE store_id=%s',(store,))
                c.execute('DELETE FROM booking_quotes WHERE user_id IN (SELECT id FROM users WHERE firebase_uid=ANY(%s))',(uids,))
                c.execute('DELETE FROM booking_drafts WHERE user_id IN (SELECT id FROM users WHERE firebase_uid=ANY(%s))',(uids,))
                c.execute('DELETE FROM availability_slots WHERE store_id=%s',(store,))
                c.execute('DELETE FROM inventory_items WHERE id=%s',(inventory,))
                c.execute('DELETE FROM plan_stores WHERE plan_id=%s',(plan,))
                c.execute('DELETE FROM plan_kimonos WHERE plan_id=%s',(plan,))
                c.execute('DELETE FROM plans WHERE id=%s',(plan,))
                c.execute('DELETE FROM kimonos WHERE id=%s',(kimono,))
                c.execute('DELETE FROM store_booking_settings WHERE store_id=%s',(store,))
                c.execute('DELETE FROM stores WHERE id=%s',(store,))
                c.execute('DELETE FROM users WHERE firebase_uid=ANY(%s)',(uids,))
