from app.core.database import get_connection
from app.modules.stores import queries as queries
from app.modules.stores.schemas import City, Store, StoreList
from fastapi import APIRouter, Depends, Request
from typing import Annotated
from uuid import UUID
import psycopg

Connection = Annotated[psycopg.Connection, Depends(get_connection)]
router = APIRouter(prefix='/api')

@router.get('/stores', response_model=StoreList)
def stores(connection: Connection, city: City | None=None):
    return queries.stores(connection=connection, city=city)

@router.get('/stores/{store_id}', response_model=Store)
def store_detail(store_id: UUID, request: Request, connection: Connection):
    return queries.store_detail(store_id=store_id, request=request, connection=connection)
