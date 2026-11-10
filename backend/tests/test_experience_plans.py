import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import connect, get_connection
from app.modules.accounts.dependencies import current_identity


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class ExperiencePlanTests(unittest.TestCase):
    def test_catalog_and_booking_package_rules(self):
        with connect() as connection, connection.transaction(force_rollback=True):
            test_id=uuid4()
            app.dependency_overrides[get_connection]=lambda:connection
            app.dependency_overrides[current_identity]=lambda:{'uid':'plan-check-'+str(test_id),'email':'plans@example.com','email_verified':True}
            try:
                with TestClient(app) as client:
                    client.put('/api/account',json={}).raise_for_status()
                    phone='+8869'+str(test_id.int % 100_000_000).zfill(8)
                    connection.execute("UPDATE users SET display_name='Booking Test',phone_number=%s,phone_verified_at=now() WHERE firebase_uid=%s",
                                       (phone,'plan-check-'+str(test_id)))
                    catalog=client.get('/api/plans?pageSize=50').json()
                    self.assertEqual(catalog['total'],3)
                    plans={p['kind']:p for p in catalog['data']}
                    self.assertEqual(set(plans),{'SINGLE','COUPLE','GROUP'})
                    for kind,p in plans.items():
                        self.assertTrue(p['coverImageUrl'].startswith('/assets/plan-') or
                                        p['coverImageUrl'].startswith('https://') and '/catalog/' in p['coverImageUrl'])
                        self.assertTrue(p['stores'])
                        self.assertEqual(len(client.get('/api/kimonos',params={'plan':p['id']}).json()['data']),6)
                    store=plans['GROUP']['stores'][0]['id']
                    female=connection.execute("SELECT id FROM kimonos WHERE sku='RKH0002'").fetchone()['id']
                    male=connection.execute("SELECT id FROM kimonos WHERE sku='RKM0001'").fetchone()['id']
                    model=connection.execute("SELECT id FROM store_models WHERE active AND role='FEMALE' LIMIT 1").fetchone()['id']
                    for kind in ('SINGLE','COUPLE','GROUP'):
                        # Try-on operates on one traveler even when the package has multiple travelers.
                        session=client.post('/api/try-on/sessions',json={'planId':plans[kind]['id'],'kimonoId':str(female),'source':'MODEL','modelId':str(model)})
                        self.assertIn(session.status_code,(200,201),session.text)
                    for kind in ('COUPLE','GROUP'):
                        self.assertEqual(client.post('/api/looks',json={'planId':plans[kind]['id'],'kimonoId':str(female)}).status_code,422)
                    from app.modules.bookings.schemas import DraftInput
                    from app.modules.bookings.service import validate_draft
                    from app.modules.catalog.rules import pricing_lines
                    for kind,count,roles,expected in [
                        ('SINGLE',1,['FEMALE'],1500),('COUPLE',2,['FEMALE','MALE'],2800),
                        ('GROUP',2,['MALE','MALE'],2800),('GROUP',3,['FEMALE','MALE','FEMALE'],4200),
                    ]:
                        body=DraftInput.model_validate({'storeId':store,'guests':[
                            {'guestType':'ADULT_'+role,'planId':plans[kind]['id'],'kimonoId':str(female if role=='FEMALE' else male)} for role in roles]})
                        _,_,rows=validate_draft(connection,body,None)
                        self.assertEqual(sum(line['total'] for line in pricing_lines(body.guests,rows)),expected)
                    # API boundaries reject invalid packages, including unfinished outfits.
                    for kind,roles in [('SINGLE',['FEMALE','MALE']),('COUPLE',['FEMALE']),('COUPLE',['MALE','MALE']),('COUPLE',['FEMALE','MALE','FEMALE']),('GROUP',['FEMALE'])]:
                        response=client.post('/api/booking-drafts',json={'guests':[
                            {'guestType':'ADULT_'+role,'planId':plans[kind]['id']} for role in roles]})
                        self.assertEqual(response.status_code,422,response.text)
            finally:
                app.dependency_overrides.clear()
