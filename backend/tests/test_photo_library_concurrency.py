"""Concurrent upload tickets must share the member's three-photo limit."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4
import os
import unittest

from fastapi import BackgroundTasks, HTTPException
from app.core.database import connect
from app.modules.try_on.photos import CONSENT_VERSION, upload_url
from app.modules.try_on.schemas import UploadInput
from commands.seeds.catalog import identifier


@unittest.skipUnless(os.getenv('RUN_DATABASE_TESTS')=='1','Set RUN_DATABASE_TESTS=1 for RDS')
class PhotoLibraryConcurrencyTests(unittest.TestCase):
    def test_four_simultaneous_uploads_reserve_only_three_slots(self):
        member=uuid4();sessions=[uuid4() for _ in range(4)]
        try:
            with connect() as connection:
                connection.execute('INSERT INTO users(id,firebase_uid,email) VALUES (%s,%s,%s)',
                                   (member,'photo-race-'+str(member),'synthetic-photo-race@example.com'))
                for session in sessions:
                    connection.execute('''INSERT INTO try_on_sessions(id,user_id,plan_id,kimono_id,source,consent_version,consented_at)
                        VALUES (%s,%s,%s,%s,'SELF',%s,now())''',
                        (session,member,UUID('30000000-0000-4000-8000-000000000011'),identifier('kimono','RKH0002'),CONSENT_VERSION))
            def ticket(session):
                try:
                    with connect() as connection:
                        upload_url(session,UploadInput(contentType='image/jpeg',size=100,fileName='synthetic.jpg'),
                                   SimpleNamespace(headers={}),member,connection,BackgroundTasks())
                    return 200
                except HTTPException as error:
                    self.assertEqual(error.detail['code'],'PHOTO_UPLOAD_PENDING')
                    return error.status_code
            with (patch('app.modules.try_on.photos.ensure_private_storage'),
                  patch('app.modules.try_on.photos.check_upload_cors'),patch('app.modules.try_on.photos.s3_client') as storage):
                storage.return_value.generate_presigned_post.return_value={'url':'https://example.com/test','fields':{}}
                with ThreadPoolExecutor(max_workers=4) as executor:
                    self.assertEqual(sorted(executor.map(ticket,sessions)),[200,200,200,409])
            with connect() as connection:
                count=connection.execute("SELECT count(*) AS count FROM person_photos WHERE user_id=%s AND status='PENDING'",(member,)).fetchone()['count']
                self.assertEqual(count,3)
        finally:
            # Remove only this test's synthetic rows. No objects or provider requests are created.
            with connect() as connection:
                connection.execute('DELETE FROM person_photos WHERE user_id=%s',(member,))
                connection.execute('DELETE FROM try_on_sessions WHERE user_id=%s',(member,))
                connection.execute('DELETE FROM users WHERE id=%s',(member,))
