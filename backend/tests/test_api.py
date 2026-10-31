import os
import unittest

import psycopg
from fastapi.testclient import TestClient

from app.core.database import get_connection
from app.main import app
from app.core.database import connect


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_liveness_needs_no_database(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertTrue(response.json()['meta']['capabilities']['quote'])
        self.assertFalse(response.json()['meta']['capabilities']['payment'])

    def test_database_error_is_sanitized(self):
        def unavailable():
            raise psycopg.OperationalError('private-host and secret-password must not escape')
            yield
        app.dependency_overrides[get_connection] = unavailable
        response = self.client.get('/api/stores')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'DATABASE_UNAVAILABLE')
        self.assertEqual(response.json()['error']['requestId'], response.headers['X-Request-ID'])
        self.assertNotIn('secret-password', response.text)
        self.assertNotIn('private-host', response.text)

    def test_invalid_parameters_are_rejected(self):
        app.dependency_overrides[get_connection] = lambda: None
        for path in ['/api/stores?city=INVALID', '/api/stores/not-a-uuid']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT')

    def test_public_frontend_does_not_expose_environment(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for path in ['/plans', '/booking', '/stores']:
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ['/.env', '/backend/.env', '/js/../backend/.env']:
            self.assertEqual(self.client.get(path).status_code, 404)


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 to test configured RDS')
class DatabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_database_health_and_seeded_city_filters(self):
        self.assertEqual(self.client.get('/api/health/db').status_code, 200)
        for city, demo_id in [('TOKYO', '10000000-0000-4000-8000-000000000001'), ('KYOTO', '10000000-0000-4000-8000-000000000002')]:
            response = self.client.get('/api/stores', params={'city': city})
            self.assertEqual(response.status_code, 200)
            stores = response.json()['data']
            self.assertTrue(stores)
            self.assertTrue(all(store['city'] == city for store in stores))
            demo = next(store for store in stores if store['id'] == demo_id)
            self.assertTrue(demo['isDemo'])
            self.assertEqual(demo['timezone'], 'Asia/Tokyo')
            self.assertIsInstance(demo['openingHours'], dict)
            self.assertEqual(self.client.get('/api/stores/' + demo_id).json(), demo)

    def test_unpublished_stores_are_not_public(self):
        # Use a rollback-only transaction so no integration fixture remains in RDS.
        with connect() as connection:
            with connection.transaction(force_rollback=True):
                connection.execute('''INSERT INTO stores (id, slug, city, name, active)
                    VALUES ('20000000-0000-4000-8000-000000000001', 'integration-hidden-store', 'TOKYO', '{}', false)''')
                app.dependency_overrides[get_connection] = lambda: connection
                try:
                    rows = self.client.get('/api/stores').json()['data']
                    self.assertNotIn('20000000-0000-4000-8000-000000000001', [row['id'] for row in rows])
                    self.assertEqual(self.client.get('/api/stores/20000000-0000-4000-8000-000000000001').status_code, 404)
                finally:
                    app.dependency_overrides.clear()

    def test_unknown_store_is_not_found(self):
        response = self.client.get('/api/stores/30000000-0000-4000-8000-000000000001')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
