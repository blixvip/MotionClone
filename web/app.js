const $=id=>document.getElementById(id);
let token='',current=null,view='result',editing=false,lastPlan='',polling=false,ready=false,submitting=false;
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'X-Frameforge-Token':token,...options.headers}});if(!r.ok){let d;try{d=await r.json()}catch{d={detail:r.statusText}}const error=new Error(typeof d.detail==='string'?d.detail:'Check the project settings and try again.');error.status=r.status;throw error;}return r.json()}
function error(message){$('global-error').textContent=message;$('global-error').hidden=!message}
function brief(){return {brand:'',instructions:'',mode:'hyperframes',accent:'#b9abff',keep_audio:$('keep-audio').checked,auto_review:false}}
function fillBrief(b){$('brand').value=b.brand;$('instructions').value=b.instructions;$('accent').value=b.accent;$('keep-audio').checked=b.keep_audio;$('auto-review').checked=b.auto_review;document.querySelector(`[name=mode][value=${b.mode}]`).checked=true}
async function status(){
  try{
    const s=await api('/api/status');token=s.token;ready=!!(s.hyperframes&&s.ffmpeg);
    $('connection').textContent=!ready?'Setup needed':s.chatgpt?'Ready':'Sign in needed';
    $('connection-dot').classList.toggle('connected',ready&&!!s.chatgpt);
    $('connection').title=ready?(s.chatgpt?'Renderer and ChatGPT are ready':'Renderer ready; connect ChatGPT for new rebuilds'):'Check the local renderer setup';
    $('auth-help').hidden=!!s.chatgpt;$('connection-notice').hidden=true;
    window.onAccountStatus?.(s);
    if(!s.ffmpeg)error('FFmpeg is missing. Install FFmpeg and restart the app.');
    return s;
  }catch(e){$('connection').textContent='Disconnected';$('connection-dot').classList.remove('connected');$('connection-notice').hidden=false;return null;}
}
function importError(message) {
  $('import-error').textContent=message;
  $('import-error').hidden=!message;
  $('url').setAttribute('aria-invalid',String(!!message && !$('video').files.length));
}
function fileChanged() {
  const file=$('video').files[0];
  $('filename').textContent=file?file.name:'';
  $('selected-file').hidden=!file;
  $('filehint').textContent=file?`${(file.size/1048576).toFixed(1)} MB selected`:`Drag & drop · MP4, MOV, WebM · ${document.body.dataset.hosted==='true'?25:250} MB max`;
  if(file)$('url').value='';
  importError('');
}
$('remove-video').addEventListener('click',()=>{$('video').value='';fileChanged();$('url').focus();});
$('video').addEventListener('change',fileChanged);
$('logo').addEventListener('change',()=>{$('logo-label').textContent=$('logo').files[0]?.name||'＋ Add your logo'});
for(const name of ['dragenter','dragover'])$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.add('dragging')});
for(const name of ['dragleave','drop'])$('dropzone').addEventListener(name,e=>{e.preventDefault();$('dropzone').classList.remove('dragging')});
$('dropzone').addEventListener('drop',e=>{if(submitting||$('import-fields').disabled)return;const f=[...e.dataTransfer.files].find(f=>f.type.startsWith('video/')||/\.(mp4|mov|webm|mkv)$/i.test(f.name));if(f){const dt=new DataTransfer();dt.items.add(f);$('video').files=dt.files;fileChanged()}});
document.addEventListener('paste',e=>{if(submitting||$('editor-view').hidden||document.body.classList.contains('is-project')||$('import-fields').disabled)return;const f=[...(e.clipboardData?.files||[])].find(f=>f.type.startsWith('video/'));if(f){const dt=new DataTransfer();dt.items.add(f);$('video').files=dt.files;fileChanged();e.preventDefault()}});
$('url').addEventListener('input',()=>{if($('url').value){$('video').value='';fileChanged()}importError('');});
$('create-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(submitting || current && ['queued','running'].includes(current.status))return;
  importError('');error('');
  const file=$('video').files[0],url=$('url').value.trim();
  if(!file&&!url){importError('Paste a video link or upload a file to get started.');$('url').focus();return;}
  if(!file && (!$('url').validity.valid || !url.startsWith('https://'))){importError('Use a complete public video link starting with https://.');$('url').focus();return;}
  const uploadLimit=document.body.dataset.hosted==='true'?25:250;
  if(file && file.size>uploadLimit*1048576){importError(`This video is larger than ${uploadLimit} MB. Use a video link or choose a smaller file.`);return;}
  const data=new FormData();
  Object.entries(brief()).forEach(([key,value])=>data.append(key,String(value)));
  if(file)data.append('video',file);else data.append('url',url);
  if($('logo').files[0])data.append('logo',$('logo').files[0]);
  submitting=true;
  $('import-fields').disabled=true;$('new-project').disabled=true;
  $('create').disabled=true;setControl('create','Starting…','loader');
  $('create-form').setAttribute('aria-busy','true');
  try{
    const connection=await status();
    if(!connection)throw new Error('The app is disconnected. Start MotionClone, then try again.');
    if(!connection.chatgpt)throw new Error('Connect ChatGPT using the sign-in instructions above, then try again.');
    if(!ready)throw new Error('Run Start MotionClone to install HyperFrames and check FFmpeg, then try again.');
    current=await api('/api/jobs',{method:'POST',body:data});
    editing=false;lastPlan='';
    localStorage.setItem('frameforge-project',current.id);show(current);editorPage();await refreshLibrary();
  }catch(e){importError(e.message);}
  finally{
    submitting=false;
    const busy=!!current&&['queued','running'].includes(current.status);
    $('import-fields').disabled=busy;$('create').disabled=busy;
    $('new-project').disabled=false;
    setControl('create',busy?'Rebuilding…':'Rebuild video',busy?'loader':'layers');
    $('create-form').setAttribute('aria-busy',String(busy));
  }
});
function setSource(player,url){if(url&&player.getAttribute('src')!==url){player.src=url;player.load()}}
function switchView(next){view=next;for(const id of ['result','source','compare']){$(id+'-tab').classList.toggle('active',id===view);$(id+'-tab').setAttribute('aria-selected',String(id===view));$(id+'-tab').tabIndex=id===view?0:-1}updatePlayers()}
function updatePlayers(){if(!current){window.syncComparison?.(null,view);return;}const f=current.files;const result=f.output?f.output:f['output.mp4']||f['preview.mp4'];const source=f['source.mp4'];if(source)setSource($('source-video'),source);if(result)setSource($('result-video'),result+'?v='+current.created+'-'+(current.status==='complete'?current.events?.length:0));const hasMedia=!!(result||source);$('empty-stage').hidden=hasMedia;$('players').hidden=!hasMedia;$('players').classList.toggle('compare',view==='compare'&&!!result);$('result-video').hidden=view==='source'||!result;$('source-video').hidden=!!result&&view==='result';$('source-video').controls=view!=='compare';$('render-pending').hidden=!!result||!source||!['running','queued'].includes(current.status);window.syncComparison?.(current,view)}
for(const v of ['result','source','compare'])$(v+'-tab').addEventListener('click',()=>switchView(v));
const videoTabs=['result','source','compare'];
videoTabs.forEach((name,index)=>$(name+'-tab').addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  const next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3;
  switchView(videoTabs[next]);$(videoTabs[next]+'-tab').focus();
}));
let syncing=false;
for(const event of ['play','pause','seeking'])$('result-video').addEventListener(event,()=>{if(view!=='compare'||syncing)return;syncing=true;const a=$('result-video'),b=$('source-video');if(event==='seeking'||Math.abs(a.currentTime-b.currentTime)>.025){const fps=current?.media?.fps||30;const t=Math.min(Math.max(0,a.duration-.001),(Math.floor(a.currentTime*fps)+.5)/fps);if(event==='seeking'&&Math.abs(a.currentTime-t)>.001)a.currentTime=t;b.currentTime=t;}b.muted=true;if(event==='play')b.play().catch(()=>{});if(event==='pause')b.pause();syncing=false});
function show(job){current=job;const busy=['queued','running'].includes(job.status);$('create').disabled=busy;$('progress-panel').hidden=!busy;$('job-stage').textContent=job.stage;$('progress').value=job.progress;$('percent').textContent=job.progress+'%';$('project-name').textContent=job.name;$('mode-label').textContent=job.brief.mode==='adapt'?'ORIGINAL MOTION + NEW BRAND':'EDITABLE LAYER RECONSTRUCTION';$('progress-note').textContent=job.brief.mode==='hyperframes'?'Completed scenes save automatically. Retry resumes saved work.':job.brief.mode==='faithful'?'Preserving source artwork and audio. No AI analysis.':job.progress<48?'Analyzing visual detail can take several minutes.':'Frames are rendered and checked on this computer.';$('job-error').hidden=!['error','cancelled','interrupted'].includes(job.status);$('job-error-text').textContent=job.error||job.stage;const complete=job.status==='complete';$('finished').hidden=!complete;if(complete){$('finished-title').textContent=job.brief.mode==='hyperframes'?'Rebuilt video — review the match.':job.brief.mode==='faithful'?'Original video export.':job.plan?.title||'Your film is ready.';$('finished-detail').textContent=job.verification?`${job.verification.dimensions.join(' × ')} · ${job.verification.fps} fps · ${job.verification.actual_frames} frames ${job.brief.mode==='hyperframes'?'compared':job.verification.visual_check==='passed'?'checked for export integrity':'checked'}${job.timing?.cache_hit?' · Reused verified export':job.timing?.total_seconds?' · Finished in '+Math.ceil(job.timing.total_seconds)+'s':''}${job.warning?' · '+job.warning:''}`:'';$('download').href=job.files['output.mp4'];$('export').href=`/api/jobs/${job.id}/export`}
const stepStart=job.started||job.created;const elapsed=Math.max(0,Math.floor(Date.now()/1000-stepStart));$('progress-note').textContent+=` · ${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')} elapsed`;
if(job.media)$('video-meta').textContent=`${job.media.width} × ${job.media.height} / ${job.media.duration.toFixed(1)}s`;
updatePlayers();$('sheets-panel').hidden=['faithful','hyperframes'].includes(job.brief.mode)||!job.sheets?.length;
if($('sheets').dataset.job!==job.id||$('sheets').childElementCount!==job.sheets?.length){$('sheets').replaceChildren();for(const [i,url] of (job.sheets||[]).entries()){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noreferrer';const img=document.createElement('img');img.src=url;img.alt=`Reference contact sheet ${i+1} with timestamped frames`;img.loading='lazy';a.append(img);$('sheets').append(a)}$('sheets').dataset.job=job.id}
$('sheet-count').textContent=(job.sheets?.length||0)+' CONTACT SHEETS';$('edit-panel').hidden=['faithful','hyperframes'].includes(job.brief.mode)||!job.plan||busy;$('rerender').disabled=busy;$('refine').disabled=busy;
if(job.plan&&!editing&&JSON.stringify(job.plan)!==lastPlan){lastPlan=JSON.stringify(job.plan);$('plan-editor').value=JSON.stringify(job.plan,null,2);$('copy-fields').replaceChildren();for(const [i,track] of job.plan.tracks.entries()){if(track.kind!=='text')continue;const label=document.createElement('label');label.textContent=track.id;const input=document.createElement('input');input.value=track.text;input.dataset.index=i;input.maxLength=500;input.addEventListener('input',()=>{try{const p=JSON.parse($('plan-editor').value);p.tracks[i].text=input.value;$('plan-editor').value=JSON.stringify(p,null,2);editing=true}catch(e){error('Fix the project JSON before editing text.')}});label.append(input);$('copy-fields').append(label)}$('plan-summary').textContent=job.plan.summary;$('observations').replaceChildren();for(const note of job.plan.observations){const li=document.createElement('li');li.textContent=note;$('observations').append(li)}}}
$('plan-editor').addEventListener('input',()=>{editing=true});
async function refreshLibrary(){try{const jobs=await api('/api/jobs');if(jobs.length){$('history').replaceChildren();for(const job of jobs){const b=document.createElement('button');b.className='history-row';const title=document.createElement('span');title.textContent=job.name;const detail=document.createElement('small');detail.textContent=job.status+' · '+new Date(job.created*1000).toLocaleDateString();b.append(title,detail);b.addEventListener('click',()=>{editing=false;lastPlan='';fillBrief(job.brief);show(job);localStorage.setItem('frameforge-project',job.id)});$('history').append(b)}}return jobs}catch{return []}}
let cancellingId='';
$('cancel').addEventListener('click',async()=>{
  if(!current||cancellingId===current.id)return;
  cancellingId=current.id;$('cancel').disabled=true;setControl('cancel','Cancelling…','loader');
  try{await api(`/api/jobs/${current.id}/cancel`,{method:'POST'});}catch(e){cancellingId='';$('cancel').disabled=false;setControl('cancel','Cancel','stop');error(e.message);}
});
async function retry(){if(!current||$('retry').disabled)return;$('retry').disabled=true;try{error('');current=await api(`/api/jobs/${current.id}/retry`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(brief())});editing=false;show(current)}catch(e){error(e.message)}finally{$('retry').disabled=false}}
$('render-faithful').addEventListener('click',retry);$('retry').addEventListener('click',retry);$('refine').addEventListener('click',retry);
$('rerender').addEventListener('click',async()=>{try{error('');const plan=JSON.parse($('plan-editor').value);current=await api(`/api/jobs/${current.id}/render`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(plan)});editing=false;show(current)}catch(e){error(e.message)}});
$('refresh-auth').addEventListener('click',status);
$('new-project').addEventListener('click',()=>{if(submitting)return;if(current&&['running','queued'].includes(current.status)){error('Wait for the current video or cancel it before starting another.');return}current=null;editing=false;lastPlan='';localStorage.removeItem('frameforge-project');$('create-form').reset();$('import-fields').disabled=false;fileChanged();view='result';switchView('result');$('video-meta').textContent='Preview';setControl('create','Rebuild video','layers');$('create-form').setAttribute('aria-busy','false');$('logo-label').textContent='＋ Add your logo';for(const id of ['progress-panel','finished','job-error','edit-panel','sheets-panel','players','render-pending'])$(id).hidden=true;for(const v of ['source-video','result-video']){$(v).pause();$(v).removeAttribute('src');$(v).load()}$('empty-stage').hidden=false;$('project-name').textContent='Untitled project';$('create').disabled=false;error('');window.scrollTo({top:0,behavior:'smooth'})});
async function poll(){if(polling)return;if(!current){if(!$('connection-notice').hidden)await status();return;}polling=true;try{const old=current.status,id=current.id;const job=await api(`/api/jobs/${id}`);if(current?.id!==id)return;show(job);$('connection-notice').hidden=true;if(old!==job.status)await refreshLibrary()}catch{$('connection-notice').hidden=false;await status();}finally{polling=false}}
window.addEventListener('DOMContentLoaded',async()=>{
  try{
    await status();
    const jobs=await refreshLibrary();
    const requested=new URLSearchParams(location.search).get('project');
    const saved=localStorage.getItem('frameforge-project');
    const job=jobs.find(job=>job.id===requested)||jobs.find(job=>['running','queued'].includes(job.status))||jobs.find(job=>job.id===saved&&['error','interrupted','cancelled'].includes(job.status));
    if(job)await openProject(job.id);
  }catch(e){error('Could not load the project. Refresh the page to reconnect.');}
  setInterval(poll,1800);setInterval(status,30000);
});
