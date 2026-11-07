// Export progress belongs to its project and survives a refresh in this tab.
(() => {
  const button=$('download');
  const message=document.createElement('p');message.id='recording-export-status';message.setAttribute('role','status');message.hidden=true;
  $('finished').append(message);
  const raw=document.createElement('a');raw.id='download-rebuild-only';raw.className='secondary';raw.textContent='Rebuilt video only';raw.setAttribute('download','motionclone-rebuilt.mp4');
  $('export-details').append(raw);
  const entries=new Map(),prefix='motionclone-export:';
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const endpoint=entry=>`/api/jobs/${entry.project}/recording`;
  const downloadURL=entry=>`${endpoint(entry)}/${entry.key}/download`;
  function persist(entry){
    const {project,settings,key,status,stage,progress,error,started}=entry;
    try{sessionStorage.setItem(prefix+project,JSON.stringify({project,settings,key,status,stage,progress,error,started}));}catch{}
  }
  function restore(project){
    if(entries.has(project))return entries.get(project);
    try{
      const entry=JSON.parse(sessionStorage.getItem(prefix+project));
      if(!entry||entry.project!==project||Date.now()-entry.started>86400000)return null;
      if(!['queued','running','complete','error'].includes(entry.status))return null;
      if(entry.key&&!/^[a-f0-9]{20}$/.test(entry.key))return null;
      if(!['studio','paper','signal','cobalt','peach','mono'].includes(entry.settings?.look)
        ||!['landscape','portrait','square','ultrawide','feed'].includes(entry.settings?.format)
        ||!['split','stack','spotlight','wipe'].includes(entry.settings?.layout))return null;
      entries.set(project,entry);return entry;
    }catch{return null;}
  }
  function display(entry){
    if(entry&&current?.id!==entry.project)return;
    const busy=entry&&['queued','running'].includes(entry.status);
    button.toggleAttribute('aria-disabled',!!busy);button.toggleAttribute('aria-busy',!!busy);
    if(busy){button.setAttribute('aria-disabled','true');button.setAttribute('aria-busy','true');}
    const label=busy?`Saving MP4 · ${Math.round(entry.progress||0)}%`:'Save comparison MP4';
    if(button.textContent!==label)setControl(button,label,busy?'loader':'download');
    message.hidden=!entry;
    message.classList.toggle('export-error',entry?.status==='error');
    if(!entry){message.replaceChildren();return;}
    if(entry.status==='complete'){
      message.textContent='Recording MP4 ready. ';
      const link=document.createElement('a');link.href=downloadURL(entry);link.download='';link.textContent='Save MP4 again';message.append(link);
    }else if(entry.status==='error'){
      message.textContent=(entry.error||'Export interrupted.')+' Click Save comparison MP4 to retry.';
    }else message.textContent=`${entry.stage||'Preparing recording'} · ${Math.round(entry.progress||0)}% · ${entry.settings.look}, ${entry.settings.format}. You can refresh; export progress is saved.`;
  }
  function update(entry,values){Object.assign(entry,values);persist(entry);display(entry);}
  async function request(entry,path,options={},head=false){
    for(let attempt=0;attempt<7;attempt++){
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
      try{
        if(!head)return await api(path,{...options,signal:controller.signal});
        const response=await fetch(path,{method:'HEAD',signal:controller.signal});
        if(!response.ok){const error=new Error('The MP4 is unavailable. Please retry the export.');error.status=response.status;throw error;}
        if(!response.headers.get('Content-Type')?.includes('video/mp4'))throw new Error('The download did not return an MP4. Please retry the export.');
        return response;
      }catch(error){
        const transient=!error.status||[408,429,502,503,504].includes(error.status)||error.status>=500;
        if(error.status===403&&attempt===0){await status();continue;}
        if(!transient||attempt===6)throw error;
        update(entry,{stage:'Connection interrupted — reconnecting automatically'});
        await pause(Math.min(8000,1000*2**attempt));
      }finally{clearTimeout(timer);}
    }
  }
  async function run(entry){
    if(entry.polling)return;
    entry.polling=true;
    try{
      let task;
      if(entry.key){
        try{task=await request(entry,`${endpoint(entry)}/${entry.key}`);}
        catch(error){if(error.status!==404)throw error;}
      }
      if(!task)task=await request(entry,endpoint(entry),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(entry.settings)});
      while(true){
        update(entry,{key:task.key,status:task.status,stage:task.stage,progress:task.progress,error:task.error});
        if(!['queued','running'].includes(task.status))break;
        if(Date.now()-entry.started>3900000)throw new Error('Export is taking longer than expected. Your saved video is still available.');
        await pause(1000);
        try{task=await request(entry,`${endpoint(entry)}/${entry.key}`);}
        catch(error){
          if(error.status!==404)throw error;
          task=await request(entry,endpoint(entry),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(entry.settings)});
        }
      }
      if(task.status!=='complete')throw new Error(task.error||'Recording export failed.');
      // Validate before handing the file to the browser's streaming downloader.
      await request(entry,downloadURL(entry),{},true);
      update(entry,{status:'complete',progress:100});
      if(current?.id===entry.project){
        const link=document.createElement('a');link.href=downloadURL(entry);link.download='';document.body.append(link);link.click();link.remove();
      }
    }catch(error){update(entry,{status:'error',error:error.name==='AbortError'?'The connection timed out.':error.message});}
    finally{entry.polling=false;display(entry);}
  }
  const savedShow=show;
  show=job=>{
    savedShow(job);
    if(job.files?.['output.mp4'])raw.href=job.files['output.mp4'];else raw.removeAttribute('href');
    const entry=restore(job.id);display(entry);
    if(entry&&['queued','running'].includes(entry.status))void run(entry);
  };
  button.addEventListener('click',event=>{
    event.preventDefault();if(!current||current.status!=='complete')return;
    if(entries.get(current.id)?.polling)return;
    const entry={project:current.id,settings:window.recordingPresentation.settings(),key:null,status:'queued',stage:'Preparing recording',progress:0,started:Date.now()};
    entries.set(entry.project,entry);persist(entry);display(entry);void run(entry);
  });
})();
