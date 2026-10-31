from io import BytesIO
from PIL import Image, ImageOps
from app.core.config import BACKEND_DIR, DATA_DIR


STORE_IMAGES = {'demo-kyoto': 'kyoto.jpg', 'demo-tokyo': 'tokiyo.jpg'}


def read_product_image(key):
    return read_webp(DATA_DIR / 'catalog-media', key)


def read_plan_cover(url):
    if not url.startswith('/assets/'):
        raise RuntimeError('Plan cover must reference a local /assets/ WebP image')
    return read_webp(BACKEND_DIR.parent / 'frontend' / 'public' / 'assets', url.removeprefix('/assets/'))


def read_store_image(slug):
    if slug not in STORE_IMAGES:
        raise RuntimeError('No supplied image for this store')
    source = DATA_DIR / 'assets' / 'store' / STORE_IMAGES[slug]
    if not source.is_file() or source.stat().st_size > 10 * 1024 * 1024:
        raise RuntimeError('Store image is missing or exceeds 10 MB')
    with Image.open(source) as image:
        preview = ImageOps.exif_transpose(image).convert('RGB')
        preview.thumbnail((1600, 1600))
        output = BytesIO()
        preview.save(output, 'WEBP', quality=82, method=6)
    return output.getvalue()


def read_webp(directory, key):
    directory = directory.resolve()
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
