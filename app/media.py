import ipaddress
import json
import math
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse, urljoin
import cv2
import httpx
import numpy as np
from PIL import Image, ImageDraw
from .process import run, Cancelled
from .models import MAX_DURATION

MAX_BYTES = 250 * 1024 * 1024
VIDEO_FORMATS = 'mov,matroska,webm,avi,mpegts,mpeg,ogg,flv'


def validate_url(url):
    p=urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('Use a public HTTPS video link.')
    if p.port not in (None,443): raise ValueError('Only standard HTTPS links are supported.')
    if os.environ.get('FRAMEFORGE_HOSTED')=='1':
        # Public workers only fetch fixed video providers/CDNs, never arbitrary user-controlled hosts.
        providers=('x.com','twitter.com','twimg.com','youtube.com','youtu.be','googlevideo.com','vimeo.com','vimeocdn.com')
        if not any(p.hostname==h or p.hostname.endswith('.'+h) for h in providers):
            raise ValueError('Use a public X, YouTube, or Vimeo video link, or upload your video file.')
    try:
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Local and private network links are not allowed.')
    except socket.gaierror: raise ValueError('Could not find that video host.')
    return p


def download(url, dest, cancel, progress):
    p=validate_url(url)
    if p.hostname=='github.com' and '/blob/' in p.path:
        url='https://raw.githubusercontent.com'+p.path.replace('/blob/','/',1)
        p=validate_url(url)
    hosts=('youtube.com','youtu.be','x.com','twitter.com','vimeo.com')
    if any(p.hostname==h or p.hostname.endswith('.'+h) for h in hosts):
        progress('Downloading public video', 4)
        run([sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-progress',
             '--max-filesize',str(MAX_BYTES),'--socket-timeout','20','--retries','1',
             '-f','bv*[height<=1080]+ba/b[height<=1080]/b',
             '--merge-output-format','mkv','-o',str(dest),'--',url],timeout=180,cancel=cancel)
        # yt-dlp appends the merge container to a fixed output filename.
        merged=dest.with_name(dest.name+'.mkv')
        if merged.exists():merged.replace(dest)
    else:
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
            for _ in range(6):
                validate_url(url)
                with client.stream('GET', url) as response:
                    if response.is_redirect:
                        url=urljoin(url,response.headers['location']);continue
                    if response.status_code>=400:
                        raise ValueError(f'The video host refused this link (HTTP {response.status_code}). Download the video and upload the file instead.')
                    total=0
                    with dest.open('wb') as f:
                        for chunk in response.iter_bytes(1024*512):
                            if cancel.is_set(): raise Cancelled()
                            total+=len(chunk)
                            if total>MAX_BYTES: raise ValueError('Video exceeds the 250 MB limit.')
                            f.write(chunk)
                    break
            else: raise ValueError('Too many redirects in video link.')
    if not dest.exists(): raise ValueError('No public video found. Download it and upload the file instead.')
    if dest.stat().st_size>MAX_BYTES: raise ValueError('Video exceeds the 250 MB limit.')


def probe(path):
    try:
        data=json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-format_whitelist',VIDEO_FORMATS,
                             '-show_streams','-show_format','-of','json',str(path)],timeout=30))
    except RuntimeError as e:raise ValueError('Could not read this video. Upload a valid MP4, MOV or WebM file.') from e
    stream=next((s for s in data.get('streams',[]) if s['codec_type']=='video'),None)
    if not stream: raise ValueError('This file does not contain a playable video.')
    duration=float(stream.get('duration') or data['format'].get('duration') or 0)
    if not math.isfinite(duration) or duration<=0: raise ValueError('Video duration could not be read.')
    num,den=stream.get('avg_frame_rate','24/1').split('/')
    fps=float(num)/max(1,float(den))
    return {'width':int(stream['width']),'height':int(stream['height']), 'duration':duration,
            'fps':fps or 24,'audio':any(s['codec_type']=='audio' for s in data['streams'])}


def prepare(source, folder, cancel, progress, *, faithful=False, rebuild=False):
    meta=probe(source)
    if meta['duration']>MAX_DURATION+.05: raise ValueError(f'Use a clip up to {MAX_DURATION} seconds. Trim the reference before importing.')
    if max(meta['width'],meta['height'])>8192: raise ValueError('Video dimensions exceed 8K. Resize the input first.')
    if faithful or rebuild:
        if max(meta['width'],meta['height'])>4096 or not 1<=meta['fps']<=240:
            raise ValueError('HyperFrames supports clips up to 4K and 240 fps here. Resize this reference before importing.')
        details=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_streams',
            '-show_entries','frame=best_effort_timestamp_time:stream=color_transfer','-of','json',str(source)],timeout=60,cancel=cancel))
        hdr=any(s.get('color_transfer') in ('smpte2084','arib-std-b67') for s in details.get('streams',[]))
        if hdr and not rebuild:
            raise ValueError('HDR needs a color-managed workflow. Upload an SDR copy to preserve its appearance here.')
        times=[float(f['best_effort_timestamp_time']) for f in details.get('frames',[]) if 'best_effort_timestamp_time' in f]
        deltas=[b-a for a,b in zip(times,times[1:])]
        variable=bool(deltas and max(deltas)-min(deltas)>max(.001,.02/meta['fps']))
        if variable and not rebuild:
            raise ValueError('This video has variable frame timing. Upload a constant-frame-rate copy for frame-accurate HyperFrames output.')
        normalizations=[];filters=[];rate=[]
        if hdr:
            filters+=['zscale=t=linear:npl=100','format=gbrpf32le','zscale=p=bt709',
                      'tonemap=tonemap=mobius:desat=0','zscale=t=bt709:m=bt709:r=tv','format=yuv420p']
            normalizations.append('HDR converted to SDR for browser rendering.')
        if variable:
            rate=['-r',str(min(60,max(1,round(meta['fps']))))]
            normalizations.append('Variable frame timing normalized to a constant frame rate.')
        filters+=['scale=trunc(iw*sar/2)*2:ih','setsar=1','pad=ceil(iw/2)*2:ceil(ih/2)*2']
        progress('Normalizing the reference for reconstruction' if rebuild else 'Preserving source frames and audio',8)
        run(['ffmpeg','-y','-v','error','-protocol_whitelist','file,pipe','-format_whitelist',VIDEO_FORMATS,
            '-i',str(source),'-map','0:v:0','-map','0:a:0?',
            '-vf',','.join(filters),*rate,
            '-fps_mode','cfr' if variable else 'passthrough','-c:v','libx264','-preset','veryfast','-crf','0',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','320k','-movflags','+faststart',str(folder/'source.mp4')],timeout=300,cancel=cancel)
        meta=probe(folder/'source.mp4')
        if normalizations:meta['normalizations']=normalizations
        (folder/'media.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        return meta,[]
    progress('Preparing reference frames',8)
    # A normalized local MP4 gives frame-accurate seeking, rotation handling and browser playback.
    run(['ffmpeg','-y','-v','error','-protocol_whitelist','file,pipe','-format_whitelist',VIDEO_FORMATS,
         '-i',str(source),'-map','0:v:0','-map','0:a:0?',
         '-vf',"scale='min(iw,if(gte(iw,ih),1920,1080))':'min(ih,if(gte(iw,ih),1080,1920))':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
         '-r',str(min(60,max(12,round(meta['fps'])))),'-c:v','libx264','-preset','veryfast','-crf','16',
         '-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(folder/'source.mp4')],timeout=240,cancel=cancel)
    meta=probe(folder/'source.mp4')
    (folder/'media.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    sheets=reference_frames(folder,cancel,progress)
    return meta,sheets


def scan_motion(video, cancel, budget=192):
    """Inspect every decoded frame; keep sparse AI inputs anchored to observed changes.

    Visual jumps are candidates, not guaranteed scene cuts (flashes also qualify).
    This cannot recover layers or effects hidden in a flattened reference.
    """
    meta=probe(video)
    cap=cv2.VideoCapture(str(video))
    previous=None; changes=[]; jumps=[]; index=0
    try:
        while True:
            if cancel.is_set():raise Cancelled()
            ok,frame=cap.read()
            if not ok:break
            small=cv2.resize(frame,(160,max(16,round(160*meta['height']/meta['width']))),interpolation=cv2.INTER_AREA)
            if previous is not None:
                delta=np.abs(small.astype(np.float32)-previous.astype(np.float32))/255
                score=float(delta.mean())
                changes.append((score,index))
                if score>.22 and float((delta.mean(axis=2)>.12).mean())>.60:
                    jumps.append(index)
            previous=small;index+=1
    finally:cap.release()
    if not index:raise ValueError('Could not decode reference frames.')
    if budget not in (192,384):raise ValueError('Unsupported analysis budget.')
    count=min(budget//2,max(16,math.ceil(meta['duration']*(6 if budget==384 else 4))))
    samples={round(i*(index-1)/max(1,count-1)) for i in range(count)}
    # Highest-change events are prioritized when a long/strobe-heavy input exceeds
    # the image budget. The manifest explicitly records sampling limits.
    jump_set=set(jumps)
    ranked=sorted(changes,reverse=True)
    for score,n in [(s,n) for s,n in ranked if n in jump_set]:
        neighbors={k for k in (n-1,n,n+1) if 0<=k<index}
        if len(samples|neighbors)<=budget-24:samples.update(neighbors)
    for score,n in ranked:
        if score<.012 or len(samples)>=budget:break
        if all(abs(n-k)>2 for k in samples):samples.add(n)
    return {'version':2,'budget':budget,'fps':meta['fps'],'decoded_frames':index,
            'visual_jump_frames':jumps,'sample_frames':sorted(samples),
            'unsampled_visual_jumps':[n for n in jumps if n not in samples],
            'note':'Every frame inspected at reduced resolution. AI sees selected frames; visual jumps may be flashes or cuts.'}


def reference_frames(folder, cancel, progress, budget=192):
    progress('Inspecting every frame for cuts and fast effects',10)
    temporal=scan_motion(folder/'source.mp4',cancel,budget=budget)
    (folder/'temporal.json').write_text(json.dumps(temporal,indent=2),encoding='utf-8')
    # Remove only this project's derived sheets; source and authored files survive.
    for old in folder.glob('reference-*.jpg'):old.unlink()
    return contact_sheets(folder/'source.mp4',folder/'reference',cancel=cancel,
                          timestamps=[n/temporal['fps'] for n in temporal['sample_frames']])


def thumbnail(video, dest):
    cap=cv2.VideoCapture(str(video))
    try:
        count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,int(count*.3)))
        ok,frame=cap.read()
        if ok:
            image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            image.thumbnail((640,400));image.save(dest,quality=88)
    finally:cap.release()


def review_timestamps(meta, plan, temporal=None):
    duration=meta['duration'];step=1/meta['fps']
    edges={round(max(0,min(duration-step,t+offset))*meta['fps'])/meta['fps']
           for layer in [*plan.tracks,*plan.masks] for t in [layer.start,layer.end]
           for offset in [-step,0,step]}
    critical=sorted(edges)
    if len(critical)>96:critical=[critical[round(i*(len(critical)-1)/95)] for i in range(96)]
    # Include observed changes even when the model failed to create a scene there.
    observed=sorted({n for cut in (temporal or {}).get('visual_jump_frames',[])
                     for n in [cut-1,cut,cut+1] if 0<=n<math.ceil(duration*meta['fps'])})
    if len(observed)>96:observed=[observed[round(i*(len(observed)-1)/95)] for i in range(96)]
    critical += [n/meta['fps'] for n in observed]
    count=min(48,max(16,math.ceil(duration*3)))
    regular=[round(i*duration/count*meta['fps'])/meta['fps'] for i in range(count)]
    return sorted(set(critical+regular))


def contact_sheets(video, prefix, count=24, cancel=None, timestamps=None):
    meta=probe(video)
    cap=cv2.VideoCapture(str(video))
    images=[];sheets=[]
    cell_w=min(384,round(300*meta['width']/meta['height']));cell_h=round(cell_w*meta['height']/meta['width'])
    if timestamps is not None:count=len(timestamps)
    for i in range(count):
        if cancel and cancel.is_set():
            cap.release();raise Cancelled()
        t=min(meta['duration']-1/meta['fps'],timestamps[i] if timestamps is not None else i*meta['duration']/count)
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
        ok, frame=cap.read()
        if not ok: continue
        im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));im.thumbnail((cell_w,cell_h))
        cell=Image.new('RGB',(cell_w,cell_h+26),'#191b1e');cell.paste(im,((cell_w-im.width)//2,0))
        ImageDraw.Draw(cell).text((8,cell_h+5),f'{t:.3f}s | frame {round(t*meta["fps"])}',fill='white')
        images.append(cell)
        if len(images)==12 or i==count-1:
            sheet=Image.new('RGB',(cell_w*3,(cell_h+26)*math.ceil(len(images)/3)),'#191b1e')
            for n,img in enumerate(images):sheet.paste(img,((n%3)*cell_w,(n//3)*(cell_h+26)))
            path=prefix.with_name(prefix.name+f'-{len(sheets):02}.jpg');sheet.save(path,quality=92)
            sheets.append(path);images=[]
    cap.release()
    if not sheets:raise ValueError('Could not decode reference frames.')
    return sheets
