import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.editor import Edit, Segment, assemble, validate_sources
import app.server as server
from app.media import probe
from app.process import run


@pytest.mark.parametrize('data', [
    {'project': '../secrets', 'start': 0, 'end': 1},
    {'project': 'a'*12, 'start': 2, 'end': 1},
    {'project': 'a'*12, 'start': 0, 'end': .1},
    {'project': 'a'*12, 'start': float('nan'), 'end': 1},
])
def test_segment_rejects_unsafe_paths_and_invalid_ranges(data):
    with pytest.raises(ValidationError): Segment(**data)


def test_edit_limits_duration_and_clip_count():
    clip = {'project': 'a'*12, 'start': 0, 'end': 61}
    with pytest.raises(ValidationError): Edit(segments=[clip, clip])
    with pytest.raises(ValidationError): Edit(segments=[dict(clip, end=1)]*13)


def test_sources_require_owned_finished_media_and_valid_end(tmp_path):
    edit = Edit(segments=[{'project': 'a'*12, 'start': 0, 'end': 3}])
    with pytest.raises(ValueError): validate_sources(edit, tmp_path, {})
    folder = tmp_path / ('a'*12); folder.mkdir(); (folder/'source.mp4').write_bytes(b'x')
    jobs = {'a'*12: {'status': 'complete', 'media': {'duration': 2}}}
    with pytest.raises(ValueError): validate_sources(edit, tmp_path, jobs)
    jobs['a'*12]['media']['duration'] = 4
    validate_sources(edit, tmp_path, jobs)
    jobs['a'*12]['status'] = 'running'
    with pytest.raises(ValueError): validate_sources(edit, tmp_path, jobs)


@pytest.fixture
def editor_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    monkeypatch.setattr(server, 'JOBS', {})
    monkeypatch.setattr(server, 'ACTIVE', {'id': None})
    monkeypatch.setattr(server, 'auth_status', lambda: False)
    return TestClient(server.app)


def test_draft_saved_on_server_and_protected_by_csrf(editor_client):
    draft = {'brand': 'My launch', 'instructions': 'Use blue', 'segments': []}
    assert editor_client.post('/api/editor/draft', json=draft).status_code == 403
    headers = {'X-Frameforge-Token': server.TOKEN}
    assert editor_client.post('/api/editor/draft', json=draft, headers=headers).status_code == 200
    assert editor_client.get('/api/editor/draft').json()['brand'] == 'My launch'


def test_generate_requires_own_account_before_creating_job(editor_client):
    response = editor_client.post('/api/editor/generate', json={'segments': [{'project': 'a'*12, 'start': 0, 'end': 1}]}, headers={'X-Frameforge-Token': server.TOKEN})
    assert response.status_code == 401
    assert not server.JOBS
    assert server.ACTIVE['id'] is None


def test_connected_generation_saves_order_and_brief_before_queueing(editor_client,monkeypatch):
    monkeypatch.setattr(server,'auth_status',lambda:True)
    submitted=[]
    class Pool:
        def submit(self,*args): submitted.append(args)
    monkeypatch.setattr(server,'POOL',Pool())
    ident='a'*12;folder=server.DATA/ident;folder.mkdir();(folder/'source.mp4').write_bytes(b'reference')
    server.JOBS[ident]={'id':ident,'status':'draft','media':{'duration':5}}
    spec={'brand':'Launch','instructions':'Use blue','segments':[{'project':ident,'start':1,'end':2,'notes':'Opening'},{'project':ident,'start':3,'end':5,'notes':'Closing'}]}
    response=editor_client.post('/api/editor/generate',json=spec,headers={'X-Frameforge-Token':server.TOKEN})
    assert response.status_code==200,response.text
    job=response.json();assert job['editor']['segments']==spec['segments']
    assert '0.00–1.00s: Opening' in job['brief']['instructions']
    assert '1.00–3.00s: Closing' in job['brief']['instructions']
    assert 'Use blue' in job['brief']['instructions']
    assert submitted==[(server.pipeline,job['id'])]
    assert (server.DATA/job['id']/'job.json').is_file()
    assert editor_client.post('/api/editor/generate',json=spec,headers={'X-Frameforge-Token':server.TOKEN}).status_code==409


def test_assemble_real_order_audio_and_duration(tmp_path):
    for ident, color, audio in [('a'*12, 'red', True), ('b'*12, 'blue', False)]:
        folder = tmp_path/ident; folder.mkdir()
        cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=160x90:r=30:d=1']
        if audio: cmd += ['-f','lavfi','-i','sine=frequency=440:duration=1']
        run(cmd+['-c:v','libx264','-pix_fmt','yuv420p','-t','1',str(folder/'source.mp4')])
    edit = Edit(segments=[{'project':'b'*12,'start':.1,'end':.6},{'project':'a'*12,'start':.2,'end':.95}])
    dest = tmp_path/'result'; dest.mkdir()
    assemble(edit,tmp_path,dest,threading.Event(),lambda *args:None)
    media = probe(dest/'input.bin')
    assert abs(media['duration']-1.25)<.1
    assert media['audio'] and (media['width'],media['height'])==(1280,720)
    import numpy as np
    for timestamp, channel in [(.2,2),(.8,0)]:
        frame = run(['ffmpeg','-v','error','-ss',str(timestamp),'-i',str(dest/'input.bin'),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        pixel = np.frombuffer(frame,dtype=np.uint8).reshape(720,1280,3)[360,640]
        assert pixel[channel]>200 and pixel[(channel+1)%3]<30
