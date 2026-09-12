(function(global){'use strict';
 const CREW=[{name:'Titan'}];
 const storedChoice=()=>null;
 const assignCrew=agents=>new Map(agents.filter(a=>!a.isGroup).map(a=>[a.id,{character:'Titan',index:0,source:'first',opt:null}]));
 const CELEBRATION_MS=6000;
  function moodFor(record, options) {
    const now = options && Number.isFinite(options.now) ? options.now : Date.now();
    const until = options && Number.isFinite(options.celebratingUntil) ? options.celebratingUntil : 0;
    // A person is wanted: attentive, not bouncing. The turn that asks for them is attentionFor.
    if (record && record.needsYou === true) return "curious";
    if (record && record.status === "working") return "curious";
    if (until > now) return "excited";
    return "calm";
  }
  function attentionFor(record) {
    return Boolean(record && record.needsYou === true);
  }
  function celebrationUntil(previousStatus, record, now, ms) {
    if (previousStatus !== "working") return 0;
    if (!record || !["ready", "idle"].includes(record.status)) return 0;
    return (Number.isFinite(now) ? now : Date.now()) + (Number.isFinite(ms) ? ms : CELEBRATION_MS);
  }
const stillFor=(_,mood)=>`assets/characters/titan-${['curious','excited'].includes(mood)?mood:'calm'}.png`;
 global.TitanCrew={CREW,storedChoice,assignCrew,moodFor,attentionFor,celebrationUntil,stillFor};
})(window);
