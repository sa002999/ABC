import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from firebase_admin import auth

from app.main import app
from app.modules.accounts.dependencies import current_identity
from app.core.database import connect, get_connection


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_missing_invalid_and_unavailable_credentials(self):
        self.assertEqual(self.client.get('/api/account').status_code, 401)
        with patch('app.modules.accounts.dependencies.firebase_app', return_value=None), patch('app.modules.accounts.dependencies.auth.verify_id_token') as verify:
            for error, status in [(auth.InvalidIdTokenError('bad'), 401),
                                  (auth.RevokedIdTokenError('revoked'), 401),
                                  (auth.UserDisabledError('disabled'), 401),
                                  (auth.CertificateFetchError('private-url', None), 503)]:
                verify.side_effect = error
                response = self.client.get('/api/account', headers={'Authorization': 'Bearer fake'})
                self.assertEqual(response.status_code, status)
                self.assertNotIn('private-url', response.text)
            self.assertTrue(verify.call_args.kwargs['check_revoked'])

    def test_client_cannot_assign_roles_or_verification(self):
        app.dependency_overrides[current_identity] = lambda: {'uid': 'test', 'email': 'test@example.com'}
        app.dependency_overrides[get_connection] = lambda: None
        for body in [{'role': 'ADMIN'}, {'emailVerified': True}, {'firebase_uid': 'other'}]:
            self.assertEqual(self.client.put('/api/account', json=body).status_code, 422)


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for RDS')
class AccountDatabaseTests(unittest.TestCase):
    def test_sync_is_idempotent_preserves_role_and_honors_disabled(self):
        connection = connect()
        identity = {'uid': 'test-' + str(uuid4()), 'email': 'integration@example.com', 'email_verified': False}
        app.dependency_overrides[current_identity] = lambda: identity
        app.dependency_overrides[get_connection] = lambda: connection
        try:
            with TestClient(app) as client:
                first = client.put('/api/account', json={})
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.json()['role'], 'CUSTOMER')
                connection.execute("UPDATE users SET role = 'STORE_STAFF' WHERE firebase_uid = %s", (identity['uid'],))
                identity['email_verified'] = True
                second = client.put('/api/account', json={})
                self.assertEqual(first.json()['id'], second.json()['id'])
                self.assertEqual(second.json()['role'], 'STORE_STAFF')
                self.assertTrue(second.json()['emailVerified'])
                self.assertEqual(client.get('/api/account').json(), second.json())
                connection.execute('UPDATE users SET active = false WHERE firebase_uid = %s', (identity['uid'],))
                self.assertEqual(client.put('/api/account', json={}).status_code, 403)
                self.assertEqual(client.get('/api/account').status_code, 403)
        finally:
            connection.rollback()
            connection.close()
            app.dependency_overrides.clear()
