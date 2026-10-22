import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app import app
from auth import current_identity
from database import connect, get_connection
from seed_catalog import identifier


class LooksAuthenticationTests(unittest.TestCase):
    def test_every_private_route_requires_login(self):
        with TestClient(app) as client:
            for method, path, body in [('GET', '/api/looks', None), ('POST', '/api/looks', {}),
                                      ('GET', '/api/looks/' + str(uuid4()), None),
                                      ('PATCH', '/api/looks/' + str(uuid4()), {}),
                                      ('DELETE', '/api/looks/' + str(uuid4()), None),
                                      ('POST', '/api/plans/compare', {})]:
                response = client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['cache-control'], 'no-store')


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for RDS')
class LooksIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect()
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        app.dependency_overrides[get_connection] = lambda: self.connection
        self.identity = {'uid': 'looks-test-' + str(uuid4()), 'email': 'looks-test@example.com', 'email_verified': False}
        app.dependency_overrides[current_identity] = lambda: self.identity
        self.client = TestClient(app)
        self.member = self.client.put('/api/account', json={}).json()['id']

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.transaction.__exit__(None, None, None)
        self.connection.close()

    def selection(self, sku='RKH0002'):
        return {'planId': str(identifier('plan', sku)), 'kimonoId': str(identifier('kimono', sku)),
                'accessoryIds': [], 'sceneId': None, 'generationId': None}

    def create(self, sku='RKH0002'):
        response = self.client.post('/api/looks', json=self.selection(sku))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_deduplication_replay_and_current_prices(self):
        selection = self.selection()
        headers = {'Idempotency-Key': str(uuid4())}
        first = self.client.post('/api/looks', json=selection, headers=headers)
        self.assertEqual(first.status_code, 201)
        look = first.json()
        self.assertNotIn('size', look)
        self.assertEqual(look['imageSource'], 'PRODUCT')
        self.assertTrue(look['image']['url'].startswith('https://'))
        for replay_headers in [headers, {}]:
            replay = self.client.post('/api/looks', json=selection, headers=replay_headers)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.json()['lookId'], look['lookId'])
        self.assertEqual(self.client.post('/api/looks', json=self.selection('RKH0057'), headers=headers).status_code, 409)
        self.connection.execute('UPDATE plans SET base_price=base_price+100 WHERE id=%s', (identifier('plan', 'RKH0002'),))
        with TestClient(app) as other_device:
            data = other_device.get('/api/looks').json()
            self.assertEqual(data['total'], 1)
            self.assertEqual(data['data'][0]['currentPrice'], look['currentPrice'] + 100)
            self.assertNotIn('userId', data['data'][0])

    def test_member_isolation_and_disabled_account(self):
        look = self.create()
        self.identity['uid'] = 'other-' + str(uuid4())
        self.client.put('/api/account', json={})
        path = '/api/looks/' + look['lookId']
        self.assertEqual(self.client.get('/api/looks').json()['data'], [])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 404)
        self.assertEqual(self.client.patch(path, json={**self.selection(), 'version': 1}).status_code, 404)
        own = self.create('RKH0103')
        self.assertEqual(self.client.post('/api/plans/compare', json={'lookIds': [look['lookId'], own['lookId']]}).status_code, 404)
        self.connection.execute('UPDATE users SET active=false WHERE firebase_uid=%s', (self.identity['uid'],))
        self.assertEqual(self.client.get('/api/looks').status_code, 403)

    def test_invalid_or_unsupported_selections_are_rejected(self):
        for invalid in [{**self.selection(), 'kimonoId': str(uuid4())},
                        {**self.selection(), 'accessoryIds': [str(uuid4())]},
                        {**self.selection(), 'generationId': str(uuid4())},
                        {**self.selection(), 'sceneId': str(uuid4())},
                        {**self.selection(), 'userId': str(uuid4())},
                        {**self.selection(), 'currentPrice': 1}]:
            self.assertEqual(self.client.post('/api/looks', json=invalid).status_code, 422)
        self.connection.execute('UPDATE plans SET active=false WHERE id=%s', (identifier('plan', 'RKH0002'),))
        self.assertEqual(self.client.post('/api/looks', json=self.selection()).status_code, 422)

    def test_confirmed_update_version_and_duplicate_conflicts(self):
        first = self.create()
        self.create('RKH0057')
        path = '/api/looks/' + first['lookId']
        changed = self.client.patch(path, json={**self.selection('RKH0103'), 'version': first['version']})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['version'], 2)
        self.assertEqual(changed.json()['planId'], str(identifier('plan','RKH0103')))
        self.assertEqual(self.client.patch(path, json={**self.selection(), 'version': 1}).status_code, 409)
        self.assertEqual(self.client.patch(path, json={**self.selection('RKH0057'), 'version': 2}).status_code, 409)
        self.assertEqual(self.client.get(path).json()['planId'], str(identifier('plan','RKH0103')))

    def test_hidden_plan_is_preserved_and_delete_does_not_touch_images(self):
        look = self.create()
        path = '/api/looks/' + look['lookId']
        asset_count = self.connection.execute('SELECT count(*) AS count FROM product_assets').fetchone()['count']
        self.connection.execute('UPDATE plans SET active=false WHERE id=%s', (identifier('plan', 'RKH0002'),))
        unavailable = self.client.get(path).json()
        self.assertFalse(unavailable['available'])
        self.assertIsNone(unavailable['currentPrice'])
        self.assertIsNone(unavailable['image'])
        self.assertEqual(self.client.get('/api/looks').json()['total'], 1)
        self.assertEqual(self.client.delete(path).json(), {'ok': True})
        self.assertEqual(self.connection.execute('SELECT count(*) AS count FROM product_assets').fetchone()['count'], asset_count)
        self.assertEqual(self.client.get('/api/looks').json()['total'], 0)

    def test_pagination_and_compare_rules(self):
        looks = [self.create(sku) for sku in ['RKH0002', 'RKH0057', 'RKH0103']]
        ids = [look['lookId'] for look in looks]
        page = self.client.get('/api/looks?pageSize=2').json()
        self.assertEqual(page['total'], 3)
        self.assertEqual(page['nextPage'], 1)
        self.assertEqual(len(self.client.get('/api/looks?pageSize=2&page=1').json()['data']), 1)
        for selected in [ids[:2], ids[::-1]]:
            result = self.client.post('/api/plans/compare', json={'lookIds': selected})
            self.assertEqual(result.status_code, 200)
            self.assertEqual([look['lookId'] for look in result.json()], selected)
        for invalid in [ids[:1], ids + ids[:1], [ids[0], ids[0]]]:
            self.assertEqual(self.client.post('/api/plans/compare', json={'lookIds': invalid}).status_code, 422)
        self.connection.execute('UPDATE plans SET active=false WHERE id=%s', (identifier('plan', 'RKH0002'),))
        self.assertEqual(self.client.post('/api/plans/compare', json={'lookIds': ids[:2]}).status_code, 409)
