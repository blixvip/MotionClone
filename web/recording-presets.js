// Recording presentation only: the original video elements and playback stay shared.
(() => {
  const stage=$('comparison-stage');
  const canvas=document.createElement('div');canvas.id='recording-canvas';
  for(const child of [...stage.children])if(!['promo-controls','promo-exit'].includes(child.id))canvas.append(child);
  stage.prepend(canvas);stage.after($('promo-controls'));
  const presets=[
    {id:'studio',name:'Studio',detail:'Ice blue · widescreen',format:'landscape',layout:'split'},
    {id:'paper',name:'Editorial',detail:'Cream & ink · square',format:'square',layout:'stack'},
    {id:'signal',name:'Signal',detail:'Acid lime · short form',format:'portrait',layout:'stack'},
    {id:'cobalt',name:'Cobalt',detail:'Electric blue · spotlight',format:'landscape',layout:'spotlight'},
    {id:'peach',name:'Peach',detail:'Warm poster · short form',format:'portrait',layout:'spotlight'},
    {id:'mono',name:'Monochrome',detail:'Black & white · square',format:'square',layout:'split'},
  ];
  const formats={landscape:[1920,1080],portrait:[1080,1920],square:[1080,1080],ultrawide:[3840,1080],feed:[1080,1350]};
  const layouts=['split','stack','spotlight','wipe'];
  const compositions=[
    {id:'wide',name:'Wide duo',detail:'32:9 · Two full videos',format:'ultrawide',layout:'split'},
    {id:'square',name:'Square duo',detail:'1:1 · Stacked videos',format:'square',layout:'stack'},
    {id:'reveal',name:'Split reveal',detail:'16:9 · One shared frame',format:'landscape',layout:'wipe'},
    {id:'inset',name:'Picture in picture',detail:'16:9 · Large AI result',format:'landscape',layout:'spotlight'},
  ];
  const query=new URLSearchParams(location.search);
  let saved={};try{saved=JSON.parse(localStorage.getItem('motionclone-recording')||'{}')||{};}catch{}
  const hasURL=['look','format','layout'].some(key=>query.has(key));
  const requested=hasURL?Object.fromEntries(query):saved;
  let preset=presets.find(p=>p.id===requested.look)||presets[0];
  let format=Object.hasOwn(formats,requested.format)?requested.format:preset.format;
  let layout=layouts.includes(requested.layout)?requested.layout:preset.layout;
  let active=false,recording=false;
  const panel=document.createElement('section');panel.id='recording-options';panel.hidden=true;
  panel.setAttribute('aria-label','Recording view styles');
  panel.innerHTML=`<div class="recording-compositions" role="group" aria-label="Comparison format">${compositions.map(p=>`<button type="button" class="recording-composition" data-composition="${p.id}" aria-pressed="false"><span class="composition-art" aria-hidden="true"><i></i><i></i></span><span><strong>${p.name}</strong><small>${p.detail}</small></span></button>`).join('')}</div>
    <details id="recording-style-options"><summary>Color theme <span id="recording-style-name"></span></summary>
    <div class="recording-presets" role="group" aria-label="Recording look">${presets.map(p=>`<button type="button" class="recording-preset" data-look="${p.id}" aria-pressed="false"><span class="preset-art" aria-hidden="true"><i></i><i></i><i></i></span><strong>${p.name}</strong><small>${p.detail}</small><span class="preset-check" aria-hidden="true">✓</span></button>`).join('')}</div></details>
    <div class="recording-settings"><label>Format<select id="recording-format"><option value="landscape">16:9 · Landscape</option><option value="portrait">9:16 · Short form</option><option value="square">1:1 · Square</option><option value="ultrawide">32:9 · Wide duo</option><option value="feed">4:5 · Feed</option></select></label><label>Arrangement<select id="recording-layout"><option value="split">Side by side</option><option value="stack">Stacked comparison</option><option value="spotlight">Picture in picture</option><option value="wipe">Split reveal</option></select></label><div class="recording-link"><button id="copy-recording-link" type="button" class="secondary">Copy local view link</button><span id="recording-link-status" role="status"></span></div></div>
    <p id="recording-size" class="recording-size"></p><label id="recording-link-fallback" hidden>Copy this link<input id="recording-link-value" readonly></label>`;
  stage.before(panel);
  function state(){return {look:preset.id,format,layout};}
  function updateURL(){
    if(!active)return;
    const url=new URL(location.href);for(const [key,value] of Object.entries(state()))url.searchParams.set(key,value);
    history.replaceState({},'',url);
  }
  function fit(){
    if(!active)return;
    const [width,height]=formats[format];
    const available=recording?stage.clientHeight:Math.max(380,Math.min(850,innerHeight*.78));
    const scale=Math.min(stage.clientWidth/width,available/height);
    stage.style.setProperty('--capture-scale',String(scale));
    if(!recording)stage.style.height=`${Math.ceil(height*scale)}px`;
  }
  function apply(){
    const [width,height]=formats[format];
    stage.dataset.look=preset.id;stage.dataset.format=format;stage.dataset.layout=layout;
    stage.style.setProperty('--capture-width',`${width}px`);stage.style.setProperty('--capture-height',`${height}px`);
    $('recording-format').value=format;$('recording-layout').value=layout;
    for(const button of panel.querySelectorAll('[data-look]'))button.setAttribute('aria-pressed',String(button.dataset.look===preset.id));
    for(const button of panel.querySelectorAll('[data-composition]')){
      const composition=compositions.find(p=>p.id===button.dataset.composition);
      button.setAttribute('aria-pressed',String(composition.format===format&&composition.layout===layout));
    }
    $('recording-style-name').textContent=preset.name;
    const description=layout==='wipe'?'Original on the left, AI result on the right':layout==='spotlight'?'AI result with the original inset':'Two complete frames';
    $('recording-size').textContent=`${width} × ${height} · ${description} · original audio`;
    $('recording-link-status').textContent='';$('recording-link-fallback').hidden=true;
    try{localStorage.setItem('motionclone-recording',JSON.stringify(state()));}catch{}
    updateURL();fit();
  }
  panel.querySelectorAll('[data-look]').forEach(button=>button.addEventListener('click',()=>{
    preset=presets.find(p=>p.id===button.dataset.look);format=preset.format;layout=preset.layout;apply();
  }));
  panel.querySelectorAll('[data-composition]').forEach(button=>button.addEventListener('click',()=>{
    const composition=compositions.find(p=>p.id===button.dataset.composition);
    format=composition.format;layout=composition.layout;apply();
  }));
  $('recording-format').addEventListener('change',event=>{format=event.target.value;apply();});
  $('recording-layout').addEventListener('change',event=>{layout=event.target.value;apply();});
  $('copy-recording-link').addEventListener('click',async()=>{
    const url=new URL(location.href);url.searchParams.set('view','compare');url.searchParams.set('record','1');
    for(const [key,value] of Object.entries(state()))url.searchParams.set(key,value);
    try{await navigator.clipboard.writeText(url.href);$('recording-link-status').textContent='Copied · opens on this computer';}
    catch{$('recording-link-value').value=url.href;$('recording-link-fallback').hidden=false;$('recording-link-value').focus();$('recording-link-value').select();$('recording-link-status').textContent='Select and copy the link below.';}
  });
  window.recordingPresentation={
    settings:state,
    setActive(value){active=value;panel.hidden=!value;if(!value)stage.style.removeProperty('height');else{updateURL();fit();}},
    setRecording(value){recording=value;panel.hidden=!active||value;if(value)stage.style.removeProperty('height');fit();},
  };
  const observer=new ResizeObserver(fit);observer.observe(stage);window.addEventListener('resize',fit);
  window.addEventListener('pagehide',()=>{observer.disconnect();window.removeEventListener('resize',fit);},{once:true});
  apply();
})();
