// Exercise actual voice.js with fake audio objects. No browser or GUI.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
let now = 1000, tick, level = 0, stopped = 0, posts = [], sources = [], pendingMic;
const flush = async () => { for (let i=0;i<3;i++) await new Promise(setImmediate); };
class Recorder {
  static all = [];
  static isTypeSupported(type) { return type.startsWith('audio/webm'); }
  constructor(stream, options) { this.mime=options.mimeType; this.state='inactive'; Recorder.all.push(this); }
  start() { this.state='recording'; }
  stop() { this.state='inactive'; this.ondataavailable({data:new Blob(['voice'],{type:this.mime})}); queueMicrotask(()=>this.onstop()); }
}
class Context {
  constructor() { this.currentTime=0; this.destination={}; }
  resume() { return Promise.resolve(); }
  close() { return Promise.resolve(); }
  createAnalyser() { return {fftSize:16, connect(){}, getFloatTimeDomainData(samples){samples.fill(level);} }; }
  createMediaStreamSource() { return {connect(){}}; }
  async decodeAudioData() { return {}; }
  createBufferSource() { const source={connect(){},start(){},stop(){this.onended?.();}}; sources.push(source); return source; }
}
const stream = () => ({ getTracks:()=>[{stop:()=>stopped++}] });
const sandbox = {
  console, Blob, FormData, AbortController, ArrayBuffer, Float32Array, Uint8Array, Int16Array,
  Date: class extends Date { static now(){return now;} },
  performance:{now:()=>now}, innerWidth:1200, innerHeight:900,
  setTimeout:()=>1, clearTimeout(){}, setInterval:fn=>(tick=fn,1), clearInterval(){tick=null;},
  MediaRecorder:Recorder, AudioContext:Context,
  navigator:{mediaDevices:{getUserMedia:()=>pendingMic||Promise.resolve(stream())}},
  fetch:async (path, options)=>{
    if(path==='/api/voice/turn') { posts.push(options); return {ok:true,json:async()=>({heard:'Hello Titan',said:'Hello owner',audio:'/api/voice/say/test.wav'})}; }
    if(path.startsWith('/api/voice/say/')) return {ok:true,arrayBuffer:async()=>new ArrayBuffer(16)};
    throw Error('Unexpected request '+path);
  },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('lite/console/voice.js','utf8'),sandbox);
const voice=sandbox.__voice;
const enable=mode=>{voice._state.settings={enabled:true,mode};voice._state.talkMode=mode;};
(async()=>{
  enable('push');
  await voice.talkDown();
  assert.equal(Recorder.all.at(-1).state,'recording');
  assert.equal(posts.length,0);
  voice.talkUp(); await flush();
  assert.equal(posts.length,1);
  assert.equal(posts[0].body.get('file').name,'recording.webm');
  assert.equal(voice.stats().lastHeard,'Hello Titan');
  assert.equal(voice.stats().lastSaid,'Hello owner');
  assert.equal(voice.stats().orb,'speaking');
  const count=Recorder.all.length;
  tick(); assert.equal(Recorder.all.length,count,'No recording during playback');
  sources.at(-1).onended(); await flush();
  voice.stop(); assert(stopped>0); assert.equal(tick,null);

  enable('always'); await voice.start();
  now+=8000; tick(); await flush();
  assert.equal(posts.length,1,'Silence must not produce a turn');
  tick(); level=.05; now+=50; tick();
  level=0; now+=699; tick(); await flush();
  assert.equal(posts.length,1,'Wait for 700 ms quiet');
  now+=1; tick(); await flush();
  assert.equal(posts.length,2);
  assert.equal(voice.stats().orb,'speaking');
  sources.at(-1).onended(); await flush();
  const beforeTail=Recorder.all.length; tick();
  assert.equal(Recorder.all.length,beforeTail,'Playback echo tail is held');
  now+=351; tick(); assert.equal(Recorder.all.length,beforeTail+1);
  level=.05; now+=8000; tick(); await flush();
  assert.equal(posts.length,3,'Continuous speech is bounded at eight seconds');
  voice.stop(); await flush();

  let release;
  pendingMic=new Promise(resolve=>release=resolve);
  enable('push'); const opening=voice.talkDown(); voice.talkUp(); voice.stop();
  const beforeCancel=posts.length; release(stream()); await opening; await flush();
  assert.equal(posts.length,beforeCancel,'Cancelled microphone acquisition never posts');
  assert.equal(voice.stats().on,false);
  pendingMic=null;

  enable('always'); await voice.start(); level=.05; tick();
  voice._call.mute(true); await flush();
  assert.equal(posts.length,beforeCancel,'Mute discards unfinished recording');
  voice.stop();
  assert.deepEqual(Array.from(voice._CALL_WORDS),['Connecting','Listening','Thinking','Talking','Muted']);
  console.log('Voice transport: push, silence gate, 700 ms quiet, eight-second chunks, playback, echo tail, cancellation and mute passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
