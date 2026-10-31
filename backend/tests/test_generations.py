from app.core.config import RUNTIME_DIR
from app.core.config import DATA_DIR
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
from google.genai import errors

from app.main import app
from app.modules.accounts.dependencies import current_identity
from app.core.config import BACKEND_DIR
from app.core.database import connect, get_connection
from app.modules.try_on.service import day_bounds, result_url
from app.modules.try_on.worker import process_job
from app.modules.try_on.outfits import outfit_source
from commands.seeds.catalog import identifier
from app.integrations.vertex import GenerationError, clean_result, generate


def jpeg():
    output=BytesIO();Image.new('RGB',(800,1200),'white').save(output,'JPEG');return output.getvalue()


class GenerationUnitTests(unittest.TestCase):
    def test_tokyo_midnight_and_authentication(self):
        before=datetime(2026,10,17,14,59,tzinfo=timezone.utc)
        after=datetime(2026,10,17,15,0,tzinfo=timezone.utc)
        self.assertNotEqual(day_bounds(before)[0],day_bounds(after)[0])
        self.assertEqual(day_bounds(before)[1].hour,0)
        with TestClient(app) as client:
            for method,path in [('GET','/api/account/generation-usage'),('GET','/api/try-on/generations'),
                ('GET','/api/try-on/jobs/'+str(uuid4())),('DELETE','/api/try-on/generations/'+str(uuid4())),
                ('POST','/api/try-on/sessions/'+str(uuid4())+'/generations')]:
                response=client.request(method,path,json={} if method=='POST' else None)
                self.assertEqual(response.status_code,401)
                self.assertEqual(response.headers['cache-control'],'no-store')

    def test_provider_errors_are_sanitized_and_not_retried(self):
        with patch('app.integrations.vertex.genai.Client') as factory:
            client=factory.return_value.__enter__.return_value
            client.models.recontext_image.side_effect=errors.ClientError(403,{'error':{'message':'private provider detail','status':'PERMISSION_DENIED'}})
            with self.assertRaises(GenerationError) as error: generate(jpeg(),jpeg())
            self.assertEqual(error.exception.code,'VERTEX_PERMISSION')
            self.assertEqual(client.models.recontext_image.call_count,1)
            self.assertEqual(factory.call_args.kwargs['http_options'].retry_options.attempts,1)
        with self.assertRaises(GenerationError): clean_result(b'not an image')

    def test_sdk_uses_reference_person_product_and_one_image(self):
        from google.genai import types
        content=jpeg()
        with patch('app.integrations.vertex.genai.Client') as factory:
            client=factory.return_value.__enter__.return_value
            client.models.recontext_image.return_value=types.RecontextImageResponse(generated_images=[types.GeneratedImage(image=types.Image(image_bytes=content,mime_type='image/jpeg'))])
            result=generate(content,content)
            self.assertTrue(result)
            arguments=client.models.recontext_image.call_args.kwargs
            self.assertEqual(arguments['model'],'virtual-try-on-001')
            self.assertEqual(arguments['source'].person_image.image_bytes,content)
            self.assertEqual(arguments['source'].product_images[0].product_image.image_bytes,content)
            self.assertEqual(arguments['config'].number_of_images,1)


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class GenerationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection=connect();self.transaction=self.connection.transaction(force_rollback=True);self.transaction.__enter__()
        app.dependency_overrides[get_connection]=lambda:self.connection
        self.identity={'uid':'generation-test-'+str(uuid4()),'email':'generation-test@example.com','email_verified':False}
        app.dependency_overrides[current_identity]=lambda:self.identity
        self.client=TestClient(app)
        self.member=self.client.put('/api/account',json={}).json()['id']
        self.selection={'planId':str(UUID('30000000-0000-4000-8000-000000000011')),'kimonoId':str(identifier('kimono','RKH0002'))}
        self.model=self.client.get('/api/models').json()['data'][0]['id']
        session=self.client.post('/api/try-on/sessions',json={**self.selection,'source':'MODEL','modelId':self.model})
        self.assertEqual(session.status_code,201,session.text)
        self.path='/api/try-on/sessions/'+session.json()['sessionId']+'/generations'
        self.body={**self.selection,'modelId':self.model,'confirmed':True}
        self.preview=patch('app.modules.try_on.service.result_url',return_value=None);self.preview.start()

    def tearDown(self):
        self.preview.stop();self.client.close();app.dependency_overrides.clear();self.transaction.__exit__(None,None,None);self.connection.close()

    def create(self,key=None,body=None):
        return self.client.post(self.path,json=body or self.body,headers={'Idempotency-Key':key or str(uuid4())})

    def finish(self,job,status='FAILED'):
        self.connection.execute("UPDATE generation_jobs SET status=%s,completed_at=now(),expires_at=now()+interval '7 days' WHERE id=%s",(status,job))

    def test_confirmation_idempotency_and_atomic_quota(self):
        self.assertEqual(self.create(body={**self.body,'confirmed':False}).status_code,403)
        self.assertEqual(self.create(body={**self.body,'confirmed':'true'}).status_code,422)
        key=str(uuid4());created=self.create(key);self.assertEqual(created.status_code,202,created.text)
        self.assertEqual(self.create(key).json()['jobId'],created.json()['jobId'])
        self.assertEqual(self.create(key,body={**self.body,'modelId':str(uuid4())}).status_code,409)
        same=self.create();self.assertEqual(same.status_code,200,same.text)
        self.assertEqual(same.json()['jobId'],created.json()['jobId'])
        self.finish(created.json()['jobId'])
        for _ in range(4):
            response=self.create();self.assertEqual(response.status_code,202,response.text);self.finish(response.json()['jobId'])
        self.assertEqual(self.create().status_code,429)
        usage=self.client.get('/api/account/generation-usage').json()
        self.assertEqual(usage['website']['used'],5);self.assertEqual(usage['mcp']['used'],0)

    def test_all_nine_composites_and_missing_material_without_charge(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        belts=self.connection.execute('SELECT id,sku FROM accessories ORDER BY sku').fetchall()
        for sku in ['RKH0002','RKH0057','RKH0103']:
            for belt in belts:
                outfit=outfit_source(self.connection,identifier('kimono',sku),belt['id'])
                self.assertEqual(outfit['key'],f"assets/kimono-obi/{sku}_{belt['sku']}.png")
                with Image.open(BytesIO(outfit['content'])) as image:
                    self.assertEqual(image.format,'JPEG')
        plain=outfit_source(self.connection,identifier('kimono','RKH0002'))
        self.assertEqual(plain['key'],'catalog-media/kimono/RKH0002.webp')
        with TemporaryDirectory() as folder,patch('app.modules.try_on.outfits.DATA_DIR',Path(folder)):
            response=self.create(body={**self.body,'beltId':str(belts[0]['id'])})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(response.json()['error']['code'],'OUTFIT_IMAGE_UNAVAILABLE')
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'],0)
        self.assertEqual(self.create(body={**self.body,'force':True}).status_code,422)

    def test_reuse_across_sessions_and_plans_without_quota_or_expiry_extension(self):
        first=self.create().json();self.finish(first['jobId'],'SUCCEEDED')
        expires=self.connection.execute('SELECT expires_at FROM generation_jobs WHERE id=%s',(first['jobId'],)).fetchone()['expires_at']
        other_plan=str(uuid4())
        self.connection.execute('''INSERT INTO plans(id,slug,kimono_id,name,summary,description,audience,duration_minutes,base_price,included_items,is_demo,kind) SELECT %s,%s,kimono_id,name,summary,description,audience,duration_minutes,base_price,included_items,true,'SINGLE' FROM plans WHERE id=%s''',(other_plan,'reuse-test-'+other_plan,self.selection['planId']))
        self.connection.execute('INSERT INTO plan_stores(plan_id,store_id) SELECT %s,store_id FROM plan_stores WHERE plan_id=%s',(other_plan,self.selection['planId']))
        session=self.client.post('/api/try-on/sessions',json={**self.selection,'planId':other_plan,'source':'MODEL','modelId':self.model}).json()
        self.path='/api/try-on/sessions/'+session['sessionId']+'/generations'
        self.body={**self.body,'planId':other_plan}
        self.connection.execute("UPDATE generation_usage SET used=5 WHERE user_id=%s",(self.member,))
        with patch('app.modules.try_on.service.configuration',side_effect=AssertionError('Reuse must not need Vertex')):
            response=self.create()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['jobId'],first['jobId']);self.assertTrue(response.json()['reused'])
        self.assertEqual(self.connection.execute('SELECT expires_at FROM generation_jobs WHERE id=%s',(first['jobId'],)).fetchone()['expires_at'],expires)
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'],5)
        saved=self.client.post('/api/looks',json={**self.selection,'planId':other_plan,'generationId':first['jobId']})
        self.assertEqual(saved.status_code,201,saved.text)

    def test_outfit_and_person_versions_prevent_wrong_reuse(self):
        first=self.create().json()['jobId'];self.finish(first,'SUCCEEDED')
        belt='20000000-0000-4000-8000-000000000001'
        body={**self.body,'beltId':belt}
        response=self.create(body=body);self.assertEqual(response.status_code,202,response.text)
        second=response.json()['jobId'];self.finish(second,'SUCCEEDED')
        self.assertEqual(self.create(body=body).json()['jobId'],second)
        changed=outfit_source(self.connection,identifier('kimono','RKH0002'),UUID(belt))
        changed['sha256']='f'*64
        with patch('app.modules.try_on.service.outfit_source',return_value=changed):
            response=self.create(body=body)
        self.assertEqual(response.status_code,202,response.text)
        self.finish(response.json()['jobId'])
        self.connection.execute("UPDATE store_models SET source_key=source_key||'-new-version' WHERE id=%s",(self.model,))
        response=self.create();self.assertEqual(response.status_code,202,response.text)
        self.assertNotEqual(response.json()['jobId'],first);self.finish(response.json()['jobId'])
        mismatch=self.client.post('/api/looks',json={'planId':self.selection['planId'],'participants':[
            {'id':'guest_1','role':'FEMALE','kimonoId':self.selection['kimonoId'],'beltId':None,'generationId':second}]})
        self.assertEqual(mismatch.status_code,422,mismatch.text)

    def test_expired_deleted_failed_results_and_other_members_are_not_reused(self):
        old=self.create().json()['jobId'];self.finish(old,'SUCCEEDED')
        self.connection.execute("UPDATE generation_jobs SET expires_at=now()-interval '1 second' WHERE id=%s",(old,))
        for status in ['DELETED','FAILED','SUCCEEDED']:
            response=self.create();self.assertEqual(response.status_code,202,response.text)
            current=response.json()['jobId'];self.assertNotEqual(current,old)
            self.finish(current,status);old=current
        self.identity['uid']='another-member-'+str(uuid4())
        self.client.put('/api/account',json={}).raise_for_status()
        session=self.client.post('/api/try-on/sessions',json={**self.selection,'source':'MODEL','modelId':self.model}).json()
        self.path='/api/try-on/sessions/'+session['sessionId']+'/generations'
        response=self.create();self.assertEqual(response.status_code,202,response.text)
        self.assertNotEqual(response.json()['jobId'],old)

    def test_self_photo_reuse_requires_active_consent_even_for_idempotent_replay(self):
        from app.modules.try_on.photos import CONSENT_VERSION
        session=self.client.post('/api/try-on/sessions',json={**self.selection,'source':'SELF','consentAccepted':True,'consentVersion':CONSENT_VERSION}).json()
        photo_id=uuid4()
        self.connection.execute("""INSERT INTO person_photos(id,session_id,user_id,raw_key,source_key,content_type,
            expected_size,status,upload_expires_at) VALUES (%s,%s,%s,%s,%s,'image/jpeg',100,'FILE_READY',now()+interval '1 minute')""",
            (photo_id,session['sessionId'],self.member,'private/try-on/uploads/'+str(photo_id),'private/try-on/photos/'+str(photo_id)+'/source.jpg'))
        self.connection.execute('UPDATE try_on_sessions SET current_photo_id=%s WHERE id=%s',(photo_id,session['sessionId']))
        self.path='/api/try-on/sessions/'+session['sessionId']+'/generations'
        self.body={**self.selection,'photoId':str(photo_id),'confirmed':True}
        key=str(uuid4());job=self.create(key).json()['jobId'];self.finish(job,'SUCCEEDED')
        self.assertTrue(self.create().json()['reused'])
        shared=self.client.post('/api/try-on/sessions',json={**self.selection,'source':'SELF','photoId':str(photo_id)})
        self.assertEqual(shared.status_code,201,shared.text)
        shared_path='/api/try-on/sessions/'+shared.json()['sessionId']+'/generations'
        reused=self.client.post(shared_path,json=self.body,headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(reused.status_code,200,reused.text)
        self.assertEqual(reused.json()['jobId'],job);self.assertTrue(reused.json()['reused'])
        self.connection.execute('UPDATE try_on_sessions SET consent_revoked_at=now() WHERE id=%s',(session['sessionId'],))
        for request_key in [key,str(uuid4())]:
            response=self.create(request_key);self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(self.client.post(shared_path,json=self.body,headers={'Idempotency-Key':str(uuid4())}).status_code,404)
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'],1)

    def test_worker_sends_complete_composite_and_rejects_changed_source(self):
        belt='20000000-0000-4000-8000-000000000001'
        self.body={**self.body,'beltId':belt}
        job_id=self.create().json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(job_id,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        expected=outfit_source(self.connection,job['kimono_id'],job['belt_id'])['content']
        @contextmanager
        def shared(): yield self.connection
        def provider(person,clothing,location,model,before_call):
            self.assertEqual(clothing,expected);before_call();return jpeg()
        with (patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage'),
              patch('app.modules.try_on.worker.s3_client'),patch('app.modules.try_on.worker.read_source',return_value=jpeg()),
              patch('app.modules.try_on.worker.generate',side_effect=provider) as prediction):
            process_job(job);prediction.assert_called_once()
            self.assertEqual(self.create().json()['jobId'],job_id)
            self.body={**self.body,'beltId':'20000000-0000-4000-8000-000000000002'}
            changed_id=self.create().json()['jobId']
            self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',outfit_sha256=%s WHERE id=%s",('f'*64,changed_id))
            changed=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(changed_id,)).fetchone()
            prediction.reset_mock();process_job(changed);prediction.assert_not_called()
        row=self.connection.execute('SELECT status,failure_code,provider_calls FROM generation_jobs WHERE id=%s',(changed_id,)).fetchone()
        self.assertEqual(row,{'status':'FAILED','failure_code':'SOURCE_UNAVAILABLE','provider_calls':0})

    def test_owner_source_and_expired_result_protection(self):
        response=self.create(body={**self.body,'modelId':str(uuid4())});self.assertEqual(response.status_code,409)
        response=self.create();job=response.json()['jobId']
        self.finish(job,'SUCCEEDED')
        self.connection.execute("UPDATE generation_jobs SET expires_at=now()-interval '1 second' WHERE id=%s",(job,))
        data=self.client.get('/api/try-on/jobs/'+job).json()
        self.assertEqual(data['status'],'EXPIRED');self.assertIsNone(data['imageUrl'])
        website=self.client.get('/api/try-on/generations?source=WEBSITE').json()['data']
        self.assertEqual([item['jobId'] for item in website],[job])
        self.connection.execute("UPDATE generation_jobs SET source='MCP' WHERE id=%s",(job,))
        self.assertEqual(self.client.get('/api/try-on/generations?source=WEBSITE').json()['data'],[])
        self.assertEqual(self.client.get('/api/try-on/generations?source=MCP').json()['data'][0]['jobId'],job)
        self.identity['uid']='other-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        self.assertEqual(self.client.get('/api/try-on/jobs/'+job).status_code,404)
        self.assertEqual(self.client.delete('/api/try-on/generations/'+job).status_code,404)
        self.assertEqual(self.client.get('/api/try-on/generations').json()['data'],[])

    def test_worker_success_and_saved_result_fallback(self):
        job_id=self.create().json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(job_id,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        @contextmanager
        def shared(): yield self.connection
        def provider(person,clothing,location,model,before_call):
            before_call();return jpeg()
        with (patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage'),patch('app.modules.try_on.worker.s3_client') as storage,
                patch('app.modules.try_on.worker.read_source',return_value=jpeg()),patch('app.modules.try_on.worker.generate',side_effect=provider) as prediction):
            process_job(job)
            prediction.assert_called_once();storage.return_value.put_object.assert_called_once()
        row=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        self.assertEqual(row['status'],'SUCCEEDED');self.assertEqual(row['provider_calls'],1)
        with patch('app.modules.try_on.service.result_url',return_value='https://example.com/private-result'):
            participant_saved=self.client.post('/api/looks',json={'planId':self.selection['planId'],'participants':[
                {'id':'guest_1','role':'FEMALE','kimonoId':self.selection['kimonoId'],'beltId':None,'generationId':job_id}]})
            self.assertEqual(participant_saved.status_code,201,participant_saved.text)
            self.assertEqual(participant_saved.json()['imageSource'],'GENERATION')
            self.assertEqual(participant_saved.json()['imageUrl'],'https://example.com/private-result')
            saved=self.client.post('/api/looks',json={**self.selection,'generationId':job_id})
            self.assertEqual(saved.status_code,201,saved.text)
            self.assertEqual(saved.json()['imageSource'],'GENERATION')
            look_id=saved.json()['lookId']
        self.assertEqual(self.client.delete('/api/try-on/generations/'+job_id).status_code,202)
        fallback=self.client.get('/api/looks/'+look_id).json()
        self.assertEqual(fallback['imageSource'],'PRODUCT');self.assertEqual(fallback['generationStatus'],'DELETED')

    @unittest.skipUnless(os.getenv('RUN_PHOTO_STORAGE_TESTS')=='1','Opt-in real result storage test; no paid AI')
    def test_real_result_storage_preview_and_cleanup(self):
        import httpx
        from app.integrations.s3 import ensure_private_storage, remove_key
        from app.integrations.s3 import s3_client
        from app.modules.try_on.worker import cleanup_results
        versioned=ensure_private_storage();client=s3_client()
        job_id=self.create().json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(job_id,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        @contextmanager
        def shared(): yield self.connection
        def existing_result(person,clothing,location,model,before_call):
            before_call()
            # Reuse the already verified real SDK result; never issue another paid call.
            return (RUNTIME_DIR / 'verification'/'try-on-live.jpg').read_bytes()
        try:
            with (patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.generate',side_effect=existing_result),
                    patch('app.modules.try_on.service.result_url',wraps=result_url)):
                process_job(job)
                response=self.client.get('/api/try-on/jobs/'+job_id)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['status'],'SUCCEEDED')
                preview=httpx.get(response.json()['imageUrl'],timeout=20)
                self.assertEqual(preview.status_code,200)
                self.assertEqual(preview.headers['content-type'],'image/jpeg')
                self.assertEqual(self.client.delete('/api/try-on/generations/'+job_id).status_code,202)
                cleanup_results()
                row=self.connection.execute('SELECT cleanup_pending FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
                self.assertFalse(row['cleanup_pending'])
                self.assertIsNone(self.client.get('/api/try-on/jobs/'+job_id).json()['imageUrl'])
        finally:
            remove_key(client,job['result_key'],versioned)


@unittest.skipUnless(os.getenv('RUN_VERTEX_LIVE_TEST')=='1','Opt-in one paid Vertex prediction')
class VertexLiveTest(unittest.TestCase):
    def test_one_real_prediction(self):
        from app.modules.try_on.photos import normalize_photo
        person=normalize_photo((DATA_DIR / 'assets'/'default models'/'person-1.jpg').read_bytes(),'image/jpeg')[1]
        with connect() as connection:
            asset=connection.execute("SELECT image_key FROM product_assets WHERE kimono_id=%s AND kind='PRODUCT' AND active ORDER BY sort_order LIMIT 1",(identifier('kimono','RKH0002'),)).fetchone()
        from app.modules.catalog.media import read_product_image
        product=BytesIO()
        with Image.open(BytesIO(read_product_image(asset['image_key']))) as image: image.convert('RGB').save(product,'JPEG',quality=95)
        try: image=generate(person,product.getvalue())
        except GenerationError as error: self.fail('Vertex live check failed: '+error.code)
        folder=RUNTIME_DIR / 'verification';folder.mkdir(exist_ok=True)
        (folder/'try-on-live.jpg').write_bytes(image)
        self.assertGreater(len(image),1000)
