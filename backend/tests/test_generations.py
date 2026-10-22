import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from google.genai import errors

from app import app
from auth import current_identity
from database import BACKEND_DIR, connect, get_connection
from generations import day_bounds, process_job, result_url
from seed_catalog import identifier
from vertex_try_on import GenerationError, clean_result, generate


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
        with patch('vertex_try_on.genai.Client') as factory:
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
        with patch('vertex_try_on.genai.Client') as factory:
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
        self.selection={'planId':str(identifier('plan','RKH0002')),'kimonoId':str(identifier('kimono','RKH0002'))}
        self.model=self.client.get('/api/models').json()['data'][0]['id']
        session=self.client.post('/api/try-on/sessions',json={**self.selection,'source':'MODEL','modelId':self.model})
        self.assertEqual(session.status_code,201,session.text)
        self.path='/api/try-on/sessions/'+session.json()['sessionId']+'/generations'
        self.body={**self.selection,'modelId':self.model,'confirmed':True}
        self.preview=patch('generations.result_url',return_value=None);self.preview.start()

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
        self.assertEqual(self.create().status_code,409)
        self.finish(created.json()['jobId'])
        for _ in range(4):
            response=self.create();self.assertEqual(response.status_code,202,response.text);self.finish(response.json()['jobId'])
        self.assertEqual(self.create().status_code,429)
        usage=self.client.get('/api/account/generation-usage').json()
        self.assertEqual(usage['website']['used'],5);self.assertEqual(usage['mcp']['used'],0)

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
        with (patch('generations.connect',shared),patch('generations.ensure_private_storage'),patch('generations.s3_client') as storage,
                patch('generations.read_source',return_value=jpeg()),patch('generations.generate',side_effect=provider) as prediction):
            process_job(job)
            prediction.assert_called_once();storage.return_value.put_object.assert_called_once()
        row=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        self.assertEqual(row['status'],'SUCCEEDED');self.assertEqual(row['provider_calls'],1)
        with patch('generations.result_url',return_value='https://example.com/private-result'):
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
        from photo_storage import ensure_private_storage, remove_key
        from storage import s3_client
        from generations import cleanup_results
        versioned=ensure_private_storage();client=s3_client()
        job_id=self.create().json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(job_id,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(job_id,)).fetchone()
        @contextmanager
        def shared(): yield self.connection
        def existing_result(person,clothing,location,model,before_call):
            before_call()
            # Reuse the already verified real SDK result; never issue another paid call.
            return (BACKEND_DIR/'verification'/'try-on-live.jpg').read_bytes()
        try:
            with (patch('generations.connect',shared),patch('generations.generate',side_effect=existing_result),
                    patch('generations.result_url',wraps=result_url)):
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
        from photo_checks import normalize_photo
        person=normalize_photo((BACKEND_DIR/'assets'/'default models'/'person-1.jpg').read_bytes(),'image/jpeg')[1]
        with connect() as connection:
            asset=connection.execute("SELECT image_key FROM product_assets WHERE kimono_id=%s AND kind='PRODUCT' AND active ORDER BY sort_order LIMIT 1",(identifier('kimono','RKH0002'),)).fetchone()
        from storage import read_product_image
        product=BytesIO()
        with Image.open(BytesIO(read_product_image(asset['image_key']))) as image: image.convert('RGB').save(product,'JPEG',quality=95)
        try: image=generate(person,product.getvalue())
        except GenerationError as error: self.fail('Vertex live check failed: '+error.code)
        folder=BACKEND_DIR/'verification';folder.mkdir(exist_ok=True)
        (folder/'try-on-live.jpg').write_bytes(image)
        self.assertGreater(len(image),1000)
