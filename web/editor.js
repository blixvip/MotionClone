(() => {
  'use strict';
  const $=id=>document.getElementById(id), video=$('preview');
  const hosted=document.body.dataset.hosted==='true', studio=hosted?'/studio':'/?workspace=1';
  $('connect').href=studio+(hosted?'?':'&')+'settings=1';
  let token='', references=[], segments=[], selected=null, connected=false, busy=false, dirty=false, initialized=false;
  let previewEnd=null, sequenceIndex=-1, importing=false, saving=false, submitting=false, initializing=false;
  const seconds=n=>`${Number(n).toFixed(2)}s`;
  const notice=text=>{$('notice').textContent=text;$('notice').hidden=!text;};
  async function api(path,options={}) {
    const response=await fetch(path,{...options,headers:{'X-Frameforge-Token':token,...options.headers}});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:response.status===422?'Check segment times and text lengths, then try again.':'Could not complete this request. Try again.');
    return data;
  }
  const json=body=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  function edit(){return {brand:$('brand').value,instructions:$('instructions').value,format:$('format').value,keep_audio:$('keep-audio').checked,segments};}
  function changed(){dirty=true;$('save-status').textContent='Unsaved changes';updateButtons();}
  function updateButtons(){
    $('save').disabled=!initialized||!dirty||busy||saving||submitting;
    $('save').textContent=saving?'Saving…':'Save sequence';
    $('generate').disabled=!initialized||!segments.length||!connected||busy||saving||submitting;
    $('generate').textContent=submitting?'Starting generation…':'Generate my video ↗';
    for(const id of ['brand','instructions','format','keep-audio','reference-url'])$(id).disabled=!initialized;
    $('import-url').disabled=$('reference-file').disabled=!initialized||importing;
    $('refresh').disabled=initializing;
    $('play-sequence').disabled=!segments.length||busy;
    $('generate-hint').textContent=busy?'A video is processing. You can keep arranging your next sequence.':!connected?'Connect your own ChatGPT/Codex account to generate.':!segments.length?'Add a segment to begin.':'Uses your AI account allowance. No AI credits are included.';
  }
  async function refresh(){
    const status=await api('/api/status');token=status.token;connected=!!status.chatgpt;busy=!!status.active;
    $('connection-title').textContent=connected?'Your AI account is connected':'Connect your own AI account to generate';
    $('connection-dot').classList.toggle('connected',connected);$('connect').textContent=connected?'Account settings ↗':'Connect AI ↗';
    updateButtons();return status;
  }
  async function loadReferences(){
    const jobs=await api('/api/library');references=jobs.filter(j=>j.files?.['source.mp4']&&j.media&&!['running','queued'].includes(j.status));
    $('reference-count').textContent=references.length;$('reference-list').replaceChildren();
    if(!references.length){const p=document.createElement('p');p.className='empty-copy';p.textContent='No references yet. Upload a video or paste a public X, YouTube, or Vimeo link.';$('reference-list').append(p);}
    for(const job of references){
      const button=document.createElement('button');button.type='button';button.className='reference-item';button.dataset.project=job.id;button.setAttribute('aria-pressed',String(selected?.id===job.id));
      const img=document.createElement('img');img.src=job.files['thumbnail.jpg']||`/media/${job.id}/thumbnail.jpg`;img.alt='';img.loading='lazy';
      const span=document.createElement('span');span.textContent=job.name||'Untitled reference';const small=document.createElement('small');small.textContent=seconds(job.media.duration);span.append(small);button.append(img,span);
      button.addEventListener('click',()=>select(job));$('reference-list').append(button);
    }
    return jobs;
  }
  function select(job,start=0,end=Math.min(5,job.media.duration)){
    video.pause();sequenceIndex=-1;previewEnd=null;selected=job;
    $('play-sequence').textContent='Play sequence';
    video.src=job.files['source.mp4'];video.hidden=false;$('preview-empty').hidden=true;$('trim-controls').disabled=false;
    $('reference-name').textContent=job.name||'Reference';
    for(const id of ['trim-start','trim-end','trim-start-range','trim-end-range'])$(id).max=Math.min(120,job.media.duration);
    setRange(start,end);video.currentTime=start;
    for(const button of $('reference-list').querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.project===job.id));
  }
  function setRange(start,end){
    $('trim-start').value=$('trim-start-range').value=Number(start).toFixed(2);
    $('trim-end').value=$('trim-end-range').value=Number(end).toFixed(2);
    const valid=Number.isFinite(start)&&Number.isFinite(end)&&start>=0&&end<=Math.min(120,selected.media.duration)+.001&&end-start>=.25;
    $('selected-duration').textContent=valid?`${seconds(end-start)} selected`:'Choose a valid range';
    $('add-segment').disabled=$('preview-segment').disabled=!valid;
    $('trim-start').setAttribute('aria-invalid',String(!valid));$('trim-end').setAttribute('aria-invalid',String(!valid));
  }
  function range(){
    const start=Number($('trim-start').value),end=Number($('trim-end').value);
    if(!selected||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>Math.min(120,selected.media.duration)+.001||end-start<.25)throw new Error('Choose at least 0.25 seconds, within the first 120 seconds of the reference.');
    return {start,end};
  }
  for(const part of ['start','end']){
    for(const suffix of ['','-range'])$(`trim-${part}${suffix}`).addEventListener('input',()=>{
      const start=Number(part==='start'?$(`trim-start${suffix}`).value:$('trim-start').value);
      const end=Number(part==='end'?$(`trim-end${suffix}`).value:$('trim-end').value);setRange(start,end);
      stopSequence();if(part==='start')video.currentTime=start;
    });
  }
  $('mark-in').onclick=()=>setRange(video.currentTime,Number($('trim-end').value));
  $('mark-out').onclick=()=>setRange(Number($('trim-start').value),video.currentTime);
  async function playRange(start,end){previewEnd=end;video.currentTime=start;try{await video.play();}catch{notice('Playback could not start. Press play on the video and try again.');}}
  $('preview-segment').onclick=()=>{try{notice('');const {start,end}=range();stopSequence();void playRange(start,end);}catch(e){notice(e.message);}};
  $('add-segment').onclick=()=>{
    try{notice('');const {start,end}=range();if(segments.length>=12)throw new Error('Use up to 12 segments.');
      if(segments.reduce((sum,s)=>sum+s.end-s.start,0)+end-start>120)throw new Error('Keep the sequence within 120 seconds.');
      segments.push({project:selected.id,start,end,notes:''});renderSegments();changed();
    }catch(e){notice(e.message);}
  };
  function renderSegments(){
    $('segments').replaceChildren();$('segment-count').textContent=`${segments.length} / 12`;
    $('total-duration').textContent=`${seconds(segments.reduce((sum,s)=>sum+s.end-s.start,0))} / 120s`;
    if(!segments.length){const li=document.createElement('li');li.className='sequence-empty';li.textContent='Your first cut starts here. Add a segment from a reference above.';$('segments').append(li);}
    segments.forEach((segment,index)=>{
      const job=references.find(j=>j.id===segment.project),li=document.createElement('li');li.className='segment';
      const title=document.createElement('strong');title.className='segment-title';title.textContent=`${index+1}. ${job?.name||'Unavailable reference'}`;
      const times=document.createElement('p');times.className='segment-range';times.textContent=`${seconds(segment.start)} → ${seconds(segment.end)} · ${seconds(segment.end-segment.start)}`;
      const label=document.createElement('label');label.textContent='Direction for this segment';const notes=document.createElement('input');notes.maxLength=200;notes.placeholder='e.g. Use my product name';notes.value=segment.notes;notes.addEventListener('input',()=>{segment.notes=notes.value;changed();});label.append(notes);
      const actions=document.createElement('div');actions.className='segment-actions';
      function action(text,name,fn,disabled=false){const button=document.createElement('button');button.type='button';button.textContent=text;button.setAttribute('aria-label',`${name} segment ${index+1}`);button.disabled=disabled;button.onclick=fn;actions.append(button);}
      const swap=offset=>{stopSequence();[segments[index],segments[index+offset]]=[segments[index+offset],segments[index]];renderSegments();changed();};
      action('←','Move earlier',()=>swap(-1),index===0);action('→','Move later',()=>swap(1),index===segments.length-1);
      action('▶','Preview',()=>{if(job){select(job,segment.start,segment.end);void playRange(segment.start,segment.end);}},!job);
      action('×','Remove',()=>{stopSequence();segments.splice(index,1);renderSegments();changed();});
      li.append(title,times,label,actions);$('segments').append(li);
    });updateButtons();
  }
  function playSequence(index){
    const segment=segments[index];if(!segment){stopSequence();return;}
    const job=references.find(j=>j.id===segment.project);if(!job){notice('A reference is unavailable. Remove it from the sequence.');stopSequence();return;}
    select(job,segment.start,segment.end);sequenceIndex=index;$('play-sequence').textContent='Stop sequence';void playRange(segment.start,segment.end);
  }
  function stopSequence(){sequenceIndex=-1;previewEnd=null;video.pause();$('play-sequence').textContent='Play sequence';}
  $('play-sequence').onclick=()=>{if(sequenceIndex>=0)stopSequence();else playSequence(0);};
  function advance(){if(sequenceIndex>=0)playSequence(sequenceIndex+1);else{video.pause();previewEnd=null;}}
  video.addEventListener('timeupdate',()=>{$('preview-time').textContent=seconds(video.currentTime);if(previewEnd!==null&&video.currentTime>=previewEnd-.025)advance();});
  video.addEventListener('ended',()=>{if(previewEnd!==null)advance();});
  video.addEventListener('error',()=>notice('This reference could not play. Refresh references or import the file again.'));
  for(const id of ['brand','instructions','format','keep-audio'])$(id).addEventListener('input',changed);
  async function save(snapshot=edit()){
    if(saving)throw new Error('Wait for the sequence to finish saving.');
    saving=true;updateButtons();
    try{const saved=JSON.stringify(snapshot);await api('/api/editor/draft',json(snapshot));dirty=JSON.stringify(edit())!==saved;$('save-status').textContent=dirty?'Unsaved changes':'Sequence saved';}
    finally{saving=false;updateButtons();}
  }
  $('save').onclick=async()=>{try{notice('');await save();}catch(e){notice(e.message);}};
  $('refresh').onclick=async()=>{try{notice('');if(!initialized){await initialize();return;}await refresh();await loadReferences();renderSegments();}catch(e){notice(e.message);}};
  async function waitJob(id,element){
    while(true){const job=await api(`/api/jobs/${id}`);element.textContent=`${job.stage} · ${Math.round(job.progress||0)}%`;
      if(!['queued','running'].includes(job.status)){if(job.status==='error'||job.status==='cancelled'||job.status==='interrupted')throw new Error(job.error||job.stage);return job;}
      await new Promise(resolve=>setTimeout(resolve,1800));
    }
  }
  async function importReference(file){
    if(importing)return;
    const url=$('reference-url').value.trim();if(!file&&!url){notice('Choose a file or paste a public video URL.');return;}
    if(file&&file.size>(hosted?25:250)*1048576){notice(`Upload a video under ${hosted?25:250} MB.`);return;}
    if(!file&&!url.startsWith('https://')){notice('Use a public HTTPS video link.');return;}
    importing=true;$('import-url').disabled=true;$('reference-file').disabled=true;notice('');
    try{await refresh();const body=new FormData();if(file)body.append('video',file);else body.append('url',url);
      const job=await api('/api/editor/references',{method:'POST',body});busy=true;updateButtons();await waitJob(job.id,$('import-status'));
      await loadReferences();const reference=references.find(j=>j.id===job.id);if(reference)select(reference);
      $('reference-url').value='';$('reference-file').value='';$('import-status').textContent='Reference ready. Select a segment to add.';
    }catch(e){notice(e.message);$('import-status').textContent='Import did not finish. Retry or choose another reference.';}
    finally{importing=false;$('import-url').disabled=false;$('reference-file').disabled=false;await refresh().catch(()=>{});}
  }
  $('import-form').onsubmit=e=>{e.preventDefault();void importReference(null);};
  $('reference-file').onchange=()=>{if($('reference-file').files[0])void importReference($('reference-file').files[0]);};
  $('generate').onclick=async()=>{
    if(submitting||saving||busy||!initialized)return;
    submitting=true;updateButtons();const snapshot=JSON.parse(JSON.stringify(edit()));
    try{notice('');await save(snapshot);const status=await refresh();if(!status.chatgpt)throw new Error('Connect your own ChatGPT/Codex account first.');
      busy=true;updateButtons();const job=await api('/api/editor/generate',json(snapshot));
      submitting=false;updateButtons();
      const result=$('open-result');result.href=hosted?`/studio?project=${job.id}`:`/?project=${job.id}`;result.textContent='View generation progress ↗';result.hidden=false;
      await waitJob(job.id,$('generate-hint'));result.textContent='Open generated video ↗';
    }catch(e){notice(e.message);}finally{submitting=false;await refresh().catch(()=>{});updateButtons();}
  };
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refresh().catch(e=>notice(e.message));});
  async function initialize(){
    if(initializing)return;
    initializing=true;updateButtons();
    try{await refresh();await loadReferences();const draft=await api('/api/editor/draft');
    segments=draft.segments;$('brand').value=draft.brand;$('instructions').value=draft.instructions;$('format').value=draft.format;$('keep-audio').checked=draft.keep_audio;
    initialized=true;$('save-status').textContent=segments.length?'Saved sequence loaded':'No unsaved changes';renderSegments();
    }finally{initializing=false;updateButtons();}
  }
  updateButtons();
  initialize().catch(e=>{notice(e.message);$('save-status').textContent='Could not load sequence. Use Refresh to retry.';});
})();
