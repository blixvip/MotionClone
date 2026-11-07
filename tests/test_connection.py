import json
import threading

import pytest

from app.connection import Connection, safe_environment


class FakeRPC:
    def __init__(self):
        self.account = None
        self.notifications = []
        self.calls = []

    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == 'account/read':
            return {'account': self.account}
        if method == 'account/login/start':
            return {'loginId': 'attempt-1', 'verificationUrl': 'https://auth.openai.com/codex/device', 'userCode': 'ABCD-1234'}
        if method == 'account/logout':
            self.account = None
        return {}

    def close(self):
        pass


def test_login_is_reused_and_only_public_fields_are_returned():
    rpc = FakeRPC()
    connection = Connection(lambda: rpc)
    first = connection.start()
    assert first['status'] == 'pending'
    assert first['userCode'] == 'ABCD-1234'
    assert connection.start() == first
    assert len([c for c in rpc.calls if c[0] == 'account/login/start']) == 1
    rpc.account = {'type': 'chatgpt', 'email': 'person@example.com', 'planType': 'plus', 'accessToken': 'private'}
    result = connection.state()
    assert result == {'status': 'connected', 'email': 'person@example.com', 'plan': 'plus'}
    assert 'private' not in json.dumps(result)


def test_account_state_can_discover_an_existing_codex_login():
    rpc = FakeRPC()
    rpc.account = {'type': 'chatgpt', 'email': 'local@example.com', 'planType': 'plus'}
    connection = Connection(lambda: rpc)
    assert connection.state(initialize=True)['status'] == 'connected'
    assert not any(method == 'account/login/start' for method, _ in rpc.calls)


def test_cancel_and_disconnect_cannot_leave_pending_login_active():
    rpc = FakeRPC()
    connection = Connection(lambda: rpc)
    connection.start()
    connection.disconnect()
    assert ('account/login/cancel', {'loginId': 'attempt-1'}) in rpc.calls
    assert ('account/logout', None) in rpc.calls
    assert connection.state()['status'] == 'disconnected'


def test_expired_login_cannot_remain_pending():
    rpc = FakeRPC()
    connection = Connection(lambda: rpc)
    connection.start()
    connection.deadline = 0
    assert connection.state()['status'] == 'expired'
    assert ('account/login/cancel', {'loginId': 'attempt-1'}) in rpc.calls


def test_unexpected_verification_host_is_rejected():
    rpc = FakeRPC()
    original = rpc.call
    rpc.call = lambda m, p=None: dict(original(m, p), verificationUrl='https://evil.example') if m == 'account/login/start' else original(m, p)
    with pytest.raises(ValueError):
        Connection(lambda: rpc).start()


def test_tenant_environment_does_not_inherit_owner_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'owner-key')
    monkeypatch.setenv('CODEX_API_KEY', 'owner-key')
    monkeypatch.setenv('CODEX_HOME', 'owner-home')
    monkeypatch.setenv('MOTIONCLONE_GATEWAY_SECRET', 'gateway-secret')
    env = safe_environment(tmp_path)
    assert env['CODEX_HOME'] == str(tmp_path.resolve())
    assert all(k not in env for k in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'MOTIONCLONE_GATEWAY_SECRET'))
    assert 'PATH' in env or 'Path' in env
