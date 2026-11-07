from fastapi.testclient import TestClient
import app.server as server


def test_hosted_rebuild_rejected_before_any_job_or_model_work(monkeypatch):
    monkeypatch.setattr(server, 'HOSTED', True)
    monkeypatch.setattr(server, 'auth_status', lambda: False)
    before = set(server.JOBS)
    with TestClient(server.app) as client:
        response = client.post('/api/jobs', data={'url': 'https://x.com/example/status/123'},
                               headers={'X-Frameforge-Token': server.TOKEN})
    assert response.status_code == 401
    assert set(server.JOBS) == before


def test_account_endpoints_support_local_login_and_require_csrf(monkeypatch):
    from app.connection import Connection
    from test_connection import FakeRPC
    rpc = FakeRPC()
    rpc.account = {'type': 'chatgpt', 'email': 'local@example.com', 'planType': 'plus'}
    monkeypatch.setattr(server, 'HOSTED', False)
    monkeypatch.setattr(server, 'CONNECTION', Connection(lambda: rpc), raising=False)
    with TestClient(server.app) as client:
        response = client.get('/api/account')
        assert response.status_code == 200
        assert response.json()['status'] == 'connected'
        assert client.post('/api/account/connect').status_code == 403
        assert client.post('/api/account/disconnect').status_code == 403
        response = client.post('/api/account/disconnect', headers={'X-Frameforge-Token': server.TOKEN})
        assert response.status_code == 200
        assert response.json()['status'] == 'disconnected'


def test_local_connect_returns_device_code_and_recognizes_completed_login(monkeypatch):
    from app.connection import Connection
    from test_connection import FakeRPC
    rpc = FakeRPC()
    monkeypatch.setattr(server, 'HOSTED', False)
    monkeypatch.setattr(server, 'ACTIVE', {'id': None})
    monkeypatch.setattr(server, 'AUTH', {'ok': False, 'checked': 0})
    monkeypatch.setattr(server, 'CONNECTION', Connection(lambda: rpc), raising=False)
    with TestClient(server.app) as client:
        response = client.post('/api/account/connect', headers={'X-Frameforge-Token': server.TOKEN})
        assert response.status_code == 200
        assert response.json()['userCode'] == 'ABCD-1234'
        assert 'loginId' not in response.json()
        rpc.account = {'type': 'chatgpt', 'email': 'local@example.com', 'planType': 'plus'}
        assert client.get('/api/account').json()['status'] == 'connected'
        assert server.AUTH['ok'] is True


def test_connection_change_blocked_during_active_job(monkeypatch):
    monkeypatch.setattr(server, 'HOSTED', True)
    monkeypatch.setattr(server, 'ACTIVE', {'id': 'active-project'})
    with TestClient(server.app) as client:
        for action in ['connect', 'disconnect']:
            response = client.post('/api/account/' + action, headers={'X-Frameforge-Token': server.TOKEN})
            assert response.status_code == 409


def test_local_connection_change_blocked_during_active_job(monkeypatch):
    monkeypatch.setattr(server, 'HOSTED', False)
    monkeypatch.setattr(server, 'ACTIVE', {'id': 'active-project'})
    with TestClient(server.app) as client:
        for action in ['connect', 'disconnect']:
            assert client.post('/api/account/' + action, headers={'X-Frameforge-Token': server.TOKEN}).status_code == 409
