import json
import threading
import pytest
import cv2
import numpy as np
from PIL import Image
from app import scene_pipeline as scenes
from app.rebuild_author import SceneProject,Layer,SceneRevision,apply_revision


def project(text='Hello'):
    return SceneProject(title=text,background='#ffffff',layers=[dict(id='title',kind='text',text=text,end=24,
        frames=[dict(t=0,x=20,y=20,w=100,h=30)])])


def test_scene_ranges_cover_every_frame_without_gaps_or_duplication():
    scan=dict(decoded_frames=1844,fps=30,visual_jump_frames=[157,400,717,1100,1460])
    intervals=scenes.intervals(scan)
    assert [n for a,b in intervals for n in range(a,b)]==list(range(1844))
    assert all(b-a<=180 for a,b in intervals)
    assert intervals[0][1]==157


def test_merge_clips_scene_lifetimes_and_namespaces_repeated_ids():
    merged=scenes.merge([project(),project('Next')],[(0,120),(120,240)],dict(fps=10,width=320,height=180))
    titles=[layer for layer in merged.layers if layer.kind=='text']
    assert [layer.id for layer in titles]==['s0_title','s1_title']
    assert [(layer.start,layer.end) for layer in titles]==[(0,12),(12,24)]


def test_invalid_group_parent_rejected():
    data=project().model_dump();data['layers'].append({**data['layers'][0],'id':'child','parent':'title'})
    with pytest.raises(ValueError,match='group parents'):SceneProject.model_validate(data)


def test_scene_background_does_not_collide_with_authored_background_group():
    value=SceneProject(title='Background',background='#101010',layers=[
        dict(id='background',kind='group',end=2,frames=[dict(t=0,x=0,y=0,w=320,h=180)]),
        dict(id='label',parent='background',kind='text',text='Hello',end=2,
             frames=[dict(t=0,x=10,y=10,w=100,h=30)])])
    merged=scenes.merge([value],[(0,20)],dict(fps=10,width=320,height=180))
    assert len({layer.id for layer in merged.layers})==3
    assert merged.layers[-1].parent=='s0_background'


def test_grid_and_rounded_strokes_are_supported_without_external_resources():
    layer=Layer(id='outline',kind='path',path='M0 0L100 100',end=1,style={'backgroundSize':'55px 55px','strokeLinecap':'round','strokeLinejoin':'round'},frames=[dict(t=0,x=0,y=0,w=100,h=100)])
    assert layer.style['strokeLinecap']=='round'
    with pytest.raises(ValueError):Layer.model_validate({**layer.model_dump(),'style':{'backgroundImage':'url(https://example.com/frame.png)'}})


def test_worse_revision_is_rejected_and_completed_scene_resumes(tmp_path,monkeypatch):
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,visual_jump_frames=[],sample_frames=[])))
    calls=[];written=[]
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    def request(*args,**kwargs):
        calls.append(kwargs.get('tag','analysis'))
        if kwargs.get('tag'):return SceneRevision(updates=[dict(id='title',text='Bad revision')])
        return project('Good initial')
    monkeypatch.setattr(scenes,'request_scene',request)
    monkeypatch.setattr(scenes,'write_project',lambda folder,meta,value,**kw:written.append(value))
    def preview(*args,**kwargs):return [dict(scene=0,mean=.5 if kwargs.get('tag') else .8,minimum=.4 if kwargs.get('tag') else .7,image=str(tmp_path/'pair.jpg'))]
    monkeypatch.setattr(scenes,'preview',preview)
    result=scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    assert result.title=='Good initial'
    assert json.loads((tmp_path/'analysis-report.json').read_text())['revisions'][0]['accepted'] is False
    assert written[-1].title=='Good initial'
    scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    assert calls.count('analysis')==1


def test_small_revision_preserves_unmodified_geometry_and_rejects_unsafe_css():
    original=project();changed=apply_revision(original,SceneRevision(updates=[dict(id='title',text='Correct copy',style={'fontSize':'30px'})]))
    assert changed.layers[0].frames==original.layers[0].frames
    assert changed.layers[0].text=='Correct copy'
    with pytest.raises(ValueError):apply_revision(original,SceneRevision(updates=[dict(id='title',style={'background':'url(https://example.com)'})]))


def test_cancellation_does_not_start_model_work(tmp_path,monkeypatch):
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,visual_jump_frames=[],sample_frames=[])))
    stop=threading.Event();stop.set()
    with pytest.raises(scenes.Cancelled):
        scenes.build(tmp_path,dict(fps=10,width=320,height=180),stop,lambda *a:None)


def test_model_images_preserve_one_viewport_per_attachment(tmp_path):
    source=tmp_path/'frames.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,90))
    for i in range(4):writer.write(np.full((90,160,3),(i*40,20,100),dtype=np.uint8))
    writer.release()
    paths=scenes.reference_sheets(source,tmp_path,[0,1,3],10,threading.Event())
    assert len(paths)==3
    for path in paths:
        with Image.open(path) as image:assert image.size==(160,90), 'A collage changes the coordinate system the model sees.'
    assert paths[-1].name=='frame-000003-0.300s.jpg'


def test_detailed_analysis_uses_shorter_scenes_without_losing_frames():
    scan=dict(decoded_frames=556,fps=60,budget=384,visual_jump_frames=[])
    ranges=scenes.intervals(scan)
    assert max(b-a for a,b in ranges)<=198
    assert len(ranges)==3, 'A 0.27-second tail should not require a fourth model request.'
    assert [n for a,b in ranges for n in range(a,b)]==list(range(556))


def test_analysis_samples_keep_late_single_frame_flash_and_neighbors():
    scan=dict(sample_frames=list(range(180)),visual_jump_frames=[151,152])
    indices=scenes.sample_indices(0,180,scan)
    assert {150,151,152,153}.issubset(indices)
    assert {0,179}.issubset(indices)
    assert len(indices)<=16


def test_detailed_analysis_attaches_more_reference_frames():
    scan=dict(sample_frames=list(range(180)),visual_jump_frames=[],budget=384)
    assert len(scenes.sample_indices(0,180,scan))==24


def test_rebuild_receives_user_instructions_and_invalidates_changed_brief(tmp_path,monkeypatch):
    from app.models import Brief
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,sample_frames=[])))
    contexts=[]
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    monkeypatch.setattr(scenes,'write_project',lambda *a,**kw:None)
    monkeypatch.setattr(scenes,'preview',lambda *a,**kw:[])
    def request(*args,**kwargs):
        contexts.append(kwargs['context']);return project()
    monkeypatch.setattr(scenes,'request_scene',request)
    def build(instructions):
        return scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None,
                            brief=Brief(instructions=instructions))
    build('Preserve the four-panel layout.')
    assert 'Preserve the four-panel layout.' in contexts[0]
    build('Preserve the four-panel layout.')
    assert len(contexts)==1
    build('Use the exact reference typography.')
    assert len(contexts)==2 and 'Use the exact reference typography.' in contexts[-1]


@pytest.mark.parametrize('budget,expected_timeout',[(192,240),(384,420)])
def test_detailed_scene_has_time_to_finish_without_extending_total_budget(tmp_path,monkeypatch,budget,expected_timeout):
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,sample_frames=[],budget=budget)))
    timeouts=[]
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    monkeypatch.setattr(scenes,'write_project',lambda *a,**kw:None)
    monkeypatch.setattr(scenes,'preview',lambda *a,**kw:[])
    def request(*args,**kwargs):
        timeouts.append(kwargs['timeout']);return project()
    monkeypatch.setattr(scenes,'request_scene',request)
    scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    assert timeouts==[expected_timeout]
    assert max(timeouts)<scenes.MAX_SECONDS


def test_similarity_detects_wrong_colors_with_equal_brightness():
    red=np.full((32,32,3),(255,0,0),dtype=np.uint8)
    green=np.full((32,32,3),(0,130,0),dtype=np.uint8)
    assert np.array_equal(cv2.cvtColor(red,cv2.COLOR_RGB2GRAY),cv2.cvtColor(green,cv2.COLOR_RGB2GRAY))
    assert scenes.similarity(red,red)==pytest.approx(1)
    assert scenes.similarity(red,green)<.5, 'A different palette must not pass visual correction as a match.'


def test_preview_checks_detected_flash_between_regular_samples(tmp_path):
    source=tmp_path/'source.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,90))
    assert writer.isOpened()
    for n in range(20):writer.write(np.full((90,160,3),255 if n==3 else 0,dtype=np.uint8))
    writer.release()
    (tmp_path/'scene-work').mkdir();(tmp_path/'rebuild').mkdir()
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=20,visual_jump_frames=[3,4],sample_frames=[])))
    (tmp_path/'rebuild/index.html').write_text('<style>body{margin:0;background:#000}</style><script>window.drawFrame=()=>{};</script>')
    initial=scenes.preview(tmp_path,[(0,20)],dict(width=160,height=90,fps=10),threading.Event())[0]
    candidate=scenes.preview(tmp_path,[(0,20)],dict(width=160,height=90,fps=10),threading.Event(),tag='revision',only={0})[0]
    assert {2,3,4,5}.issubset(initial['frames'])
    assert initial['frames']==candidate['frames'], 'Revision decisions must compare the exact same moments.'
    assert initial['minimum']<.1, 'The missing single-frame flash must be measured.'


def test_accepted_revision_report_contains_final_measured_preview(tmp_path,monkeypatch):
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,sample_frames=[])))
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    monkeypatch.setattr(scenes,'write_project',lambda *a,**kw:None)
    monkeypatch.setattr(scenes,'request_scene',lambda *a,**kw:SceneRevision(updates=[dict(id='title',text='Better')]) if kw.get('tag') else project())
    def preview(*a,**kw):
        improved=bool(kw.get('tag'))
        return [dict(scene=0,mean=.9 if improved else .7,minimum=.8 if improved else .6,image=str(tmp_path/'pair.jpg'))]
    monkeypatch.setattr(scenes,'preview',preview)
    result=scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    report=json.loads((tmp_path/'analysis-report.json').read_text())
    assert next(layer.text for layer in result.layers if layer.kind=='text')=='Better'
    assert report['revisions'][0]['accepted'] is True
    assert report['previews'][0]['mean']==.9
    assert report['previews'][0]['minimum']==.8


@pytest.mark.parametrize('filename,contents',[
    ('checkpoint.json','{"key":'),('checkpoint.json','null'),('request.json','{"key":'),
])
def test_broken_checkpoint_is_rebuilt_instead_of_blocking_resume(tmp_path,monkeypatch,filename,contents):
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,sample_frames=[])))
    part=tmp_path/'scene-work/scene-00';part.mkdir(parents=True)
    (part/filename).write_text(contents)
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    monkeypatch.setattr(scenes,'write_project',lambda *a,**kw:None)
    monkeypatch.setattr(scenes,'preview',lambda *a,**kw:[])
    monkeypatch.setattr(scenes,'request_scene',lambda *a,**kw:project('Recovered'))
    result=scenes.build(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    assert result.title=='Recovered'
    assert json.loads((part/'checkpoint.json').read_text())['project']['title']=='Recovered'


def test_interrupted_new_request_cannot_resume_response_from_old_instructions(tmp_path,monkeypatch):
    from app.models import Brief
    (tmp_path/'source.mp4').write_bytes(b'known reference')
    (tmp_path/'temporal.json').write_text(json.dumps(dict(fps=10,decoded_frames=30,sample_frames=[])))
    part=tmp_path/'scene-work/scene-00';part.mkdir(parents=True)
    (part/'request.json').write_text(json.dumps({'key':'old instructions'}))
    (part/'repair.response.json').write_text(project('Stale').model_dump_json())
    monkeypatch.setattr(scenes,'reference_sheets',lambda *a:[])
    monkeypatch.setattr(scenes,'write_project',lambda *a,**kw:None)
    monkeypatch.setattr(scenes,'preview',lambda *a,**kw:[])
    def interrupted(*a,**kw):raise scenes.Cancelled()
    monkeypatch.setattr(scenes,'request_scene',interrupted)
    args=(tmp_path,dict(fps=10,width=320,height=180),threading.Event(),lambda *a:None)
    with pytest.raises(scenes.Cancelled):scenes.build(*args,brief=Brief(instructions='New copy'))
    monkeypatch.setattr(scenes,'request_scene',lambda *a,**kw:project('New copy'))
    result=scenes.build(*args,brief=Brief(instructions='New copy'))
    assert result.title=='New copy'
