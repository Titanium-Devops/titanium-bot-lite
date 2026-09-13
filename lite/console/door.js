/* The door paints alone. The console and animated kit are requested only on entry. */
(function(){
  const script = src => new Promise((resolve,reject)=>{const node=document.createElement('script');node.src=src;node.onload=resolve;node.onerror=()=>reject(new Error('Could not load '+src));document.body.appendChild(node);});
  const sheet = href => new Promise((resolve,reject)=>{const node=document.createElement('link');node.rel='stylesheet';node.href=href;node.onload=resolve;node.onerror=()=>reject(new Error('Could not load '+href));document.head.appendChild(node);});
  document.getElementById('enter-console').addEventListener('click',async event=>{
    event.target.disabled=true;document.getElementById('door-status').textContent='Opening your conversation…';
    try {
      const response=await fetch('console.html');if(!response.ok)throw new Error('The console could not be read.');
      document.body.innerHTML=await response.text();
      document.querySelector('link[href="door.css"]').remove();
      await script('boot-cover.js');
      // Blocking background choice precedes the console's first stylesheet.
      await script('bg-boot.js');
      await Promise.all(['motion.css','styles.css','backgrounds.css','mascots.css','settings.css','files-viewer.css'].map(sheet));
      // voice.js and its avatar come before app.js, the order index.html uses on the full product.
      // Both boot themselves on load and find their own hosts, and the Talk button is already in
      // console.html, so the only thing this list decides is whether talking exists at all.
      for(const name of ['assets/titan-mascot.js','mascot-crew.js','mascots.js','lite-adapter.js','settings.js','backgrounds.js','files-viewer.js','voice.js','voice-call-avatar.js','app.js'])await script(name);
    } catch(error) {
      const status=document.getElementById('door-status')||document.getElementById('transcript');
      if(status)status.textContent=error.message+' Reload this page to try again.';
    }
  });
})();
