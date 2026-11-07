"""Render and audit independent HyperFrames layers. Never falls back to source replay."""
import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from fractions import Fraction
from PIL import Image

from .hyperframes import run_cli, frame_info, VERSION
from .media import probe
from .process import run, Cancelled
from .scene_pipeline import digest

PROJECT_FILES=['index.html','tokens.css','shared.js','timeline.js','measurements.js','glass-vectors.js','grid-vectors.js','grid-renderer.js',
               'scene-intro.js','scene-prompt.js','scene-prompt.css','scene-middle.js','scene-middle.css',
               'scene-tools.js','scene-tools.css','hyperframes.json','package.json','project.json','project.js','renderer.js','sync-project.cjs','manifest.json','README.md']


def fingerprint(folder,brief):
    import hashlib
    project=folder/'rebuild';value=hashlib.sha256(f'{VERSION}:rebuild-v2:{brief.keep_audio}'.encode())
    paths=[folder/'source.mp4']+[project/n for n in PROJECT_FILES if n not in ('manifest.json','README.md')]
    paths+=sorted((project/'assets').glob('*'))+sorted((project/'vendor').glob('*'))
    for path in paths:
        if path.is_file():value.update(path.relative_to(folder).as_posix().encode());value.update(digest(path).encode())
    return value.hexdigest()


def audit_project(project, media):
    html=(project/'index.html').read_text(encoding='utf-8')
    generated=(project/'project.json').exists()
    if generated:
        from .rebuild_author import SceneProject
        data=json.loads((project/'project.json').read_text(encoding='utf-8'))
        SceneProject.model_validate({k:v for k,v in data.items() if k not in ('width','height','duration')})
        script=(project/'project.js').read_text(encoding='utf-8').strip()
        match=re.fullmatch(r'window\.project\s*=\s*(.*);',script,re.S)
        if not match or json.loads(match[1])!=data:raise ValueError('Generated project data is out of sync. Run npm run sync before rendering.')
    content='\n'.join((project/n).read_text(encoding='utf-8') for n in PROJECT_FILES if (project/n).exists() and n.endswith(('.html','.js','.css')) and not (generated and n=='project.js'))
    if re.search(r'<\s*(?:video|canvas)\b|createElement\([\'"](?:video|canvas)[\'"]\)|source\.mp4|input\.bin|reference-\d',content,re.I):
        raise ValueError('Rebuild rejected: source video, reference frames or raster replay found in visual layers.')
    image_assets=[]
    for path in (project/'assets').glob('*'):
        if path.suffix.lower() in ('.mp4','.webm','.mov','.gif'):
            raise ValueError('A rebuilt project cannot contain source video as an asset.')
        if path.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
            with Image.open(path) as im:
                if im.width*im.height>media['width']*media['height']*.12:
                    raise ValueError('Rebuild rejected: image asset is too large to be an isolated logo or small artwork.')
                image_assets.append({'file':path.name,'dimensions':[im.width,im.height]})
    if len(image_assets)>12:raise ValueError('Too many raster assets; full-scene patch replay is not a reconstruction.')
    if 'data-composition-id' not in html:raise ValueError('HyperFrames composition is missing.')
    return {'source_video_in_visuals':False,'full_frame_images':False,'isolated_artwork':image_assets,
            'method':'Editable text, CSS/SVG shapes and measured geometry; original audio only.'}


def compare_frames(folder, candidate, cancel):
    source=folder/'source.mp4'
    expected,fps=frame_info(source,cancel);actual,actual_fps=frame_info(candidate,cancel)
    meta=probe(source);out=probe(candidate)
    if actual!=expected or Fraction(fps)!=Fraction(actual_fps) or (meta['width'],meta['height'])!=(out['width'],out['height']):
        raise ValueError('Rebuilt frame count, timing or dimensions do not match the reference.')
    run(['ffmpeg','-y','-v','error','-i',str(source),'-i',str(candidate),'-filter_complex',
        f'[0:v]settb=AVTB,setpts=N/({fps})/TB,format=yuv420p[a];[1:v]settb=AVTB,setpts=N/({fps})/TB,format=yuv420p[b];'
        '[a][b]ssim=stats_file=rebuild-frame-comparison.log:shortest=1','-an','-f','null','-'],cwd=folder,timeout=240,cancel=cancel)
    # Anti-correlated frames have valid negative SSIM; count them as differences.
    scores=[float(x) for x in re.findall(r'All:([+-]?[\d.]+)',(folder/'rebuild-frame-comparison.log').read_text())]
    if len(scores)!=expected:raise ValueError('Not every rebuilt frame could be compared.')
    mean=sum(scores)/len(scores)
    run(['ffmpeg','-v','error','-xerror','-i',str(candidate),'-f','null','-'],timeout=240,cancel=cancel)
    audio_match=None
    if out['audio']:
        hashes=[run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-'],timeout=120,cancel=cancel).strip() for path in [source,candidate]]
        audio_match=hashes[0]==hashes[1]
        if not audio_match:raise ValueError('Original audio changed or was truncated.')
    return dict(decoded=True,expected_frames=expected,actual_frames=actual,compared_frames=len(scores),
        dimensions=[out['width'],out['height']],fps=out['fps'],duration=out['duration'],audio_present=out['audio'],
        renderer='hyperframes',renderer_version=VERSION,mode='hyperframes',source_backed=False,audio_bitstream_match=audio_match,
        ssim_mean=mean,ssim_min=min(scores),near_perfect=mean>=.97 and min(scores)>=.9,
        visual_check='matched' if mean>=.97 and min(scores)>=.9 else 'differences',
        worst_frames=sorted(range(len(scores)),key=lambda i:scores[i])[:12],
        note='All frames compared to the reference. Independent layers do not imply a 1:1 visual match. Similarity is reported separately.')


def render(folder, brief, cancel, progress):
    started=time.monotonic()
    project=folder/'rebuild'
    meta=probe(folder/'source.mp4')
    structure=audit_project(project,meta)
    key=fingerprint(folder,brief);verification=folder/'verification.json';output=folder/'output.mp4'
    if verification.exists() and output.exists():
        prior=json.loads(verification.read_text(encoding='utf-8'))
        if prior.get('fingerprint')==key and prior.get('output_sha256')==digest(output):
            if cancel.is_set():raise Cancelled()
            progress('Reusing the verified export; no changes to render',98)
            return {**prior,'cache_hit':True,'request_seconds':round(time.monotonic()-started,3)}
    expected,fps=frame_info(folder/'source.mp4',cancel)
    progress('Rendering rebuilt HyperFrames layers',60)
    frames=folder/('rebuilt-frames-'+str(time.time_ns()))
    run_cli(['render',str(project),'--format','png-sequence','--output',str(frames),
             '--fps',fps,'--quality','high','--workers','2','--no-best-effort'],folder,cancel,
            lambda stage,pct:progress('Rendering rebuilt HyperFrames layers',60+round(max(0,pct-20)*.4)))
    images=sorted(frames.glob('*.png'))
    if len(images)!=expected:raise ValueError(f'Rebuild rendered {len(images)} frames instead of {expected}.')
    progress('Encoding rebuilt layers and original audio',88)
    video_only=folder/'rebuilt-video.pending.mp4'
    run(['ffmpeg','-y','-v','error','-framerate',fps,'-start_number','1','-i',str(frames/'frame_%06d.png'),
         '-frames:v',str(expected),'-c:v','libx264','-preset','fast','-crf','12','-pix_fmt','yuv420p',str(video_only)],timeout=300,cancel=cancel)
    pending=folder/'rebuilt.pending.mp4'
    if brief.keep_audio and meta['audio']:
        run(['ffmpeg','-y','-v','error','-i',str(video_only),'-i',str(folder/'source.mp4'),'-map','0:v:0','-map','1:a:0',
             '-c','copy','-movflags','+faststart',str(pending)],timeout=120,cancel=cancel);video_only.unlink()
    else:video_only.replace(pending)
    progress('Comparing every rebuilt frame against the reference',95)
    report=compare_frames(folder,pending,cancel);report['structure']=structure
    report.update(fingerprint=key,output_sha256=digest(pending),cache_hit=False,render_seconds=round(time.monotonic()-started,2))
    analysis=folder/'analysis-report.json'
    if analysis.exists():report['analysis']=json.loads(analysis.read_text(encoding='utf-8'))
    media_file=folder/'media.json'
    if media_file.exists():report['normalizations']=json.loads(media_file.read_text(encoding='utf-8')).get('normalizations',[])
    if report['audio_present']!=bool(brief.keep_audio and meta['audio']):raise ValueError('Rebuilt audio does not match the requested setting.')
    if cancel.is_set():raise Cancelled()
    # Preserve the rejected source-copy export for provenance. Never relabel it as a rebuild.
    old=folder/'output.mp4'
    if old.exists() and not (folder/'original-copy.mp4').exists():shutil.copy2(old,folder/'original-copy.mp4')
    pending.replace(old)
    (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (project/'manifest.json').write_text(json.dumps({'renderer':'hyperframes','version':VERSION,'independent_visual_layers':True,
        'source_backed':False,'dimensions':report['dimensions'],'fps':fps,'frames':expected,'structure':structure,
        'visual_match':report['visual_check'],'ssim_mean':report['ssim_mean']},indent=2),encoding='utf-8')
    (project/'README.md').write_text('# Editable HyperFrames reconstruction\n\n'
        'The original video is NOT a visual layer. Text, panels, characters and effects are CSS/SVG objects. '
        'Any isolated artwork assets are listed in manifest.json; original audio can be preserved. '
        'measurements.js contains object bounds measured across the reference, not image frames. glass-vectors.js contains editable fragment polygons.\n\n'
        'Edit project.json and run `npm run sync` for generated scenes, or scene-*.js and tokens.css for authored scenes. Install Node.js 22+ and FFmpeg, then `npm install`, '
        '`npm run preview`, or `npm run render`. No source video is required for rendering.\n\n'
        'The verification report measures visual differences independently of checking that the project has separate layers. '
        'This render must not be described as 1:1 unless the comparison supports it.\n',encoding='utf-8')
    if frames.resolve().parent!=folder.resolve():raise ValueError('Invalid temporary frame directory.')
    shutil.rmtree(frames)
    return report


def export_project(folder):
    project=folder/'rebuild';audit_project(project,probe(folder/'source.mp4'))
    dest=folder/'hyperframes-rebuilt.zip'
    keep_audio=True
    if (folder/'brief.json').exists():keep_audio=json.loads((folder/'brief.json').read_text(encoding='utf-8')).get('keep_audio',True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in PROJECT_FILES:
            if (project/name).exists():
                if name=='index.html' and not keep_audio:
                    html=(project/name).read_text(encoding='utf-8');archive.writestr(name,re.sub(r'<audio\b[^>]*>.*?</audio>','',html,flags=re.S|re.I))
                else:archive.write(project/name,name)
        for directory in ['assets','vendor']:
            for path in (project/directory).glob('*'):
                if path.is_file() and (keep_audio or path.suffix not in ('.m4a','.aac','.mp3','.wav')):archive.write(path,directory+'/'+path.name)
        if (folder/'verification.json').exists():archive.write(folder/'verification.json','verification.json')
    return dest
