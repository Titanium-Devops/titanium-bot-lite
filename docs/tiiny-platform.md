# The Tiiny platform, for Titanium Bot Lite

Reader 3. Read 2026-09-11, web only, never signed in, nothing installed. Every fact cites a source key
from the list at the bottom. "Unknown" means their docs do not say it, not that I failed to look.

The live docs at https://dev.tiiny.ai/ are a hash-route site. Search engines still serve an older
cached copy of the index page describing a different API. Where they disagree the hash routes are
current. SPEC.md was written from the stale copy, so three of its device facts need correcting; see the
last section.

## 1. The device

| Fact | Value | Source |
| --- | --- | --- |
| CPU | ARMv9.2, 12 cores | P1 |
| NPU | custom SoC plus dNPU, about 190 TOPS | P1 |
| RAM | 80 GB LPDDR5X | P1, P5 |
| Storage | 1 TB SSD | P1, P4 |
| Power | 30 W TDP, 65 W typical | P1 |
| Size | 14.2 x 8 x 2.53 cm, about 300 g | P1 |
| OS | TiinyOS, client app for Windows and macOS only | P2 |
| Ceiling | 120B on device, about 18 tokens/s on GPT-OSS 120B | P4 |
| Engine | PowerInfer plus TurboSparse, CPU and NPU together | P1 |

What a third-party process may use: **unknown.** No CPU, RAM or disk quota for third-party code is
documented, and no documented way to run your own long-lived process on the device. The only two
documented paths into the device's insides are an MCP server registered with `runEnvironment: "Tiiny"`
(D6) and an agent installed from their store through `agents.api.tiiny` (D9). Neither has a published
packaging format. Loading a model occupies NPU memory and a large one may force unloading another (P4).

## 2. The local model API

Three protocol surfaces, one shared API key (D1):

- OpenAI-compatible `http://openai.api.tiiny/v1`, the widest surface.
- Anthropic `http://anthropic.api.tiiny`, text generation only (D11).
- Ollama `http://ollama.api.tiiny`, text generation only (D12).

Those pretty hostnames come from the CLI's own name resolution. Everything also works by raw address:
`http://<device-ip>:8800/v1/...` for inference, and `http://<device-ip>/...` with an explicit `Host:`
header (`kb.tiiny.local`, `connector.api.tiiny`, `auth.api.tiiny.local`, `p8800.api.tiiny`,
`agents.api.tiiny`, `wifi.api.tiiny`, `upgrade.api.tiiny:5555`) for everything else (D8, D5). A process
on the LAN should use the address and explicit Host headers, never the pretty names.

Auth is not a master-password call any more. Activate once with `tiiny init` or `POST /api/v1/auth/init`,
log in with `tiiny login` or `POST /api/v1/account/auth`, then read the key with `tiiny auth key`, which
prints the key and the three base URLs from local CLI config and makes no HTTP call (D3, D13). Every
later request is `Authorization: Bearer <api_key>`. Three login attempts then lockout. Recovery is email
or local-only, and local-only with a forgotten password is unrecoverable.

Routes on the OpenAI surface (D10):

| Route | Notes |
| --- | --- |
| `POST /v1/chat/completions` | file attach for multimodal; thinking mode and depth where the model supports it (D14) |
| `POST /v1/embeddings` | `dimensions` supported |
| `POST /v1/images/generations` | `b64_json` or `url`; sizes multiples of 16, presets 512x512 to 1280x960, 9 steps default |
| `POST /v1/audio/transcriptions` | ASR, multipart file, optional `language` |
| `POST /v1/audio/speech` | TTS, returns raw `audio/mpeg` |
| `POST /v1/rerank` | their extension, not OpenAI spec, marked pending engineering confirmation |
| `POST /v1/ocr`, `POST /v1/music/generate/mp3` | Tiiny-only, absent from all three compatible surfaces (D7) |

Streaming is documented for the Ollama route, which streams newline-delimited JSON by default and takes
`"stream": false` (D12). The stale index claimed streaming chat completions. The current OpenAI page
shows no `stream` example. Treat OpenAI-route streaming as likely but unproven.

Tool calling: **unknown, and it is the gap that matters most.** No page mentions `tools`, `tool_choice`,
functions or tool calling on any surface. Titan's skills and routines need a tool loop, so probe this on
Jason's unit before planning step 3 of the delivery order.

Model lifecycle, all documented (D14): list (`GET /api/v1/models/`, `online_models` for the store),
info, download, import a Hugging Face URL (Qwen3.5-9B and Z-Image-Turbo bases and their fine-tunes only,
safetensors), delete, load (`POST /api/v1/models/<id>/start`), unload (`stop`, `unload_all`), NPU status
(`GET /api/v1/npu/status`), running tasks, interrupt, and a CLI-only benchmark. The model id `default`
resolves to whatever chat model is loaded, which is convenient and non-deterministic.

Which models ship: the store carries 50-plus open-source models including GPT-OSS, Llama, Qwen, GLM,
Mistral and Phi, plus 100-plus agents, all one-click (P3, P1). The preloaded set on a beta unit is
**unknown.** Named in the docs: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` and `Supertone/supertonic-3` for
speech, `Qwen3.5-9B` and `Z-Image-Turbo` as import bases.

Already on the device and worth reusing: a **vault** with upload, index and semantic `POST /kb/retrieve`,
plus a nightly conversation summary on an hourly schedule (D5); a **profile** of `occupation`,
`preferences` and `more`, capped at 50 and 1000 characters, explicitly **not** injected into SDK or CLI
inference and only into TiinyOS Task Mode (D15); **connectors** for Outlook, Google and Outlook Calendar,
X, Telegram, Discord and WhatsApp plus custom MCP over HTTP, stdio or SSE, whose actions today run only
inside Task Mode (D6). Task Mode itself is "Coming Soon" with no docs (D16).

## 3. The SDK

Install is a shell script, not pip: `install-linux.sh`, `install-darwin.sh` or `install-windows.ps1`
from `https://files.tiinycdn.com/update/blobs/`, user-scope only on Windows, re-run to update. It puts a
`tiiny` CLI on the path (D2).

The CLI is the documented interface: `scan`, `connect`, `init`, `login`, `logout`,
`auth key|info|username|passwd|email-bind`, `status`, `top`, `ls`, `info`, `download`, `import`, `rm`,
`load`, `unload`, `run` with `embed|tts|image|asr|rerank|ocr`, `interrupt`, `tasks ls`, `bench`,
`wifi *`, `vault *`, `profile *`, `connector *`, `downloads *`, `upgrade`. Debugging is `LOG_LEVEL=DEBUG`
for the SDK and `-v` for curl (D17).

Python classes and methods: **unknown.** The current docs document the CLI and raw HTTP, not a Python
class surface. The stale index showed `from tiiny import TiinyDevice, OpenAI`, `TiinyDevice(device_ip=...)`,
`device.get_api_key(master_password=...)` and `device.get_url()`, and even it hedged its own package name.
Do not build against it.

`pip install tiiny-sdk` is a trap (D18). Version 0.1.4, 2026-02-15, Python 3.8+, was a device SDK with a
`TiinyClient` over USB-C. Version 0.2.0, 2026-04-21, Python 3.11+, replaced it with something else:
"tiiny-cli", a minimal Hermes-agent-shaped runtime with an agent loop, provider abstraction, a
JSON-schema tool registry with toolsets, `~/.tiiny/SOUL.md`, `AGENT.md`, `USER.md`, `MEMORY.md`, and
skills as `~/.tiiny/skills/<name>/SKILL.md` with `name` and `description` frontmatter. It installs a
`tiiny` console script that collides with the official CLI and it carries no author, homepage or
repository metadata. Python for the current release is 3.11 or newer. That package is both a naming
hazard and, read honestly, a rough sketch of Titanium Bot Lite shipped by someone else. Its skill folder
layout is worth matching.

## 4. Tinyverse

There is no Tinyverse. Nothing on tiiny.ai or dev.tiiny.ai uses the word and a web search returns
unrelated miniature-video accounts. The real thing is the **Agent Store** in TiinyOS, which D3 refers to
when it says Agent Store agents are already configured and need no API key. It is stocked with 100-plus
open-source agents including OpenClaw, OpenCode, Flowise, Presenton, Libra, Bella and SillyTavern (P3).
Tiiny's own coinage, "AgentBox", names a device class, not a store (P3).

- Device or beside it? **On the device**, reached from a browser on the connected computer. Installed
  agents are services: `GET /api/services`, `GET /api/services/download/<app_id>/status`, and
  `DELETE /api/services/<name>` against Host `agents.api.tiiny` (D9). A review describes the whole
  experience as a browser interface needing no special software (P6).
- Submission process: **unknown.** No developer portal, review rules, manifest or package spec, and
  nothing in the docs nav. The store is stocked with existing open-source projects, not submissions.
- Packaging format, container or Python or web app, manifest fields: **unknown.** The only clue is that
  installed items are services with an `app_id` and a download state.
- Review rules: **unknown.**
- Branding rules affecting "Brought to you by Titanium Bot": **unknown.** No developer terms, brand
  guide or trademark page exists. Site policies cover refunds, shipping, privacy and terms only (P5).
  Safe reading: our own mark and wording are fine, and we keep "Tiiny" out of the product name and never
  use their logo.

## 5. Speech

Yes, both, on device, and this is the best news in the research. ASR is `POST /v1/audio/transcriptions`,
multipart file plus optional `language`, returning `{"text": ...}`. TTS is `POST /v1/audio/speech` with
`input`, `voice` and `response_format`, returning raw `audio/mpeg` (D10, D14).
`Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` needs no voice, `Supertone/supertonic-3` requires one. Both are
file in, file out. There is **no documented streaming or realtime socket** for either, so hands-free
voice has to be push-to-talk or chunked turns, not live duplex.

## 6. Networking

Discovery is `tiiny scan`, which sends `GADGET_DISCOVER_V1` to an IPv4 broadcast address and an IPv6
multicast group on **UDP 39217**; a responder then serves metadata at `http://<device-ip>:39218/device.json`.
curl cannot do the UDP step (D4). An unactivated device must be on USB-C first; once activated it is
reachable over USB-C or the LAN and every command behaves identically. The device joins Wi-Fi itself via
`tiiny wifi connect`, and Wi-Fi is required for model downloads, connectors and updates.

IPv6: the docs only say the multicast half of discovery is IPv6 and otherwise use a neutral `<device-ip>`.
The `fd80:7:7:7::1` literal appears only in the stale page, so treat it as a USB-C link-local default,
not a fact. Whether a phone reaches the device's web server: **unknown and undocumented.** The device
serves HTTP on its LAN address and the shipped client is Windows and macOS only (P2), so a phone on the
same Wi-Fi very likely reaches it, but nobody has written that down. Probe it.

## 7. Developer program and beta

There is no gated developer program. The SDK is described as an open tool any developer can download
(P2). Hardware came through Kickstarter: launched 2026-03-11, past US$1M in five hours, super early bird
$1,399, with a further launch planned for July 2026 (P3, P2). Their Kickstarter page blocks automated
reads, so backer-tier detail is unverified here. The developer channel is their Discord,
https://discord.gg/R5CHUuXy4A, linked from tiiny.ai (P5). Beta terms, NDA or firmware channel:
**unknown.** Jason's unit is the only primary source we have.

## 8. Recommended packaging

**Ship Lite beside the device: one pip-installable Python 3.11+ process, run on the host the Tiiny plugs
into or any box on the same LAN, talking to `http://<device-ip>:8800/v1` with a Bearer key.** Reasons in
order: there is no published on-device package format, so "on it" is not a choice anyone can make today;
the inference surface is identical either way; and a process beside the device can serve its console to a
phone, which is what the owner actually wants.

- Distribution: a wheel plus a one-line installer, console script `titanbot-lite`. **Never name anything
  `tiiny`** or publish under a `tiiny*` PyPI name. Both are taken and the `tiiny` script collides.
- Config: device address and API key in the single 0600 JSON file the spec already calls for. Always the
  raw address, with explicit `Host:` headers for vault and connector routes.
- Optional second form later: register Lite's tool surface as a custom MCP connector with
  `runEnvironment: "Computer"` so TiinyOS chat can reach Titan. It is the one documented bridge into
  their UI and costs a single JSON import.
- Reuse rather than rebuild: their vault for file retrieval, their ASR and TTS for voice. Keep our
  memories, skills, routines and persona as our own files, since their profile caps at 1000 characters
  and never reaches API inference.
- Revisit an on-device package only when Tiiny publishes a submission spec. Until then an Agent Store
  listing is not a milestone we can commit to, and it should come out of the delivery order as written.

## 9. The three risks

1. **The endpoints will move.** Their own pages say "pending engineering confirmation" on the Tiiny and
   rerank routes, Task Mode is unwritten, and two doc generations already disagree about install, auth
   and the device address. Keep every route behind one adapter module with one base URL and one header.
2. **Tool calling is unverified.** Skills, routines and tools all need a function-calling loop and
   nothing says the chat route accepts `tools`. If it strips them, Titan on a 9B-class local model falls
   back to prompt-parsed tool calls, a different and worse product. Probe before building step 3.
3. **Someone is already shipping our shape under a name next to ours.** `tiiny-sdk` 0.2.0 is a
   Hermes-style agent CLI with SOUL, AGENT, USER and MEMORY files, frontmatter skills and a tool
   registry, with no author metadata and a colliding `tiiny` script. Whoever owns it, Lite has to be
   clearly distinct in name and clearly better at console, voice and routines, and must not depend on it.

## Corrections to SPEC.md

- `pip install tiiny` and `pip install tiiny-sdk` are both wrong. The SDK installs from a shell script.
- `device.get_api_key(master_password)` is gone. It is `tiiny init`, `tiiny login`, `tiiny auth key`.
- `fd80:7:7:7::1` should not stand as the device address. Use discovery plus `<device-ip>:8800`.
- Two spec unknowns are answered: on-device speech exists both directions, and the packaging format
  question has no answer to find, which is itself the answer.

## Sources

D1 https://dev.tiiny.ai/#/overview · D2 #/quickstart · D3 #/api-key · D4 #/concepts-device-network ·
D5 #/concepts-vault · D6 #/concepts-connectors · D7 #/inference-tiiny-sdk · D8 #/api-reference-hardware ·
D9 #/api-reference-other · D10 #/inference-openai · D11 #/inference-anthropic · D12 #/inference-ollama ·
D13 #/api-reference-authentication · D14 #/api-reference-models-inference · D15 #/concepts-personalization ·
D16 #/concepts-task-mode · D17 #/debug-logs (all under https://dev.tiiny.ai/)
D18 https://pypi.org/project/tiiny-sdk/ and https://pypi.org/pypi/tiiny-sdk/json
P1 https://www.prnewswire.com/apac/news-releases/tiiny-ai-reveals-worlds-smallest-personal-ai-supercomputer-verified-by-guinness-world-records-302637605.html
P2 https://audioxpress.com/news/tiiny-ai-unveils-pocket-size-ai-supercomputer-at-ces-2026
P3 https://finance.yahoo.com/news/agentbox-emerges-tiiny-ai-pocket-193500164.html
P4 https://www.geeky-gadgets.com/offline-llm-hardware/ · P5 https://tiiny.ai/ and https://tiiny.ai/collections/all
P6 https://www.openpr.com Tiiny AI Pocket Lab review, 2026-03-13

## Measured on Jason's unit, 2026-09-11 19:55 CDT, from his Mac through the TiinyOS resolver

The pretty hostnames resolve to 127.0.0.1 on a Mac running the TiinyOS client, so
`http://openai.api.tiiny/v1` works from here with the key from TiinyOS > Settings > API Key
(Bearer). From another machine the doc says `http://<device-ip>/v1` (port 80, not 8800).
`scripts/probe-device.sh` is the probe; run with TIINY_KEY, TIINY_BASE, TIINY_MODEL in the env.

| Question | Answer |
|---|---|
| Models loaded | deepreinforce-ai/Ornith-1.0-35B (Image-Text-to-Text, supported: Reasoning, Tool Use, vision), Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice, Tongyi-MAI/Z-Image-Turbo |
| Tool calling | YES. `tools` + `tool_choice: auto` returned a real `tool_calls` entry (get_weather, place "Granger, Texas") with the reasoning in `reasoning_content`. The server underneath is llama.cpp (system_fingerprint b9803). |
| Streaming | YES on the OpenAI route: `data:` chunks with `delta.reasoning_content` then `delta.content`. |
| Plain chat latency | 113 s for "Say hello in five words": the model wrote 8,407 characters of reasoning (2,875 completion tokens, about 25 tokens/s) before a six-word answer. `thinking.toggleable` is false on this model. A lite app must either pick a non-reasoning model, cap `max_tokens`, or steer with a system line; measure each. This is the number that decides whether Lite feels alive. |
| Text to speech | YES: POST /v1/audio/speech with the TTS model id and `input`, NO `voice` field ("Unsupported speaker: default" with one), returns audio/wav 24 kHz, 88 KB for one sentence. |
| Speech to text | not run yet (needs a wav; the route is documented). |
| The `default` model id | not tested; use exact ids from /v1/models. |
