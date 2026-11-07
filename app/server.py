import asyncio
import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from .ai import analyze, auth_status
from .media import MAX_BYTES, contact_sheets, download, prepare, review_timestamps, reference_frames, validate_url
from .models import Brief, Plan, LibraryUpdate
from .process import Cancelled
from .render import render
from .connection import Connection

ROOT=Path(__file__).resolve().parents[1]
HOSTED=os.environ.get('FRAMEFORGE_HOSTED')=='1'
DATA=Path(os.environ.get('FRAMEFORGE_DATA',str(ROOT/'data'))).resolve(); DATA.mkdir(parents=True,exist_ok=True)
TOKEN=os.environ.get('FRAMEFORGE_TOKEN') or secrets.token_urlsafe(32)
if HOSTED and (not os.environ.get('CODEX_HOME') or DATA==ROOT/'data'):
    raise RuntimeError('Hosted workers require isolated project and account directories.')
PORT=int(os.environ.get('FRAMEFORGE_PORT','4319'))
POOL=ThreadPoolExecutor(max_workers=1)
LOCK=threading.RLock()
JOBS={}
ACTIVE={'id':None}
AUTH={'ok':False,'checked':0.0}
app=FastAPI(title='MotionClone Local',docs_url=None,redoc_url=None)
CONNECTION=Connection()
if HOSTED:
    if (Path(os.environ['CODEX_HOME'])/'auth.json').is_file():
        CONNECTION.client()


def persist(job):
    with LOCK:
        value={k:v for k,v in job.items() if k not in ('cancel','future')}
        folder=DATA/job['id'];folder.mkdir(exist_ok=True)
        tmp=folder/'job.tmp';tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(folder/'job.json')


for path in DATA.glob('*/job.json'):
    try:
        job=json.loads(path.read_text(encoding='utf-8'));job['cancel']=threading.Event()
        if job['status'] in ('running','queued'):job.update(status='interrupted',stage='App restarted. Retry to continue.')
        JOBS[job['id']]=job
    except (ValueError,KeyError):pass


def public(job, detailed=True):
    folder=DATA/job['id']
    result={k:v for k,v in job.items() if k not in ('cancel','future')}
    result['files']={name:f'/media/{job["id"]}/{name}' for name in ['source.mp4','preview.mp4','output.mp4','verification.json','plan.json','logo.png','thumbnail.jpg'] if (folder/name).exists()}
    if job['brief']['mode']=='faithful':
        result['files'].pop('plan.json',None)
        if job.get('renderer')!='hyperframes':
            for name in ['output.mp4','preview.mp4','verification.json']:result['files'].pop(name,None)
    for key,default in [('favorite',False),('archived',False),('collection',''),('tags',[])]:result.setdefault(key,default)
    if (folder/'temporal.json').exists():
        temporal=json.loads((folder/'temporal.json').read_text(encoding='utf-8'))
        result['scan']={'decoded':temporal['decoded_frames'],'selected':len(temporal['sample_frames'])}
    result['sheets']=[f'/media/{job["id"]}/{p.name}' for p in sorted(folder.glob('reference-*.jpg'))] if detailed else []
    if detailed and job['brief']['mode'] not in ('faithful','hyperframes') and (folder/'plan.json').exists():result['plan']=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
    if job['brief']['mode']=='hyperframes':
        result['files'].pop('plan.json',None)
        report=json.loads((folder/'verification.json').read_text(encoding='utf-8')) if (folder/'verification.json').exists() else {}
        if report.get('mode')!='hyperframes':
            for name in ['output.mp4','preview.mp4','verification.json']:result['files'].pop(name,None)
    if detailed and 'verification.json' in result['files']:result['verification']=json.loads((folder/'verification.json').read_text(encoding='utf-8'))
    return result


def get_job(id):
    if not re.fullmatch(r'[a-f0-9]{12}',id) or id not in JOBS:raise HTTPException(404,'Project not found.')
    return JOBS[id]


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    host=request.headers.get('host','')
    allowed={f'127.0.0.1:{PORT}',f'localhost:{PORT}','testserver'}
    if host not in allowed:return JSONResponse({'detail':'Local access only.'},status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('x-frameforge-token')!=TOKEN:
            return JSONResponse({'detail':'Refresh this page to reconnect.'},status_code=403)
        origin=request.headers.get('origin')
        if origin and origin not in {f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}:
            return JSONResponse({'detail':'Cross-origin requests are blocked.'},status_code=403)
        try:length=int(request.headers.get('content-length','0'))
        except ValueError:return JSONResponse({'detail':'Invalid request size.'},status_code=400)
        if length>MAX_BYTES+12*1024*1024:
            return JSONResponse({'detail':'Upload exceeds 250 MB.'},status_code=413)
        if HOSTED and request.url.path.startswith('/api/jobs') and request.url.path.rsplit('/',1)[-1] in ('jobs','retry','render'):
            try:connected=await asyncio.to_thread(auth_status)
            except Exception:connected=False
            if not connected:return JSONResponse({'detail':'Connect your own ChatGPT account before rebuilding a video.'},status_code=401)
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
        'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"})
    return response


@app.get('/')
def index(request: Request):
    page=(ROOT/'web/index.html').read_text(encoding='utf-8')
    page=page.replace('<!--ACCOUNT_SETTINGS-->',(ROOT/'web/account.html').read_text(encoding='utf-8'))
    if HOSTED:
        page=page.replace('<body ', '<body data-hosted="true" ',1)
        page=page.replace('href="/"','href="/studio"')
        page=page.replace('Stored on this computer','Private to your account').replace('Saved on this computer','Saved to your account')
        page=page.replace('Projects are stored locally.','Projects are stored privately.')
        page=page.replace('Saved locally.','Saved privately.').replace('Vimeo, or direct video links.','or Vimeo video links.')
        page=page.replace('250 MB','25 MB')
        return HTMLResponse(page)
    if 'workspace' in request.query_params or 'project' in request.query_params or 'settings' in request.query_params:
        return HTMLResponse(page)
    page=(ROOT/'web/showcase.html').read_text(encoding='utf-8')
    return HTMLResponse(page.replace('href="./','href="/static/').replace('src="./','src="/static/'))


@app.get('/api/status')
def status():
    if time.monotonic()-AUTH['checked']>20:
        AUTH.update(ok=auth_status(),checked=time.monotonic())
    return {'chatgpt':AUTH['ok'],'ffmpeg':bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),
            'token':TOKEN,'active':ACTIVE['id'],'version':'2.0.0','account_connection':True,
            'remotion':(ROOT/'remotion/node_modules/@remotion/renderer').exists(),
            'hyperframes':(ROOT/'hyperframes/node_modules/hyperframes/bin/hyperframes.mjs').exists()}


@app.get('/api/account')
def account_state():
    try:
        result=CONNECTION.state(initialize=True)
        AUTH.update(ok=result['status']=='connected',checked=time.monotonic())
        return result
    except ValueError as exc:raise HTTPException(503,str(exc)) from None


@app.post('/api/account/connect')
def account_connect():
    with LOCK:
        if ACTIVE['id']:raise HTTPException(409,'Wait for your video to finish before changing accounts.')
        try:return CONNECTION.start()
        except ValueError as exc:raise HTTPException(503,str(exc)) from None


@app.post('/api/account/disconnect')
def account_disconnect():
    with LOCK:
        if ACTIVE['id']:raise HTTPException(409,'Wait for your video to finish before disconnecting.')
        try:
            CONNECTION.state(initialize=True)
            result=CONNECTION.disconnect()
            AUTH.update(ok=False,checked=0.0)
            return result
        except ValueError as exc:raise HTTPException(503,str(exc)) from None


@app.get('/api/jobs')
def list_jobs():
    with LOCK:return [public(j) for j in sorted(JOBS.values(),key=lambda j:j['created'],reverse=True)]


@app.get('/api/library')
def list_library():
    with LOCK:return [public(j,detailed=False) for j in sorted(JOBS.values(),key=lambda j:j['created'],reverse=True)]


@app.get('/api/jobs/{id}')
def read_job(id:str):
    with LOCK:return public(get_job(id))


@app.patch('/api/jobs/{id}')
def update_library(id:str, changes:LibraryUpdate):
    with LOCK:
        job=get_job(id)
        job.update(changes.model_dump(exclude_unset=True));job['updated']=time.time()
        persist(job)
        return public(job)


@app.post('/api/jobs/{id}/duplicate')
def duplicate(id:str):
    with LOCK:
        original=get_job(id)
        if original['status'] in ('running','queued'):raise HTTPException(409,'Wait for this project to finish before copying it.')
        source=DATA/id
        if not (source/'plan.json').exists() and original['brief']['mode'] not in ('faithful','hyperframes'):raise HTTPException(409,'This reference has no saved motion yet. Retry its analysis first.')
        if not (source/'source.mp4').exists():raise HTTPException(409,'Import the reference first.')
        new_id=uuid.uuid4().hex[:12];folder=DATA/new_id;folder.mkdir()
        for name in ['source.mp4','media.json','temporal.json','plan.json','brief.json','logo.png','thumbnail.jpg']:
            if (source/name).exists():shutil.copy2(source/name,folder/name)
        for path in source.glob('reference-*.jpg'):shutil.copy2(path,folder/path.name)
        if original['brief']['mode']=='hyperframes' and (source/'rebuild').exists():
            from .reconstruction import PROJECT_FILES
            target=folder/'rebuild';target.mkdir()
            for name in PROJECT_FILES:
                if (source/'rebuild'/name).exists():shutil.copy2(source/'rebuild'/name,target/name)
            for name in ['assets','vendor']:
                if (source/'rebuild'/name).exists():shutil.copytree(source/'rebuild'/name,target/name)
        job={k:v for k,v in original.items() if k not in ('cancel','future','warning','renderer')}
        job.update(id=new_id,name=original['name'][:150]+' copy',created=time.time(),updated=time.time(),
                   status='draft',stage='Saved motion copied. Edit the text, then render.',progress=0,
                   error=None,events=[],favorite=False,archived=False,cancel=threading.Event(),copied_from=id)
        if job['brief']['mode']=='faithful':job['stage']='Source frames copied. Recreate to render this copy.'
        if job['brief']['mode']=='hyperframes':job['stage']='Rebuilt layers copied. Render this version from Options.'
        JOBS[new_id]=job;persist(job)
        return public(job)


@app.get('/api/jobs/{id}/remotion')
def remotion_export(id:str):
    with LOCK:
        job=get_job(id);folder=DATA/id
        if job['status'] in ('running','queued'):raise HTTPException(409,'Wait for the render to finish.')
        if job['brief']['mode']!='rebuild':raise HTTPException(409,'Choose Rebuild in Remotion and rebuild this reference before exporting editable Remotion layers.')
        if not (folder/'plan.json').exists():raise HTTPException(409,'Build the motion first.')
        from .remotion import export_project
        dest=export_project(folder,Plan.model_validate_json((folder/'plan.json').read_text(encoding='utf-8')),Brief.model_validate(job['brief']))
        return FileResponse(dest,filename='motionclone-remotion.zip')


@app.get('/api/jobs/{id}/hyperframes')
def hyperframes_export(id:str):
    with LOCK:
        job=get_job(id)
        if job['status'] in ('running','queued'):raise HTTPException(409,'Wait for the render to finish.')
        if job['brief']['mode'] not in ('faithful','hyperframes'):raise HTTPException(409,'Create a HyperFrames version first.')
        if job['brief']['mode']=='hyperframes':from .reconstruction import export_project
        else:from .hyperframes import export_project
        try:dest=export_project(DATA/id)
        except ValueError as e:raise HTTPException(409,str(e))
        return FileResponse(dest,filename='motionclone-hyperframes.zip')


async def save_upload(upload, dest, limit):
    total=0
    with dest.open('wb') as f:
        while chunk:=await upload.read(1024*512):
            total+=len(chunk)
            if total>limit:raise HTTPException(413,'File exceeds the upload size limit.')
            f.write(chunk)
    if not total:raise HTTPException(400,'Uploaded file is empty.')


@app.post('/api/jobs')
async def create_job(video:UploadFile|None=File(None),logo:UploadFile|None=File(None),url:str=Form(''),
                     brand:str=Form(''),instructions:str=Form(''),mode:str=Form('hyperframes'),accent:str=Form('#bcf76a'),
                     keep_audio:bool=Form(True),auto_review:bool=Form(True),sampling:str=Form('standard'),import_only:bool=Form(False)):
    if not video and not url.strip():raise HTTPException(400,'Upload a video or paste a public video link.')
    if url and len(url)>2048:raise HTTPException(422,'That video link is too long.')
    if HOSTED and mode!='hyperframes':
        raise HTTPException(422,'The online studio supports editable motion reconstruction.')
    if not video:
        try:await asyncio.to_thread(validate_url,url.strip())
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    try:brief=Brief(brand=brand,instructions=instructions,mode=mode,accent=accent,keep_audio=keep_audio,auto_review=auto_review,sampling=sampling)
    except ValueError:raise HTTPException(422,'Check the brand, instructions and mode.')
    with LOCK:
        if ACTIVE['id']:raise HTTPException(409,'A video is already processing. Wait or cancel it first.')
        id=uuid.uuid4().hex[:12];ACTIVE['id']=id
    folder=DATA/id;folder.mkdir()
    try:
        if video:await save_upload(video,folder/'input.bin',MAX_BYTES)
        if logo:
            await save_upload(logo,folder/'logo-upload.bin',10*1024*1024)
            try:
                with Image.open(folder/'logo-upload.bin') as im:
                    if im.width*im.height>25_000_000:raise ValueError()
                    im.thumbnail((2048,2048));im.convert('RGBA').save(folder/'logo.png')
            except (UnidentifiedImageError,ValueError,OSError):raise HTTPException(400,'Use a PNG, JPEG or WebP logo up to 25 megapixels.')
            (folder/'logo-upload.bin').unlink(missing_ok=True)
        job={'id':id,'created':time.time(),'name':brand.strip() or (video.filename if video else 'Video reference'),
             'status':'queued','stage':'Waiting to start','progress':0,'brief':brief.model_dump(),
             'url':url.strip() if not video else '', 'reference_only':import_only, 'events':[],'error':None,'cancel':threading.Event()}
        with LOCK:JOBS[id]=job
        persist(job);job['future']=POOL.submit(pipeline,id)
        return public(job)
    except Exception:
        with LOCK:ACTIVE['id']=None
        raise


def pipeline(id, render_only=False):
    job=JOBS[id];folder=DATA/id;cancel=job['cancel'];brief=Brief.model_validate(job['brief'])
    job['started']=time.time()
    job.pop('warning',None)
    if brief.mode=='rebuild':
        from .remotion import render as render_video
    else:render_video=render
    def progress(stage, percent):
        with LOCK:
            changed=stage!=job['stage'];job.update(status='running',stage=stage,progress=percent)
            if changed:job['events'].append({'time':time.time(),'message':stage})
        persist(job)
    try:
        if job.get('editor') and not (folder/'source.mp4').exists():
            from .editor import Edit, assemble
            assemble(Edit.model_validate(job['editor']),DATA,folder,cancel,progress)
        if job.get('reference_only'):
            from .media import thumbnail
            if not (folder/'input.bin').exists():download(job['url'],folder/'input.bin',cancel,progress)
            meta,_=prepare(folder/'input.bin',folder,cancel,progress,rebuild=True)
            thumbnail(folder/'source.mp4',folder/'thumbnail.jpg')
            with LOCK:job.update(media=meta,status='draft',stage='Reference ready in the Editor',progress=100,error=None)
            return
        if brief.mode=='hyperframes':
            from .reconstruction import render as render_rebuilt
            from .rebuild_author import author
            from .media import thumbnail
            if not (folder/'source.mp4').exists():
                if not (folder/'input.bin').exists():download(job['url'],folder/'input.bin',cancel,progress)
                meta,_=prepare(folder/'input.bin',folder,cancel,progress,rebuild=True)
            else:meta=json.loads((folder/'media.json').read_text(encoding='utf-8'))
            job['media']=meta
            if not (folder/'rebuild/index.html').exists() or ((folder/'rebuild/project.json').exists() and not (folder/'analysis-report.json').exists()):
                job['checkpoint']='analysis';persist(job)
                sheets=sorted(folder.glob('reference-*.jpg'))
                if not (folder/'temporal.json').exists():sheets=reference_frames(folder,cancel,progress,budget=384 if brief.sampling=='detailed' else 192)
                author(folder,meta,sheets,cancel,progress,brief=brief)
            job['checkpoint']='render';persist(job)
            (folder/'brief.json').write_text(brief.model_dump_json(indent=2),encoding='utf-8')
            report=render_rebuilt(folder,brief,cancel,progress)
            job['timing']={'total_seconds':round(time.time()-job['started'],2),'cache_hit':report.get('cache_hit',False)}
            thumbnail(folder/'output.mp4',folder/'thumbnail.jpg')
            notices=report.get('normalizations',[])[:]
            if not report['near_perfect']:notices.append('Independent rebuild rendered. Visible differences remain; a 1:1 match has not been achieved.')
            if notices:job['warning']=' '.join(notices)
            with LOCK:job.update(status='complete',stage='Rebuilt layers rendered',progress=100,error=None,
                                updated=time.time(),checkpoint='complete',renderer='hyperframes')
            return
        if brief.mode=='faithful':
            from .hyperframes import render as render_faithful
            from .media import thumbnail
            if not (folder/'source.mp4').exists():
                if not (folder/'input.bin').exists():download(job['url'],folder/'input.bin',cancel,progress)
                meta,_=prepare(folder/'input.bin',folder,cancel,progress,faithful=True)
            else:meta=json.loads((folder/'media.json').read_text(encoding='utf-8'))
            job['media']=meta;job['checkpoint']='render';persist(job)
            (folder/'brief.json').write_text(brief.model_dump_json(indent=2),encoding='utf-8')
            render_faithful(folder,brief,cancel,progress)
            thumbnail(folder/'output.mp4',folder/'thumbnail.jpg')
            with LOCK:job.update(status='complete',stage='Video ready · every frame compared',progress=100,error=None,
                                updated=time.time(),checkpoint='complete',renderer='hyperframes')
            return
        if not (folder/'source.mp4').exists():
            if not (folder/'input.bin').exists():download(job['url'],folder/'input.bin',cancel,progress)
            meta,sheets=prepare(folder/'input.bin',folder,cancel,progress)
        else:
            meta=json.loads((folder/'media.json').read_text(encoding='utf-8'));sheets=sorted(folder.glob('reference-*.jpg'))
            if not render_only and not (folder/'temporal.json').exists():
                sheets=reference_frames(folder,cancel,progress)
        job['media']=meta
        if not render_only:
            budget=384 if brief.sampling=='detailed' else 192
            temporal_file=folder/'temporal.json'
            temporal=json.loads(temporal_file.read_text(encoding='utf-8')) if temporal_file.exists() else {}
            if temporal.get('budget',192)!=budget:
                sheets=reference_frames(folder,cancel,progress,budget=budget)
        prior=Plan.model_validate_json((folder/'plan.json').read_text(encoding='utf-8')) if (folder/'plan.json').exists() else None
        if render_only:
            if prior is None:raise ValueError('No editable project exists yet.')
            plan=prior
        else:
            job['checkpoint']='analysis';persist(job)
            plan=analyze(folder,meta,brief,sheets,cancel,progress,previous=prior)
            (folder/'plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf-8')
            if brief.auto_review:
                render_video(folder,plan,brief,cancel,progress,preview=True)
                temporal=json.loads((folder/'temporal.json').read_text(encoding='utf-8')) if (folder/'temporal.json').exists() else None
                times=review_timestamps(meta,plan,temporal)
                review_source=contact_sheets(folder/'source.mp4',folder/'review-source',cancel=cancel,timestamps=times)
                rendered=contact_sheets(folder/'preview.mp4',folder/'rendered',cancel=cancel,timestamps=times)
                try:plan=analyze(folder,meta,brief,review_source+rendered,cancel,progress,previous=plan,review=True)
                except Cancelled:raise
                except (ValueError,TimeoutError):
                    job['events'].append({'time':time.time(),'message':'Visual review unavailable; rendering the validated first plan.'})
                    job['warning']='Automatic visual review was unavailable. Inspect the result before using it.'
        (folder/'plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf-8')
        (folder/'brief.json').write_text(brief.model_dump_json(indent=2),encoding='utf-8')
        job['checkpoint']='render';persist(job)
        render_video(folder,plan,brief,cancel,progress)
        from .media import thumbnail
        thumbnail(folder/'output.mp4',folder/'thumbnail.jpg')
        with LOCK:job.update(status='complete',stage='Video ready',progress=100,error=None,
                            updated=time.time(),checkpoint='complete',renderer='remotion' if brief.mode=='rebuild' else 'original-frames')
    except Cancelled:
        with LOCK:job.update(status='cancelled',stage='Cancelled. Your project is saved.')
    except Exception as e:
        import traceback
        (folder/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        message=str(e) if isinstance(e,(ValueError,TimeoutError)) else 'This step failed. Retry; technical details are saved in the project folder.'
        with LOCK:job.update(status='error',stage='Needs attention',error=message)
    finally:
        with LOCK:ACTIVE['id']=None
        persist(job)


@app.post('/api/jobs/{id}/cancel')
def cancel_job(id:str):
    job=get_job(id)
    if job['status'] in ('running','queued'):
        job['cancel'].set();job['stage']='Cancelling current step…';persist(job)
    return {'ok':True}


@app.post('/api/jobs/{id}/retry')
def retry(id:str, brief:Brief):
    with LOCK:
        if ACTIVE['id']:raise HTTPException(409,'Another video is processing.')
        job=get_job(id);ACTIVE['id']=id
        job.pop('reference_only',None)
        resume_render=(job['status'] in ('error','cancelled','interrupted') and job.get('checkpoint')=='render'
                       and Brief.model_validate(job['brief'])==brief and (DATA/id/'plan.json').exists())
        job.update(brief=brief.model_dump(),error=None,status='queued',stage='Starting saved project',progress=0,started=time.time(),cancel=threading.Event())
        persist(job);job['future']=POOL.submit(pipeline,id,resume_render)
    return public(job)


@app.post('/api/jobs/{id}/render')
def rerender(id:str, plan:Plan):
    with LOCK:
        if ACTIVE['id']:raise HTTPException(409,'Another video is processing.')
        job=get_job(id);folder=DATA/id
        if job['brief']['mode'] in ('faithful','hyperframes'):raise HTTPException(409,'Edit the HyperFrames project download, then render it in HyperFrames.')
        if not (folder/'media.json').exists():raise HTTPException(409,'Import the reference first.')
        (folder/'plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf-8')
        ACTIVE['id']=id;job.update(error=None,status='queued',cancel=threading.Event())
        persist(job);job['future']=POOL.submit(pipeline,id,True)
    return public(job)


@app.get('/api/jobs/{id}/export')
def export(id:str):
    job=get_job(id)
    if job['status'] in ('running','queued'):raise HTTPException(409,'Wait for this render to finish.')
    folder=DATA/id;dest=folder/'project.zip'
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in folder.iterdir():
            if path.suffix in ('.json','.txt','.jpg','.png','.mp4') and '.pending.' not in path.name:
                archive.write(path,'project/'+path.name)
        for path in (ROOT/'app').glob('*.py'):archive.write(path,'app/'+path.name)
        if job['brief']['mode']=='hyperframes':
            from .reconstruction import export_project
            with zipfile.ZipFile(export_project(folder)) as composition:
                for name in composition.namelist():archive.writestr('project/rebuild/'+name,composition.read(name))
            for name in ['package.json','package-lock.json']:
                archive.write(ROOT/'hyperframes'/name,'hyperframes/'+name)
        if job['brief']['mode']=='faithful':
            for path in (folder/'hyperframes').rglob('*'):
                if path.is_file() and path.relative_to(folder/'hyperframes').parts[0] in ('assets','vendor','index.html','manifest.json','package.json','hyperframes.json','README.md'):
                    archive.write(path,'project/hyperframes/'+path.relative_to(folder/'hyperframes').as_posix())
            for name in ['package.json','package-lock.json']:
                archive.write(ROOT/'hyperframes'/name,'hyperframes/'+name)
        archive.write(ROOT/'scripts/render_project.py','render_project.py')
        for name in ['requirements.lock.txt','README.md','THIRD_PARTY.md']:
            if (ROOT/name).exists():archive.write(ROOT/name,name)
        for path in (ROOT/'licenses').glob('*'):archive.write(path,'licenses/'+path.name)
    return FileResponse(dest,filename='motionclone-project.zip')


@app.get('/media/{id}/{name}')
def media(id:str,name:str):
    get_job(id)
    allowed={'source.mp4','preview.mp4','output.mp4','verification.json','plan.json','logo.png','thumbnail.jpg'}
    if name not in allowed and not re.fullmatch(r'(reference|rendered)-\d{2}\.jpg',name):raise HTTPException(404)
    path=DATA/id/name
    if name=='thumbnail.jpg' and not path.exists():
        from .media import thumbnail
        folder=DATA/id
        source=folder/'output.mp4' if (folder/'output.mp4').exists() else folder/'source.mp4'
        if source.exists():thumbnail(source,path)
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path)


from .recording_routes import install as install_recording_exports
install_recording_exports(app, DATA, get_job, PORT)

app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')

from .editor import install as install_editor
import sys
install_editor(app, sys.modules[__name__])
