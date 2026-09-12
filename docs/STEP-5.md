# Step 5: voice through the device's own ears and mouth

Read SPEC.md, docs/tiiny-platform.md (ASR at POST /v1/audio/transcriptions, multipart file; TTS at
POST /v1/audio/speech with the TTS model id and `input`, NO voice field, returns audio/wav 24 kHz;
no realtime socket, so voice is turns, not duplex), docs/console-pieces.md (voice.js and the call
screen port unchanged because the page never talks to a vendor), lite/console/voice.js and
lite/console/voice-call-avatar.js as vendored, and lite/server.py.

1. Server: `POST /api/voice/turn` takes a multipart audio file (webm or wav from the browser),
   sends it to the device's ASR (model: the first row whose type is Speech-to-Text or
   capabilities include "asr"; if none is loaded, the plain sentence "Load a speech model on the
   device first"), runs the transcript as an ordinary turn through the tool loop, then sends the
   final text to the device's TTS (first Text-to-Speech row) and answers JSON
   {heard, said, audio: "/api/voice/say/<id>.wav"} with the wav cached in <data dir>/voice/ for one
   hour. `GET /api/voice/settings` answers {enabled, mode, asrModel, ttsModel}. All device calls
   hold the OneLane lane. Load the TTS model per session and release it after five idle minutes
   the way story-lantern does (docs/tiiny-platform.md).
2. Console: voice.js's transport swaps from the relay's WebSocket to this route: push-to-talk
   records with MediaRecorder while held, posts on release, shows the heard words as the person's
   line with the Spoken chip, plays the wav, shows Titan's line. Always-listening: record in 8 s
   chunks with a simple energy gate and post when the person goes quiet for 700 ms. The call
   screen (voice-call-avatar.js) keeps its five words and the mascot morph driven by the playback
   level (an AnalyserNode on the wav) and the microphone level. Desktop keeps the strip.
3. Settings > General: a Voice row (off, push to talk, always listening) and the device speech
   models shown read-only.
4. Tests: the route with a fake device that returns a fixed transcript and a tiny wav; the model
   picking; the "load a speech model" sentence; the cache expiry. `python3 -m unittest` green.
   Bump lite/VERSION by one on the last number. Append a "Step 5" section to docs/REPORT.md. No
   browser or GUI from your sandbox; the orchestrator measures the console afterwards. Commit is
   not possible from your sandbox.
