from app.core.config import DATA_DIR
from app.core.database import connect
from app.integrations.s3 import ensure_private_storage, private_bucket, s3_client
from app.modules.try_on.photos import normalize_photo, preview_bytes
from psycopg.types.json import Jsonb
from uuid import UUID, uuid5
import hashlib


def seed_models():
    ensure_private_storage()
    client, bucket = s3_client(), private_bucket()
    folder = DATA_DIR / 'model-previews'
    folder.mkdir(exist_ok=True)
    with connect() as connection:
        for index in range(1,7):
            path = DATA_DIR / 'assets' / 'default models' / f'person-{index}.jpg'
            image, content = normalize_photo(path.read_bytes(), 'image/jpeg')
            model_id = uuid5(UUID('5281aa4b-3ca8-40f9-b231-3a1362f97aa2'), 'person-model:' + str(index))
            key = 'private/try-on/models/' + str(model_id) + '/' + hashlib.sha256(content).hexdigest() + '.jpg'
            client.put_object(Bucket=bucket, Key=key, Body=content, ContentType='image/jpeg', CacheControl='no-store')
            preview_path = str(model_id) + '.webp'
            (folder / preview_path).write_bytes(preview_bytes(image))
            warning = '照片中有狗，腿部局部遮擋可能影響試穿效果。' if index == 3 else None
            role = 'FEMALE' if index<=3 else 'MALE'
            label = '女生' if index<=3 else '男生'
            number = index if index<=3 else index-3
            connection.execute('''INSERT INTO store_models (id,name,source_key,preview_path,warning,role)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET source_key=EXCLUDED.source_key,
                name=EXCLUDED.name,role=EXCLUDED.role,preview_path=EXCLUDED.preview_path,warning=EXCLUDED.warning,reviewed_at=now()''',
                (model_id, Jsonb({'zh-Hant': label+'模特兒 '+str(number)}), key, preview_path, warning,role))
    print('6 reviewed model sources imported privately: 3 female, 3 male; public previews contain no EXIF.')
