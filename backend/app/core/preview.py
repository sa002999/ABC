from fastapi.staticfiles import StaticFiles
from app.core.config import BACKEND_DIR
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException


frontend = BACKEND_DIR.parent / 'frontend' / 'dist'


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


def mount_frontend(app):
    if (frontend / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')
    app.add_api_route('/{path:path}', frontend_page, include_in_schema=False)
