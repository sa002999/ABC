import os
import unittest

from fastapi.testclient import TestClient

from app import app, get_connection
from database import connect
from seed_catalog import identifier


class CatalogValidationTests(unittest.TestCase):
    def test_invalid_filters_have_structured_errors(self):
        app.dependency_overrides[get_connection] = lambda: None
        try:
            with TestClient(app) as client:
                for query in ['city=OSAKA', 'page=-1', 'pageSize=51', 'minPrice=-1', 'minPrice=2000&maxPrice=1000', 'sort=SQL', 'store=bad-id']:
                    response = client.get('/api/plans?' + query)
                    self.assertEqual(response.status_code, 422, query)
                    self.assertIn('error', response.json())
        finally:
            app.dependency_overrides.clear()


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 to test configured RDS')
class CatalogIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect()
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        app.dependency_overrides[get_connection] = lambda: self.connection
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.transaction.__exit__(None, None, None)
        self.connection.close()

    def plans(self, query=''):
        response = self.client.get('/api/plans' + query)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_city_assignment_and_combined_filters(self):
        kyoto = self.plans('?city=KYOTO')
        tokyo = self.plans('?city=TOKYO')
        self.assertEqual({p['kimono']['sku'] for p in kyoto['data']}, {'RKH0002', 'RKH0057', 'RKH0103'})
        self.assertEqual({p['kimono']['sku'] for p in tokyo['data']}, {'RKH0002', 'RKH0057', 'RKH0103'})
        filtered = self.plans('?city=KYOTO&style=ROMANTIC&audience=FAMILY&minPrice=1600&maxPrice=1900')
        self.assertEqual([p['kimono']['sku'] for p in filtered['data']], ['RKH0057'])
        self.assertTrue(all('ELEGANT' in p['kimono']['styleTags'] for p in self.plans('?city=TOKYO&style=ELEGANT')['data']))
        self.assertEqual(self.plans('?city=TOKYO&store=10000000-0000-4000-8000-000000000002')['data'], [])

    def test_pagination_sorting_and_literal_search(self):
        first = self.plans('?pageSize=2&sort=priceAsc')
        second = self.plans('?pageSize=2&page=1&sort=priceAsc')
        self.assertEqual(first['total'], 4)
        self.assertEqual(first['nextPage'], 1)
        self.assertIsNone(second['nextPage'])
        self.assertEqual(len({p['id'] for p in first['data'] + second['data']}), 4)
        self.assertEqual([p['basePrice'] for p in first['data']], [1500, 1800])
        self.assertEqual(self.plans('?page=99')['data'], [])
        self.assertEqual(self.plans('?keyword=RKH0002')['total'], 2)
        self.assertEqual(self.client.get('/api/plans', params={'keyword': '%'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/plans', params={'keyword': "' OR 1=1 --"}).json()['total'], 0)

    def test_plan_kimono_and_public_product_image(self):
        plan = self.plans()['data'][0]
        detail = self.client.get('/api/plans/' + plan['id'])
        self.assertEqual(detail.json(), plan)
        self.assertEqual(plan['currency'], 'TWD')
        self.assertNotIn('sizes',plan['kimono'])
        self.assertTrue(plan['isDemo'])
        self.assertEqual(self.client.get('/api/kimonos/' + plan['kimono']['id']).json(), plan['kimono'])
        self.assertEqual(len(self.client.get('/api/kimonos?city=KYOTO').json()['data']), 3)
        image = plan['kimono']['images'][0]
        self.assertEqual(image['kind'], 'PRODUCT')
        response = self.client.get('/api/catalog-assets/' + image['id'], follow_redirects=False)
        if image['url'].startswith('https://'):
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['location'], image['url'])
        else:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'image/webp')
            self.assertLess(len(response.content), 400000)
        self.assertEqual(self.client.get('/assets/default%20models/person.jpg').status_code, 404)
        self.assertEqual(self.client.get('/backend/assets/default%20models/person.jpg').status_code, 404)

    def test_hidden_products_plans_and_stores_do_not_leak(self):
        plan_id = identifier('plan', 'RKH0002')
        asset_url = '/api/catalog-assets/' + str(identifier('asset', 'RKH0002'))
        kimono_url = '/api/kimonos/' + str(identifier('kimono', 'RKH0002'))
        self.connection.execute('UPDATE plans SET active = false WHERE id = %s', (plan_id,))
        self.assertEqual(self.client.get('/api/plans/' + str(plan_id)).status_code, 404)
        self.assertIn(self.client.get(asset_url,follow_redirects=False).status_code,(200,302))
        self.assertEqual(self.client.get(kimono_url).status_code, 200)
        self.assertEqual(self.plans()['total'], 3)
        self.connection.execute('UPDATE plans SET active = true WHERE id = %s', (plan_id,))
        self.connection.execute('UPDATE kimonos SET active = false WHERE id = %s', (identifier('kimono', 'RKH0002'),))
        self.assertEqual(self.client.get('/api/plans/' + str(plan_id)).status_code, 404)
        self.connection.execute("UPDATE stores SET active = false WHERE slug = 'demo-tokyo'")
        self.assertEqual(self.plans('?city=TOKYO')['data'], [])

    def test_missing_resource_and_unsafe_asset_path(self):
        missing = '40000000-0000-4000-8000-000000000001'
        for resource in ['plans', 'kimonos', 'catalog-assets']:
            self.assertEqual(self.client.get('/api/' + resource + '/' + missing).status_code, 404)
        self.connection.execute("UPDATE product_assets SET image_key = '../.env', s3_key = NULL WHERE id = %s", (identifier('asset', 'RKH0002'),))
        self.assertEqual(self.client.get('/api/catalog-assets/' + str(identifier('asset', 'RKH0002'))).status_code, 404)


if __name__ == '__main__':
    unittest.main()
