import os
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from app import app
from auth import current_identity
from database import connect,get_connection
from seed_catalog import identifier


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class ReactIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection=connect();self.tx=self.connection.transaction(force_rollback=True);self.tx.__enter__()
        app.dependency_overrides[get_connection]=lambda:self.connection
        self.identity={'uid':'react-test-'+str(uuid4()),'email':'react@example.com','email_verified':True}
        app.dependency_overrides[current_identity]=lambda:self.identity
        self.client=TestClient(app);self.client.put('/api/account',json={}).raise_for_status()
        self.store=self.connection.execute("SELECT id FROM stores WHERE slug='demo-kyoto'").fetchone()['id']
        self.slot=self.connection.execute("SELECT id FROM availability_slots WHERE store_id=%s AND starts_at>now()+interval '60 days' ORDER BY starts_at LIMIT 1",(self.store,)).fetchone()['id']
        self.plan='30000000-0000-4000-8000-000000000001';self.belt='20000000-0000-4000-8000-000000000001'

    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.tx.__exit__(None,None,None);self.connection.close()

    def people(self):
        return [{'id':'female','role':'FEMALE','kimonoId':str(identifier('kimono','RKH0002')),'beltId':self.belt},
                {'id':'male','role':'MALE','kimonoId':str(identifier('kimono','RKH0103')),'beltId':None}]

    def body(self):
        people=self.people()+[{'id':'third','role':'FEMALE','kimonoId':str(identifier('kimono','RKH0057')),'beltId':None}]
        return {'storeId':str(self.store),'slotId':str(self.slot),'guests':[
            {'guestType':'ADULT_'+p['role'],'planId':self.plan,'kimonoId':p['kimonoId'],'accessoryIds':[p['beltId']] if p['beltId'] else []} for p in people],
            'contactName':'整合測試','contactEmail':'react@example.com','contactPhone':'+886912345678'}

    def test_couple_third_belt_quote_atomic_hold_and_restore(self):
        saved=self.client.post('/api/booking-drafts',json=self.body());self.assertEqual(saved.status_code,201,saved.text);saved=saved.json()
        restored=self.client.get('/api/booking-drafts/'+saved['draftId']).json()
        self.assertEqual(restored['data']['contactName'],'整合測試')
        self.assertEqual(restored['data']['guests'][0]['accessoryIds'],[self.belt])
        quote=self.client.post('/api/pricing/quote',json={'draftId':saved['draftId'],'version':saved['version']})
        self.assertEqual(quote.status_code,200,quote.text);quote=quote.json();self.assertEqual(quote['total'],4500)
        key=str(uuid4());payload={'draftId':saved['draftId'],'quoteToken':quote['quoteToken']}
        held=self.client.post('/api/availability/holds',json=payload,headers={'Idempotency-Key':key})
        self.assertEqual(held.status_code,201,held.text);held=held.json();self.assertEqual(held['partySize'],3)
        allocations=self.connection.execute('SELECT inventory_id FROM inventory_allocations WHERE hold_id=%s',(held['holdId'],)).fetchall()
        self.assertEqual(len({r['inventory_id'] for r in allocations}),3)
        again=self.client.post('/api/availability/holds',json=payload,headers={'Idempotency-Key':key}).json()
        self.assertEqual(held['expiresAt'],again['expiresAt'])
        self.assertFalse(held['bookingConfirmed']);self.assertFalse(held['paymentAvailable'])
        self.assertEqual(self.client.get('/api/booking-drafts/'+saved['draftId']).json()['activeHold']['holdId'],held['holdId'])
        self.client.delete('/api/availability/holds/'+held['holdId']).raise_for_status()

    def test_look_persists_belt_and_price_changes_invalidate_quote(self):
        look=self.client.post('/api/looks',json={'planId':self.plan,'participants':self.people()})
        self.assertEqual(look.status_code,201,look.text);look=look.json()
        self.assertEqual(look['participants'][0]['beltId'],self.belt);self.assertEqual(look['price'],3000)
        saved=self.client.post('/api/booking-drafts',json=self.body()).json()
        quote=self.client.post('/api/pricing/quote',json={'draftId':saved['draftId'],'version':saved['version']}).json()
        self.connection.execute('UPDATE accessories SET price=price+1 WHERE id=%s',(self.belt,))
        held=self.client.post('/api/availability/holds',json={'draftId':saved['draftId'],'quoteToken':quote['quoteToken']},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(held.status_code,409,held.text);self.assertEqual(held.json()['error']['code'],'PRICE_CHANGED')
        self.assertEqual(self.client.get('/api/looks/'+look['lookId']).json()['price'],3001)

    def test_partial_draft_and_rejected_child_male_belt(self):
        partial=self.body();partial['slotId']=None
        for guest in partial['guests']: guest['kimonoId']=None;guest['accessoryIds']=[]
        response=self.client.post('/api/booking-drafts',json=partial)
        self.assertEqual(response.status_code,201,response.text)
        body=self.body();body['guests'][1]['accessoryIds']=[self.belt]
        response=self.client.patch('/api/booking-drafts/'+response.json()['draftId'],json={**body,'version':1})
        self.assertEqual(response.status_code,422)
