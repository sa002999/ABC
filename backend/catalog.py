from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

from database import BACKEND_DIR, get_connection
from storage import cloudfront_url

router = APIRouter(prefix='/api', tags=['商品與方案'])
Connection = Annotated[psycopg.Connection, Depends(get_connection)]
City = Literal['TOKYO', 'KYOTO']


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Asset(CamelModel):
    id: UUID
    kind: Literal['PRODUCT', 'STYLED', 'GENERATION']
    url: str
    alt: dict[str, str]

    @model_validator(mode='before')
    @classmethod
    def image_url(cls, value):
        if value.get('s3_key'):
            value = {**value, 'url': cloudfront_url(value['s3_key'])}
        return value


class Kimono(CamelModel):
    id: UUID
    sku: str
    name: dict[str, str]
    gender: str = 'FEMALE'
    kimono_type: str
    style_tags: list[str]
    is_demo: bool
    images: list[Asset]


class StoreSummary(CamelModel):
    id: UUID
    slug: str
    city: City
    name: dict[str, str]


class Plan(CamelModel):
    id: UUID
    slug: str
    name: dict[str, str]
    summary: dict[str, str]
    description: dict[str, str]
    audience: list[str]
    duration_minutes: int
    kind: str = 'SINGLE'
    additional_guest_price: int = 1500
    base_price: int
    currency: Literal['TWD']
    included_items: list[str]
    is_demo: bool
    kimono: Kimono
    stores: list[StoreSummary]


class PlanList(CamelModel):
    data: list[Plan]
    total: int
    next_page: int | None


class KimonoList(CamelModel):
    data: list[Kimono]
    next_page: int | None


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


@router.get('/plans', response_model=PlanList)
def list_plans(
    connection: Connection,
    city: City | None = None,
    store: UUID | None = None,
    audience: str | None = Query(default=None, max_length=40),
    style: str | None = Query(default=None, max_length=40),
    min_price: int | None = Query(default=None, alias='minPrice', ge=0, le=1000000000),
    max_price: int | None = Query(default=None, alias='maxPrice', ge=0, le=1000000000),
    keyword: str = Query(default='', max_length=100),
    page: int = Query(default=0, ge=0, le=100000),
    page_size: int = Query(default=12, alias='pageSize', ge=1, le=50),
    sort: Literal['recommended', 'priceAsc', 'priceDesc'] = 'recommended',
):
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


@router.get('/plans/{plan_id}', response_model=Plan)
def plan_detail(plan_id: UUID, connection: Connection):
    row = connection.execute(PLAN_SELECT + PLAN_FROM + ' WHERE ' + PUBLIC_PLAN + ' AND p.id = %s', (plan_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail={'code': 'PLAN_NOT_FOUND', 'message': '找不到這個方案，可能已下架。'})
    return row


@router.get('/kimonos', response_model=KimonoList)
def list_kimonos(connection: Connection, city: City | None = None, store: UUID | None = None,
                 plan: UUID | None = None,
                 page: int = Query(default=0, ge=0, le=100000), page_size: int = Query(default=12, alias='pageSize', ge=1, le=50)):
    conditions, params = ['k.active'], []
    scope = 'EXISTS (SELECT 1 FROM plans p JOIN plan_stores ps ON ps.plan_id = p.id JOIN stores s ON s.id = ps.store_id WHERE p.kimono_id = k.id AND p.active AND s.active'
    for value, expression in [(city, 's.city = %s'), (store, 's.id = %s'), (plan, 'p.id = %s')]:
        if value is not None:
            scope += ' AND ' + expression
            params.append(value)
    conditions.append(scope + ')')
    query = 'SELECT ' + KIMONO_SQL + ' AS kimono FROM kimonos k WHERE ' + ' AND '.join(conditions)
    rows = connection.execute(query + ' ORDER BY k.sku LIMIT %s OFFSET %s', [*params, page_size + 1, page * page_size]).fetchall()
    return {'data': [row['kimono'] for row in rows[:page_size]], 'next_page': page + 1 if len(rows) > page_size else None}


@router.get('/kimonos/{kimono_id}', response_model=Kimono)
def kimono_detail(kimono_id: UUID, connection: Connection):
    row = connection.execute('SELECT ' + KIMONO_SQL + ' AS kimono FROM kimonos k WHERE k.id = %s AND k.active AND EXISTS ('
                             'SELECT 1 FROM plans p JOIN plan_stores ps ON ps.plan_id = p.id JOIN stores s ON s.id = ps.store_id '
                             'WHERE p.kimono_id = k.id AND p.active AND s.active)', (kimono_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail={'code': 'KIMONO_NOT_FOUND', 'message': '找不到這件和服。'})
    return row['kimono']


@router.get('/catalog-assets/{asset_id}', include_in_schema=False)
def catalog_asset(asset_id: UUID, connection: Connection):
    row = connection.execute('''SELECT a.image_key, a.s3_key FROM product_assets a JOIN kimonos k ON k.id = a.kimono_id
        WHERE a.id = %s AND a.active AND k.active AND EXISTS (
            SELECT 1 FROM plans p JOIN plan_stores ps ON ps.plan_id = p.id JOIN stores s ON s.id = ps.store_id
            WHERE p.kimono_id = k.id AND p.active AND s.active)''', (asset_id,)).fetchone()
    if row is not None:
        if row['s3_key']:
            return RedirectResponse(cloudfront_url(row['s3_key']), status_code=302, headers={'Cache-Control': 'no-store'})
        directory = (BACKEND_DIR / 'catalog-media').resolve()
        image = (directory / row['image_key']).resolve()
        if image.is_relative_to(directory) and image.is_file() and image.suffix == '.webp':
            return FileResponse(image, media_type='image/webp')
    raise HTTPException(404, detail={'code': 'IMAGE_NOT_FOUND', 'message': '商品圖片尚未提供。'})


@router.get('/belts')
def belts(connection: Connection):
    rows=connection.execute("SELECT id,name,category,price FROM accessories WHERE active ORDER BY price,id").fetchall()
    return {'data':[{'id':r['id'],'name':r['name'],'category':r['category'],'priceTwd':r['price']} for r in rows]}


@router.get('/photography-options')
def photography_options():
    return {'data':[]}
