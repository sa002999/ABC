import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.modules.try_on.photos import require_photo_capacity


class PhotoCapacityTests(unittest.TestCase):
    def test_pending_reservation_is_not_reported_as_saved_photo(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'saved':2,'pending':1,'retry_seconds':42}
        with patch('app.modules.try_on.photos.library_count', return_value=3):
            with self.assertRaises(HTTPException) as caught:
                require_photo_capacity(connection, 'member')
        self.assertEqual(caught.exception.detail['code'], 'PHOTO_UPLOAD_PENDING')
        self.assertIn('42 秒', caught.exception.detail['message'])
        self.assertIn('不需要刪除', caught.exception.detail['message'])

    def test_three_saved_photos_still_require_library_management(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'saved':3,'pending':0,'retry_seconds':None}
        with patch('app.modules.try_on.photos.library_count', return_value=3):
            with self.assertRaises(HTTPException) as caught:
                require_photo_capacity(connection, 'member')
        self.assertEqual(caught.exception.detail['code'], 'PHOTO_LIMIT_REACHED')

    def test_expired_reservation_does_not_block_capacity(self):
        connection = MagicMock()
        with patch('app.modules.try_on.photos.library_count', return_value=2):
            require_photo_capacity(connection, 'member')
        connection.execute.assert_not_called()
