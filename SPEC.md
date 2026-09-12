# Titanium Tiiny Bot, the spec

Status: draft, 2026-09-11. Owner: Jason Brashear. Written by the orchestrator; the sections marked
"from the readers" are filled by the three readers named at the end.

## What it is

One small process on, or beside, a Tiiny AI Pocket Lab that gives its owner Titan: a chat with
memory, skills and routines, a persona they can edit, and voice, using the model running on the
device. It is the cute little cousin of Titanium Bot, and it says so: "Brought to you by Titanium
Bot" with the Ti mark, linking to https://titanium.bot, on the door and in Settings.

## What it is not

Not multi-tenant. No accounts. No control plane. No Docker, no desktop, no box. No mail plane, no
push, no code sandboxes, no marketplace, no team of bots. One owner, one Titan, one device.

## Facts about the device (readers 1 to 3, 2026-09-11; sources in docs/tiiny-platform.md)

- Tiiny AI Pocket Lab: 80 GB LPDDR5X, 1 TB SSD, 12-core ARMv9.2, a ~190 TOPS NPU, 30 W TDP; runs
  models up to 120B on the device. TiinyOS runs them and an Agent Store of existing open-source
  agents installed as services. There is NO documented way to submit an app to that store and no
  package format, so "Tinyverse" is not a delivery target.
- The model API is OpenAI-compatible at http://<device-ip>:8800/v1 with a Bearer key from the
  official CLI (`tiiny init`, `tiiny login`, `tiiny auth key`; the official SDK installs from a shell
  script at files.tiinycdn.com, not pip). Chat completions, embeddings, images, speech-to-text
  (POST /v1/audio/transcriptions) and text-to-speech (POST /v1/audio/speech) are documented. Model
  list, load, unload and NPU status are documented; model id `default` is whatever is loaded.
- Tool calling WORKS (measured on Jason's unit 2026-09-11: a real `tool_calls` entry from
  Ornith-1.0-35B in 2.4 s). Streaming works. Text to speech works (Qwen3-TTS, audio/wav). A plain
  turn takes 1.2 s with `chat_template_kwargs: {"enable_thinking": false}` and 113 s without, so
  Lite decides per request whether Titan thinks (see docs/tiiny-platform.md).
- No realtime speech socket: voice is push-to-talk or chunked turns, not live duplex. No cloud key
  is needed for a basic voice loop.
- PyPI `tiiny-sdk` 0.2.0 is an unrelated Hermes-shaped agent runtime whose `tiiny` script collides
  with the official CLI. Nothing of ours is ever named `tiiny`; the package is `titanium-bot-lite`.

## Shape

- Server: one Python process (FastAPI or the stdlib), because their SDK is Python and a Tinyverse
  package is more likely to be Python than Node. It serves the console and runs the agent loop.
- Console: plain HTML and JS, no build step, phone-sized first (the Tiiny is used from a phone or
  its own small screen). Borrowed from Titanium Bot's console where the piece is portable.
- Model: Settings picks (a) a model on this Tiiny, listed from the device, with start and stop;
  (b) any OpenAI-compatible endpoint on the LAN (Ollama, llama.cpp); (c) a pasted cloud key.
  Keys live in one 0600 JSON file and never reach the page.
- Memory: one fact per markdown file, 500 characters max, in a folder the owner can read.
- Skills: markdown files Titan reads, same frontmatter as Titanium Bot's managed skills.
- Routines: cron only, stored as files, run by the same process.
- Persona: one file the owner edits, seeded with Titan's standing persona in plain words.
- Tools: files under one folder, fetch a URL, remember a fact, run a skill, schedule a routine.
  No shell by default.
- Voice: on-device speech if TiinyOS exposes it; otherwise a pasted realtime key. Push-to-talk and
  a hands-free call screen with the Titan mascot morphing to the voice level.
- Budget, measured and printed at startup: idle under 200 MB RAM, first paint under 250 KB, cold
  start under 5 s.

## Brand

The Ti mark (`brand/ti-mark.svg`), Midnight #090D14, Signal Cyan #00C8F0, Titan the blob mascot.
The product name is "Titanium Tiiny Bot". "Brought to you by Titanium Bot" links to
https://titanium.bot on the door, in Settings > About, and in the README. "Built for" with the
Tiiny logo (`brand/tiiny-logo.svg`) links to https://tiiny.ai on the door (20 px high), in the
console header (16 px high), and in About. The white Tiiny mark sits on a Midnight pill to
retain contrast across themes. The command and Python package names stay unchanged.
Copy for a person is plain words; no em dashes.

## What the readers found, folded in

### Packaging: beside the device, not on it (docs/tiiny-platform.md)
One pip-installable Python 3.11+ package, `titanium-bot-lite`, run on the Mac or any LAN box the
Tiiny is reachable from; `titanium-bot-lite start` serves the console on the LAN and talks to the
device at <device-ip>:8800. Optional second form: register Lite as a custom MCP connector in
TiinyOS so their own chat can reach Titan's memory and skills.

### The console (docs/console-pieces.md)
Ports as is: the phone layout (insets, 690 px blocks, drawers, jump-newest, 44 px targets), the
composer, the transcript renderer (code chips, tool receipts, the Spoken chip), the whole Titan
mascot kit, the boot cover, the background picker (three plates, not seventeen), files-viewer.js,
voice.js including the call screen. The job is splitting app.js: about 3,500 of its 8,325 lines
port, and a new lite-adapter.js of about 300 lines replaces gateway-adapter.js (5,326 lines) and
adapter.js. settings.js keeps its shell and registry with four sections plus About, Computer
becomes Model. Drops: marketplace, screen tile, cloud browser, code tasks, push, account menu, bot
setup, both old adapters (11,600 lines, 1.7 MB). The server contract is 12 routes plus one
WebSocket for voice, listed in the doc against the delivery steps. The SSE stream is one poke
("re-read", debounced 900 ms). The page never talks to a voice vendor itself, so on-device speech
plugs in server-side without touching voice.js.

### The agent (docs/agent-pieces.md)
Memory: one fact per line `- (YYYY-MM-DD) <fact>` in memory/profile.md and memory/log/YYYY-MM.md,
500 characters, refuse over-long facts rather than slice. Skills: one folder, one SKILL.md with
name and description frontmatter; the name in the file is the name it is filed under. Routines: a
real five-field cron or nothing, created disabled. Persona: a seeded persona.md the owner edits,
keeping five habits (precedence to what is on the device, first-time setup asks its first
question in the same message, the handbook pointer, never ask for a credential, backticks on
identifiers) and dropping every fleet fact. Tools, five, as OpenAI schemas: Read, Write,
fetch_url, update_state (memory, routine, profile), run_skill. Packs: handbook-never-ask,
handbook-plain-words and onboarding ship after a trim; handbook-what-i-can-do is rewritten as
this device's map; the six packs that need mail, a browser, a box or a crew carry one line,
"that is part of the full Titanium Bot, not this device". The skill catalog is in the prompt from
day one (the product does not do this yet; KB-1f).

## Delivery order, revised

0. DONE 2026-09-11: tools, streaming and speech all work on the unit; thinking off per request
   gives 1.2 s turns. Reuse Jason's onelane (device lock) and story-lantern (device client
   patterns), both stdlib Python; details in docs/tiiny-platform.md.
1. Console split plus lite-adapter.js against an echo server; the door says "Brought to you by
   Titanium Bot".
2. Settings, Model section: list, load, unload on the device; LAN endpoint and cloud key fallbacks.
3. Memory, persona, skills with the catalog in the prompt; the five tools.
4. Routines on cron.
5. Voice: push-to-talk and the call screen through the device's ASR and TTS.
6. `pip install titanium-bot-lite`, a README a non-technical owner follows in ten minutes, and
   the optional MCP connector registration.
