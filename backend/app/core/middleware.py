import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from uuid import uuid4


async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    if request.url.path == '/' or request.url.path.startswith(('/js/', '/css/')):
        response.headers['Cache-Control'] = 'no-cache'
    if request.headers.get('authorization') or request.url.path.startswith(('/api/mcp', '/api/looks', '/api/account', '/api/plans/compare', '/api/try-on/photos', '/api/try-on/sessions', '/api/try-on/jobs', '/api/try-on/generations', '/api/booking-drafts', '/api/pricing', '/api/availability/holds')):
        response.headers['Cache-Control'] = 'no-store'
    if request.url.path.startswith(('/api/bookings','/api/orders')) or request.url.path.endswith('/availability') or request.url.path == '/api/catalog/party-availability':
        response.headers['Cache-Control'] = 'no-store'
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def configure_middleware(app):
    app.add_middleware(CORSMiddleware,
        allow_origins=[v.strip() for v in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if v.strip()],
        allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],
        allow_headers=['Authorization','Content-Type','Idempotency-Key'],
        expose_headers=['X-Request-ID'])
    app.middleware('http')(request_id)
