"""Lightweight Post Schedule site, independent of the video-rendering server."""
import os
import secrets
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .posts import install

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('FRAMEFORGE_DATA', str(ROOT / 'data'))).resolve()
PORT = int(os.environ.get('POST_SCHEDULE_PORT', '4321'))
TOKEN = secrets.token_urlsafe(32)
app = FastAPI(title='Post Schedule', docs_url=None, redoc_url=None)


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    allowed = {f'127.0.0.1:{PORT}', f'localhost:{PORT}', 'testserver'}
    if request.headers.get('host', '') not in allowed:
        return JSONResponse({'detail':'Local access only.'}, status_code=403)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('x-frameforge-token') != TOKEN:
            return JSONResponse({'detail':'Refresh to reconnect to your library.'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in {f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'}:
            return JSONResponse({'detail':'Cross-origin requests are blocked.'}, status_code=403)
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail':'Invalid request size.'}, status_code=400)
        if length > 5 * 1024 * 1024:
            return JSONResponse({'detail':'Choose a backup smaller than 5 MB.'}, status_code=413)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY',
        'Referrer-Policy':'no-referrer', 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'"})
    return response


@app.get('/')
def index(request: Request):
    if 'workspace' in request.query_params:
        return RedirectResponse('http://127.0.0.1:4319/?workspace=1')
    return RedirectResponse('/posts')


@app.get('/editor')
def editor():
    return RedirectResponse('http://127.0.0.1:4319/editor')


@app.get('/api/status')
def status():
    return {'token':TOKEN, 'name':'Post Schedule'}


install(app, SimpleNamespace(ROOT=ROOT, DATA=DATA))
app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
