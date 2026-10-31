"""Opt-in Firebase smoke test. Creates and deletes its own disposable user; rolls back RDS."""
import os
import re
import secrets
import unittest
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from firebase_admin import auth

from app.main import app
from app.integrations.firebase import firebase_app
from app.core.config import BACKEND_DIR
from app.core.database import connect, get_connection


@unittest.skipUnless(os.getenv('RUN_FIREBASE_TESTS') == '1', 'Set RUN_FIREBASE_TESTS=1 for live Firebase')
class LiveFirebaseTests(unittest.TestCase):
    def test_real_token_sync_and_disabled_user(self):
        firebase = firebase_app()
        from dotenv import dotenv_values
        config=dotenv_values(BACKEND_DIR.parent/'frontend'/'.env.local')
        self.assertEqual(config['VITE_FIREBASE_PROJECT_ID'],os.environ['FIREBASE_PROJECT_ID'])
        api_key=config['VITE_FIREBASE_API_KEY']
        email = f'kinu-smoke-{uuid4().hex}@example.com'
        password = secrets.token_urlsafe(24) + 'Aa1!'
        user = auth.create_user(email=email, password=password, app=firebase)
        connection = None
        try:
            connection = connect()
            app.dependency_overrides[get_connection] = lambda: connection
            with httpx.Client(timeout=20) as firebase_client, TestClient(app) as client:
                def sign_in():
                    result = firebase_client.post(
                        'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword',
                        params={'key': api_key}, json={'email': email, 'password': password, 'returnSecureToken': True})
                    self.assertEqual(result.status_code, 200, 'Firebase password sign-in failed')
                    return {'Authorization': 'Bearer ' + result.json()['idToken']}

                headers = sign_in()
                first = client.put('/api/account', json={}, headers=headers)
                self.assertEqual(first.status_code, 200)
                self.assertFalse(first.json()['emailVerified'])
                auth.update_user(user.uid, email_verified=True, app=firebase)
                verified = client.put('/api/account', json={}, headers=sign_in())
                self.assertTrue(verified.json()['emailVerified'])
                self.assertEqual(first.json()['id'], verified.json()['id'])
                auth.update_user(user.uid, disabled=True, app=firebase)
                self.assertEqual(client.get('/api/account', headers=headers).status_code, 401)
        finally:
            app.dependency_overrides.clear()
            if connection:
                connection.rollback()
                connection.close()
            auth.delete_user(user.uid, app=firebase)
