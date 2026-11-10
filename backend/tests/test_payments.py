import os
import unittest
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app
from app.core.database import connect,get_connection
from app.modules.accounts.dependencies import current_identity,current_member
from app.modules.bookings import payments
from app.modules.bookings.rules import utcnow
from app.modules.bookings.schemas import PaymentInput
from app.integrations import tappay_service as tappay


class PaymentVerificationTests(unittest.TestCase):
    def test_strict_transaction_match_and_states(self):
        order={'merchant_id':'m','bank_transaction_id':'B','total':1500,'order_no':'KT1','rec_trade_id':None}
        record={'merchant_id':'m','bank_transaction_id':'B','amount':1500,'order_number':'KT1','currency':'TWD','rec_trade_id':'r','record_status':0}
        self.assertEqual(payments.verified_status(order,record),'AUTHORIZED')
        for field in ('merchant_id','bank_transaction_id','amount','currency','rec_trade_id','order_number'):
            self.assertEqual(payments.verified_status(order,{**record,field:None}),'REVIEW_REQUIRED')
        for state,status in [(1,'PAID'),(4,'PAYMENT_PENDING'),(-1,'FAILED'),(5,'FAILED'),(3,'REVIEW_REQUIRED')]:
            self.assertEqual(payments.verified_status(order,{**record,'record_status':state}),status)

    def test_production_endpoint_is_rejected(self):
        with patch.dict(os.environ,{'TAPPAY_ENDPOINT':'https://prod.tappaysdk.com/tpc/payment/pay-by-prime'}):
            self.assertFalse(tappay.configured())
            with self.assertRaises(tappay.TapPayConfigurationError): tappay.request('payment/pay-by-prime',{})


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1')
class PaymentIntegrationTests(unittest.TestCase):
    """Session-local temporary tables allow real commits without touching member records."""
    def setUp(self):
        self.c=connect()
        for table in ('booking_drafts','availability_holds','inventory_allocations','payment_orders','bookings'):
            self.c.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.c.execute('CREATE TEMP TABLE users(id uuid PRIMARY KEY,email text,email_verified boolean,display_name text,phone_number text,phone_verified_at timestamptz)')
        self.c.execute('CREATE TEMP TABLE stores(id uuid PRIMARY KEY)')
        self.c.execute('CREATE TEMP TABLE kimonos(id uuid PRIMARY KEY,name jsonb)')
        self.c.execute('CREATE TEMP TABLE accessories(id uuid PRIMARY KEY,name jsonb)')
        self.member=uuid4();self.store=uuid4();self.hold=uuid4();self.quote=uuid4();self.draft=uuid4();self.garment=uuid4()
        self.c.execute("INSERT INTO users VALUES (%s,'test@example.com',true,'Sandbox Test','+886912345678',now())",(self.member,));self.c.execute('INSERT INTO stores VALUES (%s)',(self.store,))
        self.c.execute('INSERT INTO kimonos VALUES (%s,%s)',(self.garment,Jsonb({'zh-Hant':'測試和服'})))
        data={'contactMode':'member','contactName':'Sandbox Test','contactEmail':'test@example.com','contactPhone':'+886912345678',
              'guests':[{'guestType':'ADULT_FEMALE','kimonoId':str(self.garment),'accessoryIds':[]}]}
        self.c.execute('INSERT INTO booking_drafts(id,user_id,data) VALUES (%s,%s,%s)',(self.draft,self.member,Jsonb(data)))
        snap={'storeName':'測試門市','startsAt':(utcnow()+timedelta(days=10)).isoformat(),'lineItems':[{'guestIndex':0,'name':'測試方案','total':1500}]}
        self.c.execute('''INSERT INTO availability_holds(id,user_id,draft_id,draft_version,quote_id,store_id,slot_id,party_size,idempotency_key,request_hash,total,snapshot)
            VALUES (%s,%s,%s,1,%s,%s,%s,1,%s,'test',1500,%s)''',(self.hold,self.member,self.draft,self.quote,self.store,uuid4(),uuid4(),Jsonb(snap)))
        self.c.execute('''INSERT INTO inventory_allocations(id,inventory_id,hold_id,guest_index,rental_starts_at,rental_ends_at,cleaning_ends_at)
            VALUES (%s,%s,%s,0,now()+interval '10 days',now()+interval '10 days 8 hours',now()+interval '10 days 10 hours')''',(uuid4(),uuid4(),self.hold))
        self.c.commit()
        self.body=PaymentInput(holdId=self.hold,quoteToken=self.quote,prime='never-persist-this-prime',acceptedPolicy=True,policyVersion=payments.POLICY_VERSION)
        self.env=patch.dict(os.environ,{'TAPPAY_PARTNER_KEY':'test-key','TAPPAY_MERCHANT_ID':'test-merchant','TAPPAY_ENDPOINT':tappay.BASE+'payment/pay-by-prime'});self.env.start()
        self.pay=patch.object(tappay,'pay_by_prime',return_value={'status':0,'rec_trade_id':'TRADE1'}).start()
        self.query=patch.object(tappay,'records',side_effect=self.record).start()

    def tearDown(self):
        patch.stopall();self.env.stop();app.dependency_overrides.clear();self.c.close()

    def record(self,row):
        return {'status':0,'trade_records':[{'merchant_id':row['merchant_id'],'bank_transaction_id':row['bank_transaction_id'],
            'order_number':row['order_no'],'amount':row['total'],'currency':'TWD','rec_trade_id':'TRADE1','record_status':0}]}

    def submit(self,key=None,body=None):
        return payments.submit(self.c,self.member,{'email_verified':True},body or self.body,key or uuid4())

    def status(self): return self.c.execute('SELECT status FROM availability_holds WHERE id=%s',(self.hold,)).fetchone()['status']

    def test_authorized_confirmed_once_and_captured_same_booking(self):
        key=uuid4();first=self.submit(key);second=self.submit(key);third=self.submit()
        self.assertEqual(first,second);self.assertEqual(first,third);self.assertEqual(self.pay.call_count,1)
        self.assertEqual(first['paymentStatus'],'AUTHORIZED');self.assertTrue(first['bookingNo']);self.assertEqual(self.status(),'RESERVED')
        self.c.execute("UPDATE payment_orders SET checked_at=now()-interval '1 minute'");self.c.commit()
        self.query.side_effect=lambda row:{'status':0,'trade_records':[{**self.record(row)['trade_records'][0],'record_status':1}]}
        payments.reconcile(self.c,first['orderNo'])
        updated=payments.order_data(self.c,payments.owned_order(self.c,first['orderNo'],self.member))
        self.assertEqual(updated['paymentStatus'],'PAID');self.assertEqual(updated['bookingNo'],first['bookingNo'])
        detail=payments.bookings(self.c,self.member,first['bookingNo']);self.assertEqual(detail['guests'][0]['kimonoName'],'測試和服')
        stored=self.c.execute('SELECT row_to_json(o)::text AS data FROM payment_orders o').fetchone()['data']
        self.assertNotIn('never-persist',stored)

    def test_timeout_and_no_record_never_resend_or_expire(self):
        self.pay.side_effect=tappay.TapPayRequestError();first=self.submit()
        self.assertEqual(first['paymentStatus'],'PAYMENT_PENDING');self.assertEqual(self.status(),'PAYMENT_PENDING')
        self.c.execute("UPDATE availability_holds SET expires_at=now()-interval '1 minute'")
        self.query.side_effect=None;self.query.return_value={'status':2,'trade_records':[]}
        payments.reconcile(self.c,first['orderNo']);self.submit()
        self.assertEqual(self.pay.call_count,1);self.assertEqual(self.status(),'PAYMENT_PENDING')
        from app.modules.bookings.service import get_hold
        self.assertEqual(get_hold(self.hold,self.member,self.c)['orderNo'],first['orderNo'])

    def test_concurrent_different_keys_send_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from psycopg import sql
        schema='payment_test_'+uuid4().hex
        tables=('users','stores','kimonos','accessories','booking_drafts','availability_holds','inventory_allocations','payment_orders','bookings')
        self.c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            for table in tables:
                self.c.execute(sql.SQL('CREATE TABLE {}.{} (LIKE pg_temp.{} INCLUDING ALL)').format(sql.Identifier(schema),sql.Identifier(table),sql.Identifier(table)))
                self.c.execute(sql.SQL('INSERT INTO {}.{} SELECT * FROM pg_temp.{}').format(sql.Identifier(schema),sql.Identifier(table),sql.Identifier(table)))
            self.c.commit()
            def submit(_):
                with connect() as connection:
                    connection.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(schema)))
                    # Wait for the first thread's durable order; default production timeout is only 5s.
                    connection.execute('SET statement_timeout=30000')
                    return payments.submit(connection,self.member,{'email_verified':True},self.body,uuid4())
            with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(submit,range(4)))
            self.assertEqual(self.pay.call_count,1)
            self.assertEqual(len({r['orderNo'] for r in results}),1)
            self.assertEqual(self.c.execute(sql.SQL('SELECT count(*) AS n FROM {}.bookings').format(sql.Identifier(schema))).fetchone()['n'],1)
        finally:
            self.c.rollback()
            self.c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            self.c.commit()

    def test_mismatch_blocks_booking_and_retains_resources(self):
        self.query.side_effect=lambda row:{'status':0,'trade_records':[{**self.record(row)['trade_records'][0],'amount':1}]}
        result=self.submit();self.assertEqual(result['paymentStatus'],'REVIEW_REQUIRED');self.assertIsNone(result['bookingNo'])
        self.assertEqual(self.status(),'PAYMENT_PENDING')

    def test_verified_failure_releases_allocation(self):
        self.query.side_effect=lambda row:{'status':0,'trade_records':[{**self.record(row)['trade_records'][0],'record_status':-1}]}
        result=self.submit();self.assertEqual(result['paymentStatus'],'FAILED');self.assertIsNone(result['bookingNo'])
        self.assertEqual(self.status(),'RELEASED');self.assertEqual(self.c.execute('SELECT status FROM inventory_allocations').fetchone()['status'],'RELEASED')

    def test_paid_without_resources_requires_refund(self):
        self.pay.side_effect=tappay.TapPayRequestError();result=self.submit()
        self.c.execute("UPDATE inventory_allocations SET status='RELEASED'");self.c.commit()
        payments.reconcile(self.c,result['orderNo'])
        row=payments.owned_order(self.c,result['orderNo'],self.member)
        self.assertEqual(row['status'],'REFUND_REQUIRED');self.assertIsNone(payments.order_data(self.c,row)['bookingNo'])

    def test_expiry_policy_email_and_quote_rejected_before_payment(self):
        variants=[self.body.model_copy(update={'accepted_policy':False}),self.body.model_copy(update={'quote_token':uuid4()}),self.body.model_copy(update={'policy_version':'old'})]
        for body in variants:
            with self.assertRaises(HTTPException): self.submit(body=body)
        with self.assertRaises(HTTPException): payments.submit(self.c,self.member,{},self.body,uuid4())
        self.c.execute("UPDATE availability_holds SET expires_at=now()-interval '1 second'")
        with self.assertRaises(HTTPException): self.submit()
        self.pay.assert_not_called()

    def test_http_owner_isolation_recovery_and_no_store(self):
        app.dependency_overrides[get_connection]=lambda:self.c
        app.dependency_overrides[current_member]=lambda:self.member
        app.dependency_overrides[current_identity]=lambda:{'email_verified':True}
        with TestClient(app) as client:
            result=client.post('/api/bookings',json=self.body.model_dump(mode='json',by_alias=True),headers={'Idempotency-Key':str(uuid4())})
            self.assertEqual(result.status_code,200,result.text);data=result.json()
            self.assertEqual(client.get('/api/bookings').json()['data'][0]['bookingNo'],data['bookingNo'])
            self.assertEqual(client.get('/api/orders/'+data['orderNo']).headers['cache-control'],'no-store')
            other=uuid4();app.dependency_overrides[current_member]=lambda:other
            self.assertEqual(client.get('/api/orders/'+data['orderNo']).status_code,404)
            self.assertEqual(client.get('/api/bookings/'+data['bookingNo']).status_code,404)
            self.assertEqual(client.get('/api/bookings').json()['data'],[])

    @unittest.skipUnless(os.getenv('RUN_TAPPAY_SANDBOX_TEST')=='1','Explicit opt-in sends one real Sandbox test payment')
    def test_real_sandbox_payment(self):
        # Restore actual local Sandbox credentials, while retaining synthetic temp-table fixtures.
        patch.stopall()
        self.assertTrue(tappay.configured())
        body=self.body.model_copy(update={'prime':'test_3a2fb2b7e892b914a03c95dd4dd5dc7970c908df67a49527c0a648b2bc9'})
        original=tappay.pay_by_prime
        def observed(*args):
            response=original(*args)
            print('Sandbox Pay API code:',response.get('status'),'trade ID returned:',bool(response.get('rec_trade_id')),'provider time:',response.get('millis'),flush=True)
            return response
        with patch.object(tappay,'pay_by_prime',side_effect=observed): result=self.submit(body=body)
        if result['paymentStatus']=='PAYMENT_PENDING':
            import time
            for _ in range(3):
                time.sleep(5)
                self.c.execute("UPDATE payment_orders SET checked_at=now()-interval '1 minute'");self.c.commit()
                payments.reconcile(self.c,result['orderNo'])
                result=payments.order_data(self.c,payments.owned_order(self.c,result['orderNo'],self.member))
                if result['paymentStatus']!='PAYMENT_PENDING': break
        print('Sandbox verification:',result['paymentStatus'],'booking created:',bool(result['bookingNo']),flush=True)
        if result['paymentStatus'] not in ('AUTHORIZED','PAID'):
            row=payments.owned_order(self.c,result['orderNo'],self.member)
            response=tappay.records(row)
            print('Record query code:',response.get('status'),'record count:',len(response.get('trade_records',[])),flush=True)
            for record in response.get('trade_records',[]):
                print('Record fields:',','.join(sorted(record.keys())),'status:',record.get('record_status'),flush=True)
        self.assertIn(result['paymentStatus'],('AUTHORIZED','PAID'))
        self.assertTrue(result['bookingNo'])


if __name__=='__main__': unittest.main()
