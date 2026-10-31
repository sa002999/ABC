import os
import unittest
from io import BytesIO
from unittest.mock import patch
from uuid import UUID, uuid4

from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.modules.accounts.dependencies import current_identity
from app.core.database import connect, get_connection
from app.modules.try_on.photos import InvalidPhoto, normalize_photo
from app.modules.try_on.photos import CONSENT_VERSION
from commands.seeds.catalog import identifier


def image_bytes(size=(800, 1200), format='JPEG', **options):
    output = BytesIO()
    Image.new('RGB', size, 'white').save(output, format, **options)
    return output.getvalue()


class PhotoFileTests(unittest.TestCase):
    def test_decode_metadata_orientation_and_formats(self):
        exif = Image.Exif(); exif[274] = 6; exif[315] = 'private author'
        clean, content = normalize_photo(image_bytes(exif=exif), 'image/jpeg')
        self.assertEqual(clean.size, (1200, 800))
        self.assertFalse(Image.open(BytesIO(content)).getexif())
        for format, mime in [('PNG', 'image/png'), ('HEIF', 'image/heic')]:
            self.assertEqual(normalize_photo(image_bytes(format=format), mime)[0].size, (800, 1200))

    def test_reject_bad_format_size_and_resolution(self):
        for content, mime, code in [
            (b'not an image', 'image/jpeg', 'UNSUPPORTED_FILE'),
            (image_bytes(), 'image/png', 'UNSUPPORTED_FILE'),
            (image_bytes((300, 500)), 'image/jpeg', 'LOW_RESOLUTION'),
            (image_bytes((1, 6001)), 'image/jpeg', 'HIGH_RESOLUTION'),
            (b'0' * (10 * 1024 * 1024 + 1), 'image/jpeg', 'FILE_TOO_LARGE')]:
            with self.assertRaises(InvalidPhoto) as error:
                normalize_photo(content, mime)
            self.assertIn(code, error.exception.codes)

    def test_private_routes_require_authentication(self):
        session = str(uuid4())
        with TestClient(app) as client:
            for method, suffix, body in [('GET', '', None), ('POST', '', {}),
                    ('GET', '/'+session, None), ('POST', '/'+session+'/upload-url', {}),
                    ('POST', '/'+session+'/validate', {}), ('DELETE', '/'+session+'/photo', None)]:
                response = client.request(method, '/api/try-on/sessions'+suffix, json=body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['cache-control'], 'no-store')
            for method,path in [('GET','/api/try-on/photos'),('DELETE','/api/try-on/photos/'+str(uuid4()))]:
                response=client.request(method,path)
                self.assertEqual(response.status_code,401)
                self.assertEqual(response.headers['cache-control'],'no-store')


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS') == '1', 'Set RUN_DATABASE_TESTS=1 for RDS')
class PersonSourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect()
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        app.dependency_overrides[get_connection] = lambda: self.connection
        self.identity = {'uid':'photo-test-'+str(uuid4()), 'email':'photo-test@example.com', 'email_verified':False}
        app.dependency_overrides[current_identity] = lambda: self.identity
        self.client = TestClient(app)
        self.client.put('/api/account', json={}).raise_for_status()
        self.patches = [patch('app.modules.try_on.photos.ensure_private_storage', return_value=False),
            patch('app.modules.try_on.photos.check_upload_cors'), patch('app.modules.try_on.photos.cleanup_photos'),
            patch('app.modules.try_on.photos.preview_url', return_value='https://example.com/private-preview'),
            patch('app.modules.try_on.photos.pose_issue', return_value=None),
            patch('app.modules.try_on.photos.s3_client')]
        self.mocks = [p.start() for p in self.patches]
        self.storage = self.mocks[-1].return_value
        self.pose = self.mocks[-2]
        self.storage.generate_presigned_post.return_value = {'url':'https://example.com/upload','fields':{'key':'private/test'}}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        app.dependency_overrides.clear()
        self.transaction.__exit__(None, None, None)
        self.connection.close()

    def selection(self):
        return {'planId':str(UUID('30000000-0000-4000-8000-000000000011')), 'kimonoId':str(identifier('kimono','RKH0002'))}

    def create(self):
        response = self.client.post('/api/try-on/sessions', json={**self.selection(), 'source':'SELF',
            'consentAccepted':True, 'consentVersion':CONSENT_VERSION})
        self.assertEqual(response.status_code, 201, response.text)
        return '/api/try-on/sessions/'+response.json()['sessionId']

    def upload(self, path, content, replace_id=None):
        response = self.client.post(path+'/upload-url', json={'contentType':'image/jpeg','size':len(content),'fileName':'test.jpg','replacePhotoId':replace_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.storage.head_object.return_value = {'ContentLength':len(content)}
        self.storage.get_object.return_value = {'Body':BytesIO(content)}
        result = self.client.post(path+'/validate', json={'photoId':response.json()['photoId']})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_consent_ownership_and_public_models(self):
        response = self.client.post('/api/try-on/sessions', json={**self.selection(),'source':'SELF'})
        self.assertEqual(response.status_code, 403)
        models = self.client.get('/api/models').json()['data']
        self.assertEqual(len(models), 6)
        self.assertEqual([m['role'] for m in models].count('FEMALE'),3)
        self.assertEqual([m['role'] for m in models].count('MALE'),3)
        self.assertNotIn('sourceKey', models[0])
        model = self.client.post('/api/try-on/sessions', json={**self.selection(),'source':'MODEL','modelId':models[0]['id']})
        self.assertEqual(model.status_code, 201, model.text)
        path = self.create()
        listed = self.client.get('/api/try-on/sessions?page=0')
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual({item['sessionId'] for item in listed.json()['data']},
                         {model.json()['sessionId'], path.rsplit('/', 1)[-1]})
        self.identity['uid'] = 'other-'+str(uuid4())
        self.client.put('/api/account', json={}).raise_for_status()
        for method, suffix, body in [('GET','',None),('PATCH','',self.selection()),('DELETE','/photo',None),
            ('POST','/upload-url',{'contentType':'image/jpeg','size':100,'fileName':'x.jpg'}),
            ('POST','/validate',{'photoId':str(uuid4())})]:
            self.assertEqual(self.client.request(method,path+suffix,json=body).status_code,404)

    def test_library_limit_targeted_replacement_and_shared_originals(self):
        first=self.upload(self.create(),image_bytes())
        second=self.upload(self.create(),image_bytes())
        third=self.upload(self.create(),image_bytes())
        original_ids={p['photoId'] for p in [first,second,third]}
        self.assertEqual({p['photoId'] for p in self.client.get('/api/try-on/photos').json()['data']},original_ids)
        extra=self.create()
        ticket=self.client.post(extra+'/upload-url',json={'contentType':'image/jpeg','size':100,'fileName':'fourth.jpg'})
        self.assertEqual(ticket.status_code,409,ticket.text)
        self.assertEqual(ticket.json()['error']['code'],'PHOTO_LIMIT_REACHED')
        shared=self.client.post('/api/try-on/sessions',json={**self.selection(),'source':'SELF','photoId':second['photoId']})
        self.assertEqual(shared.status_code,201,shared.text)
        self.assertEqual(shared.json()['photo']['photoId'],second['photoId'])
        rejected=self.upload(extra,b'bad image',second['photoId'])
        self.assertEqual(rejected['status'],'REJECTED')
        self.assertEqual({p['photoId'] for p in self.client.get('/api/try-on/photos').json()['data']},original_ids)
        replacement=self.upload(extra,image_bytes(),second['photoId'])
        current=self.client.get('/api/try-on/photos').json()['data']
        self.assertEqual({p['photoId'] for p in current},{first['photoId'],third['photoId'],replacement['photoId']})
        self.assertIsNone(self.client.get('/api/try-on/sessions/'+shared.json()['sessionId']).json()['photo'])
        self.assertEqual(self.connection.execute('SELECT status FROM person_photos WHERE id=%s',(second['photoId'],)).fetchone()['status'],'DELETED')
        self.assertEqual(self.client.delete('/api/try-on/photos/'+third['photoId']).status_code,202)
        self.assertEqual(len(self.client.get('/api/try-on/photos').json()['data']),2)
        self.assertEqual(self.upload(self.create(),image_bytes())['status'],'READY')

    def test_library_is_private_and_only_originals_are_accepted(self):
        photo=self.upload(self.create(),image_bytes())
        self.assertEqual(self.client.post('/api/try-on/sessions',json={**self.selection(),'source':'SELF','photoId':str(uuid4())}).status_code,404)
        models=self.client.get('/api/models').json()['data']
        male=next(m for m in models if m['role']=='MALE')
        mismatch=self.client.post('/api/try-on/sessions',json={**self.selection(),'source':'MODEL','modelId':male['id']})
        self.assertEqual(mismatch.status_code,422,mismatch.text)
        male_selection={**self.selection(),'kimonoId':str(identifier('kimono','RKM0001'))}
        self.assertEqual(self.client.post('/api/try-on/sessions',json={**male_selection,'source':'MODEL','modelId':male['id']}).status_code,201)
        self.identity['uid']='other-library-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        self.assertEqual(self.client.get('/api/try-on/photos').json()['data'],[])
        self.assertEqual(self.client.delete('/api/try-on/photos/'+photo['photoId']).status_code,404)
        self.assertEqual(self.client.post('/api/try-on/sessions',json={**self.selection(),'source':'SELF','photoId':photo['photoId']}).status_code,404)
        path=self.create()
        response=self.client.post(path+'/upload-url',json={'contentType':'image/jpeg','size':100,'fileName':'x.jpg','replacePhotoId':photo['photoId']})
        self.assertEqual(response.status_code,404)

    def test_upload_rejection_replacement_reuse_and_withdrawal(self):
        path = self.create()
        first = self.upload(path,image_bytes())
        self.assertEqual(first['status'],'READY')
        self.assertEqual(first['qualityStatus'],'PASSED')
        rejected = self.upload(path,b'bad image')
        self.assertEqual(rejected['status'],'REJECTED')
        self.assertEqual(self.client.get(path).json()['photo']['photoId'],first['photoId'])
        second = self.upload(path,image_bytes())
        self.assertNotEqual(first['photoId'],second['photoId'])
        changed = self.client.patch(path,json=self.selection())
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(changed.json()['photo']['photoId'],second['photoId'])
        self.assertEqual(self.client.delete(path+'/photo?withdrawConsent=true').status_code,202)
        current = self.client.get(path).json()
        self.assertIsNone(current['photo'])
        self.assertEqual(current['consentStatus'],'REVOKED')
        self.assertEqual(self.client.post(path+'/upload-url',json={'contentType':'image/jpeg','size':100,'fileName':'x.jpg'}).status_code,403)

    def test_pose_rejection_preserves_original_and_blocks_generation(self):
        path = self.create()
        original = self.upload(path, image_bytes())
        for code in ['NO_PERSON', 'MULTIPLE_PEOPLE', 'BODY_CROPPED']:
            with self.subTest(code=code):
                self.pose.return_value = code
                self.storage.put_object.reset_mock()
                rejected = self.upload(path, image_bytes(), original['photoId'])
                self.assertEqual(rejected['status'], 'REJECTED')
                self.assertEqual(rejected['issues'][0]['code'], code)
                self.assertIsNone(rejected['previewUrl'])
                self.storage.put_object.assert_not_called()
                self.assertEqual(self.client.get(path).json()['photo']['photoId'], original['photoId'])
                self.assertEqual([p['photoId'] for p in self.client.get('/api/try-on/photos').json()['data']], [original['photoId']])
                response = self.client.post(path+'/generations', json={**self.selection(), 'photoId':rejected['photoId'], 'confirmed':True},
                                            headers={'Idempotency-Key':str(uuid4())})
                self.assertEqual(response.status_code, 409, response.text)
                response = self.client.post('/api/try-on/sessions', json={**self.selection(), 'source':'SELF', 'photoId':rejected['photoId']})
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.client.get('/api/account/generation-usage').json()['website']['used'], 0)
        self.assertEqual(self.client.get('/api/try-on/generations').json()['data'], [])

    def test_pose_service_failure_can_retry_and_preserves_original(self):
        path = self.create()
        original = self.upload(path, image_bytes())
        content = image_bytes()
        ticket = self.client.post(path+'/upload-url', json={'contentType':'image/jpeg', 'size':len(content),
            'fileName':'test.jpg', 'replacePhotoId':original['photoId']}).json()
        self.storage.head_object.return_value = {'ContentLength':len(content)}
        self.storage.get_object.return_value = {'Body':BytesIO(content)}
        self.storage.put_object.reset_mock()
        self.pose.side_effect = RuntimeError('private-model-path must not escape')
        response = self.client.post(path+'/validate', json={'photoId':ticket['photoId']})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()['error']['code'], 'PHOTO_VALIDATION_UNAVAILABLE')
        self.assertNotIn('private-model-path', response.text)
        self.assertEqual(self.connection.execute('SELECT status FROM person_photos WHERE id=%s', (ticket['photoId'],)).fetchone()['status'], 'PENDING')
        self.storage.put_object.assert_not_called()
        self.assertEqual(self.client.get(path).json()['photo']['photoId'], original['photoId'])
        self.pose.side_effect = None
        self.storage.get_object.return_value = {'Body':BytesIO(content)}
        response = self.client.post(path+'/validate', json={'photoId':ticket['photoId']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'READY')
        self.assertEqual(self.client.get(path).json()['photo']['photoId'], ticket['photoId'])

    def test_legacy_photos_remain_usable_without_rechecking(self):
        path = self.create()
        photo = self.upload(path, image_bytes())
        self.connection.execute("UPDATE person_photos SET status='FILE_READY' WHERE id=%s", (photo['photoId'],))
        self.connection.execute("UPDATE try_on_sessions SET consent_version='photo-consent-2026-10-23-scenes' WHERE id=%s", (path.rsplit('/',1)[-1],))
        self.pose.reset_mock()
        self.pose.side_effect = AssertionError('Legacy photos must not be checked')
        response = self.client.post(path+'/validate', json={'photoId':photo['photoId']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'FILE_READY')
        response = self.client.post('/api/try-on/sessions', json={**self.selection(), 'source':'SELF', 'photoId':photo['photoId']})
        self.assertEqual(response.status_code, 201, response.text)
        self.pose.assert_not_called()

    def test_authenticated_api_transfer_when_vite_cors_is_unavailable(self):
        from fastapi import HTTPException
        self.mocks[1].side_effect=HTTPException(503,{'code':'PHOTO_CORS_UNAVAILABLE'})
        path=self.create();content=image_bytes()
        ticket=self.client.post(path+'/upload-url',json={'contentType':'image/jpeg','size':len(content),'fileName':'synthetic.jpg'})
        self.assertEqual(ticket.status_code,200,ticket.text);ticket=ticket.json()
        self.assertEqual(ticket['transport'],'API')
        sent=self.client.put(ticket['uploadUrl'],content=content,headers={'Content-Type':'image/jpeg'})
        self.assertEqual(sent.status_code,200,sent.text)
        self.assertEqual(self.storage.put_object.call_args.kwargs['Body'],content)
        self.assertTrue(self.storage.put_object.call_args.kwargs['Key'].startswith('private/try-on/uploads/'))
        self.assertEqual(self.client.put(ticket['uploadUrl'],content=content+b'extra',headers={'Content-Type':'image/jpeg'}).status_code,413)
        self.assertEqual(self.client.put(ticket['uploadUrl'],content=content,headers={'Content-Type':'image/png'}).status_code,422)
        self.identity['uid']='other-transfer-'+str(uuid4());self.client.put('/api/account',json={}).raise_for_status()
        self.assertEqual(self.client.put(ticket['uploadUrl'],content=content,headers={'Content-Type':'image/jpeg'}).status_code,404)

    @unittest.skipUnless(os.getenv('RUN_PHOTO_STORAGE_TESTS') == '1', 'Opt-in real S3 upload test')
    def test_real_s3_direct_upload_and_private_preview(self):
        import httpx
        from app.integrations.s3 import ensure_private_storage, check_upload_cors, private_bucket, remove_key, preview_url
        from app.integrations.s3 import s3_client
        versioned = ensure_private_storage()
        check_upload_cors('http://127.0.0.1:8010')
        client = s3_client()
        path = self.create()
        keys = []
        try:
            with patch('app.modules.try_on.photos.s3_client', return_value=client):
                content = image_bytes()
                response = self.client.post(path+'/upload-url', json={'contentType':'image/jpeg','size':len(content),'fileName':'synthetic-test.jpg'})
                self.assertEqual(response.status_code,200,response.text)
                data = response.json()
                row = self.connection.execute('SELECT * FROM person_photos WHERE id=%s',(data['photoId'],)).fetchone()
                keys = [row['raw_key'],row['source_key'],row['preview_key']]
                sent = httpx.post(data['uploadUrl'], data=data['fields'], files={'file':('test.jpg',content,'image/jpeg')},timeout=30)
                self.assertIn(sent.status_code,(200,201,204))
                validated = self.client.post(path+'/validate',json={'photoId':data['photoId']})
                self.assertEqual(validated.status_code,200,validated.text)
                self.assertEqual(validated.json()['status'],'READY')
                preview = httpx.get(preview_url(row['preview_key']),timeout=20)
                self.assertEqual(preview.status_code,200)
                self.assertEqual(preview.headers['content-type'],'image/webp')
                clean = client.get_object(Bucket=private_bucket(),Key=row['source_key'])['Body']
                try: self.assertFalse(Image.open(BytesIO(clean.read())).getexif())
                finally: clean.close()
                self.assertEqual(self.client.delete(path+'/photo').status_code,202)
                self.assertIsNone(self.client.get(path).json()['photo'])
        finally:
            for key in keys: remove_key(client,key,versioned)
