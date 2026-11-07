"""Persist a reference sequence and feed its trimmed montage into reconstruction."""
import json
import threading
import time
import uuid
from typing import Literal

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import Field, model_validator

from .models import Strict, Brief, MAX_DURATION
from .media import probe
from .process import run


class Segment(Strict):
    project: str = Field(pattern=r'^[a-f0-9]{12}$')
    start: float = Field(ge=0, le=MAX_DURATION)
    end: float = Field(gt=0, le=MAX_DURATION)
    notes: str = Field(default='', max_length=200)

    @model_validator(mode='after')
    def range(self):
        if self.end-self.start < .25:
            raise ValueError('Each segment must be at least 0.25 seconds.')
        return self


class Edit(Strict):
    brand: str = Field(default='', max_length=120)
    instructions: str = Field(default='', max_length=2500)
    format: Literal['landscape','portrait','square'] = 'landscape'
    keep_audio: bool = True
    segments: list[Segment] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def duration(self):
        if sum(s.end-s.start for s in self.segments)>MAX_DURATION:
            raise ValueError('Keep the sequence within 120 seconds.')
        return self


def validate_sources(edit, data, jobs):
    for segment in edit.segments:
        job = jobs.get(segment.project)
        path = data/segment.project/'source.mp4'
        if not job or not path.is_file():
            raise ValueError('A selected reference is unavailable. Remove it and choose another.')
        if job['status'] in ('queued','running'):
            raise ValueError('Wait for the reference to finish importing.')
        duration = job.get('media',{}).get('duration',0)
        if segment.end>duration+.001:
            raise ValueError('A selected segment ends after its reference video.')


def assemble(edit, data, folder, cancel, progress):
    width,height = {'landscape':(1280,720),'portrait':(720,1280),'square':(1080,1080)}[edit.format]
    parts=[]
    for index, segment in enumerate(edit.segments):
        source=data/segment.project/'source.mp4'
        meta=probe(source)
        if segment.end>meta['duration']+.001:
            raise ValueError('A reference changed. Choose its segment again.')
        duration=segment.end-segment.start
        dest=folder/f'edit-part-{index:02}.mp4'
        progress(f'Preparing segment {index+1} of {len(edit.segments)}',2+index*3)
        command=['ffmpeg','-y','-v','error','-ss',str(segment.start),'-i',str(source)]
        if not meta['audio'] or not edit.keep_audio:
            command+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']
        command+=['-map','0:v:0','-map','0:a:0' if meta['audio'] and edit.keep_audio else '1:a:0',
                  '-t',str(duration),'-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                  '-af','apad,aresample=48000','-ac','2','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(dest)]
        run(command,timeout=300,cancel=cancel);parts.append(dest)
    listing=folder/'edit-parts.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in parts),encoding='utf-8')
    # Bound the final duration: per-part AAC padding must not push a 120s edit
    # past the reconstruction input limit.
    duration=sum(segment.end-segment.start for segment in edit.segments)
    run(['ffmpeg','-y','-v','error','-f','concat','-safe','1','-i',str(listing),'-t',str(duration),
         '-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-movflags','+faststart','-f','mp4',str(folder/'input.bin')],timeout=300,cancel=cancel)
    for part in parts: part.unlink()
    listing.unlink()


def install(app, server):
    @app.get('/editor')
    def editor_page():
        page=(server.ROOT/'web/editor.html').read_text(encoding='utf-8')
        if server.HOSTED:
            page=page.replace('<body>', '<body data-hosted="true">').replace('href="/?workspace=1"','href="/studio"').replace('250 MB','25 MB')
        return HTMLResponse(page)

    @app.get('/api/editor/draft')
    def read_draft():
        path=server.DATA/'editor-draft.json'
        if not path.exists(): return Edit()
        try: return Edit.model_validate_json(path.read_text(encoding='utf-8'))
        except ValueError: raise HTTPException(409,'The saved sequence could not be read. Save a new sequence to replace it.') from None

    @app.post('/api/editor/draft')
    def save_draft(edit: Edit):
        with server.LOCK:
            validate_or_error(edit)
            path=server.DATA/'editor-draft.tmp'
            path.write_text(edit.model_dump_json(indent=2),encoding='utf-8')
            path.replace(server.DATA/'editor-draft.json')
        return edit

    def validate_or_error(edit):
        try: validate_sources(edit,server.DATA,server.JOBS)
        except ValueError as exc: raise HTTPException(422,str(exc)) from None

    @app.post('/api/editor/references')
    async def import_reference(video: UploadFile|None=File(None),url: str=Form('')):
        return await server.create_job(video=video,logo=None,url=url,brand='',instructions='',mode='hyperframes',accent='#bcf76a',keep_audio=True,auto_review=True,sampling='standard',import_only=True)

    @app.post('/api/editor/generate')
    def generate(edit: Edit):
        if not server.auth_status():
            raise HTTPException(401,'Connect your own ChatGPT/Codex account before generating. Your account costs and usage limits apply.')
        if not edit.segments: raise HTTPException(422,'Add at least one segment.')
        with server.LOCK:
            if server.ACTIVE['id']: raise HTTPException(409,'Another video is processing. Wait for it to finish.')
            validate_or_error(edit)
            timeline=[];offset=0
            for index,segment in enumerate(edit.segments):
                end=offset+segment.end-segment.start
                timeline.append(f'Segment {index+1}, {offset:.2f}–{end:.2f}s: {segment.notes or "Use this reference motion."}')
                offset=end
            instructions='Create one cohesive, editable video from this assembled reference sequence. Respect segment order and timing. Adapt to the requested brand and brief.\n'+edit.instructions+'\n'+'\n'.join(timeline)
            brief=Brief(brand=edit.brand,instructions=instructions,keep_audio=edit.keep_audio)
            ident=uuid.uuid4().hex[:12]
            job={'id':ident,'created':time.time(),'name':edit.brand.strip() or 'Editor sequence','status':'queued',
                 'stage':'Preparing selected segments','progress':0,'brief':brief.model_dump(),'url':'','editor':edit.model_dump(),
                 'events':[],'error':None,'cancel':threading.Event()}
            server.JOBS[ident]=job;server.ACTIVE['id']=ident
            server.persist(job)
            job['future']=server.POOL.submit(server.pipeline,ident)
            return server.public(job)
