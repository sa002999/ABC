from PIL import Image, ImageOps
from app.core.config import DATA_DIR
from app.core.database import connect
from psycopg.types.json import Jsonb
from uuid import UUID, uuid5


NAMESPACE = UUID('5281aa4b-3ca8-40f9-b231-3a1362f97aa2')


MEDIA_DIR = DATA_DIR / 'catalog-media'


CATALOG = [
    ('RKH0002', '紫藤花語', '淡紫色與花葉圖案，為京都散步增添柔和色彩。', 'ELEGANT', 1500, 'demo-kyoto', ['SOLO', 'COUPLE']),
    ('RKH0057', '粉映花枝', '白底搭配粉色花卉，呈現輕盈明亮的旅行造型。', 'ROMANTIC', 1800, 'demo-kyoto', ['SOLO', 'FAMILY']),
    ('RKH0103', '墨葉留白', '以白底與墨色葉紋呈現俐落的東京街景搭配。', 'MODERN', 2100, 'demo-tokyo', ['SOLO', 'COUPLE']),
]

MALE_SKUS = ['RKM0001', 'RKM0002', 'RKM0003']
BELT_SKUS = ['ROW0001', 'ROW0002', 'ROW0003']


def prepare_image(folder, sku):
    source = DATA_DIR / 'assets' / folder / (sku + '.png')
    if not source.is_file():
        raise RuntimeError('Missing supplied product source: ' + sku)
    target = MEDIA_DIR / folder / (sku + '.webp')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with Image.open(source) as image:
            preview = ImageOps.exif_transpose(image).convert('RGBA' if 'A' in image.getbands() else 'RGB')
            preview.thumbnail((800, 1200))
            preview.save(target, 'WEBP', quality=82, method=6)


def identifier(kind, sku):
    return uuid5(NAMESPACE, kind + ':' + sku)


def localize(value):
    return Jsonb({'zh-Hant': value})


def seed_catalog():
    for sku, *_ in CATALOG:
        prepare_image('kimono', sku)
    for sku in MALE_SKUS:
        prepare_image('kimono', sku)
    for sku in BELT_SKUS:
        prepare_image('obi', sku)
    with connect() as connection:
        for sku, name, summary, style, price, store_slug, audience in CATALOG:
            store = connection.execute('SELECT id FROM stores WHERE slug = %s AND active', (store_slug,)).fetchone()
            if not store:
                raise RuntimeError('Run seed-demo before seed-catalog.')
            kimono_id = identifier('kimono', sku)
            connection.execute('''INSERT INTO kimonos (id, sku, name, kimono_type, style_tags, is_demo)
                VALUES (%s, %s, %s, 'KIMONO', %s, true) ON CONFLICT DO NOTHING''',
                (kimono_id, sku, localize(name), [style]))
            connection.execute('''INSERT INTO product_assets (id, kimono_id, kind, image_key, alt)
                VALUES (%s, %s, 'PRODUCT', %s, %s) ON CONFLICT DO NOTHING''',
                (identifier('asset', sku), kimono_id, 'kimono/' + sku + '.webp', localize(name + '和服正面商品圖')))
        # RKH denotes women's garments; RKM denotes men's garments.
        connection.execute("UPDATE kimonos SET gender='FEMALE' WHERE sku=ANY(%s)", ([row[0] for row in CATALOG],))
        for sku in MALE_SKUS:
            kimono_id = identifier('kimono', sku)
            connection.execute('''INSERT INTO kimonos(id,sku,name,kimono_type,gender,is_demo)
                VALUES (%s,%s,%s,'KIMONO','MALE',true) ON CONFLICT (sku) DO NOTHING''',
                (kimono_id, sku, localize('男性和服 ' + sku)))
            connection.execute('''INSERT INTO product_assets(id,kimono_id,kind,image_key,alt)
                SELECT %s,id,'PRODUCT',%s,%s FROM kimonos WHERE sku=%s ON CONFLICT DO NOTHING''',
                (identifier('asset', sku), 'kimono/' + sku + '.webp', localize('男性和服 ' + sku + ' 商品圖'), sku))
        # Preserve existing accessory IDs and prices so saved selections remain valid.
        for index, sku in enumerate(BELT_SKUS, 1):
            belt_id = UUID('20000000-0000-4000-8000-' + str(index).zfill(12))
            connection.execute('''INSERT INTO accessories(id,sku,name,category,price)
                VALUES (%s,%s,%s,'BELT',%s) ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku''',
                (belt_id, sku, '女性腰帶 ' + sku, 200 if index == 1 else 350))
            connection.execute('''INSERT INTO product_assets(id,accessory_id,kind,image_key,alt)
                SELECT %s,id,'PRODUCT',%s,%s FROM accessories WHERE sku=%s ON CONFLICT DO NOTHING''',
                (identifier('asset', sku), 'obi/' + sku + '.webp', localize('女性腰帶 ' + sku + ' 商品圖'), sku))
        # Pricing packages are independent of the selected garment SKU.
        for number, kind, label, price in [(11,'SINGLE','單人和服體驗',1500),(12,'COUPLE','情侶和服體驗',2800),(13,'GROUP','團體和服體驗',1400)]:
            key=kind.lower()
            connection.execute('''INSERT INTO plans(id,slug,kimono_id,name,summary,description,audience,duration_minutes,base_price,included_items,is_demo,kind,additional_guest_price,cover_image_url)
                VALUES (%s,%s,%s,%s,%s,%s,%s,480,%s,%s,true,%s,%s,%s) ON CONFLICT (id) DO NOTHING''',
                (UUID('30000000-0000-4000-8000-'+str(number).zfill(12)),'demo-'+key+'-experience',identifier('kimono','RKH0002'),
                 localize(label),localize(label),localize('開發測試方案；單人 1 人、情侶固定一男一女、團體 2～3 人。女生腰帶另計。'),
                 [kind],price,Jsonb(['和服租借（測試）','著裝服務（測試）']),kind,0 if kind=='COUPLE' else price,'/assets/plan-'+key+'.webp'))
        connection.execute('''INSERT INTO plan_stores(plan_id,store_id)
            SELECT p.id,s.id FROM plans p CROSS JOIN stores s
            WHERE p.slug IN ('demo-single-experience','demo-couple-experience','demo-group-experience')
            AND s.is_demo AND s.active ON CONFLICT DO NOTHING''')
        connection.execute("UPDATE plans SET active=false WHERE is_demo AND slug IN ('demo-rkh0002','demo-rkh0057','demo-rkh0103','demo-couple')")
        connection.execute('''INSERT INTO plan_kimonos(plan_id,kimono_id)
            SELECT p.id,k.id FROM plans p CROSS JOIN kimonos k
            WHERE p.is_demo AND k.sku=ANY(%s) ON CONFLICT DO NOTHING''',
            ([row[0] for row in CATALOG] + MALE_SKUS,))
        connection.execute('''INSERT INTO inventory_items(id,code,store_id,kimono_id,is_demo)
            SELECT md5('catalog-item:'||s.id::text||k.id::text||n::text)::uuid,
                'CATALOG-'||s.slug||'-'||k.sku||'-'||n,s.id,k.id,true
            FROM stores s CROSS JOIN kimonos k CROSS JOIN generate_series(1,3) n
            WHERE s.is_demo AND s.active AND k.sku=ANY(%s)
                AND NOT EXISTS(SELECT 1 FROM inventory_items i WHERE i.store_id=s.id AND i.kimono_id=k.id)
            ON CONFLICT DO NOTHING''', (MALE_SKUS,))
    print('Catalog ready: 3 female kimonos, 3 male kimonos, 3 belts and 9 product images. Existing prices and inventory preserved.')
