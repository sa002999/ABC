"""Import supplied product images only; never import person-source photos as garments."""
from uuid import UUID, uuid5

from PIL import Image, ImageOps
from psycopg.types.json import Jsonb

from database import BACKEND_DIR, connect

NAMESPACE = UUID('5281aa4b-3ca8-40f9-b231-3a1362f97aa2')
MEDIA_DIR = BACKEND_DIR / 'catalog-media'
CATALOG = [
    ('RKH0002', '紫藤花語', '淡紫色與花葉圖案，為京都散步增添柔和色彩。', 'ELEGANT', 1500, 'demo-kyoto', ['SOLO', 'COUPLE']),
    ('RKH0057', '粉映花枝', '白底搭配粉色花卉，呈現輕盈明亮的旅行造型。', 'ROMANTIC', 1800, 'demo-kyoto', ['SOLO', 'FAMILY']),
    ('RKH0103', '墨葉留白', '以白底與墨色葉紋呈現俐落的東京街景搭配。', 'MODERN', 2100, 'demo-tokyo', ['SOLO', 'COUPLE']),
]


def identifier(kind, sku):
    return uuid5(NAMESPACE, kind + ':' + sku)


def localize(value):
    return Jsonb({'zh-Hant': value})


def seed_catalog():
    for sku, *_ in CATALOG:
        if not (BACKEND_DIR / 'assets' / 'kimono' / (sku + '.png')).is_file():
            raise RuntimeError('Missing supplied kimono source: ' + sku)
    (MEDIA_DIR / 'kimono').mkdir(parents=True, exist_ok=True)
    for sku, *_ in CATALOG:
        target = MEDIA_DIR / 'kimono' / (sku + '.webp')
        if not target.exists():
            with Image.open(BACKEND_DIR / 'assets' / 'kimono' / (sku + '.png')) as image:
                preview = ImageOps.exif_transpose(image).convert('RGB')
                preview.thumbnail((800, 1200))
                preview.save(target, 'WEBP', quality=82, method=6)
    with connect() as connection:
        for sku, name, summary, style, price, store_slug, audience in CATALOG:
            store = connection.execute('SELECT id FROM stores WHERE slug = %s AND active', (store_slug,)).fetchone()
            if not store:
                raise RuntimeError('Run seed-demo before seed-catalog.')
            kimono_id = identifier('kimono', sku)
            plan_id = identifier('plan', sku)
            connection.execute('''INSERT INTO kimonos (id, sku, name, kimono_type, style_tags, is_demo)
                VALUES (%s, %s, %s, 'KIMONO', %s, true) ON CONFLICT DO NOTHING''',
                (kimono_id, sku, localize(name), [style]))
            connection.execute('''INSERT INTO plans
                (id, slug, kimono_id, name, summary, description, audience, duration_minutes, base_price, included_items, is_demo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 480, %s, %s, true) ON CONFLICT DO NOTHING''',
                (plan_id, 'demo-' + sku.lower(), kimono_id, localize(name + '和服體驗'), localize(summary),
                 localize(summary + ' 本方案的名稱、類型、服務與售價均為開發測試設定，不能作為正式預約依據。'),
                 audience, price, Jsonb(['和服租借（測試）', '基本腰帶（測試）', '著裝服務（測試）'])))
            connection.execute('INSERT INTO plan_stores (plan_id, store_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (plan_id, store['id']))
            connection.execute('''INSERT INTO product_assets (id, kimono_id, kind, image_key, alt)
                VALUES (%s, %s, 'PRODUCT', %s, %s) ON CONFLICT DO NOTHING''',
                (identifier('asset', sku), kimono_id, 'kimono/' + sku + '.webp', localize(name + '和服正面商品圖')))
    print('Catalog ready: 3 demo plans, 3 kimonos and 3 optimized product images. Existing rows were not overwritten.')
