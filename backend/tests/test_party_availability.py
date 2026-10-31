import os
import unittest
from datetime import timedelta
from uuid import uuid4

import test_bookings as booking_tests
from zoneinfo import ZoneInfo
from commands.seeds.catalog import identifier


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for RDS')
class PartyAvailabilityTests(unittest.TestCase):
    setUp = booking_tests.BookingIntegrationTests.setUp
    tearDown = booking_tests.BookingIntegrationTests.tearDown
    body = booking_tests.BookingIntegrationTests.body

    def query(self, count=2, **changes):
        day = self.slot['starts_at'].astimezone(ZoneInfo('Asia/Tokyo')).date().isoformat()
        return self.client.post('/api/catalog/party-availability', json={
            'city':'KYOTO', 'storeId':str(self.store), 'guests':self.body(count)['guests'],
            'from':day, 'to':day, **changes})

    def chosen(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        return next(s for s in response.json()['slots'] if s['slotId'] == str(self.slot['id']))

    def test_full_party_inventory_capacity_and_no_writes(self):
        def counts():
            return [self.connection.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n']
                    for table in ('booking_drafts','booking_quotes','availability_holds','inventory_allocations')]
        before = counts()
        self.assertTrue(self.chosen(self.query())['available'])
        self.connection.execute("UPDATE inventory_items SET status='MAINTENANCE' WHERE kimono_id=%s AND code<>%s",
                                (identifier('kimono','RKH0002'),'DEMO-RKH0002-001'))
        self.assertEqual(self.chosen(self.query())['reason'], 'INVENTORY_UNAVAILABLE')
        self.connection.execute('UPDATE availability_slots SET capacity_total=1 WHERE id=%s', (self.slot['id'],))
        self.assertEqual(self.chosen(self.query())['reason'], 'SLOT_FULL')
        self.assertEqual(counts(), before)

    def test_date_store_and_private_input_validation(self):
        for changes in [{'from':'2026-01-02','to':'2026-01-01'}, {'from':'2026-01-01','to':'2026-02-02'},
                        {'storeId':str(uuid4())}, {'city':'TOKYO'}, {'userId':str(uuid4())}, {'to':'9999-12-31'}]:
            self.assertEqual(self.query(**changes).status_code, 422)
        response = self.query()
        self.chosen(response)
        data = response.json()
        self.assertEqual(data['timezone'], 'Asia/Tokyo')
        self.assertFalse(data['inventoryReserved'])
        self.assertFalse(data['bookingCreated'])
        self.assertTrue(data['isDemo'])

    def test_closing_and_cleaning_period(self):
        # A real booking hold supplies the overlap; every row rolls back after this test.
        self.connection.execute("UPDATE inventory_items SET status='MAINTENANCE' WHERE kimono_id=%s AND code<>%s",
                                (identifier('kimono','RKH0002'),'DEMO-RKH0002-001'))
        self.connection.execute('UPDATE plans SET duration_minutes=60 WHERE id=%s', (self.body()['guests'][0]['planId'],))
        draft = booking_tests.BookingIntegrationTests.draft(self, self.body())
        quote = booking_tests.BookingIntegrationTests.quote(self, draft)
        self.assertEqual(quote.status_code, 200, quote.text)
        held = booking_tests.BookingIntegrationTests.hold(self, draft, quote.json())
        self.assertEqual(held.status_code, 201, held.text)
        later = uuid4()
        self.connection.execute('''INSERT INTO availability_slots(id,store_id,starts_at,ends_at,capacity_total,is_demo)
            VALUES (%s,%s,%s,%s,10,true)''', (later,self.store,self.slot['starts_at']+timedelta(minutes=65),self.slot['ends_at']+timedelta(minutes=65)))
        data = self.query(1).json()
        self.assertEqual(next(s for s in data['slots'] if s['slotId']==str(later))['reason'], 'INVENTORY_UNAVAILABLE')
        self.connection.execute("UPDATE store_booking_settings SET closes_at='00:01' WHERE store_id=%s", (self.store,))
        self.assertEqual(self.chosen(self.query(1))['reason'], 'RENTAL_AFTER_CLOSING')

    def test_mixed_plans_and_closed_slots(self):
        guests = self.body(3)['guests']
        guests[2] = self.body(1)['guests'][0]
        self.assertTrue(self.chosen(self.query(guests=guests))['available'])
        self.assertEqual(self.query(guests=guests[:1]).status_code, 422)  # incomplete GROUP package
        self.connection.execute("UPDATE availability_slots SET status='CLOSED' WHERE id=%s", (self.slot['id'],))
        self.assertEqual(self.chosen(self.query(guests=guests))['reason'], 'SLOT_CLOSED')
