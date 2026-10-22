"""Private photo storage. Never hand out source-image download URLs."""
import os
from functools import lru_cache
from uuid import uuid4

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from storage import cloudfront_url, s3_client


def private_bucket():
    value = os.getenv('S3_PRIVATE_BUCKET') or os.getenv('S3_BUCKET', '')
    if not value or '/' in value:
        raise HTTPException(503, {'code': 'PHOTO_STORAGE_UNAVAILABLE', 'message': '照片儲存服務尚未就緒。'})
    return value


def remove_key(client, key, versioned=False):
    if not key or not key.startswith('private/try-on/'):
        raise ValueError('Invalid private photo key')
    bucket = private_bucket()
    if versioned:
        for page in client.get_paginator('list_object_versions').paginate(Bucket=bucket, Prefix=key):
            for item in page.get('Versions', []) + page.get('DeleteMarkers', []):
                if item['Key'] == key:
                    client.delete_object(Bucket=bucket, Key=key, VersionId=item['VersionId'])
    else:
        client.delete_object(Bucket=bucket, Key=key)


def storage_error():
    return HTTPException(503, {'code': 'PHOTO_STORAGE_UNAVAILABLE', 'message': '照片儲存服務暫時無法使用，請稍後重試。'})


@lru_cache(maxsize=1)
def ensure_private_storage():
    client, bucket = s3_client(), private_bucket()
    key = 'private/try-on/_probe/' + uuid4().hex + '.txt'
    created, versioned = False, False
    try:
        result = client.put_object(Bucket=bucket, Key=key, Body=b'Photo privacy check; no personal data.',
                                   ContentType='text/plain', CacheControl='no-store', IfNoneMatch='*')
        created = True
        versioned = bool(result.get('VersionId'))
        with httpx.Client(timeout=10, follow_redirects=False) as http:
            origin = 'https://' + bucket + '.s3.' + os.environ['AWS_REGION'] + '.amazonaws.com/' + key
            if http.get(origin).status_code not in (403, 404):
                raise HTTPException(503, {'code': 'PHOTO_STORAGE_NOT_PRIVATE', 'message': '私人照片儲存尚未完成設定，暫時無法上傳。'})
            if bucket == os.getenv('S3_BUCKET'):
                public = cloudfront_url('catalog/00000000-0000-0000-0000-000000000000/' + '0' * 64 + '.webp')
                base = public.split('/catalog/')[0]
                if http.get(base + '/' + key).status_code not in (403, 404):
                    raise HTTPException(503, {'code': 'PHOTO_STORAGE_NOT_PRIVATE', 'message': '私人照片儲存尚未完成設定，暫時無法上傳。'})
    except (ClientError, BotoCoreError, httpx.HTTPError):
        raise storage_error() from None
    finally:
        if created:
            try:
                remove_key(client, key, versioned)
            except (ClientError, BotoCoreError):
                raise storage_error() from None
    return versioned


def check_upload_cors(origin):
    if not origin:
        return
    url = 'https://' + private_bucket() + '.s3.' + os.environ['AWS_REGION'] + '.amazonaws.com/'
    try:
        response = httpx.options(url, headers={'Origin': origin, 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type'}, timeout=10)
    except httpx.HTTPError:
        raise storage_error() from None
    if response.status_code != 200 or response.headers.get('access-control-allow-origin') != origin:
        raise HTTPException(503, {'code': 'PHOTO_CORS_UNAVAILABLE', 'message': '目前網站的照片上傳設定尚未完成，請稍後再試。'})


def preview_url(key):
    if not key or not key.startswith('private/try-on/photos/') or not key.endswith('/preview.webp'):
        return None
    return s3_client().generate_presigned_url('get_object', Params={
        'Bucket': private_bucket(), 'Key': key, 'ResponseCacheControl': 'no-store',
        'ResponseContentType': 'image/webp'}, ExpiresIn=120)
