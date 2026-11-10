import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.modules.bookings import contact
from app.modules.bookings.router import booking_member


class BookingContactTests(unittest.TestCase):
    def setUp(self):
        self.draft_id, self.member = uuid4(), uuid4()
        self.row = {
            'id': self.draft_id, 'user_id': self.member, 'version': 1,
            'data': {'contactMode': 'other', 'contactName': 'Guest',
                     'contactEmail': 'other@example.com', 'contactPhone': '+886912345678'},
        }
        self.account = {'email': 'member@example.com', 'email_verified': True,
                        'display_name': 'Member', 'phone_number': '+886912345678',
                        'phone_verified_at': True}

    def test_unverified_login_is_rejected_at_booking_gate(self):
        with self.assertRaises(HTTPException) as error:
            contact.verified_identity({'email_verified': False})
        self.assertEqual(error.exception.detail['code'], 'EMAIL_VERIFICATION_REQUIRED')

    def test_booking_gate_requires_name_and_verified_phone(self):
        connection = MagicMock()
        for patch in ({'display_name': ' '}, {'phone_number': None}, {'phone_verified_at': None}):
            with self.subTest(patch=patch):
                connection.execute.return_value.fetchone.return_value = {**self.account, **patch}
                with self.assertRaises(HTTPException) as error:
                    booking_member(member=self.member, connection=connection)
                self.assertEqual(error.exception.status_code, 403)
                self.assertEqual(error.exception.detail['code'], 'BOOKING_PROFILE_REQUIRED')
        connection.execute.return_value.fetchone.return_value = self.account
        self.assertEqual(booking_member(member=self.member, connection=connection), self.member)

    def test_other_contact_requires_proof_for_selected_value(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = self.account
        connection.execute.return_value.fetchall.return_value = []
        self.assertEqual(contact.contact_status(connection, self.row),
                         {'email': False, 'phone': True, 'memberName': True})
        with self.assertRaises(HTTPException) as error:
            contact.require_contact(connection, self.row)
        self.assertEqual(error.exception.detail['code'], 'CONTACT_VERIFICATION_REQUIRED')
        connection.execute.return_value.fetchall.return_value = [{'channel': 'email', 'value': 'other@example.com'}]
        contact.require_contact(connection, self.row)
        self.assertEqual(connection.execute.call_args.args[1],
                         (self.draft_id, 'other@example.com', '+886912345678'))

    @patch.dict('os.environ', {'RESEND_API_KEY': 'test-key', 'RESEND_FROM_EMAIL': 'onboarding@resend.dev'})
    def test_resend_code_is_hashed_in_storage_and_sent_to_contact(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'latest': None}
        with patch.object(contact, 'owned_draft', return_value=self.row), \
             patch.object(contact, 'contact_status', return_value={'email': False}), \
             patch.object(contact.secrets, 'randbelow', return_value=42), \
             patch.object(contact.httpx, 'post') as send:
            contact.send_email(connection, self.draft_id, self.member, 1)
        params = connection.execute.call_args.args[1]
        self.assertEqual(params, (self.draft_id, 'other@example.com',
                                  contact.code_hash('test-key', self.draft_id, 'other@example.com', '000042')))
        connection.commit.assert_called_once()
        self.assertEqual(send.call_args.kwargs['json']['to'], ['other@example.com'])
        self.assertIn('000042', send.call_args.kwargs['json']['text'])

    @patch.dict('os.environ', {'RESEND_API_KEY': 'test-key'})
    def test_wrong_code_counts_and_correct_code_verifies(self):
        connection = MagicMock()
        digest = contact.code_hash('test-key', self.draft_id, 'other@example.com', '123456')
        connection.execute.return_value.fetchone.return_value = {'code_hash': digest}
        with patch.object(contact, 'owned_draft', return_value=self.row):
            self.assertFalse(contact.confirm_email(connection, self.draft_id, self.member, 1, '000000'))
            self.assertIs(connection.execute.call_args.args[1][0], False)
            self.assertTrue(contact.confirm_email(connection, self.draft_id, self.member, 1, '123456'))
            self.assertIs(connection.execute.call_args.args[1][0], True)
        self.assertEqual(connection.commit.call_count, 2)
