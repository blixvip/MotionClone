import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.recording_export import RecordingOptions, cached, encoder_command
from app.hyperframes import frame_info
from app.process import run
from PIL import Image
from app import recording_routes
from app.server import app as server_app


def test_recording_options_only_accept_known_presets_and_no_audio_opt_out():
    for data in ({'look': '../../secrets'}, {'format': '4k'}, {'layout': '<script>'}, {'audio': False}):
        with pytest.raises(ValidationError):
            RecordingOptions.model_validate(data)


@pytest.mark.parametrize('format_name,size', [('ultrawide', (3840, 1080)), ('feed', (1080, 1350))])
def test_recording_new_formats_support_wipe_export(format_name, size):
    from app.recording_export import FORMATS
    options = RecordingOptions(format=format_name, layout='wipe')
    assert FORMATS[options.format] == size
    assert RecordingOptions.model_validate_json(options.model_dump_json()) == options


def test_recording_cache_rejects_changed_output(tmp_path):
    output = tmp_path / 'recording.mp4'
    output.write_bytes(b'verified-video')
    (tmp_path / 'verification.json').write_text(json.dumps({'verified': True, 'settings': RecordingOptions().model_dump(), 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))
    assert cached(tmp_path)
    output.write_bytes(b'corrupted')
    assert cached(tmp_path) is None


@pytest.mark.parametrize('report', [[], None, {'verified': True}, {'verified': True, 'settings': {'look': '../bad'}}])
def test_recording_cache_rejects_malformed_reports_without_crashing(tmp_path, report):
    output = tmp_path / 'recording.mp4'
    output.write_bytes(b'verified-video')
    if isinstance(report, dict):
        report['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    (tmp_path / 'verification.json').write_text(json.dumps(report))
    assert cached(tmp_path) is None


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_encoder_preserves_audio_packets_beyond_final_video_frame(tmp_path):
    audio, output = tmp_path / 'audio.m4a', tmp_path / 'recording.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1.024', '-c:a', 'aac', str(audio)])
    image = io.BytesIO()
    Image.new('RGB', (64, 64), '#101018').save(image, format='PNG')
    run(encoder_command(audio, output, '30'), input=image.getvalue() * 30)
    assert frame_info(output)[0] == 30
    hashes = [run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-']) for path in (audio, output)]
    assert hashes[0] == hashes[1]


@pytest.fixture
def routes(tmp_path, monkeypatch):
    calls = []
    class Pool:
        def __init__(self, **kwargs): pass
        def submit(self, *args): calls.append(args)
    monkeypatch.setattr(recording_routes, 'ThreadPoolExecutor', Pool)
    monkeypatch.setattr(recording_routes, 'fingerprint', lambda folder, options: {'mono': 'a', 'signal': 'b', 'cobalt': 'c', 'peach': 'd'}.get(options.look, 'e') * 20)
    job = {'id': '123456abcdef', 'status': 'complete'}
    folder = tmp_path / job['id']; folder.mkdir()
    (folder / 'source.mp4').write_bytes(b'source')
    (folder / 'output.mp4').write_bytes(b'rebuild')
    app = FastAPI()
    recording_routes.install(app, tmp_path, lambda id: job, 4319)
    return TestClient(app), folder, job, calls


def test_duplicate_export_is_coalesced_and_other_export_cannot_queue_unbounded(routes):
    client, folder, job, calls = routes
    url = f'/api/jobs/{job["id"]}/recording'
    first = client.post(url, json={'look': 'mono'}).json()
    second = client.post(url, json={'look': 'mono'}).json()
    assert first == second and first['status'] == 'queued'
    assert len(calls) == 1
    assert client.post(url, json={'look': 'signal'}).json()['status'] == 'queued'
    assert client.post(url, json={'look': 'cobalt'}).json()['status'] == 'queued'
    blocked = client.post(url, json={'look': 'peach'})
    assert blocked.status_code == 409 and blocked.headers['retry-after']
    assert len(calls) == 3
    assert client.get(first['url']).status_code == 409


def test_export_requires_both_finished_videos(routes):
    client, folder, job, calls = routes
    job['status'] = 'running'
    assert client.post(f'/api/jobs/{job["id"]}/recording', json={}).status_code == 409
    job['status'] = 'complete'; (folder / 'source.mp4').unlink()
    assert client.post(f'/api/jobs/{job["id"]}/recording', json={}).status_code == 409
    assert not calls


def test_verified_recording_can_be_downloaded_after_restart(routes):
    client, folder, job, calls = routes
    target = folder / 'recordings' / ('a' * 20); target.mkdir(parents=True)
    content = b'framed-recording'
    (target / 'recording.mp4').write_bytes(content)
    (target / 'verification.json').write_text(json.dumps({'verified': True, 'settings': {'look': 'mono', 'format': 'landscape', 'layout': 'split'}, 'output_sha256': hashlib.sha256(content).hexdigest()}))
    response = client.get(f'/api/jobs/{job["id"]}/recording/{"a" * 20}/download')
    assert response.status_code == 200 and response.content == content
    assert 'motionclone-mono-landscape-split.mp4' in response.headers['content-disposition']
    status = client.get(f'/api/jobs/{job["id"]}/recording/{"a" * 20}')
    assert status.status_code == 200 and status.json()['status'] == 'complete'
    head = client.head(response.request.url)
    assert head.status_code == 200 and not head.content
    assert head.headers['content-length'] == str(len(content))
    assert not calls


def test_pending_export_status_survives_restart_with_actionable_error(routes):
    client, folder, job, calls = routes
    task = client.post(f'/api/jobs/{job["id"]}/recording', json={'look': 'mono'}).json()
    restarted = FastAPI()
    recording_routes.install(restarted, folder.parent, lambda id: job, 4319)
    response = TestClient(restarted).get(f'/api/jobs/{job["id"]}/recording/{task["key"]}')
    assert response.status_code == 200
    assert response.json()['status'] == 'error'
    assert 'restart' in response.json()['error'].lower()


def test_export_retries_a_transient_browser_failure_and_persists_success(routes, monkeypatch):
    from playwright.sync_api import Error
    client, folder, job, calls = routes
    attempts = []
    def render(*args):
        attempts.append(True)
        if len(attempts) == 1:
            raise Error('Target page, context or browser has been closed')
        return {'verified': True}
    monkeypatch.setattr(recording_routes, 'render', render)
    task = client.post(f'/api/jobs/{job["id"]}/recording', json={'look': 'mono'}).json()
    function, *arguments = calls[0]
    function(*arguments)
    response = client.get(f'/api/jobs/{job["id"]}/recording/{task["key"]}')
    assert len(attempts) == 2 and response.json()['status'] == 'complete'


def test_export_validation_failure_is_not_retried_and_can_be_restarted(routes, monkeypatch):
    client, folder, job, calls = routes
    attempts = []
    def render(*args):
        attempts.append(True)
        raise ValueError('The source duration changed.')
    monkeypatch.setattr(recording_routes, 'render', render)
    task = client.post(f'/api/jobs/{job["id"]}/recording', json={'look': 'mono'}).json()
    function, *arguments = calls[0]
    function(*arguments)
    response = client.get(f'/api/jobs/{job["id"]}/recording/{task["key"]}')
    assert len(attempts) == 1 and response.json()['error'] == 'The source duration changed.'
    retry = client.post(f'/api/jobs/{job["id"]}/recording', json={'look': 'mono'})
    assert retry.json()['status'] == 'queued' and len(calls) == 2


def test_recording_browser_falls_back_to_installed_edge(monkeypatch):
    from app import recording_export
    from playwright.sync_api import Error
    class Chromium:
        def launch(self, **kwargs):
            if kwargs.get('channel') == 'chrome':
                raise Error('Chromium distribution chrome is not found')
            assert kwargs.get('channel') == 'msedge'
            return 'edge-browser'
    assert recording_export.launch_browser(Chromium()) == 'edge-browser'


def test_export_failure_releases_queue_even_when_error_log_cannot_be_written(routes, monkeypatch):
    client, folder, job, calls = routes
    def render(*args):
        raise ValueError('Not enough disk space for this recording.')
    monkeypatch.setattr(recording_routes, 'render', render)
    task = client.post(f'/api/jobs/{job["id"]}/recording', json={'look': 'mono'}).json()
    original = Path.write_text
    def write(path, *args, **kwargs):
        if path.name == 'error.log':
            raise OSError('Disk full')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    function, *arguments = calls[0]
    function(*arguments)
    response = client.get(f'/api/jobs/{job["id"]}/recording/{task["key"]}')
    assert response.json()['status'] == 'error'
    assert 'disk space' in response.json()['error']


def test_export_uses_existing_local_token_boundary():
    client = TestClient(server_app)
    assert client.post('/api/jobs/123456abcdef/recording', json={}).status_code == 403
