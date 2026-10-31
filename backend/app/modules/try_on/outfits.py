"""Choose one complete garment image; never send a belt-only image to Vertex."""
from hashlib import sha256
from io import BytesIO
import json
import re

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import DATA_DIR, PHOTO_MAX_BYTES
from app.modules.catalog.media import read_product_image
from app.modules.catalog.rules import selected_belts


def outfit_source(connection, kimono_id, belt_id=None):
    garment = connection.execute('SELECT sku,gender FROM kimonos WHERE id=%s AND active', (kimono_id,)).fetchone()
    if not garment:
        raise HTTPException(422, {'code':'INVALID_OUTFIT','message':'和服已無法選用。'})
    selected_belts(connection, garment['gender'], [belt_id] if belt_id else [])
    try:
        if belt_id:
            belt = connection.execute('SELECT sku FROM accessories WHERE id=%s AND active', (belt_id,)).fetchone()
            if (not re.fullmatch(r'RKH\d{4}', garment['sku']) or not belt
                    or not re.fullmatch(r'ROW\d{4}', belt['sku'] or '')):
                raise FileNotFoundError()
            key = 'assets/kimono-obi/' + garment['sku'] + '_' + belt['sku'] + '.png'
            path = DATA_DIR / key
            if not path.is_file() or path.stat().st_size > PHOTO_MAX_BYTES:
                raise FileNotFoundError()
            content = path.read_bytes()
        else:
            asset = connection.execute("SELECT image_key FROM product_assets WHERE kimono_id=%s AND kind='PRODUCT' AND active ORDER BY sort_order,id LIMIT 1", (kimono_id,)).fetchone()
            if not asset:
                raise FileNotFoundError()
            key = 'catalog-media/' + asset['image_key']
            content = read_product_image(asset['image_key'])
        # Fingerprint the exact JPEG bytes sent to Vertex, including image normalization.
        with Image.open(BytesIO(content)) as image:
            if image.format not in ('PNG','WEBP') or max(image.size) > 6000:
                raise ValueError()
            image = ImageOps.exif_transpose(image).convert('RGBA')
            canvas = Image.new('RGB', image.size, 'white')
            canvas.paste(image, mask=image.getchannel('A'))
            output = BytesIO()
            canvas.save(output, 'JPEG', quality=95)
        content = output.getvalue()
    except (OSError, ValueError, RuntimeError, UnidentifiedImageError, Image.DecompressionBombError):
        message = '所選和服與腰帶的合成素材尚未備妥，請更換搭配或取消加選腰帶；未扣生成額度。' if belt_id else '所選和服的試穿素材尚未備妥；未扣生成額度。'
        raise HTTPException(422, {'code':'OUTFIT_IMAGE_UNAVAILABLE','message':message}) from None
    return {'key':key,'sha256':sha256(content).hexdigest(),'content':content}


def reuse_key(kimono_id, belt_id, photo_id, model_id, person_source_key, outfit_sha256):
    # Plans affect price, not the resulting pixels. Reuse is scoped to a member in SQL.
    selection = {'kimonoId':kimono_id,'beltId':belt_id,'photoId':photo_id,'modelId':model_id,
                 'personSource':person_source_key,'outfitVersion':outfit_sha256}
    return sha256(json.dumps(selection, default=str, sort_keys=True).encode()).hexdigest()
