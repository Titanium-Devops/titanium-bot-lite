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
      +group('voice','Voice',row('Microphone','Voice conversations are not connected yet.','<span>Not connected</span>')+row('Talk mode','Keep using the message box for now.','<span>Off</span>'));
  }
  function usage(){
    return group('usage','This process',(facts.usage?.tokens==null?'':row('Tokens used','Work completed since the server started.',`<span>${esc(facts.usage.tokens)}</span>`))+(facts.usage?.minutes==null?'':row('Minutes answering','Time spent waiting for answers.',`<span>${esc(facts.usage.minutes)}</span>`)));
  }
  function about(){
    return group('about','Titanium Tiiny Bot',`<a class="lite-attribution" href="https://titanium.bot" target="_blank" rel="noopener"><img src="brand/ti-mark.svg" alt="Ti">Brought to you by Titanium Bot</a><a class="built-for" href="https://tiiny.ai" target="_blank" rel="noopener">Built for <img src="brand/tiiny-logo.svg" height="20" alt="Tiiny"></a>`+row('Version','The version running on this device.',`<span>${esc(facts.version)}</span>`)+(facts.budget?row('Measured budget','Memory, first page and start time.',`<span>${esc(facts.budget.rssMb)} MB · ${esc(facts.budget.firstPaintKb)} KB · ${esc(facts.budget.coldStartMs)} ms</span>`):''));
  }
  async function model(host,ticket){
    host.innerHTML=group('model','Your device',row('API address','The OpenAI address shown in TiinyOS.',input('base',facts.base,'API address'))+row('Model','Use default for the first chat model your device lists.',`<input type="text" data-setting="model" aria-label="Model" value="${esc(facts.model)}" list="device-models"><datalist id="device-models"><option value="default">First chat model</option></datalist>`)+row('Resolved model','The chat model Titan will use.',`<span data-resolved-model>${esc(facts.resolvedModel||'Not yet available')}</span>`)+row('Model controls','Start and stop models in your device settings.','<span>On your device</span>'))
      +group('preferences','Your preferences',row('Ask me before…','Things Titan should ask you about first.',input('askBefore',facts.askBefore,'Ask me before',true)))
      +group('connections','Other computers','<p>Connecting another computer or a cloud model is not available yet.</p>');
    try {
      const models=await adapter().getModels();if(ticket!==generation)return;
      host.querySelector('[data-resolved-model]').textContent=models.live?.resolvedModel||'Not yet available';
      host.querySelector('#device-models').insertAdjacentHTML('beforeend',models.device.filter(m=>m.id!=='default').map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join(''));
    }catch(error){
      if(ticket===generation){const status=document.querySelector('[data-settings-status]');if(status)status.textContent='Device models are unavailable. You can still edit the API address and model.';}
    }
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
  document.addEventListener('change',async event=>{
    const field=event.target;if(!field.matches?.('[data-setting]'))return;
    const status=document.querySelector('[data-settings-status]');field.disabled=true;
    try{
      const name=field.dataset.setting;
      const changes=name==='base'||name==='model'?{base:document.querySelector('[data-setting="base"]').value,model:document.querySelector('[data-setting="model"]').value}:{[name]:field.value};
      facts=await adapter().saveSettings(changes);
      if((name==='base'||name==='model')&&current==='model')await model(document.querySelector('[data-settings-section]'),generation);
      if(name==='theme'){document.documentElement.dataset.theme=facts.theme;try{localStorage.setItem('machineRoom.theme',facts.theme);}catch{}}
      if(status)status.textContent=Object.keys(changes).some(key=>(key==='base'||key==='model')&&changes[key]!==facts[key])?'Saved; command-line or environment settings still override this value.':'Saved';
    }catch(error){if(status)status.textContent=error.message;else ui().showToast(error.message);}
    finally{field.disabled=false;}
  });
  global.__mrSettings={open,openSubview,register(entry){if(!entry?.id||typeof entry.markup!=='function')return false;contributors.set(entry.id,entry);return true;}};
})(window);
