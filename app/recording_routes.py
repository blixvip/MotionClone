"""Bounded background recording exports; the saved reconstruction stays unchanged."""
import json
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from fastapi.responses import FileResponse
from playwright.sync_api import Error as BrowserError

from .recording_export import RecordingOptions, cached, fingerprint, render

MAX_EXPORTS = 3  # One renderer, at most two waiting exports.


def install(app, data, get_job, port):
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='recording-export')
    lock = threading.RLock()
    exports = {}

    def present(value):
        return {key: value[key] for key in ('key', 'status', 'stage', 'progress', 'error', 'url', 'settings')}

    def persist(project, value):
        target = data / project / 'recordings' / value['key']
        target.mkdir(parents=True, exist_ok=True)
        pending = target / 'status.pending.json'
        pending.write_text(json.dumps(present(value)), encoding='utf-8')
        pending.replace(target / 'status.json')

    def item(project, key, options, report=None, stage=None):
        return dict(key=key, status='complete' if report else 'queued',
                    stage='Recording MP4 ready' if report else stage or 'Preparing recording export',
                    progress=100 if report else 0, error=None, settings=options.model_dump(),
                    url=f'/api/jobs/{project}/recording/{key}/download')

    def work(project, key, options):
        item = exports[(project, key)]
        folder = data / project
        target = folder / 'recordings' / key
        def progress(stage, percent):
            with lock:
                item.update(status='running', stage=stage, progress=percent)
                persist(project, item)
        try:
            for attempt in range(2):
                try:
                    report = render(folder, target, options, port, progress)
                    break
                except (BrowserError, BrokenPipeError):
                    if attempt:
                        raise
                    target.mkdir(parents=True, exist_ok=True)
                    (target / 'retry.log').write_text(traceback.format_exc(), encoding='utf-8')
                    progress('Reconnecting recording renderer; retrying export', 1)
            if fingerprint(folder, options) != key:
                (target / 'verification.json').unlink(missing_ok=True)
                raise ValueError('The video or recording design changed during export. Download again to use the latest version.')
            with lock:
                item.update(status='complete', stage='Recording MP4 ready', progress=100, verification=report)
                persist(project, item)
        except Exception as exc:
            with lock:
                item.update(status='error', stage='Export needs attention', error=str(exc) if isinstance(exc, (ValueError, TimeoutError)) else 'Recording export failed. Retry the download; details are saved locally.')
                # A full/unavailable disk must not leave the only renderer busy
                # forever merely because its diagnostic file could not be saved.
                try:
                    persist(project, item)
                    (target / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
                except OSError:
                    pass

    @app.post('/api/jobs/{id}/recording')
    def create_recording(id: str, options: RecordingOptions):
        job = get_job(id)
        folder = data / id
        if job['status'] != 'complete' or not all((folder / name).is_file() for name in ('source.mp4', 'output.mp4')):
            raise HTTPException(409, 'Finish rebuilding this video before downloading its recording view.')
        key = fingerprint(folder, options)
        target = folder / 'recordings' / key
        with lock:
            prior = exports.get((id, key))
            if prior and prior['status'] in ('queued', 'running'):
                return present(prior)
            report = cached(target)
            active = sum(value['status'] in ('queued', 'running') for value in exports.values())
            if not report and active >= MAX_EXPORTS:
                raise HTTPException(409, 'The recording queue is full. Retry when an export finishes.', headers={'Retry-After': '5'})
            value = item(id, key, options, report, f'Queued behind {active} recording export(s)' if active else None)
            persist(id, value)
            exports[(id, key)] = value
            if not report:
                try:
                    pool.submit(work, id, key, options)
                except RuntimeError:
                    value.update(status='error', stage='Export needs attention', error='The app is restarting. Retry Save MP4 in a moment.')
                    persist(id, value)
            return present(value)

    @app.get('/api/jobs/{id}/recording/{key}')
    def recording_status(id: str, key: str):
        get_job(id)
        if not re.fullmatch(r'[a-f0-9]{20}', key):
            raise HTTPException(404, 'Recording export not found.')
        with lock:
            value = exports.get((id, key))
            if value:
                return present(value)
            target = data / id / 'recordings' / key
            report = cached(target)
            if report:
                value = item(id, key, RecordingOptions.model_validate(report['settings']), report)
                exports[(id, key)] = value
                return present(value)
            try:
                saved = json.loads((target / 'status.json').read_text(encoding='utf-8'))
                options = RecordingOptions.model_validate(saved['settings'])
                value = item(id, key, options)
                value.update(status='error', stage='Export needs attention',
                             error=saved.get('error') if saved.get('status') == 'error' else 'The app restarted before this export finished. Retry Save MP4.')
                exports[(id, key)] = value
                return present(value)
            except (OSError, ValueError, KeyError, TypeError):
                pass
        raise HTTPException(404, 'Recording export was interrupted. Download again to resume.')

    @app.head('/api/jobs/{id}/recording/{key}/download')
    @app.get('/api/jobs/{id}/recording/{key}/download')
    def recording_download(id: str, key: str):
        get_job(id)
        if not re.fullmatch(r'[a-f0-9]{20}', key):
            raise HTTPException(404, 'Recording export not found.')
        folder = data / id / 'recordings' / key
        report = cached(folder)
        if not report:
            raise HTTPException(409, 'This recording export is not ready. Use Download MP4 to create it.')
        settings = report['settings']
        name = f'motionclone-{settings["look"]}-{settings["format"]}-{settings["layout"]}.mp4'
        return FileResponse(folder / 'recording.mp4', filename=name, media_type='video/mp4')
