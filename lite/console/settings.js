/* Lite keeps the console's section/nav/card shell and contributor seam. */
(function(global){
  'use strict';
  const SECTIONS=[{id:'general',label:'General',icon:'◉'},{id:'model',label:'Model',icon:'◈'},{id:'usage',label:'Usage',icon:'◷'},{id:'about',label:'About',icon:'Ti'}];
  let current='general', facts=null, generation=0;
  const contributors=new Map();
  const adapter=()=>global.__machineRoomAdapter;
  const ui=()=>global.__mrUi;
  const esc=value=>ui().escapeHtml(value);
  const row=(label,note,control)=>`<div class="setting-row"><div><strong>${esc(label)}</strong>${note?`<small>${esc(note)}</small>`:''}</div><div class="setting-control">${control}</div></div>`;
  const input=(key,value,label,area=false)=>area?`<textarea data-setting="${key}" aria-label="${esc(label)}" rows="4">${esc(value)}</textarea>`:`<input type="text" data-setting="${key}" aria-label="${esc(label)}" value="${esc(value)}">`;
  const group=(id,label,rows)=>`<section class="settings-group" data-settings-group="${id}"><p class="settings-group-label">${esc(label)}</p><div class="settings-card">${rows}</div></section>`;
  const select=(key,value,options,label)=>`<select data-setting="${key}" aria-label="${esc(label)}">${options.map(([id,name])=>`<option value="${esc(id)}"${value===id?' selected':''}>${esc(name)}</option>`).join('')}</select>`;
  function shellMarkup(active){
    return `<div class="settings-surface" data-settings-surface><nav class="settings-nav" aria-label="Settings sections"><div class="settings-nav-list" role="tablist">${SECTIONS.map(section=>`<button class="settings-nav-button${section.id===active?' is-active':''}" type="button" role="tab" aria-selected="${section.id===active}" data-settings-nav="${section.id}"><span class="settings-nav-icon" aria-hidden="true">${section.icon}</span><span>${section.label}</span></button>`).join('')}</div></nav><div class="settings-body" data-settings-body></div></div>`;
  }
  function general(){
    return group('appearance','Appearance',row('Theme','Choose how the console looks.',select('theme',facts.theme,[['dusk','Dusk'],['mist','Mist'],['ink','Ink']],'Theme'))+row('Language','The language saved for this device.',select('language',facts.language,[['en','English'],['es','Español'],['fr','Français']],'Language'))+'<div data-settings-mount="background"></div>')
      +group('assistant','Your assistant',row('Bot name','What you call your assistant.',input('botName',facts.botName,'Bot name'))+row('Personality','How Titan should answer you.',input('persona',facts.persona,'Personality',true)))
      // The microphone row is drawn only when this browser can name the microphones, which is the
      // surface's own rule: a fact the machine could not answer omits its row rather than showing an
      // empty one. voice.js owns that answer, so an absent module means no row at all.
      +group('voice','Voice',row('Voice','Choose when Titan listens.',select('voiceMode',facts.voice?.mode||'off',[['off','Off'],['push','Push to talk'],['always','Always listening']],'Voice'))
        +(global.__voice?.supportsMicChoice?row('Microphone','Which microphone Titan listens through.',`<select data-setting="micDeviceId" aria-label="Microphone"><option value="">Reading…</option></select>`):'')
        +row('Speech to text','The speech model on your device.','<span data-asr-model>Reading…</span>')+row('Text to speech','The voice model on your device.','<span data-tts-model>Reading…</span>'));
  }
  function usage(){
    return group('usage','This process',(facts.usage?.tokens==null?'':row('Tokens used','Work completed since the server started.',`<span>${esc(facts.usage.tokens)}</span>`))+(facts.usage?.minutes==null?'':row('Minutes answering','Time spent waiting for answers.',`<span>${esc(facts.usage.minutes)}</span>`)));
  }
  function about(){
    return group('about','Titanium Tiiny Bot',`<a class="lite-attribution" href="https://titanium.bot" target="_blank" rel="noopener"><img src="brand/ti-mark.svg" alt="Ti">Brought to you by Titanium Bot</a><a class="built-for" href="https://tiiny.ai" target="_blank" rel="noopener">Built for <img src="brand/tiiny-logo.svg" height="20" alt="Tiiny"></a>`+row('Full Titanium Bot','Mail, a browser, a crew and a computer.','<span>That is part of the full Titanium Bot, not this device.</span>')+row('Version','The version running on this device.',`<span>${esc(facts.version)}</span>`)+(facts.budget?row('Measured budget','Memory, first page and start time.',`<span>${esc(facts.budget.rssMb)} MB · ${esc(facts.budget.firstPaintKb)} KB · ${esc(facts.budget.coldStartMs)} ms</span>`):''));
  }
  // Where the turns are going, in words a person reads rather than a source name.
  const SOURCE_WORDS={device:'Your Tiiny',lan:'Another computer on your network',cloud:'A cloud model'};
  const modelButton=(action,label,extra='')=>`<button class="ghost-button model-button" type="button" data-model-action="${esc(action)}"${extra}>${esc(label)}</button>`;
  function deviceRows(models){
    if(!models.length)return '<p class="settings-note">Your device listed no models.</p>';
    return models.map(entry=>row(entry.name,entry.running?'Running now':'Not running',
      modelButton(entry.running?'stop':'start',entry.running?'Stop':'Start',` data-model-id="${esc(entry.id)}"`))).join('');
  }
  function endpointRows(saved,live){
    if(!saved.length)return '<p class="settings-note">No other computer is saved yet.</p>';
    return saved.map(entry=>{
      const inUse=live.endpoint===entry.baseUrl;
      const marks=` data-base-url="${esc(entry.baseUrl)}" data-model="${esc(entry.model)}"`;
      return row(entry.baseUrl,entry.model+(entry.hasKey?' · key saved':' · no key'),
        (inUse?'<span>In use</span>':modelButton('use-endpoint','Use',marks))+modelButton('forget-endpoint','Remove',marks));
    }).join('');
  }
  function fillModel(host,models){
    const live=models.live||{};
    host.querySelector('[data-live-source]').textContent=(SOURCE_WORDS[live.source]||'Your Tiiny')+' · '+(live.model||'no model yet');
    host.querySelector('[data-resolved-model]').textContent=live.resolvedModel||'Not yet available';
    host.querySelector('#device-models').insertAdjacentHTML('beforeend',(models.device||[]).filter(entry=>entry.id!=='default').map(entry=>`<option value="${esc(entry.id)}">${esc(entry.name)}</option>`).join(''));
    host.querySelector('[data-device-models]').innerHTML=deviceRows(models.device||[])+(models.note?`<p class="settings-note">${esc(models.note)}</p>`:'');
    host.querySelector('[data-endpoint-list]').innerHTML=endpointRows(models.lan||[],live);
  }
  async function model(host,ticket){
    host.innerHTML=group('model','Your device',row('In use','Where Titan sends the next message.','<span data-live-source>Reading…</span>')+row('API address','The OpenAI address shown in TiinyOS.',input('base',facts.base,'API address'))+row('Model','Use default for the first chat model your device lists.',`<input type="text" data-setting="model" aria-label="Model" value="${esc(facts.model)}" list="device-models"><datalist id="device-models"><option value="default">First chat model</option></datalist>`)+row('Resolved model','The chat model Titan will use.',`<span data-resolved-model>${esc(facts.resolvedModel||'Not yet available')}</span>`))
      +group('devicemodels','Models on your device','<div data-device-models><p class="settings-note">Reading your device…</p></div>')
      +group('preferences','Your preferences',row('Ask me before…','Things Titan should ask you about first.',input('askBefore',facts.askBefore,'Ask me before',true)))
      // The key box is the only place a credential is ever typed. It starts empty
      // every time and is never filled from the server, because the server does
      // not send it: the saved key stays in keys.json and never reaches this page.
      +group('connections','Another computer or a cloud model',row('Address','An address that speaks the OpenAI API, ending in /v1.','<input type="text" data-endpoint-base aria-label="Address" placeholder="http://192.168.1.20:11434/v1" value="">')+row('Model','The model name that computer serves.','<input type="text" data-endpoint-model aria-label="Model name" value="">')+row('Key','Type it here and nowhere else. Leave it empty for a computer that needs none, or to keep the key already saved.','<input type="password" data-endpoint-key aria-label="Key" autocomplete="off" value="">')+row('Save and use','Your next message goes there. A message already being answered finishes where it started.',modelButton('save-endpoint','Save and use'))+'<div data-endpoint-list></div>'+row('Use this device','Send messages back to your Tiiny.',modelButton('use-device','Use this device')));
    try {
      const models=await adapter().getModels();if(ticket!==generation)return;
      fillModel(host,models);
    }catch(error){
      if(ticket!==generation)return;
      host.querySelector('[data-device-models]').innerHTML='<p class="settings-note">Your device is not answering, so its models cannot be listed.</p>';
      const status=document.querySelector('[data-settings-status]');if(status)status.textContent='Device models are unavailable. You can still edit the API address and model.';
    }
  }
  async function modelPress(button){
    const status=document.querySelector('[data-settings-status]');
    const host=button.closest('[data-settings-section]');
    const name=button.dataset.modelAction;
    let body={action:name,id:button.dataset.modelId};
    if(name==='save-endpoint'){
      const key=host.querySelector('[data-endpoint-key]').value;
      body={action:'use',baseUrl:host.querySelector('[data-endpoint-base]').value.trim(),model:host.querySelector('[data-endpoint-model]').value.trim()};
      if(key)body.apiKey=key;
    }else if(name==='use-device')body={action:'use',source:'device'};
    else if(name==='use-endpoint')body={action:'use',baseUrl:button.dataset.baseUrl,model:button.dataset.model};
    else if(name==='forget-endpoint')body={action:'forget',baseUrl:button.dataset.baseUrl};
    button.disabled=true;
    if(status)status.textContent='Working…';
    try{
      const answer=await adapter().setModel(body);
      facts=await adapter().getSettings();
      // A saved address that did not take is TIINY_BASE or a command-line setting
      // winning, which is the documented order. Saying "Saved" and leaving the
      // page pointing somewhere else is the one answer a person cannot act on.
      const live=answer?.live||{};
      const asked=body.baseUrl?live.endpoint===body.baseUrl:body.source!=='device'||live.source==='device';
      if(status)status.textContent=asked?'Saved':'Saved, but TIINY_BASE or a command-line setting still sends messages somewhere else.';
      await model(host,generation);
    }catch(error){
      button.disabled=false;
      if(status)status.textContent=error.message;else ui().showToast(error.message);
    }
  }
  // A browser names a microphone only after it has been allowed to hear one, so before that every
  // label is an empty string. Numbering them is the honest fallback: the person can still tell two
  // apart and pick the other one, and the names arrive on their own once they have talked once.
  async function fillMicrophones(host,ticket){
    const field=host.querySelector('[data-setting="micDeviceId"]');
    if(!field)return;
    let inputs=[];
    // A microphone with no id of its own IS the usual one, so it is not offered twice. A browser
    // that has never been allowed to listen reports exactly one of those and nothing else.
    try{inputs=(await global.navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='audioinput'&&d.deviceId&&d.deviceId!=='default');}catch{inputs=[];}
    if(ticket!==generation)return;
    const chosen=facts.micDeviceId||'';
    const options=[['','This device’s usual microphone'],...inputs.map((d,index)=>[d.deviceId,d.label||`Microphone ${index+1}`])];
    field.innerHTML=options.map(([id,name])=>`<option value="${esc(id)}"${chosen===id?' selected':''}>${esc(name)}</option>`).join('');
  }
  async function open(id='general'){
    const ticket=++generation;
    current=SECTIONS.some(s=>s.id===id)?id:'general';
    ui().openPanel('Your device','Settings',shellMarkup(current));
    document.getElementById('panel-dialog').classList.add('is-settings');
    const body=document.querySelector('[data-settings-body]');body.textContent='Reading your settings…';
    try{
      facts=await adapter().getSettings();if(ticket!==generation)return;
      body.innerHTML=`<header class="settings-head"><h2>${SECTIONS.find(s=>s.id===current).label}</h2></header><div class="settings-rows" data-settings-section="${current}"></div><p role="status" data-settings-status></p>`;
      const host=body.querySelector('[data-settings-section]');
      if(current==='model')await model(host,ticket);
      else host.innerHTML=current==='general'?general():current==='usage'?usage():about();
      if(current==='general'){
        try {
          const response=await fetch('/api/voice/settings');
          const voice=await response.json();if(ticket!==generation)return;
          if(!response.ok)throw new Error(voice.error);
          host.querySelector('[data-asr-model]').textContent=voice.asrModel||'No speech model loaded';
          host.querySelector('[data-tts-model]').textContent=voice.ttsModel||'No voice model loaded';
        }catch{if(ticket===generation){host.querySelector('[data-asr-model]').textContent='Unavailable';host.querySelector('[data-tts-model]').textContent='Unavailable';}}
        await fillMicrophones(host,ticket);
      }
      for(const entry of contributors.values())if(entry.section===current){host.insertAdjacentHTML('beforeend',entry.markup());entry.fill?.(host);}
      document.dispatchEvent(new CustomEvent('titanbot:settings-section',{detail:{id:current,host}}));
    }catch(error){if(ticket===generation)body.textContent=error.message;}
  }
  function openSubview(view){
    ++generation;current=view.section||'general';
    const body=document.querySelector('[data-settings-body]');if(!body)return;
    body.innerHTML=`<button class="ghost-button" type="button" data-settings-nav="${esc(current)}">Back</button><header class="settings-head"><h2>${esc(view.title)}</h2></header>${view.markup()}`;
    view.fill?.(body);
  }
  document.addEventListener('click',event=>{const button=event.target.closest?.('[data-settings-nav]');if(button)open(button.dataset.settingsNav);});
  document.addEventListener('click',event=>{const button=event.target.closest?.('[data-model-action]');if(button&&!button.disabled)modelPress(button);});
  document.addEventListener('change',async event=>{
    const field=event.target;if(!field.matches?.('[data-setting]'))return;
    const status=document.querySelector('[data-settings-status]');field.disabled=true;
    try{
      const name=field.dataset.setting;
      const changes=name==='voiceMode'?{voice:{mode:field.value}}:name==='base'||name==='model'?{base:document.querySelector('[data-setting="base"]').value,model:document.querySelector('[data-setting="model"]').value}:{[name]:field.value};
      facts=await adapter().saveSettings(changes);
      if(name==='voiceMode'){
        global.__voice?.stop();
        if(global.__voice){global.__voice._state.settings=facts.voice;global.__voice._adoptTalkMode(facts.voice.mode);}
      }
      // The saved choice has to reach the module that opens the stream, not only the file. Without
      // this the next press would still open the usual microphone until the page was reloaded.
      if(name==='micDeviceId')global.__voice?.setMicDeviceId?.(facts.micDeviceId??field.value);
      if((name==='base'||name==='model')&&current==='model')await model(document.querySelector('[data-settings-section]'),generation);
      if(name==='theme'){document.documentElement.dataset.theme=facts.theme;try{localStorage.setItem('machineRoom.theme',facts.theme);}catch{}}
      if(status)status.textContent=Object.keys(changes).some(key=>(key==='base'||key==='model')&&changes[key]!==facts[key])?'Saved; command-line or environment settings still override this value.':'Saved';
    }catch(error){if(status)status.textContent=error.message;else ui().showToast(error.message);}
    finally{field.disabled=false;}
  });
  global.__mrSettings={open,openSubview,register(entry){if(!entry?.id||typeof entry.markup!=='function')return false;contributors.set(entry.id,entry);return true;}};
})(window);
