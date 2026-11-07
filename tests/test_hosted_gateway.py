import hashlib
import hmac
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.hosted_gateway import create_gateway, signed_message, tenant_directory


SECRET = 'test-only-' + 'x' * 48


def headers(user='alice', path='/api/status', method='GET', body=b'', timestamp=None):
    values = {'x-motion-user': user, 'x-motion-time': str(timestamp or int(time.time())),
              'x-motion-nonce': uuid.uuid4().hex, 'content-type': '', 'range': ''}
    values['x-motion-body-sha256'] = hashlib.sha256(body).hexdigest()
    message = signed_message(method, path, values, body)
    values['x-motion-signature'] = hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()
    return values


class Workers:
    def __init__(self):
        self.users = []

    async def forward(self, user, request, body):
        from fastapi.responses import JSONResponse
        self.users.append(user)
        return JSONResponse({'user': user})


@pytest.fixture
def gateway(tmp_path):
    workers = Workers()
    return TestClient(create_gateway(SECRET, tmp_path, workers=workers)), workers


def test_gateway_rejects_unsigned_or_forged_identity(gateway):
    client, workers = gateway
    assert client.get('/api/status').status_code == 401
    values = headers()
    values['x-motion-user'] = 'bob'
    assert client.get('/api/status', headers=values).status_code == 401
    assert workers.users == []


def test_gateway_routes_only_verified_identity(gateway):
    client, workers = gateway
    assert client.get('/api/status', headers=headers('alice')).json() == {'user': 'alice'}
    assert client.get('/api/status', headers=headers('bob')).json() == {'user': 'bob'}
    assert workers.users == ['alice', 'bob']


def test_editor_routes_keep_signature_and_tenant_boundary(gateway):
    client, workers = gateway
    for path in ['/editor','/api/editor/draft']:
        assert client.get(path).status_code==401
        assert client.get(path,headers=headers('alice',path=path)).json()=={'user':'alice'}
    for path in ['/api/editor/references','/api/editor/generate']:
        assert client.post(path,headers=headers('bob',path=path,method='POST')).json()=={'user':'bob'}
    assert workers.users==['alice','alice','bob','bob']


def test_signature_binds_body_path_and_timestamp(gateway):
    client, workers = gateway
    assert client.get('/api/library', headers=headers()).status_code == 401
    assert client.post('/api/jobs', content=b'tampered', headers=headers(path='/api/jobs', method='POST', body=b'original')).status_code == 401
    assert client.get('/api/status', headers=headers(timestamp=int(time.time())-120)).status_code == 401
    assert workers.users == []


def test_signature_cannot_be_replayed(gateway):
    client, _ = gateway
    values = headers()
    assert client.get('/api/status', headers=values).status_code == 200
    assert client.get('/api/status', headers=values).status_code == 401


def test_tenant_paths_cannot_escape_or_share_owner_data(tmp_path):
    alice = tenant_directory(tmp_path, 'alice')
    bob = tenant_directory(tmp_path, 'bob')
    assert alice != bob
    assert tenant_directory(tmp_path, '../../data').parent == tmp_path.resolve()
    assert len(alice.name) == 64


def test_unknown_routes_never_reach_workers(gateway):
    client, workers = gateway
    path = '/.codex/auth.json'
    assert client.get(path, headers=headers(path=path)).status_code == 404
    assert workers.users == []


def test_connection_attempts_are_limited_per_user(gateway):
    client, _ = gateway
    for _ in range(5):
        assert client.post('/api/account/connect', headers=headers(path='/api/account/connect', method='POST')).status_code == 200
    assert client.post('/api/account/connect', headers=headers(path='/api/account/connect', method='POST')).status_code == 429
    assert client.post('/api/account/connect', headers=headers('bob', path='/api/account/connect', method='POST')).status_code == 200
