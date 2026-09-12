# Titanium Bot Lite, the spec

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

## Facts about the device (read 2026-09-11 at dev.tiiny.ai and tiiny.ai)

- TiinyOS runs open-source LLMs on the device's NPU and "AI agents with a single click".
- OpenAI-compatible chat API on the device: base URL from the SDK, api key from
  `device.get_api_key(master_password)`, device address like `fd80:7:7:7::1` (IPv6).
- Model list, start, stop; embeddings; rerank; image generation. Python SDK: `pip install tiiny`.
- Unknown: the packaging format Tinyverse accepts, CPU and RAM available to a third-party process,
  whether on-device speech-to-text or text-to-speech is exposed. Reader 3 answers these.

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
"Brought to you by Titanium Bot" on the sign-in door, the About row in Settings, and the README.
Copy for a person is plain words; no em dashes.

## Delivery order, each step runnable

1. Console plus an echo model.
2. The Tiiny model behind Settings, with list, start and stop.
3. Memories and skills.
4. Routines.
5. Voice.
6. The Tinyverse package.

## From the readers

See `docs/console-pieces.md` (reader 1), `docs/agent-pieces.md` (reader 2) and
`docs/tiiny-platform.md` (reader 3). Their findings are folded back into this file when they land.
