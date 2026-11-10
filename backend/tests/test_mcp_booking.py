import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException, Response

from app.modules.bookings import mcp, service


class McpBookingTests(unittest.TestCase):
    def setUp(self):
        self.member, self.draft_id, self.quote_token = uuid4(), uuid4(), uuid4()
        self.connection = MagicMock()
        self.profile = {'display_name': 'Member', 'email': 'member@example.test', 'phone_number': '+886912345678'}
        self.selection = mcp.Selection(
            store_id=uuid4(), slot_id=uuid4(),
            guests=[{'guest_type': 'ADULT_FEMALE', 'plan_id': uuid4(), 'kimono_id': uuid4()}],
        )

    def test_prepare_quotes_with_member_contacts_and_no_hold(self):
        def save(draft, member, connection, response):
            self.assertEqual(member, self.member)
            self.assertEqual(draft.contact_mode, 'member')
            self.assertEqual(draft.contact_email, self.profile['email'])
            self.assertEqual(draft.contact_phone, self.profile['phone_number'])
            return {'draftId': self.draft_id, 'version': 1, 'data': service.draft_json(draft), 'activeHold': None}

        with (patch.object(mcp, 'require_booking_profile', return_value=self.profile),
              patch.object(service, 'create_draft', side_effect=save),
              patch.object(service, 'quote', return_value={'quoteToken': self.quote_token}) as quote,
              patch.object(service, 'create_hold') as hold):
            result = mcp.prepare(self.selection, self.member, self.connection, Response())
        self.assertEqual(result['quoteToken'], self.quote_token)
        self.assertEqual(quote.call_args.args[0].draft_id, self.draft_id)
        hold.assert_not_called()

    def test_different_draft_requires_current_version_to_replace(self):
        original = {'draftId': self.draft_id, 'version': 5, 'data': {}, 'activeHold': None}
        with (patch.object(mcp, 'require_booking_profile', return_value=self.profile),
              patch.object(service, 'create_draft', return_value=original),
              patch.object(service, 'update_draft', return_value={**original, 'version': 6}) as update,
              patch.object(service, 'quote', return_value={'quoteToken': self.quote_token}) as quote):
            conflict = mcp.prepare(self.selection, self.member, self.connection, Response())
            self.assertTrue(conflict['draftConflict'])
            stale = self.selection.model_copy(update={'replace_draft_id': self.draft_id, 'replace_version': 4})
            self.assertTrue(mcp.prepare(stale, self.member, self.connection, Response())['draftConflict'])
            update.assert_not_called()
            quote.assert_not_called()

            confirmed = stale.model_copy(update={'replace_version': 5})
            mcp.prepare(confirmed, self.member, self.connection, Response())
            self.assertEqual(update.call_args.args[1].version, 5)
            self.assertEqual(quote.call_args.args[0].version, 6)

    def test_hold_reuses_quote_as_idempotency_key_and_requires_payment(self):
        body = mcp.ConfirmHold(draft_id=self.draft_id, quote_token=self.quote_token, confirmed=True)
        with (patch.object(mcp, 'require_booking_profile'),
              patch.object(mcp, 'configured', return_value=False),
              patch.object(service, 'create_hold') as hold):
            with self.assertRaises(HTTPException):
                mcp.hold(body, self.member, self.connection, Response())
            hold.assert_not_called()
        with (patch.object(mcp, 'require_booking_profile'),
              patch.object(mcp, 'configured', return_value=True),
              patch.object(service, 'create_hold') as hold):
            for _ in range(2):
                mcp.hold(body, self.member, self.connection, Response())
            self.assertEqual([call.args[4] for call in hold.call_args_list], [self.quote_token] * 2)
