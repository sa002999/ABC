from contextlib import asynccontextmanager
from typing import Annotated
import psycopg
from fastapi import Depends, FastAPI
from app.core.errors import register_exception_handlers
from app.core.middleware import configure_middleware
from app.core.preview import mount_frontend
from app.core.database import close_pool, get_connection
from app.modules.accounts.router import router as accounts_router
from app.modules.accounts.mcp import router as mcp_router
from app.modules.bookings.router import router as bookings_router
from app.modules.catalog.router import router as catalog_router
from app.modules.catalog.outfits import router as outfits_router
from app.modules.looks.router import router as looks_router
from app.modules.stores.router import router as stores_router
from app.modules.try_on.router import router as try_on_router
from app.modules.try_on.mcp import router as mcp_try_on_router

Connection = Annotated[psycopg.Connection, Depends(get_connection)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        close_pool()


def health():
    return {"status": "ok", "meta": {"capabilities": {
        "catalogRead": True, "bookingDraft": True, "quote": True, "inventoryHold": True,
        "aiGeneration": True, "account": True, "looks": True,
        "booking": False, "payment": False, "orderRead": False, "voucher": False,
        "cancellation": False, "mcp": True}}}


def database_health(connection: Connection):
    connection.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ok"}


app = FastAPI(title="KINU TABI API", version="0.1.0", lifespan=lifespan)
configure_middleware(app)
register_exception_handlers(app)
app.get('/api/health')(health)
app.get('/api/health/db')(database_health)
app.include_router(stores_router)
app.include_router(catalog_router)
app.include_router(outfits_router)
app.include_router(accounts_router)
app.include_router(mcp_router)
app.include_router(looks_router)
app.include_router(try_on_router)
app.include_router(mcp_try_on_router)
app.include_router(bookings_router)

mount_frontend(app)
