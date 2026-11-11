import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from google.genai import types, errors
from app.integrations.vertex import generate_scene, GenerationError
from app.modules.try_on.worker import process_job
from tests import test_generations as fixtures


class SceneProviderTests(unittest.TestCase):
    def test_scene_list_and_generation_require_explicit_member_confirmation(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            self.assertEqual([row['name'] for row in client.get('/api/scenes').json()['data']],['櫻花','寺廟'])
            response=client.post('/api/try-on/jobs/'+str(uuid4())+'/scene-generations',json={'sceneId':'TEMPLE','confirmed':True})
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers['cache-control'],'no-store')

    @patch.dict(os.environ, {
        'GOOGLE_CLOUD_PROJECT': 'test-project',
        'VERTEX_SCENE_LOCATION': 'global',
        'VERTEX_SCENE_MODEL': 'gemini-nano-banana-2.1',
    })
    def test_one_image_edit_with_no_sampling_parameters_or_retry(self):
        with patch('app.integrations.vertex.genai.Client') as factory:
            client=factory.return_value.__enter__.return_value
            client.models.generate_content.return_value=types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(parts=[types.Part.from_bytes(data=fixtures.jpeg(),mime_type='image/jpeg')]))])
            self.assertTrue(generate_scene(fixtures.jpeg(),'Keep clothes; change background'))
            args=client.models.generate_content.call_args.kwargs
            self.assertEqual(args['model'],'gemini-nano-banana-2.1')
            self.assertEqual(factory.call_args.kwargs['location'],'global')
            self.assertEqual(factory.call_args.kwargs['http_options'].retry_options.attempts,1)
            self.assertEqual(args['config'].response_modalities,['IMAGE'])
            self.assertIsNone(args['config'].temperature)
            self.assertLess(len(args['contents'][0].inline_data.data),7*1024*1024)
            client.models.generate_content.side_effect=errors.ClientError(403,{'error':{'message':'private detail'}})
            with self.assertRaises(GenerationError) as error: generate_scene(fixtures.jpeg(),'temple')
            self.assertEqual(error.exception.code,'VERTEX_PERMISSION')


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class SceneIntegrationTests(unittest.TestCase):
    setUp=fixtures.GenerationIntegrationTests.setUp
    tearDown=fixtures.GenerationIntegrationTests.tearDown
    create=fixtures.GenerationIntegrationTests.create
    finish=fixtures.GenerationIntegrationTests.finish

    def scene(self,parent,scene='CHERRY_BLOSSOM',key=None,**extra):
        return self.client.post('/api/try-on/jobs/'+parent+'/scene-generations',
            json={'sceneId':scene,'confirmed':True,**extra},headers={'Idempotency-Key':key or str(uuid4())})

    def test_quota_cache_permissions_and_original_source(self):
        parent=self.create().json()['jobId']
        self.assertEqual(self.scene(parent).status_code,422)
        self.finish(parent,'SUCCEEDED')
        for extra in ({'confirmed':False},{'confirmed':'true'},{'force':True}):
            self.assertIn(self.scene(parent,**extra).status_code,(403,422))
        self.assertEqual(self.scene(parent,scene='UNKNOWN').status_code,422)
        key=str(uuid4());scene=self.scene(parent,key=key)
        self.assertEqual(scene.status_code,202,scene.text);scene_id=scene.json()['jobId']
        self.assertEqual(scene.json()['parentJobId'],parent)
        self.assertEqual(self.scene(parent,key=key).json()['jobId'],scene_id)
        self.assertEqual(self.scene(parent).json()['jobId'],scene_id)
        self.finish(scene_id,'SUCCEEDED')
        expires=self.connection.execute('SELECT expires_at FROM generation_jobs WHERE id=%s',(scene_id,)).fetchone()['expires_at']
        self.connection.execute('UPDATE generation_usage SET used=5 WHERE user_id=%s',(self.member,))
        with patch('app.modules.try_on.scenes.scene_configuration',side_effect=AssertionError('Cache does not need provider')):
            reused=self.scene(parent)
        self.assertTrue(reused.json()['reused']);self.assertEqual(reused.json()['jobId'],scene_id)
        self.assertEqual(self.connection.execute('SELECT expires_at FROM generation_jobs WHERE id=%s',(scene_id,)).fetchone()['expires_at'],expires)
        self.assertEqual(self.scene(parent,scene='TEMPLE').status_code,429)
        self.assertEqual(self.scene(scene_id).status_code,422)
        self.identity['uid']='other-scene-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        self.assertEqual(self.scene(parent).status_code,422)
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'],0)

    def test_worker_uses_original_result_and_scene_can_be_saved(self):
        parent=self.create().json()['jobId'];self.finish(parent,'SUCCEEDED')
        scene=self.scene(parent).json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(scene,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(scene,)).fetchone()
        parent_key=self.connection.execute('SELECT result_key FROM generation_jobs WHERE id=%s',(parent,)).fetchone()['result_key']
        @contextmanager
        def shared(): yield self.connection
        def provider(source,prompt,location,model,before_call):
            self.assertIn('cherry blossom',prompt);self.assertIn('obi belt',prompt);before_call();return fixtures.jpeg()
        with (patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage'),
              patch('app.modules.try_on.worker.s3_client'),patch('app.modules.try_on.worker.read_source',return_value=fixtures.jpeg()) as read,
              patch('app.modules.try_on.worker.generate_scene',side_effect=provider),patch('app.modules.try_on.worker.generate') as try_on):
            process_job(job);try_on.assert_not_called();self.assertEqual(read.call_args.args[1],parent_key)
        self.assertEqual(self.client.get('/api/try-on/jobs/'+scene).json()['status'],'SUCCEEDED')
        with patch('app.modules.try_on.service.result_url',return_value='https://example.com/scene.jpg'):
            saved=self.client.post('/api/looks',json={**self.selection,'participants':[
                {'id':'one','role':'FEMALE','kimonoId':self.selection['kimonoId'],'beltId':None,'generationId':scene}]})
            self.assertEqual(saved.status_code,201,saved.text)
            self.assertEqual(saved.json()['imageSource'],'GENERATION')
        self.identity['email_verified']=True
        self.client.put('/api/account',json={}).raise_for_status()
        phone='+8869'+str(uuid4().int % 100_000_000).zfill(8)
        self.connection.execute("UPDATE users SET display_name='Booking Test',phone_number=%s,phone_verified_at=now() WHERE id=%s",
                                (phone,self.member))
        draft=self.client.post('/api/booking-drafts',json={'guests':[{'planId':self.selection['planId'],
            'kimonoId':self.selection['kimonoId'],'guestType':'ADULT_FEMALE','generationId':scene}]})
        self.assertEqual(draft.status_code,201,draft.text)
        # Different scenes always retain the original TRY_ON parent.
        temple=self.scene(parent,scene='TEMPLE');self.assertEqual(temple.status_code,202,temple.text)
        self.assertEqual(temple.json()['parentJobId'],parent)
        self.finish(temple.json()['jobId'])
        self.client.delete('/api/try-on/generations/'+parent).raise_for_status()
        self.assertEqual(self.scene(parent).status_code,422)
        self.assertEqual(self.client.get('/api/try-on/jobs/'+scene).json()['status'],'SUCCEEDED')

    def test_failure_keeps_original_and_retry_uses_only_scene_quota(self):
        parent=self.create().json()['jobId'];self.finish(parent,'SUCCEEDED')
        scene=self.scene(parent).json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(scene,))
        job=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(scene,)).fetchone()
        @contextmanager
        def shared(): yield self.connection
        def provider(*args): args[-1]();raise GenerationError('PROVIDER_TIMEOUT')
        with (patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage'),
              patch('app.modules.try_on.worker.s3_client'),patch('app.modules.try_on.worker.read_source',return_value=fixtures.jpeg()),
              patch('app.modules.try_on.worker.generate_scene',side_effect=provider)):
            process_job(job)
        self.assertEqual(self.client.get('/api/try-on/jobs/'+scene).json()['status'],'FAILED')
        self.assertEqual(self.client.get('/api/try-on/jobs/'+parent).json()['status'],'SUCCEEDED')
        retried=self.scene(parent);self.assertEqual(retried.status_code,202,retried.text)
        self.assertNotEqual(retried.json()['jobId'],scene)
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'],3)
