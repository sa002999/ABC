from app.core.config import DATA_DIR
from app.integrations.s3 import cloudfront_url
from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse


ASSETS_SQL = """COALESCE((SELECT jsonb_agg(jsonb_build_object(
    'id', a.id, 'kind', a.kind, 'url', '/api/catalog-assets/' || a.id::text, 's3_key', a.s3_key, 'alt', a.alt
    ) ORDER BY a.sort_order, a.id)
    FROM product_assets a WHERE a.kimono_id = k.id AND a.active), '[]'::jsonb)"""


KIMONO_SQL = """jsonb_build_object('id', k.id, 'sku', k.sku, 'name', k.name,
    'gender', k.gender, 'kimono_type', k.kimono_type, 'style_tags', k.style_tags,
    'is_demo', k.is_demo, 'images', """ + ASSETS_SQL + ')'


STORES_SQL = """COALESCE((SELECT jsonb_agg(jsonb_build_object('id', s.id, 'slug', s.slug,
    'city', s.city, 'name', s.name) ORDER BY s.slug)
    FROM plan_stores ps JOIN stores s ON s.id = ps.store_id
    WHERE ps.plan_id = p.id AND s.active), '[]'::jsonb)"""


PUBLIC_PLAN = """p.active AND k.active AND EXISTS (
    SELECT 1 FROM plan_stores ps JOIN stores s ON s.id = ps.store_id
    WHERE ps.plan_id = p.id AND s.active)"""


PLAN_FROM = ' FROM plans p JOIN kimonos k ON k.id = p.kimono_id '


PLAN_SELECT = 'SELECT p.*, ' + KIMONO_SQL + ' AS kimono, ' + STORES_SQL + ' AS stores '


KIMONO_SCOPE = '''EXISTS (SELECT 1 FROM plan_kimonos pk JOIN plans p ON p.id=pk.plan_id
    JOIN plan_stores ps ON ps.plan_id=p.id JOIN stores s ON s.id=ps.store_id
    WHERE pk.kimono_id=k.id AND p.active AND s.active'''

ASSET_FROM = ''' FROM product_assets a LEFT JOIN kimonos k ON k.id=a.kimono_id
    LEFT JOIN accessories b ON b.id=a.accessory_id '''

PUBLIC_ASSET = 'a.active AND ((k.active AND ' + KIMONO_SCOPE + ')) OR b.active)'


def list_plans(connection, city, store, audience, style, min_price, max_price, keyword, page, page_size, sort):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, detail={'code': 'INVALID_PRICE_RANGE', 'message': '最低價格不能高於最高價格。', 'field': 'minPrice'})
    clauses, params = [PUBLIC_PLAN], []
    if city or store:
        condition = 'EXISTS (SELECT 1 FROM plan_stores ps JOIN stores s ON s.id = ps.store_id WHERE ps.plan_id = p.id AND s.active'
        if city:
            condition += ' AND s.city = %s'
            params.append(city)
        if store:
            condition += ' AND s.id = %s'
            params.append(store)
        clauses.append(condition + ')')
    for value, expression in [(audience, '%s = ANY(p.audience)'), (style, '%s = ANY(k.style_tags)'),
                              (min_price, 'p.base_price >= %s'), (max_price, 'p.base_price <= %s')]:
        if value is not None:
            clauses.append(expression)
            params.append(value)
    if keyword.strip():
        clauses.append("(p.name::text ILIKE %s OR p.summary::text ILIKE %s OR k.sku ILIKE %s)")
        # Treat SQL wildcard characters as literal search text.
        search = '%' + keyword.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        params.extend([search] * 3)
    where = ' WHERE ' + ' AND '.join(clauses)
    total = connection.execute('SELECT count(*) AS total' + PLAN_FROM + where, params).fetchone()['total']
    ordering = {'recommended': 'k.sku, p.id', 'priceAsc': 'p.base_price, p.id', 'priceDesc': 'p.base_price DESC, p.id'}[sort]
    rows = connection.execute(PLAN_SELECT + PLAN_FROM + where + ' ORDER BY ' + ordering + ' LIMIT %s OFFSET %s',
                              [*params, page_size, page * page_size]).fetchall()
    return {'data': rows, 'total': total, 'next_page': page + 1 if (page + 1) * page_size < total else None}


def plan_detail(plan_id, connection):
    row = connection.execute(PLAN_SELECT + PLAN_FROM + ' WHERE ' + PUBLIC_PLAN + ' AND p.id = %s', (plan_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail={'code': 'PLAN_NOT_FOUND', 'message': '找不到這個方案，可能已下架。'})
    return row


def list_kimonos(connection, city, store, plan, page, page_size):
    conditions, params = ['k.active'], []
    scope = KIMONO_SCOPE
    for value, expression in [(city, 's.city = %s'), (store, 's.id = %s'), (plan, 'p.id = %s')]:
        if value is not None:
            scope += ' AND ' + expression
            params.append(value)
    conditions.append(scope + ')')
    query = 'SELECT ' + KIMONO_SQL + ' AS kimono FROM kimonos k WHERE ' + ' AND '.join(conditions)
    rows = connection.execute(query + ' ORDER BY k.sku LIMIT %s OFFSET %s', [*params, page_size + 1, page * page_size]).fetchall()
    return {'data': [row['kimono'] for row in rows[:page_size]], 'next_page': page + 1 if len(rows) > page_size else None}


def kimono_detail(kimono_id, connection):
    row = connection.execute('SELECT ' + KIMONO_SQL + ' AS kimono FROM kimonos k WHERE k.id = %s AND k.active AND '
                             + KIMONO_SCOPE + ')', (kimono_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail={'code': 'KIMONO_NOT_FOUND', 'message': '找不到這件和服。'})
    return row['kimono']


def catalog_asset(asset_id, connection):
    row = connection.execute('SELECT a.image_key, a.s3_key' + ASSET_FROM +
                             ' WHERE a.id = %s AND ' + PUBLIC_ASSET, (asset_id,)).fetchone()
    if row is not None:
        if row['s3_key']:
            return RedirectResponse(cloudfront_url(row['s3_key']), status_code=302, headers={'Cache-Control': 'no-store'})
        directory = (DATA_DIR / 'catalog-media').resolve()
        image = (directory / row['image_key']).resolve()
        if image.is_relative_to(directory) and image.is_file() and image.suffix == '.webp':
            return FileResponse(image, media_type='image/webp')
    raise HTTPException(404, detail={'code': 'IMAGE_NOT_FOUND', 'message': '商品圖片尚未提供。'})


def belts(connection):
    rows=connection.execute('''SELECT b.id,b.sku,b.name,b.category,b.price,a.id AS asset_id,a.s3_key
        FROM accessories b LEFT JOIN LATERAL (
            SELECT id,s3_key FROM product_assets WHERE accessory_id=b.id AND active AND kind='PRODUCT'
            ORDER BY sort_order,id LIMIT 1) a ON true
        WHERE b.active ORDER BY b.price,b.sku,b.id''').fetchall()
    return {'data':[{'id':r['id'],'sku':r['sku'],'name':r['name'],'category':r['category'],'priceTwd':r['price'],
        'imageUrl':cloudfront_url(r['s3_key']) if r['s3_key'] else '/api/catalog-assets/'+str(r['asset_id']) if r['asset_id'] else None} for r in rows]}


def photography_options():
    return {'data':[]}
