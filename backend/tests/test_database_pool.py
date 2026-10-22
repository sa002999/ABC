import unittest
from unittest.mock import patch

import database


class DatabasePoolTests(unittest.TestCase):
    def test_pool_is_reused_and_closed(self):
        with patch.object(database, 'connection_options', return_value={}), patch.object(database, 'ConnectionPool') as factory:
            database.close_pool()
            try:
                self.assertIs(database.get_pool(), database.get_pool())
                self.assertEqual(factory.call_count, 1)
            finally:
                database.close_pool()
            factory.return_value.close.assert_called_once()
