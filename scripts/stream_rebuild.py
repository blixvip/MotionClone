"""Export an existing editable rebuild without storing a PNG for every frame."""
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hyperframes import VERSION, frame_info, run_cli
from app.media import probe
from app.models import Brief
from app.process import run
from app.reconstruction import audit_project, compare_frames, digest, fingerprint


def export(job_id):
    folder = (ROOT / 'data' / job_id).resolve()
    if folder.parent != (ROOT / 'data').resolve():
        raise ValueError('Invalid project ID.')
    job = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
    if job['status'] in ('running', 'queued'):
        raise ValueError('Wait for the active render to finish before exporting.')
    brief = Brief.model_validate(job['brief'])
    project = folder / 'rebuild'
    meta = probe(folder / 'source.mp4')
    structure = audit_project(project, meta)
    key = fingerprint(folder, brief)
    cancel = threading.Event()
    started = time.monotonic()
    expected, fps = frame_info(folder / 'source.mp4', cancel)
    rendered = folder / 'stream-video.pending.mp4'
    pending = folder / 'stream-final.pending.mp4'
    print(f'Streaming {job_id}: {expected} frames at {fps} fps', flush=True)
    run_cli(['render', str(project), '--format', 'mp4', '--output', str(rendered),
             '--fps', fps, '--quality', 'high', '--crf', '12', '--workers', '1',
             '--video-frame-format', 'png', '--low-memory-mode', '--no-best-effort'],
            folder, cancel)
    # HyperFrames can encode its audio track. Restore the exact original bitstream.
    args = ['ffmpeg', '-y', '-v', 'error', '-i', str(rendered)]
    if brief.keep_audio and meta['audio']:
        args += ['-i', str(folder / 'source.mp4'), '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy']
    else:
        args += ['-map', '0:v:0', '-c:v', 'copy', '-an']
    run(args + ['-movflags', '+faststart', str(pending)], timeout=120, cancel=cancel)
    print(f'Verifying {job_id}: every frame and original audio', flush=True)
    report = compare_frames(folder, pending, cancel)
    if report['audio_present'] != bool(brief.keep_audio and meta['audio']):
        raise ValueError('Audio does not match the requested setting.')
    if fingerprint(folder, brief) != key:
        raise ValueError('Project changed during export; output was not published.')
    report.update(structure=structure, fingerprint=key, output_sha256=digest(pending),
                  cache_hit=False, render_seconds=round(time.monotonic()-started, 2),
                  capture_method='HyperFrames streaming MP4; no temporary frame sequence')
    analysis = folder / 'analysis-report.json'
    if analysis.exists():
        report['analysis'] = json.loads(analysis.read_text(encoding='utf-8'))
    report['normalizations'] = json.loads((folder/'media.json').read_text()).get('normalizations', [])
    output = folder / 'output.mp4'
    if output.exists():
        raise ValueError('A finished output already exists; leaving it untouched.')
    pending.replace(output)
    (folder/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (project/'manifest.json').write_text(json.dumps(dict(renderer='hyperframes', version=VERSION,
        independent_visual_layers=True, source_backed=False, dimensions=report['dimensions'],
        fps=fps, frames=expected, structure=structure, visual_match=report['visual_check'],
        ssim_mean=report['ssim_mean']), indent=2), encoding='utf-8')
    (project/'README.md').write_text('# Editable reconstruction\n\n'
        'Edit project.json, then run npm run sync. Install dependencies with npm install.\n\n'
        'For export with limited disk space, run npx hyperframes render --low-memory-mode '
        '--workers 1 --quality high --crf 12 --output output.mp4.\n\n'
        'The original video is not used as a visual layer. Visible differences are recorded '
        'in verification.json. Original audio is preserved in the verified MP4.\n', encoding='utf-8')
    rendered.unlink()
    print(f'Verified streaming export: {output}', flush=True)


if __name__ == '__main__':
    export(sys.argv[1])
