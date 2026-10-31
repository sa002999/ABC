import os
import unittest
from io import BytesIO
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from PIL import Image
from botocore.exceptions import ClientError
from app.main import app
from app.core.database import connect, get_connection
from app.modules.accounts.dependencies import current_identity
from app.modules.try_on.photos import CONSENT_VERSION
from app.modules.try_on.service import day_bounds
from app.modules.try_on.worker import process_job, cleanup_results


class McpTryOnBoundaryTests(unittest.TestCase):
    def test_private_routes_require_member_and_never_accept_channel_or_identity(self):
        app.dependency_overrides[get_connection] = lambda: None
        try:
            with TestClient(app) as client:
                for method,path in [('POST','/sources'),('POST','/prepare'),('POST','/confirm'),('GET','/jobs'),('GET','/jobs/'+str(uuid4())),('GET','/photo-consent'),('POST','/photo-uploads'),('POST','/photo-uploads/complete')]:
                    result=client.request(method,'/api/mcp/try-on'+path,json={} if method=='POST' else None)
                    self.assertEqual(result.status_code,401)
                    self.assertEqual(result.headers['cache-control'],'no-store')
        finally: app.dependency_overrides.clear()


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for rollback database tests')
class McpTryOnDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection=connect(); self.transaction=self.connection.transaction(force_rollback=True); self.transaction.__enter__()
        app.dependency_overrides[get_connection]=lambda:self.connection
        self.identity={'uid':'mcp-try-on-'+str(uuid4()),'email':'try-on@example.com','email_verified':True}
        app.dependency_overrides[current_identity]=lambda:self.identity
        self.client=TestClient(app)
        self.member=self.client.put('/api/account',json={}).json()['id']
        token=self.client.post('/api/account/mcp-token',json={'confirmed':True}).json()['token']
        self.headers={'Authorization':'Bearer '+token}
        self.plan=self.client.get('/api/plans?pageSize=50').json()['data'][0]['id']
        self.kimono=self.client.get('/api/kimonos',params={'plan':self.plan}).json()['data'][0]
        self.model=next(m for m in self.client.get('/api/models').json()['data'] if m['role']==self.kimono['gender'])['id']
        self.outfit={'planId':self.plan,'kimonoId':self.kimono['id'],'conversationId':str(uuid4())}
        self.source={**self.outfit,'source':'MODEL','modelId':self.model}
        self.patches=[patch('app.modules.try_on.service.result_url',return_value=None),patch('app.modules.try_on.photos.preview_url',return_value=None),
                      patch('app.modules.try_on.mcp.s3_client'),
                      patch('app.modules.try_on.service.configuration',return_value=('test-project','test-region','test-model'))]
        for p in self.patches:
            mocked=p.start()
            if hasattr(mocked,'return_value') and hasattr(mocked.return_value,'generate_presigned_url'):
                mocked.return_value.generate_presigned_url.return_value='https://test.s3.amazonaws.com/private/model.jpg?signature=test'

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.client.close();app.dependency_overrides.clear();self.transaction.__exit__(None,None,None);self.connection.close()

    def post(self,path,body):return self.client.post('/api/mcp/try-on/'+path,json=body,headers=self.headers)
    def prepare(self,body=None):
        result=self.post('prepare',body or self.source);self.assertEqual(result.status_code,201,result.text);return result.json()
    def confirm(self,review):return self.post('confirm',{'reviewId':review['reviewId'],'confirmed':True})
    def finish(self,job):self.connection.execute("UPDATE generation_jobs SET status='FAILED',completed_at=now() WHERE id=%s",(job,))

    def test_confirmation_quota_channel_retry_and_expired_review(self):
        sources=self.post('sources',self.outfit)
        self.assertEqual(sources.status_code,200,sources.text)
        self.assertTrue(sources.json()['models'])
        for extra in ({'channel':'WEBSITE'},{'userId':str(uuid4())},{'source':'MCP'}):
            self.assertEqual(self.post('sources',{**self.outfit,**extra}).status_code,422)
        review=self.prepare()
        self.assertEqual(review['usage']['mcp']['used'],0)
        self.assertEqual(self.post('confirm',{'reviewId':review['reviewId'],'confirmed':False}).status_code,403)
        self.assertEqual(self.post('confirm',{'reviewId':review['reviewId'],'confirmed':'true'}).status_code,422)
        first=self.confirm(review);self.assertEqual(first.status_code,202,first.text)
        job=first.json()['jobId']
        self.assertEqual(first.json()['source'],'MCP')
        self.assertEqual(self.confirm(review).json()['jobId'],job)
        self.assertEqual(self.post('sources',self.outfit).json()['usage']['mcp']['used'],1)
        self.finish(job)
        for _ in range(2):
            result=self.confirm(self.prepare());self.assertEqual(result.status_code,202,result.text);self.finish(result.json()['jobId'])
        self.assertEqual(self.confirm(self.prepare()).status_code,429)
        usage=self.post('sources',self.outfit).json()['usage']
        self.assertEqual(usage['mcp']['used'],3);self.assertEqual(usage['website']['used'],0)
        expired=self.prepare();self.connection.execute("UPDATE mcp_try_on_reviews SET expires_at=now()-interval '1 minute' WHERE id=%s",(expired['reviewId'],))
        self.assertEqual(self.confirm(expired).json()['error']['code'],'REVIEW_EXPIRED')
        midnight=self.prepare();self.connection.execute("UPDATE mcp_try_on_reviews SET usage_day=usage_day-1 WHERE id=%s",(midnight['reviewId'],))
        self.assertEqual(self.confirm(midnight).json()['error']['code'],'REVIEW_EXPIRED')

    def test_ownership_history_and_source_changes(self):
        review=self.prepare()
        self.connection.execute("UPDATE mcp_try_on_reviews SET material_version='changed' WHERE id=%s",(review['reviewId'],))
        self.assertEqual(self.confirm(review).json()['error']['code'],'SOURCE_CHANGED')
        good=self.prepare(); result=self.confirm(good);self.assertEqual(result.status_code,202,result.text)
        job=result.json()['jobId']
        history=self.client.get('/api/mcp/try-on/jobs',params={'conversation_id':self.outfit['conversationId']},headers=self.headers).json()['jobs']
        self.assertEqual([j['jobId'] for j in history],[job])
        self.assertEqual(self.client.get('/api/try-on/generations').json()['data'],[])
        self.identity['uid']='other-'+str(uuid4())
        self.client.put('/api/account',json={}).raise_for_status()
        other=self.client.post('/api/account/mcp-token',json={'confirmed':True}).json()['token']
        other_headers={'Authorization':'Bearer '+other}
        self.assertEqual(self.client.post('/api/mcp/try-on/confirm',json={'reviewId':good['reviewId'],'confirmed':True},headers=other_headers).status_code,404)
        self.assertEqual(self.client.get('/api/mcp/try-on/jobs/'+job,headers=other_headers).status_code,404)
        self.assertEqual(self.client.get('/api/mcp/try-on/jobs',headers=other_headers).json()['jobs'],[])

    def test_saved_photo_ownership_and_withdrawn_consent(self):
        # Build an already validated library entry without uploading/transmitting a real photo.
        session=self.client.post('/api/try-on/sessions',json={**self.outfit_without_conversation(),'source':'SELF','consentAccepted':True,'consentVersion':CONSENT_VERSION}).json()['sessionId']
        photo=uuid4();base=f'private/try-on/photos/{self.member}/{photo}'
        self.connection.execute('''INSERT INTO person_photos(id,session_id,user_id,raw_key,source_key,preview_key,content_type,expected_size,status,upload_expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,'image/jpeg',100,'READY',now()+interval '5 minutes')''',(photo,session,self.member,base+'/raw',base+'/source.jpg',base+'/preview.webp'))
        self.connection.execute('UPDATE try_on_sessions SET current_photo_id=%s WHERE id=%s',(photo,session))
        review=self.prepare({**self.outfit,'source':'SELF','photoId':str(photo)})
        self.connection.execute('UPDATE try_on_sessions SET consent_revoked_at=now() WHERE id=%s',(session,))
        self.assertEqual(self.confirm(review).status_code,404)
        self.assertEqual(self.post('sources',self.outfit).json()['usage']['mcp']['used'],0)
        self.assertEqual(self.post('prepare',{**self.outfit,'source':'SELF','photoId':str(uuid4())}).status_code,404)

    def outfit_without_conversation(self):return {k:v for k,v in self.outfit.items() if k!='conversationId'}

    def test_mcp_photo_upload_consent_verification_retry_and_member_isolation(self):
        image=BytesIO();Image.new('RGB',(800,1200),'white').save(image,'JPEG');content=image.getvalue()
        body={**self.outfit,'consentAccepted':True,'consentVersion':CONSENT_VERSION,'contentType':'image/jpeg','size':len(content)}
        self.assertEqual(self.client.get('/api/mcp/try-on/photo-consent',headers=self.headers).json()['version'],CONSENT_VERSION)
        for extra,status in [({'consentAccepted':False},403),({'consentAccepted':'true'},422),({'consentVersion':'stale'},403),({'size':10485761},422),({'userId':str(uuid4())},422),({'token':'forbidden'},422)]:
            self.assertEqual(self.post('photo-uploads',{**body,**extra}).status_code,status)
        with patch('app.modules.try_on.photos.ensure_private_storage',return_value=False), \
             patch('app.modules.try_on.photos.check_upload_cors',side_effect=AssertionError('No CORS changes for opaque signed form upload')), \
             patch('app.modules.try_on.photos.cleanup_photos'), \
             patch('app.modules.try_on.photos.pose_issue',return_value=None), \
             patch('app.modules.try_on.photos.s3_client') as s3:
            storage=s3.return_value
            storage.generate_presigned_post.return_value={'url':'https://test.s3.amazonaws.com/','fields':{'key':'private/try-on/uploads/test','policy':'synthetic-policy'}}
            upload=self.post('photo-uploads',body);self.assertEqual(upload.status_code,201,upload.text)
            ids={key:upload.json()[key] for key in ('sessionId','photoId')}
            self.assertEqual(upload.json()['upload']['method'],'POST')
            self.assertEqual(storage.generate_presigned_post.call_args.kwargs['ExpiresIn'],300)
            # An opaque browser response is not proof the object exists.
            storage.head_object.side_effect=ClientError({'Error':{'Code':'404'}},'HeadObject')
            self.assertEqual(self.post('photo-uploads/complete',ids).json()['error']['code'],'PHOTO_UPLOAD_MISSING')
            storage.head_object.side_effect=None;storage.head_object.return_value={'ContentLength':len(content)}
            storage.get_object.return_value={'Body':BytesIO(content)}
            completed=self.post('photo-uploads/complete',ids);self.assertEqual(completed.status_code,200,completed.text)
            self.assertEqual(completed.json()['photo']['status'],'READY')
            repeated=self.post('photo-uploads/complete',ids);self.assertEqual(repeated.json()['photo']['status'],'READY')
            self.assertEqual(storage.get_object.call_count,1)
            library=self.client.get('/api/try-on/photos').json()['data'];self.assertEqual([p['photoId'] for p in library],[ids['photoId']])
            self.assertEqual(self.connection.execute('SELECT count(*) AS n FROM generation_jobs WHERE user_id=%s',(self.member,)).fetchone()['n'],0)
            # A different authenticated member cannot finalize or discover this upload.
            self.identity['uid']='other-photo-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
            other=self.client.post('/api/account/mcp-token',json={'confirmed':True}).json()['token']
            result=self.client.post('/api/mcp/try-on/photo-uploads/complete',json=ids,headers={'Authorization':'Bearer '+other})
            self.assertEqual(result.status_code,404);self.assertEqual(storage.get_object.call_count,1)

    def test_mcp_upload_reservations_limit_and_rejected_photo_never_enters_library(self):
        body={**self.outfit,'consentAccepted':True,'consentVersion':CONSENT_VERSION,'contentType':'image/jpeg','size':12}
        with patch('app.modules.try_on.photos.ensure_private_storage',return_value=False), \
             patch('app.modules.try_on.photos.cleanup_photos'), \
             patch('app.modules.try_on.photos.s3_client') as s3:
            storage=s3.return_value;storage.generate_presigned_post.return_value={'url':'https://test.s3.amazonaws.com/','fields':{}}
            uploads=[self.post('photo-uploads',body) for _ in range(3)]
            self.assertEqual([r.status_code for r in uploads],[201,201,201])
            self.assertEqual(self.post('photo-uploads',body).json()['error']['code'],'PHOTO_UPLOAD_PENDING')
            # Two saved photos plus a failed upload must not claim three saved photos.
            saved_ids=[r.json()['photoId'] for r in uploads[:2]]
            self.connection.execute("UPDATE person_photos SET status='FILE_READY' WHERE id=ANY(%s::uuid[])", (saved_ids,))
            blocked=self.post('photo-uploads',body)
            self.assertEqual(blocked.json()['error']['code'],'PHOTO_UPLOAD_PENDING')
            self.assertIn('2 張照片',blocked.json()['error']['message'])
            self.assertIn('1 筆未完成',blocked.json()['error']['message'])
            self.connection.execute("UPDATE person_photos SET status='PENDING' WHERE id=ANY(%s::uuid[])", (saved_ids,))
            ids={key:uploads[0].json()[key] for key in ('sessionId','photoId')}
            storage.head_object.return_value={'ContentLength':12};storage.get_object.return_value={'Body':BytesIO(b'not an image')}
            rejected=self.post('photo-uploads/complete',ids)
            self.assertEqual(rejected.json()['photo']['status'],'REJECTED')
            self.assertEqual(self.client.get('/api/try-on/photos').json()['data'],[])
            self.assertEqual(self.post('photo-uploads',body).status_code,201)
            expired={key:uploads[1].json()[key] for key in ('sessionId','photoId')}
            self.connection.execute("UPDATE person_photos SET upload_expires_at=now()-interval '1 second' WHERE id=%s",(expired['photoId'],))
            self.assertEqual(self.post('photo-uploads/complete',expired).json()['photo']['status'],'REJECTED')
            self.assertEqual(self.connection.execute('SELECT count(*) AS n FROM generation_jobs WHERE user_id=%s',(self.member,)).fetchone()['n'],0)

    def test_worker_expiry_reuse_and_cleanup_without_paid_prediction(self):
        first=self.confirm(self.prepare());self.assertEqual(first.status_code,202,first.text)
        identity=first.json()['jobId']
        self.connection.execute("UPDATE generation_jobs SET status='VALIDATING',started_at=now() WHERE id=%s",(identity,))
        row=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(identity,)).fetchone()
        @contextmanager
        def shared():yield self.connection
        def fake_prediction(person,garment,location,model,before_call):before_call();return b'controlled-test-result'
        with patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage',return_value=False),patch('app.modules.try_on.worker.s3_client'),patch('app.modules.try_on.worker.read_source',return_value=b'controlled-person'),patch('app.modules.try_on.worker.generate',side_effect=fake_prediction) as provider:
            process_job(row);provider.assert_called_once()
        saved=self.connection.execute('SELECT * FROM generation_jobs WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(saved['status'],'SUCCEEDED');self.assertEqual(saved['expires_at'],day_bounds(saved['completed_at'])[1])
        reused=self.confirm(self.prepare());self.assertEqual(reused.json()['jobId'],identity)
        self.assertEqual(self.post('sources',self.outfit).json()['usage']['mcp']['used'],1)
        self.connection.execute("UPDATE generation_jobs SET expires_at=now()-interval '1 second' WHERE id=%s",(identity,))
        response=self.client.get('/api/mcp/try-on/jobs/'+identity,headers=self.headers).json()
        self.assertEqual(response['status'],'EXPIRED');self.assertIsNone(response['imageUrl'])
        with patch('app.modules.try_on.worker.connect',shared),patch('app.modules.try_on.worker.ensure_private_storage',return_value=False),patch('app.modules.try_on.worker.s3_client'),patch('app.modules.try_on.worker.remove_key') as remove:
            cleanup_results();remove.assert_called()
        saved=self.connection.execute('SELECT status,cleanup_pending FROM generation_jobs WHERE id=%s',(identity,)).fetchone()
        self.assertEqual(saved,{'status':'EXPIRED','cleanup_pending':False})
