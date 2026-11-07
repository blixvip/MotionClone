"""Signed Sites-to-engine gateway; each visitor gets a separate worker and data root."""
import asyncio
import hashlib
import hmac
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .connection import safe_environment
from .process import own_process_tree, popen

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 25 * 1024 * 1024
ALLOWED = re.compile(r'^/(?:studio|editor|static/[A-Za-z0-9_./-]+|media/[a-f0-9]{12}/[A-Za-z0-9_.-]+|api/(?:editor/(?:draft|references|generate)|status|account(?:/(?:connect|disconnect))?|library|jobs(?:/[a-f0-9]{12}(?:/(?:duplicate|cancel|retry|render|export|remotion|hyperframes|recording(?:/[a-f0-9]{20}(?:/download)?)?))?)?))$')


def signed_message(method, path, headers, body):
    return '\n'.join([method, path, headers.get('x-motion-user', ''),
        headers.get('x-motion-time', ''), headers.get('x-motion-nonce', ''),
        headers.get('content-type', ''), headers.get('range', ''),
        headers.get('x-motion-body-sha256', '') if body is None else hashlib.sha256(body).hexdigest()]).encode()


def tenant_directory(root, user):
    return Path(root).resolve() / hashlib.sha256(user.encode()).hexdigest()


class Workers:
    def __init__(self, root, capacity=3):
        self.root = Path(root).resolve()
        self.capacity = capacity
        self.workers = {}
        self.lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=45, trust_env=False, follow_redirects=False)

    async def acquire(self, user):
        async with self.lock:
            now = time.monotonic()
            for key, worker in list(self.workers.items()):
                # A live tab polls; unobserved jobs have a bounded 20-minute grace period.
                if worker['proc'].poll() is not None or now - worker['seen'] > 1800:
                    try:
                        status = await self.client.get(worker['url'] + '/api/status', timeout=3)
                        if status.json().get('active'):
                            continue
                    except Exception:
                        pass
                    self.stop(worker)
                    del self.workers[key]
            if user in self.workers:
                self.workers[user]['seen'] = now
                return self.workers[user]
            if len(self.workers) >= self.capacity:
                return None
            folder = tenant_directory(self.root, user)
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            env = safe_environment(folder / 'account')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            token = secrets.token_urlsafe(32)
            env.update(FRAMEFORGE_HOSTED='1', FRAMEFORGE_DATA=str(folder / 'projects'),
                       FRAMEFORGE_PORT=str(port), FRAMEFORGE_TOKEN=token,
                       PYTHONUNBUFFERED='1', FRAMEFORGE_MODEL=os.environ.get('FRAMEFORGE_MODEL', 'gpt-6-astra'))
            log = (folder / 'worker.log').open('ab')
            try:
                proc = popen([sys.executable, '-m', 'uvicorn', 'app.server:app', '--host', '127.0.0.1',
                              '--port', str(port), '--no-access-log'], cwd=ROOT, env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            finally:
                log.close()
            cleanup = own_process_tree(proc)
            worker = {'proc': proc, 'cleanup': cleanup, 'url': f'http://127.0.0.1:{port}',
                      'token': token, 'seen': now}
            self.workers[user] = worker
            for _ in range(80):
                if proc.poll() is not None:
                    break
                try:
                    response = await self.client.get(worker['url'] + '/?workspace=1', timeout=1)
                    if response.status_code == 200:
                        return worker
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.25)
            self.stop(worker)
            del self.workers[user]
            return None

    def stop(self, worker):
        worker['cleanup']()  # Own Windows Job Object, contains only this worker's children.
        proc = worker['proc']
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    async def close(self):
        for worker in self.workers.values():
            self.stop(worker)
        await self.client.aclose()

    async def forward(self, user, request, body):
        path = request.url.path
        if path.startswith('/static/'):
            file = (ROOT / 'web' / path[len('/static/'):]).resolve()
            if not file.is_relative_to(ROOT / 'web') or not file.is_file():
                return JSONResponse({'detail': 'Not found.'}, status_code=404)
            return FileResponse(file)
        worker = await self.acquire(user)
        if worker is None:
            return JSONResponse({'detail': 'All video workers are busy. Try again shortly.'}, status_code=503, headers={'Retry-After': '30'})
        if request.method == 'POST' and (path in ('/api/jobs','/api/editor/references','/api/editor/generate') or path.endswith('/duplicate')):
            projects = tenant_directory(self.root, user) / 'projects'
            count = sum(1 for _ in projects.glob('*/job.json'))
            size = sum(p.stat().st_size for p in projects.rglob('*') if p.is_file())
            if count >= 20 or size >= 2 * 1024 ** 3:
                return JSONResponse({'detail': 'Your beta storage limit is reached. Download your videos and contact us for more space.'}, status_code=409)
        target = '/?workspace=1' + ('&' + request.url.query if request.url.query else '') if path == '/studio' else path + ('?' + request.url.query if request.url.query else '')
        headers = {'X-Frameforge-Token': worker['token']}
        for key in ('content-type', 'range', 'if-range'):
            if request.headers.get(key):
                headers[key] = request.headers[key]
        upstream = self.client.build_request(request.method, worker['url'] + target, content=body, headers=headers)
        try:
            response = await self.client.send(upstream, stream=True)
        except httpx.HTTPError:
            return JSONResponse({'detail': 'Video processing is temporarily unavailable. Your saved projects are safe; try again.'}, status_code=503)
        allowed = {'content-type', 'content-length', 'content-range', 'accept-ranges', 'content-disposition',
                   'content-security-policy', 'x-content-type-options', 'x-frame-options', 'referrer-policy'}
        response_headers = {k: v for k, v in response.headers.items() if k.lower() in allowed}
        return StreamingResponse(response.aiter_raw(), status_code=response.status_code, headers=response_headers,
                                 background=BackgroundTask(response.aclose))


def create_gateway(secret, root, workers=None):
    if len(secret) < 40:
        raise ValueError('Gateway requires a randomly generated secret of at least 40 characters.')
    workers = workers or Workers(root, int(os.environ.get('MOTIONCLONE_MAX_USERS', '3')))
    nonces = {}
    attempts = {}

    @asynccontextmanager
    async def lifespan(app):
        yield
        await workers.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PATCH'])
    async def forward(request: Request, path: str):
        now = time.time()
        user = request.headers.get('x-motion-user', '')
        nonce = request.headers.get('x-motion-nonce', '')
        try:
            timestamp = int(request.headers.get('x-motion-time', '0'))
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': 'Unauthorized.'}, status_code=401)
        if not re.fullmatch(r'[A-Za-z0-9_:.@-]{1,200}', user) or not re.fullmatch(r'[a-f0-9]{32}', nonce) or abs(now-timestamp) > 30:
            return JSONResponse({'detail': 'Unauthorized.'}, status_code=401)
        full_path = request.url.path + ('?' + request.url.query if request.url.query else '')
        digest = request.headers.get('x-motion-body-sha256', '')
        expected = hmac.new(secret.encode(), signed_message(request.method, full_path, request.headers, None), hashlib.sha256).hexdigest()
        supplied = request.headers.get('x-motion-signature', '')
        if not re.fullmatch(r'[a-f0-9]{64}', digest) or not re.fullmatch(r'[a-f0-9]{64}', supplied) or not hmac.compare_digest(expected, supplied):
            return JSONResponse({'detail': 'Unauthorized.'}, status_code=401)
        if length > MAX_BODY:
            return JSONResponse({'detail': 'Uploads are limited to 25 MB. Use a video link for larger videos.'}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return JSONResponse({'detail': 'Upload exceeds 25 MB.'}, status_code=413)
        if not hmac.compare_digest(hashlib.sha256(body).hexdigest(), digest):
            return JSONResponse({'detail': 'Unauthorized.'}, status_code=401)
        for key, expires in list(nonces.items()):
            if expires < now:
                nonces.pop(key, None)
        if nonce in nonces:
            return JSONResponse({'detail': 'Unauthorized.'}, status_code=401)
        nonces[nonce] = now + 65
        if not ALLOWED.fullmatch(request.url.path):
            return JSONResponse({'detail': 'Not found.'}, status_code=404)
        if request.method == 'POST' and (request.url.path == '/api/account/connect' or request.url.path in ('/api/jobs','/api/editor/references','/api/editor/generate') or request.url.path.endswith('/retry')):
            category = 'connect' if request.url.path == '/api/account/connect' else 'rebuild'
            period, limit = (60, 5) if category == 'connect' else (3600, 10)
            key = (user, category)
            prior = [t for t in attempts.get(key, []) if t > now - period]
            attempts[key] = prior
            if len(prior) >= limit:
                return JSONResponse({'detail': 'Too many attempts. Wait a little before trying again.'}, status_code=429,
                                    headers={'Retry-After': str(max(1, int(prior[0] + period - now)))})
            prior.append(now)
        response = await workers.forward(user, request, bytes(body))
        response.headers.update({'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'})
        return response

    return app


def configured_gateway():
    root = Path(os.environ.get('MOTIONCLONE_HOSTED_DATA', str(ROOT / 'data' / '.hosted'))).resolve()
    return create_gateway(os.environ['MOTIONCLONE_GATEWAY_SECRET'], root)
