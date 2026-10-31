from botocore.exceptions import BotoCoreError, ClientError
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import psycopg
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import NoReturn


def error(status,code,message) -> NoReturn:
    raise HTTPException(status,{'code':code,'message':message})


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


async def invalid_input(request: Request, error: RequestValidationError):
    if request.url.path.startswith('/api/booking-drafts') and any(e['loc'][-1] in ('guests','partySize','party_size') and e['type'] in ('too_long','too_short','greater_than_equal','less_than_equal') for e in error.errors()):
        return error_response(request,422,'INVALID_GUEST_COUNT','每筆預約限 1～3 人','guests')
    field = str(error.errors()[0]["loc"][-1])
    return error_response(
        request, 422, "INVALID_INPUT", "查詢參數不正確，請確認條件或資源編號。", field
    )


async def database_unavailable(request: Request, error: Exception):
    return error_response(
        request, 503, "DATABASE_UNAVAILABLE", "暫時無法取得資料，請稍後重試。"
    )


async def http_error(request: Request, error: HTTPException):
    detail = error.detail if isinstance(error.detail, dict) else {}
    return error_response(request, error.status_code, detail.get('code', 'NOT_FOUND' if error.status_code == 404 else 'REQUEST_FAILED'),
                          detail.get('message', '找不到要求的資源。'), detail.get('field'))


async def storage_unavailable(request: Request, error: Exception):
    return error_response(request, 503, 'PHOTO_STORAGE_UNAVAILABLE', '照片儲存服務暫時無法使用，請稍後重試。')


def register_exception_handlers(app):
    app.add_exception_handler(RequestValidationError, invalid_input)
    app.add_exception_handler(psycopg.Error, database_unavailable)
    app.add_exception_handler(RuntimeError, database_unavailable)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(BotoCoreError, storage_unavailable)
    app.add_exception_handler(ClientError, storage_unavailable)
