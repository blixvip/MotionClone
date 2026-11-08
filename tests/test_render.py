import json
import subprocess
import threading
from pathlib import Path
import cv2
import numpy as np
import pytest
from PIL import ImageFont
from app.media import prepare, probe
from app.models import Plan, Track, Keyframe, Brief
from app.render import font_for, render


def test_real_rebuild_does_not_reuse_reference_pixels_and_verifies_audio(tmp_path):
    source=tmp_path/'input.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=red:s=320x180:r=12:d=1',
                    '-f','lavfi','-i','sine=frequency=600:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    stop=threading.Event()
    prepare(source,tmp_path,stop,lambda *a:None)
    plan=Plan(background='#0000ff',tracks=[Track(id='title',kind='text',text='REBUILT',start=0,end=1,
                     keyframes=[Keyframe(t=0,x=.2,y=.3,w=.6,h=.4)])])
    result=render(tmp_path,plan,Brief(mode='rebuild',keep_audio=False),stop,lambda *a:None)
    report=json.loads((tmp_path/'verification.json').read_text())
    assert report['actual_frames']==12
    assert report['audio_present'] is False
    cap=cv2.VideoCapture(str(result));ok,frame=cap.read();cap.release()
    assert ok
    assert frame[10,10,0]>240 and frame[10,10,2]<10 # BGR blue, reference was red
    assert np.count_nonzero(frame[50:125,60:260,1]>120)>100 # visible text


def test_cancel_before_render_stops_owned_work(tmp_path):
    from app.process import run, Cancelled
    import pytest,sys
    stop=threading.Event();stop.set()
    with pytest.raises(Cancelled):
        run([sys.executable,'-c','import time;time.sleep(20)'],cancel=stop)


def test_portrait_import_preserves_vertical_resolution(tmp_path):
    source=tmp_path/'portrait.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=blue:s=720x1280:r=12:d=0.5',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    meta,_=prepare(source,tmp_path,threading.Event(),lambda *a:None)
    assert (meta['width'],meta['height'])==(720,1280)


@pytest.mark.parametrize('family,weight,face',[
    ('sans','regular','DejaVuSans.ttf'),
    ('sans','bold','DejaVuSans-Bold.ttf'),
    ('serif','regular','DejaVuSerif.ttf'),
    ('serif','bold','DejaVuSerif-Bold.ttf'),
    ('mono','regular','DejaVuSansMono.ttf'),
    ('mono','bold','DejaVuSansMono-Bold.ttf')])
def test_font_fallback_keeps_family_and_weight(monkeypatch,tmp_path,family,weight,face):
    # No Fonts dir under the patched WINDIR, so the Windows lookup misses.
    monkeypatch.setenv('WINDIR',str(tmp_path))
    monkeypatch.setattr(Path,'exists',lambda self:self.name==face)
    chosen=[]
    monkeypatch.setattr(ImageFont,'truetype',lambda *a,**k:chosen.append(a[0]) or (family,weight))
    monkeypatch.setattr(ImageFont,'load_default',lambda *a,**k:'default')
    font_for.cache_clear()
    try:
        assert font_for(family,weight,32)==(family,weight)
        assert Path(chosen[0]).name==face
    finally:
        font_for.cache_clear()
