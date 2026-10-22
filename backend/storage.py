"""Publish catalog WebP files only. Member photos never pass through this command."""
import hashlib
import os
import re
from urllib.parse import urlsplit

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image

from database import BACKEND_DIR, connect

KEY_PATTERN = re.compile(r'catalog/[0-9a-f-]{36}/[0-9a-f]{64}\.webp')
CACHE_CONTROL = 'public, max-age=31536000, immutable'


def cloudfront_url(key):
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError('Invalid catalog object key')
    domain = os.getenv('CLOUDFRONT_DOMAIN', '').strip()
    url = urlsplit(domain if '://' in domain else 'https://' + domain)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.port or url.path not in ('', '/') or url.query or url.fragment
            or not re.fullmatch(r'[A-Za-z0-9.-]+', url.hostname)):
        raise RuntimeError('Set CLOUDFRONT_DOMAIN to a valid HTTPS hostname without a path')
    return 'https://' + url.hostname + '/' + key


def s3_client():
    # The SDK reads .env credentials locally and the EC2 instance role after deployment.
    return boto3.client('s3', region_name=os.getenv('AWS_REGION'), config=Config(
        connect_timeout=5, read_timeout=15, retries={'mode': 'standard', 'max_attempts': 2}))


def read_product_image(key):
    directory = (BACKEND_DIR / 'catalog-media').resolve()
    image = (directory / key).resolve()
    if not image.is_relative_to(directory) or image.suffix != '.webp' or not image.is_file():
        raise RuntimeError('A catalog image is missing or has an unsafe local path')
    if image.stat().st_size > 10 * 1024 * 1024:
        raise RuntimeError('Catalog image exceeds 10 MB')
    with Image.open(image) as decoded:
        if decoded.format != 'WEBP':
            raise RuntimeError('Catalog source must be a WebP image')
        decoded.verify()
    return image.read_bytes()


def upload_object(client, bucket, key, content):
    checksum = hashlib.sha256(content).hexdigest()
    try:
        client.put_object(Bucket=bucket, Key=key, Body=content, ContentType='image/webp',
                          CacheControl=CACHE_CONTROL, Metadata={'sha256': checksum}, IfNoneMatch='*')
    except ClientError as error:
        if error.response['Error']['Code'] not in ('412', 'PreconditionFailed'):
            raise
        existing = client.head_object(Bucket=bucket, Key=key)
        if (existing.get('Metadata', {}).get('sha256') != checksum
                or existing.get('ContentLength') != len(content)
                or existing.get('ContentType') != 'image/webp'
                or existing.get('CacheControl') != CACHE_CONTROL):
            raise RuntimeError('Existing object does not match; refusing to overwrite')
        return 'unchanged'
    return 'uploaded'


def publish_catalog():
    bucket = os.getenv('S3_BUCKET', '').strip()
    if not bucket or '/' in bucket:
        raise RuntimeError('Set S3_BUCKET to the bucket name, without s3:// or a path')
    # Validate configuration before making any upload.
    cloudfront_url('catalog/00000000-0000-0000-0000-000000000000/' + '0' * 64 + '.webp')
    with connect() as connection:
        rows = connection.execute('''SELECT a.id, a.image_key FROM product_assets a
            JOIN kimonos k ON k.id = a.kimono_id WHERE a.active AND k.active AND EXISTS (
                SELECT 1 FROM plans p JOIN plan_stores ps ON ps.plan_id = p.id
                JOIN stores s ON s.id = ps.store_id
                WHERE p.kimono_id = k.id AND p.active AND s.active) ORDER BY a.id''').fetchall()
    if not rows:
        raise RuntimeError('No active catalog assets to publish')
    prepared = []
    for row in rows:
        content = read_product_image(row['image_key'])
        key = 'catalog/' + str(row['id']) + '/' + hashlib.sha256(content).hexdigest() + '.webp'
        prepared.append((row, key, content))
    client = s3_client()
    with httpx.Client(timeout=20, follow_redirects=False) as http:
        for row, key, content in prepared:
            result = upload_object(client, bucket, key, content)
            # A public catalog URL must not make the S3 origin itself public.
            origin = http.get('https://' + bucket + '.s3.' + os.environ['AWS_REGION'] + '.amazonaws.com/' + key)
            if origin.status_code not in (403, 404):
                raise RuntimeError('S3 direct-access check failed; database was not switched')
            response = http.get(cloudfront_url(key))
            if (response.status_code != 200 or response.headers.get('content-type', '').split(';')[0] != 'image/webp'
                    or hashlib.sha256(response.content).digest() != hashlib.sha256(content).digest()):
                raise RuntimeError('CloudFront image verification failed (HTTP ' + str(response.status_code) + '); database was not switched')
            print('Catalog asset', row['id'], result, 'and CloudFront verified')
    # Publish together, only after every uploaded object is reachable through CloudFront.
    with connect() as connection:
        for row, key, _ in prepared:
            updated = connection.execute('''UPDATE product_assets SET s3_key = %s
                WHERE id = %s AND image_key = %s RETURNING id''', (key, row['id'], row['image_key'])).fetchone()
            if updated is None:
                raise RuntimeError('Catalog changed while uploading; rerun publish-catalog')
    print('Published', len(prepared), 'catalog images. Original source files were preserved.')
