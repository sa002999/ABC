from app.core.database import get_connection
from app.modules.catalog import queries as queries
from app.modules.catalog.schemas import City, Kimono, KimonoList, Plan, PlanList
from fastapi import APIRouter, Depends, Query
from typing import Annotated, Literal
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection)]
router = APIRouter(prefix='/api', tags=['商品與方案'])

@router.get('/plans', response_model=PlanList)
def list_plans(connection: Connection, city: City | None=None, store: UUID | None=None, audience: str | None=Query(default=None, max_length=40), style: str | None=Query(default=None, max_length=40), min_price: int | None=Query(default=None, alias='minPrice', ge=0, le=1000000000), max_price: int | None=Query(default=None, alias='maxPrice', ge=0, le=1000000000), keyword: str=Query(default='', max_length=100), page: int=Query(default=0, ge=0, le=100000), page_size: int=Query(default=12, alias='pageSize', ge=1, le=50), sort: Literal['recommended', 'priceAsc', 'priceDesc']='recommended'):
    return queries.list_plans(connection=connection, city=city, store=store, audience=audience, style=style, min_price=min_price, max_price=max_price, keyword=keyword, page=page, page_size=page_size, sort=sort)

@router.get('/plans/{plan_id}', response_model=Plan)
def plan_detail(plan_id: UUID, connection: Connection):
    return queries.plan_detail(plan_id=plan_id, connection=connection)

@router.get('/kimonos', response_model=KimonoList)
def list_kimonos(connection: Connection, city: City | None=None, store: UUID | None=None, plan: UUID | None=None, page: int=Query(default=0, ge=0, le=100000), page_size: int=Query(default=12, alias='pageSize', ge=1, le=50)):
    return queries.list_kimonos(connection=connection, city=city, store=store, plan=plan, page=page, page_size=page_size)

@router.get('/kimonos/{kimono_id}', response_model=Kimono)
def kimono_detail(kimono_id: UUID, connection: Connection):
    return queries.kimono_detail(kimono_id=kimono_id, connection=connection)

@router.get('/catalog-assets/{asset_id}', include_in_schema=False)
def catalog_asset(asset_id: UUID, connection: Connection):
    return queries.catalog_asset(asset_id=asset_id, connection=connection)

@router.get('/belts')
def belts(connection: Connection):
    return queries.belts(connection=connection)

@router.get('/photography-options')
def photography_options():
    return queries.photography_options()
