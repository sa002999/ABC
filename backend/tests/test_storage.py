import hashlib
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import app
from catalog import Asset
from database import get_connection
from storage import CACHE_CONTROL, cloudfront_url, publish_catalog, read_product_image, upload_object

KEY = 'catalog/10000000-0000-4000-8000-000000000001/' + 'a' * 64 + '.webp'


class StorageTests(unittest.TestCase):
    @patch.dict(os.environ, {'S3_BUCKET': 'example-bucket', 'AWS_REGION': 'ap-southeast-2', 'CLOUDFRONT_DOMAIN': 'example.cloudfront.net'})
    def test_database_switch_requires_private_origin_and_verified_cdn(self):
        for outcome in ['public-origin', 'cdn-failure', 'success']:
            with self.subTest(outcome=outcome), patch('storage.connect') as connect, patch('storage.s3_client'), \
                    patch('storage.read_product_image', return_value=b'content'), patch('storage.upload_object'), \
                    patch('storage.httpx.Client') as client, patch('builtins.print'):
                connection = connect.return_value.__enter__.return_value
                connection.execute.return_value.fetchall.return_value = [{'id': UUID(int=1), 'image_key': 'kimono/test.webp'}]
                origin = MagicMock(status_code=200 if outcome == 'public-origin' else 403)
                cdn = MagicMock(status_code=500 if outcome == 'cdn-failure' else 200,
                                headers={'content-type': 'image/webp'}, content=b'content')
                client.return_value.__enter__.return_value.get.side_effect = [origin, cdn]
                if outcome == 'success':
                    publish_catalog()
                    self.assertEqual(connect.call_count, 2)
                    self.assertIn('UPDATE product_assets', connection.execute.call_args.args[0])
                else:
                    with self.assertRaises(RuntimeError):
                        publish_catalog()
                    self.assertEqual(connect.call_count, 1)
                    self.assertEqual(connection.execute.call_count, 1)

    @patch.dict(os.environ, {'CLOUDFRONT_DOMAIN': 'example.cloudfront.net'})
    def test_public_url_rejects_private_keys_and_invalid_origins(self):
        expected = 'https://example.cloudfront.net/' + KEY
        self.assertEqual(cloudfront_url(KEY), expected)
        for key in ['../.env', 'private/photos/person.jpg', 'catalog/../private/a.webp', '/catalog/a.webp']:
            with self.assertRaises(ValueError):
                cloudfront_url(key)
        for domain in ['', 'http://example.com', 'https://user:pass@example.com', 'example.com/private', 'example.com?x=1']:
            with patch.dict(os.environ, {'CLOUDFRONT_DOMAIN': domain}), self.assertRaises(RuntimeError):
                cloudfront_url(KEY)
        asset = Asset.model_validate({'id': UUID(int=1), 'kind': 'PRODUCT', 'url': '/api/catalog-assets/test',
                                      's3_key': KEY, 'alt': {'zh-Hant': '商品圖'}})
        self.assertEqual(asset.url, expected)
        self.assertNotIn('s3_key', asset.model_dump())

    def test_upload_is_private_immutable_and_repeatable(self):
        client = MagicMock()
        content = b'webp-test'
        self.assertEqual(upload_object(client, 'bucket', KEY, content), 'uploaded')
        arguments = client.put_object.call_args.kwargs
        self.assertEqual(arguments['IfNoneMatch'], '*')
        self.assertNotIn('ACL', arguments)
        self.assertEqual(arguments['ContentType'], 'image/webp')
        client.put_object.side_effect = ClientError({'Error': {'Code': '412'}}, 'PutObject')
        client.head_object.return_value = {'Metadata': {'sha256': hashlib.sha256(content).hexdigest()},
                                         'ContentLength': len(content), 'ContentType': 'image/webp', 'CacheControl': CACHE_CONTROL}
        client.put_object.reset_mock()
        self.assertEqual(upload_object(client, 'bucket', KEY, content), 'unchanged')
        self.assertEqual(client.put_object.call_args.kwargs['IfNoneMatch'], '*')
        client.head_object.return_value['Metadata']['sha256'] = 'wrong'
        with self.assertRaises(RuntimeError):
            upload_object(client, 'bucket', KEY, content)
        client.put_object.side_effect = ClientError({'Error': {'Code': '403'}}, 'PutObject')
        with self.assertRaises(ClientError):
            upload_object(client, 'bucket', KEY, content)

    def test_local_source_cannot_escape_catalog_directory(self):
        for key in ['../.env', '../assets/default models/person.jpg']:
            with self.assertRaises(RuntimeError):
                read_product_image(key)

    @patch.dict(os.environ, {'CLOUDFRONT_DOMAIN': 'example.cloudfront.net'})
    def test_legacy_image_endpoint_redirects_only_published_assets(self):
        connection = MagicMock()
        app.dependency_overrides[get_connection] = lambda: connection
        try:
            with TestClient(app) as client:
                connection.execute.return_value.fetchone.return_value = {'image_key': 'kimono/test.webp', 's3_key': KEY}
                response = client.get('/api/catalog-assets/10000000-0000-4000-8000-000000000001', follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers['location'], cloudfront_url(KEY))
                self.assertEqual(response.headers['cache-control'], 'no-store')
                connection.execute.return_value.fetchone.return_value = None
                self.assertEqual(client.get('/api/catalog-assets/10000000-0000-4000-8000-000000000001').status_code, 404)
        finally:
            app.dependency_overrides.clear()
