from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from database import BACKEND_DIR, close_pool, get_connection
from catalog import router as catalog_router
from auth import router as auth_router
from looks import router as looks_router
from person_sources import router as person_sources_router
from generations import router as generations_router
from bookings import router as bookings_router

@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="KINU TABI API", version="0.1.0", lifespan=lifespan)


app.add_middleware(CORSMiddleware,
    allow_origins=[v.strip() for v in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if v.strip()],
    allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],
    allow_headers=['Authorization','Content-Type','Idempotency-Key'],
    expose_headers=['X-Request-ID'])


class City(StrEnum):
    TOKYO = "TOKYO"
    KYOTO = "KYOTO"


class Store(BaseModel):
    id: UUID
    slug: str
    city: City
    name: dict[str, str]
    address: dict[str, str]
    latitude: float | None
    longitude: float | None
    timezone: str
    opening_hours: dict = Field(serialization_alias="openingHours")
    languages: list[str]
    is_demo: bool = Field(serialization_alias="isDemo")


class StoreList(BaseModel):
    data: list[Store]


def error_response(
    request: Request, status: int, code: str, message: str, field: str | None = None
):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "field": field,
                "requestId": request.state.request_id,
            }
        },
    )


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    if request.url.path == '/' or request.url.path.startswith(('/js/', '/css/')):
        response.headers['Cache-Control'] = 'no-cache'
    if request.headers.get('authorization') or request.url.path.startswith(('/api/looks', '/api/account', '/api/plans/compare', '/api/try-on/sessions', '/api/try-on/jobs', '/api/try-on/generations', '/api/booking-drafts', '/api/pricing', '/api/availability/holds')):
        response.headers['Cache-Control'] = 'no-store'
    if request.url.path.endswith('/availability'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, error: RequestValidationError):
    if request.url.path.startswith('/api/booking-drafts') and any(e['loc'][-1] in ('guests','partySize','party_size') and e['type'] in ('too_long','too_short','greater_than_equal','less_than_equal') for e in error.errors()):
        return error_response(request,422,'INVALID_GUEST_COUNT','每筆預約限 1～3 人','guests')
    field = str(error.errors()[0]["loc"][-1])
    return error_response(
        request, 422, "INVALID_INPUT", "查詢參數不正確，請確認條件或資源編號。", field
    )


@app.exception_handler(psycopg.Error)
@app.exception_handler(RuntimeError)
async def database_unavailable(request: Request, error: Exception):
    return error_response(
        request, 503, "DATABASE_UNAVAILABLE", "暫時無法取得資料，請稍後重試。"
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    detail = error.detail if isinstance(error.detail, dict) else {}
    return error_response(request, error.status_code, detail.get('code', 'NOT_FOUND' if error.status_code == 404 else 'REQUEST_FAILED'),
                          detail.get('message', '找不到要求的資源。'), detail.get('field'))


@app.exception_handler(BotoCoreError)
@app.exception_handler(ClientError)
async def storage_unavailable(request: Request, error: Exception):
    return error_response(request, 503, 'PHOTO_STORAGE_UNAVAILABLE', '照片儲存服務暫時無法使用，請稍後重試。')


Connection = Annotated[psycopg.Connection, Depends(get_connection)]
STORE_COLUMNS = "id, slug, city, name, address, latitude, longitude, timezone, opening_hours, languages, is_demo"


@app.get("/api/health")
def health():
    return {"status": "ok", "meta": {"capabilities": {
        "catalogRead": True, "bookingDraft": True, "quote": True, "inventoryHold": True,
        "aiGeneration": True, "account": True, "looks": True,
        "booking": False, "payment": False, "orderRead": False, "voucher": False,
        "cancellation": False, "mcp": False}}}


@app.get("/api/health/db")
def database_health(connection: Connection):
    connection.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ok"}


@app.get("/api/stores", response_model=StoreList)
def stores(connection: Connection, city: City | None = None):
    query = f"SELECT {STORE_COLUMNS} FROM stores WHERE active"
    params = ()
    if city is not None:
        query += " AND city = %s"
        params = (city.value,)
    rows = connection.execute(query + " ORDER BY city, slug", params).fetchall()
    return {"data": rows}


@app.get("/api/stores/{store_id}", response_model=Store)
def store_detail(store_id: UUID, request: Request, connection: Connection):
    row = connection.execute(
        f"SELECT {STORE_COLUMNS} FROM stores WHERE active AND id = %s", (store_id,)
    ).fetchone()
    if row is None:
        return error_response(request, 404, "STORE_NOT_FOUND", "找不到這間門市。")
    return row


app.include_router(catalog_router)
app.include_router(auth_router)
app.include_router(looks_router)
app.include_router(person_sources_router)
app.include_router(generations_router)
app.include_router(bookings_router)

# React build only. API routes are registered before the SPA fallback.
frontend = BACKEND_DIR.parent / 'frontend' / 'dist'
if (frontend / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')


@app.get('/{path:path}', include_in_schema=False)
def frontend_page(path: str):
    if any(part.startswith('.') for part in path.split('/')) or path.startswith(('backend/','src/','js/','css/')) or path == 'api' or path.startswith('api/'):
        raise HTTPException(404)
    candidate=(frontend / path).resolve()
    if path and not candidate.is_file() and '.' in path.split('/')[-1]:
        raise HTTPException(404)
    if candidate.is_relative_to(frontend.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    if (frontend / 'index.html').is_file():
        return FileResponse(frontend / 'index.html',headers={'Cache-Control':'no-cache'})
    raise HTTPException(503, {'code':'FRONTEND_NOT_BUILT','message':'請先在 frontend 執行 npm ci 與 npm run build，或使用 Vite 開發伺服器。'})
