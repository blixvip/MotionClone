"""Inventory the requested references before submitting any rebuilds."""
import concurrent.futures
import json
from pathlib import Path
import re
import sys
import hashlib
import subprocess
import time
import httpx

import yt_dlp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'ads-20260916'
URLS = [
    'https://x.com/rajzmotion/status/2089412477641760788/video/1',
    'https://x.com/rajzmotion/status/2096237878464622927/video/1',
    'https://x.com/rajzmotion/status/2095924719044415732/video/1',
    'https://x.com/rajzmotion/status/2094670123890344039/video/1',
    'https://x.com/kail_designs/status/2097932370498531365/video/1',
    'https://x.com/rajzmotion/status/2094419587945378287/video/1',
    'https://x.com/rajzmotion/status/2091508067074773423/video/1',
    'https://x.com/rajzmotion/status/2091044826796167593/video/1',
    'https://x.com/rajzmotion/status/2090295702836621744/video/1',
    *[f'https://x.com/kail_designs/status/1976270636654919715/video/{n}' for n in range(1, 5)],
    'https://x.com/kail_designs/status/2097282374229000639/video/1',
]


def identity(url):
    found = re.search(r'/status/(\d+)(?:/video/(\d+))?', url)
    return (found[1], int(found[2] or 1)) if found else None


def fetch(url):
    path = OUT / f'{identity(url)[0]}-metadata.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 20, 'retries': 1}) as downloader:
        info = downloader.sanitize_info(downloader.extract_info(url, download=False))
    path.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
    return info


def survey():
    OUT.mkdir(parents=True, exist_ok=True)
    existing = {}
    for path in (ROOT / 'data').glob('*/job.json'):
        job = json.loads(path.read_text(encoding='utf-8'))
        if job.get('status') == 'complete' and (path.parent / 'output.mp4').exists():
            key = identity(job.get('url', ''))
            if key:
                existing[key] = job['id']
    unique_posts = {identity(url)[0]: url for url in URLS}
    metadata = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, url): post for post, url in unique_posts.items()}
        for future in concurrent.futures.as_completed(futures):
            post = futures[future]
            try:
                metadata[post] = future.result()
            except Exception as exc:
                metadata[post] = {'error': str(exc)}
    rows = []
    for url in URLS:
        post, number = identity(url)
        row = {'url': url, 'post': post, 'video': number}
        info = metadata[post]
        entries = info.get('entries') or [info]
        item = entries[number-1] if number <= len(entries) else {}
        row.update(title=item.get('title', ''), duration=item.get('duration'), media_id=item.get('id'))
        if (post, number) in existing:
            row.update(action='already rebuilt', job=existing[(post, number)])
        elif info.get('error') or not item:
            row.update(action='unavailable', error=info.get('error', 'Video missing'))
        elif row['duration'] is None:
            row.update(action='probe duration')
        elif row['duration'] < 10:
            row.update(action='skip short')
        elif row['duration'] > 120:
            row.update(action='over app limit')
        else:
            row.update(action='rebuild')
        rows.append(row)
    (OUT / 'inventory.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(rows, indent=2, ensure_ascii=True), flush=True)


def download_one(row):
    target = OUT / 'inputs' / f"{row['media_id']}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        metadata = json.loads((OUT / f"{row['post']}-metadata.json").read_text(encoding='utf-8'))
        item = (metadata.get('entries') or [metadata])[row['video']-1]
        with yt_dlp.YoutubeDL({'quiet': True, 'noprogress': True, 'no_warnings': True, 'socket_timeout': 20,
                              'retries': 2, 'outtmpl': str(target),
                              'format': 'bv*[height<=1080]+ba/b[height<=1080]/b',
                              'merge_output_format': 'mp4'}) as downloader:
            downloader.process_ie_result(item, download=True)
    details = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                         'format=duration:stream=width,height,codec_type', '-of', 'json', str(target)]))
    duration = float(details['format']['duration'])
    if abs(duration-row['duration']) > 1:
        raise RuntimeError(f"Wrong duration for {row['url']}: {duration}")
    row.update(input=str(target), actual_duration=duration,
               sha256=hashlib.sha256(target.read_bytes()).hexdigest(), action='rebuild')
    row.pop('error', None)
    print(f"Downloaded {row['post']}/{row['video']}: {duration:.2f}s", flush=True)
    return row


def downloads():
    rows = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(download_one, row): row for row in rows if row['action'] in ('rebuild', 'download failed')}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                futures[future].update(action='download failed', error=str(exc))
                print(f"Download failed: {futures[future]['url']}: {exc}", flush=True)
    (OUT / 'inventory.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')


def contact():
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    rows = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    eligible = [r for r in rows if r.get('input')]
    sheet = Image.new('RGB', (1200, 240*len(eligible)), '#15151b')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    for i, row in enumerate(eligible):
        draw.text((12, i*240+8), f"{row['post']} / video {row['video']} — {row['duration']:.1f}s", font=font, fill='white')
        cap = cv2.VideoCapture(row['input'])
        for col, ratio in enumerate((.15, .5, .8)):
            cap.set(cv2.CAP_PROP_POS_MSEC, row['actual_duration']*ratio*1000)
            ok, frame = cap.read()
            if ok:
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                image.thumbnail((390, 196))
                sheet.paste(image, (col*400+(400-image.width)//2, i*240+38))
        cap.release()
    sheet.save(OUT / 'reference-contact.jpg')


def rebuild():
    inventory = OUT / 'inventory.json'
    rows = json.loads(inventory.read_text(encoding='utf-8'))
    def save():
        temporary = inventory.with_suffix('.tmp')
        temporary.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(inventory)
        lines = ['# Requested ad rebuilds', '', 'Clips under 10 seconds and previous rebuilds are excluded. Longest first.', '']
        for row in sorted(rows, key=lambda r:r.get('duration') or 0, reverse=True):
            status = row.get('result', row['action'])
            target = f"http://127.0.0.1:4319/?project={row['job']}" if row.get('job') else row['url']
            lines.append(f"- [{row['title'].replace('[', '').replace(']', '')}]({target}) — {row.get('duration', '?')}s — {status}")
        (OUT / 'results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:4319', timeout=180, trust_env=False,
                      limits=httpx.Limits(max_keepalive_connections=0)) as client:
        def api(method, path, **kwargs):
            for attempt in range(6):
                try:
                    response = client.request(method, path, **kwargs)
                    break
                except httpx.TransportError:
                    if method != 'GET' or attempt == 5:
                        raise
                    time.sleep(2)
            response.raise_for_status()
            return response.json()
        state = api('GET', '/api/status')
        if not state.get('chatgpt'):
            raise RuntimeError('Connect the existing AI account before starting the batch.')
        client.headers['X-Frameforge-Token'] = state['token']
        for row in sorted(rows, key=lambda r:r.get('duration') or 0, reverse=True):
            if row['action'] != 'rebuild':
                continue
            tag = f"source:x:{row['post']}:{row['video']}"
            library = api('GET', '/api/library')
            existing = next((job for job in library if tag in job.get('tags', []) or identity(job.get('url', '')) == identity(row['url'])), None)
            if existing and existing['status'] == 'complete':
                row.update(job=existing['id'], result='already rebuilt');save();continue
            if not row.get('job') and existing:
                row['job'] = existing['id'];save()
            while api('GET', '/api/status').get('active'):
                active = api('GET', '/api/status')['active']
                if active == row.get('job'):
                    break
                time.sleep(5)
            if not row.get('job'):
                with open(row['input'], 'rb') as media:
                    job = api('POST', '/api/jobs', files={'video': (f"{row['post']}-video-{row['video']}.mp4", media, 'video/mp4')},
                              data={'mode': 'hyperframes', 'sampling': 'detailed', 'keep_audio': 'true', 'auto_review': 'true',
                                    'instructions': 'Rebuild this entire reference ad as independent editable motion graphics. Preserve its original message, product names, palette, typography, composition, scene order and timing. Reconstruct the visible UI, text and transitions faithfully. Do not substitute generic placeholder scenes. Keep the original audio.'})
                row.update(job=job['id'], result='processing');save()
                api('PATCH', f"/api/jobs/{job['id']}", json={'name': row['title'][:140]+(f" · video {row['video']}" if row['post']=='1976270636654919715' else ''),
                    'collection': 'X ads · September 16', 'tags': [tag, 'ad-batch-20260916']})
                print(f"START {row['post']}/{row['video']} {row['duration']:.1f}s job={job['id']}", flush=True)
            previous = None
            while True:
                job = api('GET', f"/api/jobs/{row['job']}")
                stage = job.get('stage')
                if stage != previous:
                    print(f"{row['job']}: {stage}", flush=True);previous = stage
                if job['status'] not in ('running', 'queued'):
                    render_log = ROOT/'data'/row['job']/'hyperframes-render.log'
                    disk_limit = render_log.exists() and 'Disk capture may need' in render_log.read_text(encoding='utf-8', errors='replace')[-16000:]
                    if job['status'] == 'error' and disk_limit and row.get('stream_attempts', 0) < 2:
                        row['stream_attempts'] = row.get('stream_attempts', 0)+1;save()
                        print(f"Streaming export avoids temporary frame storage: {row['job']}", flush=True)
                        streamed = subprocess.run([sys.executable, str(ROOT/'scripts/stream_rebuild.py'), row['job']], cwd=ROOT)
                        if streamed.returncode == 0:
                            api('POST', f"/api/jobs/{row['job']}/retry", json=job['brief'])
                            continue
                    checkpoints = len(list((ROOT/'data'/row['job']/'scene-work').glob('*/checkpoint.json')))
                    made_progress = checkpoints > row.get('checkpoints_at_retry', 0)
                    no_progress = 0 if made_progress else row.get('no_progress_retries', 0)+1
                    if job['status'] == 'error' and no_progress <= 2 and row.get('retries', 0) < 12:
                        row.update(checkpoints_at_retry=checkpoints, no_progress_retries=no_progress)
                        row['retries'] = row.get('retries', 0)+1;save()
                        print(f"Retry {row['job']}: {job.get('error')}", flush=True)
                        api('POST', f"/api/jobs/{row['job']}/retry", json=job['brief'])
                        continue
                    row.update(result=job['status'], error=job.get('error'), warning=job.get('warning'))
                    if job['status']=='complete':
                        folder = ROOT / 'data' / row['job']
                        report = json.loads((folder/'verification.json').read_text(encoding='utf-8'))
                        row.update(output=str(folder/'output.mp4'), verification=report)
                    save()
                    print(f"FINISH {row['job']}: {row['result']}", flush=True)
                    break
                time.sleep(5)
        print('BATCH FINISHED', flush=True)


if __name__ == '__main__':
    rebuild() if '--rebuild' in sys.argv else contact() if '--contact' in sys.argv else downloads() if '--download' in sys.argv else survey()
