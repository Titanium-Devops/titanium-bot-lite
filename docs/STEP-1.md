# Step 1: the console split and a Python server that talks to the Tiiny

You are building Titanium Bot Lite in this repo. Read, in this order: README.md, SPEC.md,
docs/console-pieces.md (the port plan and the 12-route contract), docs/agent-pieces.md (formats
and the prompt loop), docs/tiiny-platform.md (the device: how to call it, what was measured),
brand/BRAND.md. The product's console source is vendored read-only under vendor/machine-room/ and
its docs under vendor/docs/. Never edit vendor/. Never write outside this repo.

Deliver, in this order, each runnable:

1. `lite/server.py`: Python 3.11+, standard library only (http.server + threads, or asyncio),
   no pip dependencies. `python3 -m lite` serves the console at http://0.0.0.0:7777 and the
   12 routes plus the SSE poke from docs/console-pieces.md. Config from env: TIINY_BASE
   (default empty, meaning "find the device"), TIINY_KEY, TIINY_MODEL, and a data dir (default
   ./data, created on first run: memory/, skills/, routines/, persona.md, keys.json at 0600).
   Use lite/onelane.py for every device call (`with lane.hold(why=...)`), treat device error
   150004 and a 502 upstream error as "wait and retry" with a bounded backoff (copy the
   pattern described in docs/tiiny-platform.md), send `chat_template_kwargs: {"enable_thinking":
   false}` and max_tokens >= 800 on ordinary turns, stream tokens to the console.
2. `lite/console/`: the ported console. Copy from vendor/machine-room/ only the files
   docs/console-pieces.md marks "ports as is" or "needs a named change", apply the named
   changes (split app.js keeping the listed line ranges; write lite-adapter.js of about 300 lines
   implementing the 12-route contract; settings.js with General, Model, Usage, About; three
   background plates; bg-boot.js trimmed). The sign-in door and the About row carry
   "Brought to you by Titanium Bot" with brand/ti-mark.svg linking to https://titanium.bot.
   Titan's mascot kit and the boot cover ship. No marketplace, no screen tile, no cloud browser,
   no code tasks, no push, no account menu, no bot setup.
3. An echo model for development: TIINY_MODEL=echo answers with the prompt reversed, so the
   console can be driven with no device. `python3 -m lite --selfcheck` runs one turn against
   the configured model and prints the timings, RAM in use, and the first-paint bytes of the
   console (sum of the files the door loads).
4. Tests with the standard library `unittest`: the route contract (each route's request and
   response shape), the adapter against the echo model through a real HTTP server on a spare
   port, the persona and memory readers. `python3 -m unittest` must pass.
5. README: "Run it in ten minutes" for a non-technical owner: install Python, set two env
   values from TiinyOS Settings > API Key, run, open the page on the phone. Plain words, no
   em dashes, never the old upstream's name, never a package or command named `tiiny`.

Budget printed by --selfcheck and asserted by a test: idle RAM under 200 MB, first paint under
250 KB, cold start under 5 s. Commit as you go with plain-prose messages, no attribution lines.
When done, write docs/REPORT.md: what ported as is, what changed, what was dropped, the
selfcheck numbers, every deviation from this brief with its reason, and what step 2 needs.
