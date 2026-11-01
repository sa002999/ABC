import os
import time
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from psycopg.errors import UniqueViolation

from app.modules.accounts.schemas import PhoneBinding, ProfileUpdate
from app.modules.accounts.service import bind_phone, sync_account


class MemberProfileTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(id=uuid4(), active=True, email='member@example.test', email_verified=True,
                        display_name='會員姓名', role='CUSTOMER', phone_number=None, phone_verified_at=None)
        self.identity = dict(uid='member', email=self.row['email'], auth_time=int(time.time()),
                             firebase={'sign_in_provider': 'password'})
        self.proof = dict(uid='phone-only', phone_number='+886912345678', auth_time=int(time.time()),
                          firebase={'sign_in_provider': 'phone'})
        self.connection = MagicMock()
        self.body = PhoneBinding(phoneToken='signed-proof')

    def bind(self, proof=None):
        with patch('app.integrations.firebase.firebase_app', return_value=None), \
                patch('firebase_admin.auth.verify_id_token', return_value=self.proof if proof is None else proof) as verify:
            result = bind_phone(self.body, self.identity, self.connection)
            self.assertTrue(verify.call_args.kwargs['check_revoked'])
            return result

    def test_profile_validation_and_no_client_verification_flags(self):
        self.assertEqual(ProfileUpdate(displayName='  會員姓名  ').display_name, '會員姓名')
        for body in [{'displayName': ' '}, {'displayName': 'a'*101}, {'displayName': '姓名', 'phoneVerified': True},
                     {'displayName': '姓名', 'email': 'other@example.test'}]:
            with self.assertRaises(ValidationError):
                ProfileUpdate(**body)

    def test_login_sync_does_not_overwrite_edited_name(self):
        self.connection.execute.return_value.fetchone.return_value = self.row
        result = sync_account(None, {**self.identity, 'name': 'Firebase舊姓名'}, self.connection)
        sql = self.connection.execute.call_args.args[0].split('DO UPDATE SET')[1]
        self.assertNotIn('display_name =', sql)
        self.assertEqual(result['displayName'], '會員姓名')

    def test_binding_requires_recent_password_authentication(self):
        self.connection.execute.return_value.fetchone.return_value = self.row
        for patch_identity in [{'auth_time': int(time.time())-301}, {'firebase': {'sign_in_provider': 'phone'}}]:
            with self.subTest(patch_identity=patch_identity):
                original = self.identity
                self.identity = {**original, **patch_identity}
                with self.assertRaises(HTTPException) as error:
                    self.bind()
                self.assertEqual(error.exception.detail['code'], 'REAUTH_REQUIRED')
                self.identity = original

    def test_rejects_expired_wrong_provider_and_unsupported_phone_proofs(self):
        self.connection.execute.return_value.fetchone.return_value = self.row
        for invalid in [{'auth_time': int(time.time())-301}, {'phone_number': '+15551234567'},
                        {'firebase': {'sign_in_provider': 'password'}}, {'email': 'other@example.test'}, {'uid': 'member'}]:
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException) as error:
                self.bind({**self.proof, **invalid})
            self.assertEqual(error.exception.detail['code'], 'INVALID_PHONE_PROOF')

    def test_verifies_and_binds_server_claims(self):
        saved = {**self.row, 'phone_number': self.proof['phone_number'], 'phone_verified_at': 'now'}
        self.connection.execute.return_value.fetchone.side_effect = [self.row,
                                                                   {'user_id': self.row['id']}, saved]
        result = self.bind()
        self.assertTrue(result['phoneVerified'])
        self.assertEqual(result['phoneNumber'], '+886912345678')
        self.assertEqual(self.connection.execute.call_args.args[1], ('+886912345678', self.row['id']))

    def test_duplicate_number_rolls_back_replacement(self):
        self.connection.execute.return_value.fetchone.side_effect = [self.row,
                                                                   {'user_id': self.row['id']}, UniqueViolation()]
        with self.assertRaises(HTTPException) as error:
            self.bind()
        self.assertEqual(error.exception.detail['code'], 'PHONE_ALREADY_BOUND')
        self.assertIsNotNone(self.connection.transaction.return_value.__exit__.call_args.args[0])

    def test_old_proof_cannot_bind_again_after_replacement(self):
        self.connection.execute.return_value.fetchone.side_effect = [self.row, None,
                                                                   {'user_id': self.row['id']}, self.row]
        with self.assertRaises(HTTPException) as error:
            self.bind()
        self.assertEqual(error.exception.detail['code'], 'PHONE_PROOF_USED')

    def test_phone_login_is_rejected_even_if_token_has_email(self):
        from fastapi.security import HTTPAuthorizationCredentials
        from app.modules.accounts.dependencies import current_identity
        identity = {**self.identity, 'firebase': {'sign_in_provider': 'phone'}}
        with patch('app.modules.accounts.dependencies.firebase_app', return_value=None), \
                patch('app.modules.accounts.dependencies.auth.verify_id_token', return_value=identity), \
                self.assertRaises(HTTPException) as error:
            current_identity(HTTPAuthorizationCredentials(scheme='Bearer', credentials='token'))
        self.assertEqual(error.exception.status_code, 401)


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for database checks')
class MemberProfileDatabaseTests(unittest.TestCase):
    def test_profile_persistence_phone_uniqueness_and_failed_replacement(self):
        from app.core.database import connect
        from app.modules.accounts.service import update_profile, get_account
        connection = connect()
        identity = dict(uid='profile-test-'+str(uuid4()), email='profile@example.test',
                        auth_time=int(time.time()), firebase={'sign_in_provider': 'password'})
        second = {**identity, 'uid': 'profile-test-'+str(uuid4())}
        # Transaction is always rolled back; no real SMS or Firebase user is created.
        suffix = str(int(uuid4().hex[:8], 16) % 100000000).zfill(8)
        proof = dict(uid='phone-test-'+str(uuid4()), phone_number='+8869'+suffix,
                     auth_time=int(time.time()), firebase={'sign_in_provider': 'phone'})
        try:
            sync_account(None, identity, connection)
            update_profile(ProfileUpdate(displayName='編輯後姓名'), identity, connection)
            self.assertEqual(sync_account(None, {**identity, 'name': '舊姓名'}, connection)['displayName'], '編輯後姓名')
            with patch('app.integrations.firebase.firebase_app', return_value=None), \
                    patch('firebase_admin.auth.verify_id_token', return_value=proof):
                first = bind_phone(PhoneBinding(phoneToken='proof'), identity, connection)
                self.assertTrue(first['phoneVerified'])
                self.assertEqual(bind_phone(PhoneBinding(phoneToken='proof'), identity, connection)['phoneNumber'], proof['phone_number'])
                sync_account(None, second, connection)
                proof = {**proof, 'uid': 'phone-test-'+str(uuid4())}
            with patch('app.integrations.firebase.firebase_app', return_value=None), \
                    patch('firebase_admin.auth.verify_id_token', return_value=proof):
                with self.assertRaises(HTTPException) as error:
                    bind_phone(PhoneBinding(phoneToken='proof'), second, connection)
                self.assertEqual(error.exception.detail['code'], 'PHONE_ALREADY_BOUND')
            self.assertEqual(get_account(identity, connection)['phoneNumber'], first['phoneNumber'])
            self.assertIsNone(get_account(second, connection)['phoneNumber'])
        finally:
            connection.rollback()
            connection.close()


if __name__ == '__main__':
    unittest.main()
