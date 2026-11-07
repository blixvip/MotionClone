from fastapi.testclient import TestClient
from app.server import app, TOKEN

client=TestClient(app)


def test_local_app_has_security_headers():
    r=client.get('/')
    assert r.status_code==200
    assert r.headers['x-frame-options']=='DENY'
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']


def test_showcase_and_workspace_routes_remain_separate():
    showcase=client.get('/')
    assert 'hero-title' in showcase.text
    assert '/static/showcase.css' in showcase.text
    workspace=client.get('/?workspace=1')
    assert 'id="create-form"' in workspace.text
    assert 'hero-title' not in workspace.text
    assert 'id="create-form"' in client.get('/?project=aaaaaaaaaaaa').text


def test_settings_and_support_are_present_in_local_and_hosted_workspace(monkeypatch):
    import app.server as server
    for hosted in (False, True):
        monkeypatch.setattr(server, 'HOSTED', hosted)
        response = client.get('/?workspace=1&settings=1')
        assert response.status_code == 200
        assert response.text.count('id="settings-dialog"') == 1
        assert 'id="open-settings"' in response.text
        assert '<!--ACCOUNT_SETTINGS-->' not in response.text
        header = response.text.split('</header>', 1)[0]
        assert 'https://buymeacoffee.com/blix' in header
        assert 'https://github.com/blixvip/MotionClone' in header


def test_mutation_requires_local_token():
    assert client.post('/api/jobs').status_code==403


def test_cross_origin_mutation_blocked_even_with_token():
    r=client.post('/api/jobs',headers={'X-Frameforge-Token':TOKEN,'Origin':'https://evil.example'})
    assert r.status_code==403


def test_dns_rebinding_host_blocked():
    assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==403


def test_missing_video_rejected():
    assert client.post('/api/jobs',headers={'X-Frameforge-Token':TOKEN}).status_code==400


def test_no_arbitrary_local_file_reads():
    assert client.get('/media/aaaaaaaaaaaa/auth.json').status_code==404
    assert client.get('/media/aaaaaaaaaaaa/../../.codex/auth.json').status_code==404


def test_invalid_render_schema_rejected_before_job_execution():
    r=client.post('/api/jobs/aaaaaaaaaaaa/render',headers={'X-Frameforge-Token':TOKEN},json={'tracks':[{'id':'x','kind':'script'}]})
    assert r.status_code==422
