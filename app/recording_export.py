"""Export the real recording canvas, frame by frame, with one original audio track."""
import hashlib
import json
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from .hyperframes import frame_info
from .media import probe
from .models import Strict
from .process import popen, run

ROOT = Path(__file__).resolve().parents[1]
FORMATS = {'landscape': (1920, 1080), 'portrait': (1080, 1920), 'square': (1080, 1080),
           'ultrawide': (3840, 1080), 'feed': (1080, 1350)}


class RecordingOptions(Strict):
    look: Literal['studio', 'paper', 'signal', 'cobalt', 'peach', 'mono'] = 'studio'
    format: Literal['landscape', 'portrait', 'square', 'ultrawide', 'feed'] = 'landscape'
    layout: Literal['split', 'stack', 'spotlight', 'wipe'] = 'split'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(folder, options):
    value = hashlib.sha256(b'recording-canvas-v1')
    value.update(options.model_dump_json().encode())
    paths = [folder / 'source.mp4', folder / 'output.mp4', Path(__file__)]
    paths += sorted((ROOT / 'web').glob('*.js')) + sorted((ROOT / 'web').glob('*.css'))
    paths += [ROOT / 'web/index.html'] + sorted((ROOT / 'web/assets').glob('*.svg'))
    for path in paths:
        value.update(path.name.encode())
        value.update(digest(path).encode())
    return value.hexdigest()[:20]


def cached(folder):
    report_path, output = folder / 'verification.json', folder / 'recording.mp4'
    if not report_path.exists() or not output.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if not isinstance(report, dict) or report.get('verified') is not True:
            return None
        settings = RecordingOptions.model_validate(report.get('settings'))
        if output.stat().st_size and report.get('output_sha256') == digest(output):
            report['settings'] = settings.model_dump()
            return report
    except (ValueError, OSError):
        pass
    return None


def launch_browser(chromium):
    from playwright.sync_api import Error

    last = None
    for channel in ('chrome', 'msedge', None):
        try:
            return chromium.launch(**({'channel': channel} if channel else {}))
        except Error as exc:
            last = exc
    raise ValueError('No recording browser could start. Install Chrome or Edge, then retry Save MP4.') from last


SEEK = """async t => {
  const videos=['result-video','source-video'].map(id=>document.getElementById(id));
  videos.forEach(v=>{v.pause();v.muted=true;});
  await Promise.all(videos.map(v=>new Promise((resolve,reject)=>{
    if(Math.abs(v.currentTime-t)<.0001&&v.readyState>=2&&!v.seeking){resolve();return;}
    const timer=setTimeout(()=>{v.removeEventListener('seeked',done);reject(new Error('Video frame seek timed out'));},15000);
    function done(){clearTimeout(timer);resolve();}
    v.addEventListener('seeked',done,{once:true});v.currentTime=t;
  })));
  window.seekComparisonShader?.(t);
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
}"""


def encoder_command(audio, pending, fps):
    command = ['ffmpeg', '-y', '-v', 'error', '-f', 'image2pipe', '-framerate', fps, '-vcodec', 'png', '-i', 'pipe:0']
    if audio:
        command += ['-i', str(audio), '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'copy']
    else:
        command += ['-map', '0:v:0', '-an']
    # EOF on the frame pipe ends the video. Time/frame output limits would cut
    # AAC packets that extend slightly past the final video frame.
    return command + ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(pending)]


def render(folder, target, options, port, progress):
    from playwright.sync_api import sync_playwright

    count, fps = frame_info(folder / 'output.mp4')
    rate = float(Fraction(fps))
    duration = count / rate
    source = probe(folder / 'source.mp4')
    rebuilt = probe(folder / 'output.mp4')
    if abs(source['duration'] - duration) > max(.15, 2 / rate):
        raise ValueError('The reference and rebuilt video have different durations. Rebuild them before exporting a comparison.')
    audio = folder / 'source.mp4' if source['audio'] else folder / 'output.mp4' if rebuilt['audio'] else None
    width, height = FORMATS[options.format]
    target.mkdir(parents=True, exist_ok=True)
    pending = target / 'recording.pending.mp4'
    query = urlencode({'project': folder.name, 'view': 'compare', 'record': '1', 'capture': '1', **options.model_dump()})
    command = encoder_command(audio, pending, fps)
    progress('Preparing recording layout', 2)
    started = time.monotonic()
    with sync_playwright() as pw, (target / 'encoder.log').open('wb') as log:
        browser = launch_browser(pw.chromium)
        encoder = None
        try:
            page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{port}/?{query}', wait_until='domcontentloaded')
            page.wait_for_function('() => document.body.classList.contains("recording-view")')
            page.wait_for_function('() => ["source-video","result-video"].every(id=>document.getElementById(id).readyState>=2)')
            page.evaluate('() => document.fonts.ready')
            page.wait_for_function('() => [...document.querySelectorAll("#recording-canvas img")].every(image=>image.complete && image.naturalWidth>0)')
            canvas = page.locator('#recording-canvas')
            bounds = canvas.bounding_box()
            if not bounds or abs(bounds['width'] - width) > 1 or abs(bounds['height'] - height) > 1:
                raise ValueError('Recording layout did not fit the selected export dimensions.')
            page.mouse.move(0, height - 1)
            encoder = popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            previous = -1
            for frame in range(count):
                if time.monotonic() - started > 3600:
                    raise TimeoutError('Recording export timed out. Retry the download.')
                # Mid-frame seeks avoid rounding onto the preceding decoded frame.
                page.evaluate(SEEK, (frame + .5) / rate)
                # The layout is fixed for the whole capture. Avoid locator's
                # repeated scrolling/stability checks on every video frame.
                shot = page.screenshot(type='png', clip=bounds, timeout=30000)
                encoder.stdin.write(shot)
                if frame in (0, count // 2, count - 1):
                    (target / f'frame-{frame:06d}.png').write_bytes(shot)
                percent = 3 + int((frame + 1) / count * 90)
                if percent != previous:
                    progress(f'Exporting recording view · {frame + 1}/{count} frames', percent)
                    previous = percent
            encoder.stdin.close()
            encoder.wait(timeout=180)
            if encoder.returncode:
                raise ValueError('Recording video could not be encoded. Retry the download; encoder details are saved locally.')
        finally:
            if encoder and encoder.poll() is None:
                encoder.terminate()  # Only this export's encoder, never a terminal or another application.
                try:
                    encoder.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    encoder.kill(); encoder.wait()
            browser.close()
    progress('Checking full duration and audio', 96)
    actual, actual_fps = frame_info(pending)
    output = probe(pending)
    if actual != count or Fraction(actual_fps) != Fraction(fps) or (output['width'], output['height']) != (width, height):
        raise ValueError('Recording export failed the frame-count or format check.')
    if output['audio'] != bool(audio):
        raise ValueError('Recording export is missing its audio track.')
    if abs(output['duration'] - duration) > max(.15, 2 / rate):
        raise ValueError('Recording export did not preserve the complete duration.')
    run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(pending), '-f', 'null', '-'], timeout=300)
    audio_match = None
    if audio:
        hashes = [run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-'], timeout=120).strip() for path in (audio, pending)]
        audio_match = hashes[0] == hashes[1]
        if not audio_match:
            raise ValueError('Recording audio changed or was truncated. The export was not accepted.')
    report = dict(verified=True, settings=options.model_dump(), frames=count, fps=fps,
                  dimensions=[width, height], duration=duration, audio=bool(audio), audio_bitstream_match=audio_match,
                  output_sha256=digest(pending), seconds=round(time.monotonic() - started, 2))
    pending.replace(target / 'recording.mp4')
    verification = target / 'verification.pending.json'
    verification.write_text(json.dumps(report, indent=2), encoding='utf-8')
    verification.replace(target / 'verification.json')
    return report
