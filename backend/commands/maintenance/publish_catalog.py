from app.core.database import connect
from app.integrations.s3 import CACHE_CONTROL, cloudfront_url, s3_client
from app.modules.catalog.media import STORE_IMAGES, read_product_image, read_plan_cover, read_store_image
from app.modules.catalog.queries import ASSET_FROM, PUBLIC_ASSET
from botocore.exceptions import ClientError
import hashlib
import httpx
import os


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
        rows = connection.execute('SELECT a.id, a.image_key' + ASSET_FROM +
                                  ' WHERE ' + PUBLIC_ASSET + ' ORDER BY a.id').fetchall()
        covers = connection.execute('''SELECT p.id, p.cover_image_url FROM plans p
            JOIN kimonos k ON k.id=p.kimono_id
            WHERE p.active AND k.active AND p.cover_image_url LIKE '/assets/%'
            AND EXISTS (SELECT 1 FROM plan_stores ps JOIN stores s ON s.id=ps.store_id
                WHERE ps.plan_id=p.id AND s.active) ORDER BY p.id''').fetchall()
        stores = connection.execute('''SELECT id, slug FROM stores
            WHERE active AND image_url IS NULL AND slug=ANY(%s) ORDER BY id''',
            (list(STORE_IMAGES),)).fetchall()
    if not rows and not covers and not stores:
        raise RuntimeError('No active catalog assets to publish')
    prepared = []
    for row in rows:
        content = read_product_image(row['image_key'])
        key = 'catalog/' + str(row['id']) + '/' + hashlib.sha256(content).hexdigest() + '.webp'
        prepared.append(('product', row, key, content))
    for row in covers:
        content = read_plan_cover(row['cover_image_url'])
        key = 'catalog/' + str(row['id']) + '/' + hashlib.sha256(content).hexdigest() + '.webp'
        prepared.append(('cover', row, key, content))
    for row in stores:
        content = read_store_image(row['slug'])
        key = 'catalog/' + str(row['id']) + '/' + hashlib.sha256(content).hexdigest() + '.webp'
        prepared.append(('store', row, key, content))
    client = s3_client()
    with httpx.Client(timeout=20, follow_redirects=False) as http:
        for kind, row, key, content in prepared:
            result = upload_object(client, bucket, key, content)
            # A public catalog URL must not make the S3 origin itself public.
            origin = http.get('https://' + bucket + '.s3.' + os.environ['AWS_REGION'] + '.amazonaws.com/' + key)
            if origin.status_code not in (403, 404):
                raise RuntimeError('S3 direct-access check failed; database was not switched')
            response = http.get(cloudfront_url(key))
            if (response.status_code != 200 or response.headers.get('content-type', '').split(';')[0] != 'image/webp'
                    or hashlib.sha256(response.content).digest() != hashlib.sha256(content).digest()):
                raise RuntimeError('CloudFront image verification failed (HTTP ' + str(response.status_code) + '); database was not switched')
            print('Catalog', kind, row['id'], result, 'and CloudFront verified')
    # Publish together, only after every uploaded object is reachable through CloudFront.
    with connect() as connection:
        for kind, row, key, _ in prepared:
            if kind == 'product':
                updated = connection.execute('''UPDATE product_assets SET s3_key = %s
                    WHERE id = %s AND image_key = %s RETURNING id''', (key, row['id'], row['image_key'])).fetchone()
            elif kind == 'cover':
                updated = connection.execute('''UPDATE plans SET cover_image_url = %s
                    WHERE id = %s AND cover_image_url = %s RETURNING id''',
                    (cloudfront_url(key), row['id'], row['cover_image_url'])).fetchone()
            else:
                updated = connection.execute('''UPDATE stores SET image_url = %s
                    WHERE id = %s AND image_url IS NULL RETURNING id''',
                    (cloudfront_url(key), row['id'])).fetchone()
            if updated is None:
                raise RuntimeError('Catalog changed while uploading; rerun publish-catalog')
    print('Published', len(rows), 'product images,', len(covers), 'plan covers and', len(stores),
          'store images. Original source files were preserved.')
