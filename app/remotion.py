"""Trusted Remotion source and render bridge for validated editable layers."""
import json
import math
import shutil
import subprocess
import time
import zipfile
import os
from pathlib import Path
from .media import probe
from .process import Cancelled, popen, run

RUNTIME = Path(__file__).resolve().parents[1] / 'remotion'


def write_project(folder, plan, brief):
    dest = folder / 'remotion' / 'public'
    dest.mkdir(parents=True, exist_ok=True)
    media = json.loads((folder / 'media.json').read_text(encoding='utf-8'))
    data = {'plan':plan.model_dump(), 'media':media, 'logo':None, 'audio':None}
    if (folder/'logo.png').exists():
        shutil.copy2(folder/'logo.png',dest/'logo.png'); data['logo']='logo.png'
    if brief.keep_audio and media.get('audio'):
        if not (dest/'audio.m4a').exists():
            run(['ffmpeg','-y','-v','error','-i',str(folder/'source.mp4'),'-vn','-c:a','aac',str(dest/'audio.m4a')])
        data['audio']='audio.m4a'
    (dest/'project.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return dest


def export_project(folder, plan, brief):
    public = write_project(folder,plan,brief)
    dest = folder / 'remotion-project.zip'
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['package.json','package-lock.json','render.mjs']:
            if (RUNTIME/name).exists():archive.write(RUNTIME/name,name)
        for path in (RUNTIME/'src').glob('*'):archive.write(path,'src/'+path.name)
        data=json.loads((public/'project.json').read_text(encoding='utf-8'))
        for name in ['project.json',data['logo'],data['audio']]:
            if name:archive.write(public/name,'public/'+name)
        archive.writestr('README.md','# Saved Remotion graphic\n\nRun `npm ci` (or `npm install` if no lockfile), then `npm run studio` to preview and edit. Run `npm run render` to export out/video.mp4.\n\nEdit public/project.json for copy, colors and keyframes; src/Composition.jsx contains the editable React layers. Re-rendering does not call AI. Node.js and Chrome/Chromium are required. Remotion dependencies retain their licenses.\n')
    return dest


def render(folder, plan, brief, cancel, progress, *, preview=False):
    if not (RUNTIME/'node_modules/@remotion/renderer').exists():
        raise ValueError('Remotion is not installed. Run npm ci --prefix remotion in the MotionClone folder, then try again.')
    public=write_project(folder,plan,brief)
    output=folder/('preview.mp4' if preview else 'output.mp4')
    pending=output.with_name(output.stem+'.pending.mp4')
    signal=folder/'remotion.cancel';signal.unlink(missing_ok=True)
    env=os.environ.copy();env['FRAMEFORGE_CANCEL_FILE']=str(signal)
    args=['node',str(RUNTIME/'render.mjs'),str(public/'project.json'),str(pending)]
    if preview:args.append('--preview')
    progress('Rendering Remotion preview' if preview else 'Rendering Remotion video',48 if preview else 78)
    log=folder/'remotion-render.log'
    with log.open('w',encoding='utf-8') as stream:
        proc=popen(args,cwd=RUNTIME,stdout=stream,stderr=subprocess.STDOUT,env=env)
        started=time.monotonic();stopping=None;timed_out=False
        try:
            while proc.poll() is None:
                if cancel.is_set() or time.monotonic()-started>900:
                    if stopping is None:
                        timed_out=not cancel.is_set();signal.touch();stopping=time.monotonic()
                    if time.monotonic()-stopping>20:
                        proc.terminate();proc.wait(timeout=10);break
                lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
                for line in reversed(lines[-10:]):
                    try:
                        value=json.loads(line)['progress']
                        progress('Rendering Remotion preview' if preview else 'Rendering Remotion video',
                                 round((48 if preview else 78)+value*(.16 if preview else .18)))
                        break
                    except (ValueError,KeyError,TypeError):pass
                time.sleep(.3)
            if cancel.is_set():raise Cancelled()
            if timed_out:raise TimeoutError('Remotion render timed out. Try a shorter clip.')
            if proc.returncode:raise ValueError('Remotion render failed. Details are saved in remotion-render.log in this project.')
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
            signal.unlink(missing_ok=True)
    pending.replace(output)
    if not preview:
        progress('Verifying frames and audio',97)
        run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],timeout=120,cancel=cancel)
        actual=probe(output)
        media=json.loads((folder/'media.json').read_text(encoding='utf-8'))
        count=int(run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
            'stream=nb_read_frames','-of','default=nw=1:nk=1',str(output)]))
        expected=math.ceil(media['duration']*media['fps'])
        if count!=expected or actual['audio'] != bool(brief.keep_audio and media['audio']):
            raise ValueError('Rendered frame count or audio did not match the project.')
        report=dict(decoded=True,expected_frames=expected,actual_frames=count,audio_present=actual['audio'],
            dimensions=[actual['width'],actual['height']],fps=actual['fps'],duration=actual['duration'],
            mode='rebuild',renderer='remotion')
        (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return output
