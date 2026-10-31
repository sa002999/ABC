import os
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import connect, get_connection
from app.modules.accounts.dependencies import current_identity
from app.modules.accounts.mcp import digest


class McpBoundaryTests(unittest.TestCase):
    def test_missing_credentials_and_private_input_are_rejected(self):
        # No database access is needed for missing credentials or invalid public input.
        app.dependency_overrides[get_connection] = lambda: None
        try:
            with TestClient(app) as client:
                for path in ('/api/account/mcp-token', '/api/mcp/member'):
                    self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(client.get('/api/account/mcp-config').status_code, 200)
                for body in ({'city':'KYOTO','guests':[]}, {'city':'KYOTO','guests':[], 'userId':str(uuid4())}):
                    self.assertEqual(client.post('/api/catalog/outfit-summary', json=body).status_code, 422)
        finally:
            app.dependency_overrides.clear()


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for RDS')
class McpDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect()
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        self.identity = {'uid': 'mcp-test-' + str(uuid4()), 'email': 'mcp-test@example.com', 'email_verified': True}
        app.dependency_overrides[get_connection] = lambda: self.connection
        app.dependency_overrides[current_identity] = lambda: self.identity
        self.client = TestClient(app)
        self.member = self.client.put('/api/account', json={}).json()['id']

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.transaction.__exit__(None,None,None)
        self.connection.close()

    def test_token_lifecycle_ownership_expiry_and_verification(self):
        self.assertEqual(self.client.get('/api/account/mcp-config').json()['endpoint'], 'http://127.0.0.1:3001/mcp')
        self.identity['email_verified'] = False
        self.assertEqual(self.client.post('/api/account/mcp-token', json={'confirmed':True}).status_code,403)
        self.identity['email_verified'] = True
        self.assertEqual(self.client.post('/api/account/mcp-token', json={'confirmed':False}).status_code,422)
        result = self.client.post('/api/account/mcp-token',json={'confirmed':True})
        self.assertEqual(result.status_code,200,result.text)
        token = result.json()['token']
        self.assertTrue(result.json()['valid'])
        row = self.connection.execute('SELECT * FROM mcp_tokens WHERE user_id=%s',(self.member,)).fetchone()
        self.assertEqual(row['token_hash'],digest(token))
        self.assertNotIn(token,str(row))
        headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.get('/api/mcp/member',headers=headers).status_code,200)
        self.assertNotIn('token',self.client.get('/api/account/mcp-token').json())
        self.assertEqual(self.client.post('/api/account/mcp-token',json={'confirmed':True}).status_code,409)
        # Another member cannot see or revoke this member's credential.
        original = dict(self.identity)
        self.identity.update(uid='mcp-other-'+str(uuid4()))
        self.client.put('/api/account',json={}).raise_for_status()
        self.assertFalse(self.client.get('/api/account/mcp-token').json()['valid'])
        self.client.request('DELETE','/api/account/mcp-token',json={'confirmed':True}).raise_for_status()
        self.assertEqual(self.client.get('/api/mcp/member',headers=headers).status_code,200)
        self.identity.update(original)
        rotated = self.client.post('/api/account/mcp-token/rotate',json={'confirmed':True}).json()['token']
        self.assertNotEqual(rotated,token)
        self.assertEqual(self.client.get('/api/mcp/member',headers=headers).status_code,401)
        headers={'Authorization':'Bearer '+rotated}
        self.assertEqual(self.client.get('/api/mcp/member',headers=headers).status_code,200)
        self.connection.execute("UPDATE mcp_tokens SET expires_at=now()-interval '1 second' WHERE user_id=%s",(self.member,))
        self.assertEqual(self.client.get('/api/mcp/member',headers=headers).status_code,401)
        fresh = self.client.post('/api/account/mcp-token',json={'confirmed':True}).json()['token']
        self.client.request('DELETE','/api/account/mcp-token',json={'confirmed':True}).raise_for_status()
        self.assertEqual(self.client.get('/api/mcp/member',headers={'Authorization':'Bearer '+fresh}).status_code,401)

    def test_public_outfits_authoritative_pricing_and_common_stores(self):
        plans = {p['kind']:p for p in self.client.get('/api/plans?pageSize=50').json()['data']}
        kimonos = self.client.get('/api/kimonos',params={'plan':plans['COUPLE']['id']}).json()['data']
        female = next(k for k in kimonos if k['gender']=='FEMALE')
        male = next(k for k in kimonos if k['gender']=='MALE')
        guests = [{'guestType':'ADULT_'+k['gender'],'planId':plans['COUPLE']['id'],'kimonoId':k['id']} for k in (female,male)]
        payload={'city':'KYOTO','guests':guests}
        response=self.client.post('/api/catalog/outfit-summary',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertEqual(data['estimatedTotal'],2800)
        self.assertTrue(data['commonStores'])
        self.assertTrue(all(s['city']=='KYOTO' for s in data['commonStores']))
        self.assertFalse(data['availabilityChecked'])
        self.assertFalse(data['bookingCreated'])
        guests[1]['guestType']='ADULT_FEMALE'
        self.assertEqual(self.client.post('/api/catalog/outfit-summary',json=payload).status_code,422)
        guests[1]['guestType']='ADULT_MALE'
        for g in guests: g['planId']=plans['GROUP']['id']
        self.assertEqual(self.client.post('/api/catalog/outfit-summary',json=payload).json()['estimatedTotal'],2800)
        self.connection.execute("UPDATE stores SET active=false WHERE city='KYOTO'")
        no_store=self.client.post('/api/catalog/outfit-summary',json=payload)
        self.assertEqual(no_store.status_code,200,no_store.text)
        self.assertEqual(no_store.json()['commonStores'],[])
        self.assertEqual(no_store.json()['guests'],guests)
        self.connection.execute('DELETE FROM plan_kimonos WHERE plan_id=%s AND kimono_id=%s',(guests[0]['planId'],guests[0]['kimonoId']))
        self.assertEqual(self.client.post('/api/catalog/outfit-summary',json=payload).status_code,422)
