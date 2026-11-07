import json
import threading
import zipfile
import pytest
import cv2
from app import reconstruction as rebuild, rebuild_author as author, server
from app.models import Brief
from app.media import prepare
from app.process import run


def test_generated_styles_cannot_load_source_or_execute_code():
    for style in [{'background':'url(source.mp4)'},{'backgroundImage':'url(https://example.com)'},{'color':'expression(alert(1))'}]:
        with pytest.raises(ValueError):
            author.Layer(id='title',kind='text',end=1,frames=[dict(t=0,x=0,y=0,w=100,h=20)],style=style)


def test_source_replay_rejected(tmp_path):
    (tmp_path/'index.html').write_text('<div data-composition-id="test"><video src="assets/original.mp4"></video></div>')
    with pytest.raises(ValueError,match='source video'):
        rebuild.audit_project(tmp_path,{'width':480,'height':852})


def test_real_independent_render_and_honest_comparison(tmp_path,monkeypatch):
    source=tmp_path/'input.mp4'
    run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=red:s=160x90:r=30:d=0.4','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
    stop=threading.Event();meta,_=prepare(source,tmp_path,stop,lambda *a:None,faithful=True)
    scene=author.SceneProject(title='Separate layers',background='#0000ff',layers=[dict(id='title',kind='text',text='Editable source.mp4',end=.4,
        style={'color':'#ffffff','fontSize':'18px'},frames=[dict(t=0,x=5,y=15,w=100,h=30),dict(t=.4,x=30,y=15,w=100,h=30)]),
        dict(id='translucent',kind='rect',end=.4,style={'background':'#ffffff','opacity':'0.25'},frames=[dict(t=0,x=5,y=60,w=25,h=15)])])
    author.write_project(tmp_path,meta,scene)
    # Reference/debug assets must never enter the editable project download.
    (tmp_path/'rebuild/ref-debug.png').write_bytes(b'not a project dependency')
    report=rebuild.render(tmp_path,Brief(),stop,lambda *a:None)
    assert report['actual_frames']==report['compared_frames']==12
    assert report['source_backed'] is False and report['near_perfect'] is False
    assert report['visual_check']=='differences'
    capture=cv2.VideoCapture(str(tmp_path/'output.mp4'));ok,frame=capture.read();capture.release()
    assert ok and int(frame[80,150,0])>220 and int(frame[80,150,2])<20, 'Composition background must survive alpha capture.'
    assert 40<int(frame[65,15,2])<90, 'Static opacity must survive animated pose updates.'
    with zipfile.ZipFile(rebuild.export_project(tmp_path)) as z:
        assert 'project.json' in z.namelist()
        assert not any(name.endswith(('.mp4','.png')) for name in z.namelist())
        assert not json.loads(z.read('manifest.json'))['source_backed']
    def must_not_render(*args,**kwargs):raise AssertionError('Renderer invoked')
    monkeypatch.setattr(rebuild,'run_cli',must_not_render)
    assert rebuild.render(tmp_path,Brief(),stop,lambda *a:None)['cache_hit'] is True
    with (tmp_path/'rebuild/renderer.js').open('a') as stream:stream.write('\n// author edit')
    with pytest.raises(AssertionError,match='Renderer invoked'):
        rebuild.render(tmp_path,Brief(),stop,lambda *a:None)


def test_new_pipeline_never_falls_back_to_original_copy(tmp_path,monkeypatch):
    ident='d'*12;folder=tmp_path/ident;folder.mkdir();(folder/'rebuild').mkdir()
    (folder/'rebuild/index.html').write_text('fixture')
    (folder/'source.mp4').write_bytes(b'source');(folder/'media.json').write_text('{}')
    job=dict(id=ident,brief=Brief().model_dump(),stage='Queued',events=[],status='queued',created=0,cancel=threading.Event())
    monkeypatch.setattr(server,'DATA',tmp_path);monkeypatch.setattr(server,'JOBS',{ident:job});monkeypatch.setattr(server,'ACTIVE',{'id':ident})
    def fail(*args):raise ValueError('Independent layer render failed')
    def forbidden(*args):raise AssertionError('Original-copy fallback is forbidden')
    monkeypatch.setattr(rebuild,'render',fail);monkeypatch.setattr('app.hyperframes.render',forbidden)
    server.pipeline(ident)
    assert job['status']=='error' and 'Independent layer' in job['error']
    assert not (folder/'output.mp4').exists()


def test_negative_visual_similarity_reports_differences_without_rejecting_valid_video(tmp_path):
    import numpy as np
    from PIL import Image
    y,x=np.indices((90,160));pattern=(((x//4+y//4)%2)*255).astype(np.uint8)
    for name,pixels in [('source',pattern),('candidate',255-pattern)]:
        image=tmp_path/(name+'.png');Image.fromarray(pixels).save(image)
        run(['ffmpeg','-y','-v','error','-loop','1','-i',str(image),'-r','10','-frames:v','3',
             '-c:v','libx264','-crf','0','-pix_fmt','yuv420p',str(tmp_path/(name+'.mp4'))])
    report=rebuild.compare_frames(tmp_path,tmp_path/'candidate.mp4',threading.Event())
    assert report['actual_frames']==report['compared_frames']==3
    assert report['ssim_min']<0
    assert report['visual_check']=='differences' and report['near_perfect'] is False
