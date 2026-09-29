"""Source-backed HyperFrames compositions, with a full-frame visual quality gate.

This preserves flattened source artwork; it does not infer editable objects.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from fractions import Fraction
from pathlib import Path

from .media import probe
from .process import Cancelled, popen, run, own_process_tree

RUNTIME = Path(__file__).resolve().parents[1] / 'hyperframes'
CLI = RUNTIME / 'node_modules/hyperframes/bin/hyperframes.mjs'
VERSION = '0.8.33'


def frame_info(path, cancel=None):
    value = json.loads(run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
        '-show_entries', 'stream=nb_read_frames,avg_frame_rate,width,height', '-of', 'json', str(path)], cancel=cancel))['streams'][0]
    return int(value['nb_read_frames']), str(Fraction(value['avg_frame_rate']))


def write_project(folder, brief, cancel=None):
    media = probe(folder / 'source.mp4')
    count, fps = frame_info(folder / 'source.mp4', cancel)
    duration = count / float(Fraction(fps))
    dest = folder / 'hyperframes'
    (dest / 'assets').mkdir(parents=True, exist_ok=True)
    (dest / 'vendor').mkdir(exist_ok=True)
    shutil.copy2(folder / 'source.mp4', dest / 'assets/source.mp4')
    shutil.copy2(RUNTIME / 'node_modules/gsap/dist/gsap.min.js', dest / 'vendor/gsap.min.js')
    audio = (f'<audio id="reference-audio" src="assets/source.mp4" data-start="0" '
             f'data-duration="{duration:.12f}" data-track-index="1" data-volume="1"></audio>') if brief.keep_audio and media['audio'] else ''
    (dest / 'index.html').write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Source-frame recreation</title>
<meta name="viewport" content="width={media['width']}, height={media['height']}">
<script src="vendor/gsap.min.js"></script>
<style>html,body{{margin:0;width:{media['width']}px;height:{media['height']}px;background:#000;overflow:hidden}}
#root{{position:relative;width:{media['width']}px;height:{media['height']}px;overflow:hidden}}
#reference{{position:absolute;inset:0;width:100%;height:100%;object-fit:fill;display:block}}</style></head>
<body><div id="root" data-composition-id="source-recreation" data-width="{media['width']}"
data-height="{media['height']}" data-fps="{fps}" data-duration="{duration:.12f}">
<video id="reference" src="assets/source.mp4" muted playsinline preload="auto"
data-start="0" data-duration="{duration:.12f}" data-track-index="0"></video>{audio}</div>
<script>window.__timelines=window.__timelines||{{}};
window.__timelines['source-recreation']=gsap.timeline({{paused:true}}).to({{}},{{duration:{duration:.12f}}});</script>
</body></html>''', encoding='utf-8')
    (dest / 'hyperframes.json').write_text(json.dumps({'$schema':'https://hyperframes.heygen.com/schema/hyperframes.json',
        'media':{'autoProxy':False}}, indent=2), encoding='utf-8')
    (dest / 'package.json').write_text(json.dumps({'name':'source-frame-recreation','private':True,
        'scripts':{'preview':'hyperframes preview','check':'hyperframes check',
                   'render':f'hyperframes render --video-frame-format png --quality high --crf 0 --fps {fps} --output output.mp4'},
        'dependencies':{'hyperframes':VERSION}}, indent=2), encoding='utf-8')
    manifest = {'renderer':'hyperframes','version':VERSION,'mode':'faithful','source_backed':True,
        'source_sha256':hashlib.sha256((folder/'source.mp4').read_bytes()).hexdigest(),
        'frames':count,'fps':fps,'duration':duration,'dimensions':[media['width'],media['height']],
        'audio':bool(brief.keep_audio and media['audio']),
        'description':'Every source frame is retained as flattened artwork. Text, objects and effects are not independently reconstructed.'}
    (dest / 'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (dest / 'README.md').write_text('# HyperFrames source-frame project\n\n'
        'This composition reuses every frame of assets/source.mp4, preserving the original artwork and timing. '
        'It is not an independently editable reconstruction of text, objects or effects. '
        'You can trim the media or add HTML layers over it.\n\n'
        'Install Node.js 22+ and FFmpeg. Run `npm install`, `npm run check`, then `npm run preview` or `npm run render`. '
        'The MotionClone app additionally renders PNG frames and checks every output frame against the reference before accepting it.\n', encoding='utf-8')
    return dest, manifest


def run_cli(args, folder, cancel, progress=None):
    log = folder / ('hyperframes-render.log' if args[0]=='render' else 'hyperframes-check.log')
    env = os.environ.copy()
    env.update(NO_COLOR='1', CI='1', DO_NOT_TRACK='1', PRODUCER_ENABLE_BROWSER_POOL='false')
    with log.open('w',encoding='utf-8') as stream:
        proc = popen(['node',str(CLI),*args],cwd=folder,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,env=env)
        close_tree = own_process_tree(proc)
        start = time.monotonic()
        last = -1
        try:
            while proc.poll() is None:
                if cancel.is_set():raise Cancelled()
                if time.monotonic()-start>900:raise TimeoutError('HyperFrames took too long. The project is saved; try a shorter clip.')
                tail = log.read_text(encoding='utf-8',errors='replace')[-6000:]
                # The CLI can retain idle Node handles on Windows after its final
                # validated-artifact summary. Close our job then; the independent
                # frame count, visual and audio gates below still decide acceptance.
                if args[0]=='render' and 'Render complete' in tail and 'frames · rendered in' in tail:
                    return
                if progress:
                    matches = re.findall(r'Capturing frame (\d+)/(\d+)',tail)
                    value = 20+int(int(matches[-1][0])/int(matches[-1][1])*65) if matches else 20
                    value = max(last,min(85,value))
                    if value != last:progress('Rendering every source frame in HyperFrames',value);last=value
                time.sleep(.5)
            if proc.returncode:raise ValueError(f'HyperFrames failed. Details are saved in {log.name}.')
        finally:
            close_tree()
            if proc.poll() is None:
                # Exact app-owned Node process only. Never enumerate or stop unrelated apps.
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()


def verify(source, output, folder, brief, cancel):
    expected, fps = frame_info(source,cancel)
    count, actual_fps = frame_info(output,cancel)
    reference, actual = probe(source), probe(output)
    if (count != expected or Fraction(fps)!=Fraction(actual_fps) or
        (actual['width'],actual['height'])!=(reference['width'],reference['height']) or
        actual['audio']!=bool(brief.keep_audio and reference['audio'])):
        raise ValueError('Frame count, dimensions, timing or audio do not match the reference. Output was not accepted.')
    # Normalize both timebases and index-based timestamps. Compare every frame, including the ending.
    run(['ffmpeg','-y','-v','error','-i',str(source),'-i',str(output),'-filter_complex',
        f'[0:v]settb=AVTB,setpts=N/({fps})/TB,format=yuv420p[a];'
        f'[1:v]settb=AVTB,setpts=N/({fps})/TB,format=yuv420p[b];'
        '[a][b]ssim=stats_file=fidelity-frames.log:shortest=1',
        '-an','-f','null','-'],cwd=folder,timeout=240,cancel=cancel)
    scores=[float(x) for x in re.findall(r'All:([0-9.]+)',(folder/'fidelity-frames.log').read_text())]
    if len(scores)!=expected or min(scores)<.97 or sum(scores)/len(scores)<.99:
        raise ValueError('The render did not match the reference closely enough. Output was not accepted; comparison details are saved.')
    run(['ffmpeg','-v','error','-xerror','-i',str(output),'-f','null','-'],timeout=240,cancel=cancel)
    audio_match=None
    if actual['audio']:
        hashes=[run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-'],
                    timeout=120,cancel=cancel).strip() for path in [source,output]]
        audio_match=hashes[0]==hashes[1]
        if not audio_match:raise ValueError('The original audio was changed or truncated. Output was not accepted.')
    return {'decoded':True,'expected_frames':expected,'actual_frames':count,'compared_frames':len(scores),
        'audio_present':actual['audio'],'dimensions':[actual['width'],actual['height']],
        'fps':actual['fps'],'duration':actual['duration'],'renderer':'hyperframes','renderer_version':VERSION,
        'mode':'faithful','source_backed':True,'visual_check':'passed','audio_bitstream_match':audio_match,'ssim_mean':sum(scores)/len(scores),
        'ssim_min':min(scores),'minimum_mean':.99,'minimum_frame':.97,
        'note':'SSIM compares decoded output to the imported source. Source artwork is reused, not rebuilt as editable objects.'}


def render(folder, brief, cancel, progress):
    if not CLI.exists():raise ValueError('HyperFrames is missing. Run Start MotionClone to install it.')
    progress('Preparing HyperFrames with the original artwork',12)
    project, manifest = write_project(folder,brief,cancel)
    # A fresh output directory prevents stale frames from a previous attempt entering the encode.
    frames = folder / ('frames-' + str(time.time_ns()))
    progress('Checking the HyperFrames composition',16)
    run_cli(['check',str(project),'--json'],folder,cancel)
    run_cli(['render',str(project),'--format','png-sequence','--output',str(frames),
        '--fps',manifest['fps'],'--quality','high','--video-frame-format','png','--workers','2',
        '--no-best-effort'],folder,cancel,progress)
    images = sorted(frames.glob('*.png'))
    if len(images)!=manifest['frames']:raise ValueError(f'HyperFrames returned {len(images)} frames; expected {manifest["frames"]}. Output was not accepted.')
    progress('Encoding the video and preserving audio',88)
    # The concat manifest avoids assumptions about HyperFrames filename padding.
    listing = folder/'frames.concat.txt'
    listing.write_text(''.join(f"file '{p.as_posix()}'\nduration {1/float(Fraction(manifest['fps'])):.15f}\n" for p in images),encoding='utf-8')
    pending = folder/'output.pending.mp4'
    video_only = folder/'video.pending.mp4'
    args=['ffmpeg','-y','-v','error','-f','concat','-safe','0','-r',manifest['fps'],'-i',str(listing),'-map','0:v:0']
    args+=['-c:v','libx264','-preset','fast','-crf','0','-pix_fmt','yuv420p',
           '-r',manifest['fps'],'-frames:v',str(manifest['frames']),'-movflags','+faststart',str(video_only)]
    run(args,timeout=300,cancel=cancel)
    if manifest['audio']:
        # Mux separately: -frames:v on a combined encode can truncate the last audio packets.
        run(['ffmpeg','-y','-v','error','-i',str(video_only),'-i',str(folder/'source.mp4'),
             '-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(pending)],timeout=120,cancel=cancel)
        video_only.unlink(missing_ok=True)
    else:video_only.replace(pending)
    progress('Comparing every rendered frame against the reference',95)
    report=verify(folder/'source.mp4',pending,folder,brief,cancel)
    if cancel.is_set():raise Cancelled()
    pending.replace(folder/'output.mp4')
    (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Only remove PNGs created by this call, inside the verified project directory.
    if frames.resolve().parent!=folder.resolve():raise ValueError('Invalid frame directory.')
    shutil.rmtree(frames)
    listing.unlink(missing_ok=True)
    return folder/'output.mp4'


def export_project(folder):
    project=folder/'hyperframes'
    if not (project/'manifest.json').exists():raise ValueError('Create the HyperFrames project first.')
    dest=folder/'hyperframes-project.zip'
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['index.html','hyperframes.json','package.json','manifest.json','README.md','assets/source.mp4','vendor/gsap.min.js']:
            archive.write(project/name,name)
        if (folder/'verification.json').exists():archive.write(folder/'verification.json','verification.json')
    return dest
