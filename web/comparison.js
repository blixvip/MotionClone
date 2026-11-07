// The existing project videos remain the source of truth, including their sync events.
(() => {
  const stage=$('comparison-stage'),result=$('result-video'),source=$('source-video');
  const initial=new URLSearchParams(location.search);
  let recording=false,active=false,frame=0,restoreFocus=null,playbackRequest=0;
  const fmt=t=>`${Math.floor((t||0)/60)}:${String(Math.floor((t||0)%60)).padStart(2,'0')}`;
  function paint(){
    const playing=!result.paused&&!result.ended;
    if($('promo-play').dataset.playing!==String(playing)){
      setControl('promo-play',playing?'Pause':'Play',playing?'pause':'play');
      $('promo-play').dataset.playing=String(playing);
    }
    $('promo-play').setAttribute('aria-label',playing?'Pause both videos':'Play both videos');
    $('promo-time').textContent=`${fmt(result.currentTime)} / ${fmt(result.duration)}`;
    if(Number.isFinite(result.duration))$('promo-seek').max=result.duration;
    $('promo-seek').value=result.currentTime||0;
  }
  async function play(){
    const request=++playbackRequest;
    $('promo-error').hidden=true;
    source.muted=true;source.currentTime=result.currentTime;
    try{await Promise.all([result.play(),source.play()]);}
    catch(e){if(request!==playbackRequest||e.name==='AbortError')return;result.pause();source.pause();$('promo-error').textContent='Playback could not start. Press Play to try again.';$('promo-error').hidden=false;}
    paint();
  }
  function pause(){playbackRequest++;result.pause();source.pause();paint();}
  function restart(){result.currentTime=0;source.currentTime=0;return play();}
  async function exitRecording(){
    recording=false;document.body.classList.remove('recording-view');
    window.recordingPresentation?.setRecording(false);
    if(document.fullscreenElement===stage)await document.exitFullscreen().catch(()=>{});
    const url=new URL(location.href);url.searchParams.delete('record');history.replaceState({},'',url);
    restoreFocus?.focus();
  }
  async function enterRecording(fullscreen=true){
    if(!active)return;
    restoreFocus=document.activeElement;recording=true;document.body.classList.add('recording-view');
    window.recordingPresentation?.setRecording(true);
    stage.tabIndex=-1;stage.focus({preventScroll:true});
    const url=new URL(location.href);url.searchParams.set('view','compare');url.searchParams.set('record','1');history.replaceState({},'',url);
    if(fullscreen&&stage.requestFullscreen)await stage.requestFullscreen().catch(()=>{});
    if(initial.get('capture')==='1')pause();else await restart();
  }
  window.syncComparison=(job,mode)=>{
    const available=!!job?.files?.['source.mp4']&&!!job?.files?.['output.mp4'];
    const next=available&&mode==='compare';
    $('present-comparison').hidden=!available;
    for(const id of ['promo-header','promo-labels','promo-controls','promo-identities','promo-hint'])$(id).hidden=!next;
    stage.classList.toggle('promo-active',next);
    if(job?.media)stage.style.setProperty('--video-ratio',`${job.media.width}/${job.media.height}`);
    $('promo-result-label').textContent=['hyperframes','rebuild'].includes(job?.brief?.mode)?'AI generated':'Exported';
    stage.querySelector('.rebuilt-label').textContent=$('promo-result-label').textContent;
    result.controls=!next;
    if(active!==next){pause();source.muted=true;result.muted=true;$('promo-sound').setAttribute('aria-pressed','false');$('promo-sound').setAttribute('aria-label','Unmute audio');}
    active=next;
    window.recordingPresentation?.setActive(next);
    if(!active&&recording)exitRecording();
    paint();
  };
  const priorSwitch=switchView;
  switchView=next=>{priorSwitch(next);const url=new URL(location.href);if(next==='compare')url.searchParams.set('view','compare');else url.searchParams.delete('view');history.replaceState({},'',url);};
  const priorOpen=openProject;
  openProject=async id=>{
    await priorOpen(id);
    if(initial.get('project')===id&&initial.get('view')==='compare'){
      initial.delete('view');switchView('compare');
      if(initial.get('record')==='1')enterRecording(false);
    }
  };
  $('promo-play').addEventListener('click',()=>result.paused?play():pause());
  $('promo-restart').addEventListener('click',restart);
  $('promo-seek').addEventListener('input',()=>{const t=Number($('promo-seek').value);result.currentTime=t;source.currentTime=t;paint();});
  $('promo-sound').addEventListener('click',()=>{result.muted=!result.muted;source.muted=true;$('promo-sound').setAttribute('aria-pressed',String(!result.muted));$('promo-sound').setAttribute('aria-label',result.muted?'Unmute audio':'Mute audio');});
  $('promo-speed').addEventListener('change',()=>{result.playbackRate=source.playbackRate=Number($('promo-speed').value);});
  $('present-comparison').addEventListener('click',()=>{switchView('compare');enterRecording();});
  $('promo-exit').addEventListener('click',exitRecording);
  document.addEventListener('fullscreenchange',()=>{if(recording&&!document.fullscreenElement)exitRecording();});
  document.addEventListener('keydown',event=>{
    if(recording&&event.key==='Tab'){
      const items=[...stage.querySelectorAll('a[href],button')].filter(el=>el.getClientRects().length);
      const first=items[0],last=items.at(-1);
      if(event.shiftKey&&(document.activeElement===first||document.activeElement===stage)){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
    if(!recording||event.ctrlKey||event.metaKey||event.altKey||event.target.closest('input,select,textarea'))return;
    if(event.key==='Escape'){event.preventDefault();exitRecording();}
    if(event.code==='Space'&&!event.target.closest('button,a')){event.preventDefault();result.paused?play():pause();}
    if(event.key.toLowerCase()==='r'){event.preventDefault();restart();}
  });
  result.addEventListener('ended',()=>{if(active)restart();});
  for(const event of ['play','pause','loadedmetadata','seeked'])result.addEventListener(event,paint);
  for(const video of [result,source])video.addEventListener('error',()=>{if(active){pause();$('promo-error').textContent='A video could not load. Return to the project and retry.';$('promo-error').hidden=false;}});
  function tick(){
    if(active&&!document.hidden&&!result.paused){if(Math.abs(result.currentTime-source.currentTime)>.12&&!source.seeking)source.currentTime=result.currentTime;if(source.paused&&source.readyState>=2)source.play().catch(()=>{});paint();}
    frame=requestAnimationFrame(tick);
  }
  frame=requestAnimationFrame(tick);
  window.addEventListener('pagehide',()=>cancelAnimationFrame(frame),{once:true});
})();
