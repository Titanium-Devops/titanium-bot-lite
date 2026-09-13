# Step 1 report

Date: 2026-09-11. Status: implementation and offline checks are ready for review;
full acceptance is blocked by this session's filesystem and network permissions.
No browser, Chromium, Chrome, Brave, simulator or GUI was launched. No device key
was printed. Nothing under `vendor/` was changed.

## Work retained and completed

Read the brief and its referenced documents, then read the earlier uncommitted
server, console, ignore rules and tests. Retained the working implementation.
The server runs with `python3 -m lite`, uses only the Python standard library,
and defaults to `0.0.0.0:7777`. Configuration comes from the documented environment
values, with `TIINY_DATA_DIR` or `--data-dir` for local files.

One worker serializes turns. Every real model request holds `lite/onelane.py`'s
lane. Device error 150004 and HTTP 502/503/504 receive exponential backoff with
jitter and a 90-second retry budget. A response that has already emitted content
is not replayed. Ordinary turns request 1,000 output tokens, streaming, and
`chat_template_kwargs: {"enable_thinking": false}`. Reasoning deltas are not shown.
The timeout for one upstream request is 120 seconds; the retry budget is not a
90-second deadline for the entire turn, including lane acquisition and inference.

Data initialization creates memory, skills, routines, files, transcripts and
handbook folders, editable `persona.md`, and `keys.json` at mode 0600. JSON and
persona writes are atomic. Memories normalize whitespace, reject more than 500
characters and deduplicate by normalized text. The persona is read fresh for
each turn. The skill catalog is included in the prompt.

The echo model reverses the submitted prompt. Selfcheck exercises one configured
turn and prints budget and timing evidence without exposing the key or reply.

## Ported unchanged

Source comparison tests verify byte-identical copies of:

- `tokens.css`, `motion.css`, `backgrounds.css`, `mascots.css`, `boot.css`.
- `settings.css`, `files-viewer.css`, `voice-call.css`.
- `mascots.js` and `voice-call-avatar.js`.
- The Titan mascot kit and Titan curious, calm and excited PNGs against the
  repository's console assets.

The inline code-chip renderer and repeated-row folding function also match the
vendored source exactly. The LAN clipboard fallback, Spoken chip, transcript
scroll behavior, keyboard-aware composer, drawers and jump-to-newest behavior
remain in the extraction. Static checks confirm the phone inset properties and
related source contracts; they do not measure rendered geometry.

## Changed

- `lite/server.py`, `lite/__init__.py`, `lite/__main__.py`: retained the new local
  server and entry point. First-paint resource measurement now reads the door's
  HTML and referenced assets through urllib. It also accepts an HTTP base URL
  for testing served bytes when sockets are permitted.
- `lite/console/index.html`, `door.js`, `door.css`, `console.html`: a lightweight
  branded door loads the larger console only after entry. Both the door and
  Settings About link the Ti mark and required attribution to Titanium Bot.
- `app.js`: extracted renderer and composer with one conversation and small
  files, memory, skill and routine panels. Fixed duplicate submissions while a
  send is pending. No host job bus or marketplace adapter remains.
- `lite-adapter.js`: a 95-line adapter uses the local routes. SSE frames schedule
  a state refresh in a fixed 900 ms window, so continuous tokens cannot starve
  refresh. It preserves older transcript pages and propagates route refusals.
- `settings.js`: General, Model, Usage and About retain the section and
  contributor seams, with local settings persistence and a measured budget row.
- `bg-boot.js`, `backgrounds.js`: three plates, local background persistence and
  pre-stylesheet background selection when entering the console. Plates and
  thumbnails total 205,866 bytes, outside the initial door load.
- `mascot-crew.js`: one Titan; `styles.css`: retained relevant console and phone
  blocks. `boot-cover.js` extracts the existing boot behavior and ceiling.
- `files-viewer.js`: local `/api/file` URLs. `voice.js`: local settings path and
  consistent unwrapping of the settings response's `voice` object.
- `tests/test_server.py`, `tests/test_console.py`, `tests/adapter-contract.cjs`:
  route, reader, retry, budget, provenance and adapter coverage.
- `.gitignore`: retained exclusions for local data, Python caches and OMX state.
- `README.md`: ten-minute setup, two environment values, hidden key entry,
  phone access, echo mode, checks, data location and current limits.

## Dropped

Both old adapters, marketplace, screen tile, cloud browser, code tasks, gap
badge and provenance chips, push, account menu, bot setup, demo data, host
status, mail, box handoff and teach mode are absent from the port. The extra
background plates, non-Titan sprites and design-reference image do not ship.
Removed the earlier attempt's stale `visual-verification.json`; it is not
evidence for this browser-free run.

## Route coverage and current boundaries

All twelve entries in `docs/console-pieces.md` section 11 are dispatched,
including `/events` (that table counts SSE as one of the twelve).

| Route | Current behavior |
| --- | --- |
| `GET /api/state` | One Titan, transcript tail, files, skills and routines |
| `GET /events` | Changed poke plus heartbeat comment |
| `POST /api/send` | JSON or multipart; queues a turn and returns the user row |
| `GET /api/transcript` | Bounded pagination and older-page flag |
| `POST /api/decide` | Validates decisions; 404 because no approval producer exists yet |
| `GET /api/models` | Device model list and configured live model |
| `POST /api/model` | Selects an existing model ID; lifecycle and other connections return 501 |
| `GET /api/settings` | Full settings, persona, usage, version and budget |
| `PATCH /api/settings` | Validated merge and complete response; unavailable voice enabling returns 501 |
| `GET /api/library` | Memory, skill and routine lists |
| `POST /api/library` | Remember/forget; skill enable/disable/run; routine actions return 501 |
| `GET /api/file` | Restricted file bytes, content type, strong ETag and conditional GET |

## Verification

`python3 -m unittest -v`: **26 tests, 23 passed, 3 skipped**, exit 0.
The skipped tests require binding a real HTTP server; this sandbox denied it.
They cover echo HTTP, the actual JavaScript adapter, and door assets/SSE through
urllib. The adapter test evaluates the real adapter in Node with a small
EventSource shim; its HTTP transport calls Python urllib. It does not launch a
browser. Its live transport behavior remains unverified in this session.

Completed checks include Python compileall and AST parsing, every console
JavaScript file through `node --check`, source comparisons, README copy and
whitespace checks, and `git diff --check`. There is no configured external
linter or typechecker, and none was installed. Offline wire tests exercise the
real HTTP handler with in-memory request/response streams, including errors,
multipart upload, private-file refusal, settings merges, ETags and SSE framing.

Latest standalone selfcheck results:

| Measurement | Echo | Configured device |
| --- | ---: | ---: |
| Idle high-water RSS | 29.69 MB | 30.09 MB |
| Door resource bytes | 21,574 | 21,574 |
| Fresh-process initialization | 61.50 ms | 65.29 ms |
| First token | 1.23 ms | No token |
| Turn duration | 37.94 ms | 5.81 ms to connection failure |
| Reply characters | 23 | 0 |
| Budget passed | Yes | Yes |
| Configured turn passed | Yes | No |

Commands were `TIINY_MODEL=echo python3 -m lite --selfcheck --data-dir
data/selfcheck-echo` and `python3 -m lite --selfcheck --data-dir
data/selfcheck-device`. The latter used the existing device environment without
printing it and returned the sanitized cannot-reach-device error.

RSS is the process high-water mark before inference. Cold start includes fresh
interpreter startup and App initialization, but not HTTP bind/readiness. Door
bytes were read with urllib file URLs because HTTP binding is forbidden here.
They count the initial HTML, styles, script, favicon, Ti mark and still Titan
once each. They are not a visual first-paint time, transferred compressed bytes,
or the cost of opening the deferred console. HTTP byte comparison is implemented
in the skipped integration test.

## Deviations and reasons

1. **No commits could be created.** The first checkpoint's `git add` failed with
   `Unable to create .../.git/index.lock: Operation not permitted`. This session
   explicitly grants only read access to `.git` and does not allow approval
   escalation. No alternate repository or permission bypass was attempted.
   All deliverables remain uncommitted. Intended checkpoints are server,
   console port, development selfcheck, tests, then owner README/report.
2. **Real HTTP and device acceptance are incomplete.** Socket binding was
   denied and the configured-device selfcheck could not connect. Offline tests
   are useful evidence, but do not substitute for these acceptance checks.
3. **The app extraction is smaller than the estimated source ranges.** The
   retained attempt has 681 app lines, 3,347 style lines, 95 adapter lines and
   75 settings lines. It keeps the relevant renderer/composer behavior and
   replaces the one-owner panel wiring, rather than retaining thousands of
   unreachable fleet dependencies. Original profile editor, command palette and
   first-run onboarding flow are not ported; persona editing is in Settings,
   and first-time setup is currently a persona instruction. This is narrower
   than the brief's literal keep-range request and needs acceptance review.
4. **Boot begins on console entry.** The small door defers the console, live
   mascot and background assets to meet the initial-byte budget. The boot cover
   is the first child of the mounted console, with its 8,000 ms ceiling armed
   then, rather than at initial document parsing.
5. **Three Titan mood sprites ship.** Curious, calm and excited are the kit's
   referenced still states. This resolves the document's inconsistent sprite
   pair versus Titan-still wording without shipping the other characters.
6. **Later-step features have explicit refusals.** The contract itself assigns
   model lifecycle/LAN/cloud to step 2, tools and agent memory work to step 3,
   cron to step 4 and speech transport to step 5. Consequently no fabricated
   approval card, start/stop success, cloud credential form, cron execution or
   voice session is returned. The related Settings controls explain the limit.
   Voice and the call-screen assets ship but are not loaded by the entry flow.
7. **Agent formats precede the complete loop.** Persona, memory reader/writer,
   handbook summary and skill catalog are present. Seeded handbook packs,
   automatic memory extraction, five callable tools, first-run kickstart,
   cron scheduling and attachment-to-model content are not implemented here.
   Manual skill run sends its body as a normal prompt. These belong to later
   delivery steps; uploaded files are stored and viewable only.
8. **The default lane folder is local.** To keep runtime writes in the project,
   Lite defaults the lock folder to its data directory. Coordination with
   another application requires both to set the same `ONELANE_DIR`, documented
   in the README. The copied onelane implementation is unchanged.
9. **No visual validation.** The user's no-GUI instruction precludes a rendered
   touch-target sweep, phone keyboard checks and layout/paint assertions. Static
   source checks do not establish those properties. Server support currently
   targets Mac/Linux because onelane uses `fcntl` and RSS uses `resource`.

## What step 2 needs

First rerun the three skipped HTTP tests and the configured-device selfcheck in
an environment that permits LAN/loopback connections. Review the narrower app
extraction and create the requested checkpoint commits with writable git access.

Then implement and verify the device management surface separately from the
OpenAI inference base: model list/running state, start, stop, and safe switching
while turns are queued. Add LAN and cloud connection configuration, masked
credential entry, atomic 0600 persistence, non-echoing responses, and source
tracking. Preserve the shared device lane for every management and inference
call, and verify host routing against the actual device before assuming the
management API uses the inference host. Test refused loads and busy retries as
well as successful operations. Later steps can add the tools, seeded skills,
memory extraction, cron engine and speech bridge to the retained console seams.

## Step 1b

Date: 2026-09-11. Implementation and offline verification complete. No browser
or GUI was launched. This section supersedes Step 1's port and configuration
notes above. Commit creation remains blocked by the session's read-only `.git`.

Changes:

- `lite/server.py`: default port is 7788. A busy port prints one sentence naming
  the chosen port, `--port` and the selected data directory's `config.json`, then
  exits 1 without a traceback. Other bind failures have a separate plain error.
- First run creates `<data dir>/config.json` with all five fields: `base`,
  `model`, `port`, `bind` and `name`. The data directory defaults to `./data`;
  `--data-dir` takes priority over `TIINY_DATA_DIR`. Settings resolve command
  line, then the specified environment variables, then config, then defaults.
  Keys remain separate in `keys.json` with mode 0600; environment/CLI overrides
  are not copied into config. `--show-config` prints effective settings with
  the key masked and does not initialize the app or contact the device.
- `default` discovers the first chat model before inference rather than sending
  the literal placeholder. Explicit model IDs bypass discovery; an empty chat
  model list returns an actionable refusal. Discovery skips embedding IDs and
  explicitly non-chat types; untyped model entries are treated as chat models.
- Settings and the existing model route share configuration persistence through
  the existing atomic writer. Base, model and assistant name survive restart.
  Effective command-line/environment overrides continue to win after a save.
  Active or queued turns prevent connection changes.
- `lite/console/settings.js`: Model exposes address and model inputs even when
  the device cannot be reached. It saves both through the settings route and
  explains when an override remains effective. Device model discovery supplies
  optional suggestions.
- `lite/VERSION` contains `0.1.1`; `lite/__init__.py` reads it as the single
  version source. `--version` and the existing Settings About row show it.
- `README.md`: updated startup addresses, documented every config field and
  override, masked inspection, and version rules: increment the final number
  for every change; change the middle number only when Jason says so.
- `tests/test_config.py` adds defaults, precedence, key permissions/masking,
  busy-port output/exit, malformed config, version, persistence and default
  model discovery tests. `tests/test_server.py` now checks config persistence
  and that the environment still overrides a model saved through the route.

Verification:

- `python3 -m unittest`: **34 tests, 31 passed, 3 skipped**, exit 0. The three
  existing live HTTP tests were skipped because this sandbox denies loopback
  binding. Busy-port behavior was verified by injecting `EADDRINUSE` at server
  construction; settings routes were exercised with the real in-memory HTTP
  handler. No real port collision or device discovery is claimed verified.
- `python3 -m compileall -q lite tests` passed. The suite parsed every console
  JavaScript file with Node; the final settings change also passed `node --check`.
  `git diff --check` passed. No external linter/typechecker is configured and
  no dependency was added.
- `python3 -m lite --version` printed `0.1.1`.
- Echo selfcheck (`TIINY_MODEL=echo python3 -m lite --selfcheck --data-dir
  data/selfcheck-1b`) passed: RSS 29.66 MB, initial door 21,574 bytes,
  fresh-process initialization 58.43 ms, first token 1.07 ms, turn 39.94 ms.

Remaining limits: live HTTP/device and visual behavior remain unverified here.
Legacy base/model entries in `keys.json` are no longer configuration sources;
use Settings > Model to save them in config. Existing `settings.json` botName
is superseded by config's name. The requested checkpoint could not be committed:
`git add` failed with `Unable to create .../.git/index.lock: Operation not
permitted`. No permission bypass was attempted; all Step 1b changes remain
uncommitted. Intended Lore intent line: `Keep Lite configuration persistent and
its console separate from the full product relay`.

Step 1c (2026-09-11): `lite/server.py` now checks TCP connections to
127.0.0.1 and ::1 with a 200 ms timeout before binding, refusing an accepting
listener with the existing single sentence and exit 1. Server address reuse
(SO_REUSEADDR) is disabled; the existing bind-error handler is reused.
`tests/test_config.py` adds IPv4/IPv6 refusal and free-port startup coverage,
plus a subprocess regression using a throwaway 127.0.0.1 listener on a spare
port. `lite/VERSION` advances to 0.1.2 under the per-change version rule.
Verification: `python3 -m unittest` ran 37 tests, 33 passed and 4 skipped
(sandbox denies socket binding, including the new real-listener regression).
The mocked refusal test failed before the fix and passed afterward.
Compileall, JavaScript syntax checks in the suite, and `git diff --check`
passed; no external linter/typechecker is configured. Live socket behavior
remains unverified in this sandbox. No dependencies, browser, or GUI were
used. Only these four files changed; no commit was attempted as instructed.

## Step 1d

Date: 2026-09-11. Branding and model detection implemented; offline checks pass.
Device selfcheck was executed but could not connect, so live device acceptance
remains unverified. No browser or GUI was launched, no device key was printed,
no dependency was added, and no commit was attempted. The starting tracked tree
was clean; the uncommitted changes are limited to this step.

Changed files and behavior:

- `README.md`, `SPEC.md`, `lite/console/index.html`, `console.html`, and
  `settings.js`: product name is Titanium Tiiny Bot in the page title, door
  headline, header caption, About, and documentation. Command/package names
  remain unchanged. The Titanium Bot attribution remains linked to
  https://titanium.bot.
- `lite/console/brand/tiiny-logo.svg`: byte-identical copy of the provided
  `brand/tiiny-logo.svg`. Door, console header, and About link the Tiiny mark
  and “Built for” text to https://tiiny.ai. Logo heights are 20 px on the door
  and About, and 16 px in the header. `door-resources.json` includes the asset.
- `lite/console/door.css` and `styles.css`: the provided logo is white, so a
  Midnight (#090d14) pill supports it across themes. Calculated sRGB contrast
  for the white logo and “Built for” text is **19.46:1**. Door headline contrast
  is **14.42:1**, secondary text **9.72:1**. Header attribution remains present
  at phone widths. These are source-based color calculations, not rendered
  layout measurements.
- `lite/server.py`: replaced the narrow chat/text/llm type allowlist with one
  shared chat detector and resolver. `supports_chat: true` qualifies a row;
  an explicit false excludes it. Only when the field is absent, capabilities
  containing `main` or a type containing `Text-to-Text` qualify it. `default`
  resolves to the first matching row. Unknown/untyped rows no longer qualify.
  Explicit model IDs still bypass discovery. Inference and the model-list
  route share the resolver, avoiding separate selection rules.
- Resolved IDs appear in Titan's card after discovery or inference, and in
  Settings > Model. The saved model remains `default`. Empty discovery and
  connection changes clear the prior resolution; Settings displays “Not yet
  available” when unresolved. State/settings reads do not initiate network calls.
- `tests/test_config.py`: the exact Ornith row with `supports_chat`,
  `Image-Text-to-Text`, `capabilities`, and `supported` reproduced the original
  refusal before the fix and passes afterward. Tests cover precedence,
  fallbacks, first-match selection, explicit IDs, display API fields, and stale
  resolution clearing. `lite/VERSION` advances from **0.1.2 to 0.1.3**.

Verification:

- `python3 -m unittest`: **39 tests, 35 passed, 4 skipped**, exit 0. Skips are
  the existing socket-dependent tests because this sandbox denies binding.
- `python3 -m compileall -q lite tests` and `git diff --check` passed.
  JavaScript syntax checks passed through the suite and `node --check`.
  No external lint/typecheck tools are configured. Terminal HTML/asset checks
  verified the product text, links, logo heights, source-copy equality, and
  resource-manifest entry. `python3 -m lite --version` printed `0.1.3`.
- Device command: `python3 -m lite --selfcheck --model default --data-dir
  data/selfcheck-1d-device`, using the existing environment credential without
  printing it. `--model default` explicitly exercises discovery.

| Device selfcheck measurement | Result |
| --- | ---: |
| Idle high-water RSS | 29.75 MB |
| Initial door resources | 23,197 bytes |
| Fresh-process initialization | 61.78 ms |
| First token | None |
| Turn duration to connection failure | 4.52 ms |
| Reply characters | 0 |
| Budget passed | Yes |
| Configured device turn passed | No (exit 1) |

The sanitized failure was “Cannot reach the device. Check its address and that
its model is running.” These numbers establish the local budget only; they do
not establish live Ornith response performance. Live device inference, socket
integration, and rendered layout remain the verification gaps. The report and
all implementation changes are left uncommitted as instructed.

## Step 1e

Date: 2026-09-11. Added one decorative `tiiny-watermark` image using
`brand/tiiny-logo.svg` to each of `lite/console/console.html` and `index.html`.
`styles.css` fixes the console mark at the viewport centre, above the photograph
and ambient layers (z-index 0) and below the stage/transcript (z-index 2).
`door.css` fixes the door mark at the same centre behind its content (z-index 1).
Both marks ignore pointer events and have no filter/blur. No plate assets,
picker behavior, or plate styling changed.

Computed CSS opacity is **0.08** on Titan Nebula and Deep Current, **0.12** on
the light Misty plate (`data-bg="bg1-misty"`), and **0.08** on the door.
The default rule also keeps the mark present on custom plates at 0.08.
Opacity follows the selected built-in plate, independently of the UI theme.

Expected image element bounding boxes in CSS pixels, calculated rather than
rendered: console width = max(220, min(0.40 × viewport width, 520)); door width
= 0.24 × viewport width, with no minimum or maximum requested for the door.
The SVG's 120 × 42 viewBox gives height = width × 0.35. Both use x =
(viewport width − image width) / 2 and y = (viewport height − image height) / 2.

| Page | Viewport | x | y | Width | Height |
| --- | --- | ---: | ---: | ---: | ---: |
| Console | 1280 × 800 | 384 | 310.4 | 512 | 179.2 |
| Console | 390 × 844 | 85 | 383.5 | 220 | 77 |
| Door | 1280 × 800 | 486.4 | 346.24 | 307.2 | 107.52 |
| Door | 390 × 844 | 148.2 | 405.62 | 93.6 | 32.76 |

`tests/test_console.py` adds one test checking exactly one watermark per page,
its class, asset, decorative attributes, and expected inline sizes.
`lite/VERSION` advances from **0.1.3 to 0.1.4**, with existing version assertions
in `tests/test_config.py` updated accordingly. The only other changed file is
this report. No dependencies or new abstraction were needed.

Verification: `python3 -m unittest` passed with **40 tests, 36 passed and 4
skipped** (existing socket tests cannot bind in this sandbox). Python compileall
and `git diff --check` passed; the suite includes JavaScript syntax checks.
No separate lint/typecheck tools are configured. No browser or GUI was launched.
Rendered measurement and visual comparison remain for the orchestrator, as
requested; these bounds and opacity values are source-based calculations.

## Step 3

Date: 2026-09-11. Implemented in the requested order: tool loop, memory,
skills, persona, console fixes, then tests and delivery. Version **0.1.5**.
This section supersedes the earlier report's statements that automatic tools
and seeded skills are unavailable. No browser or GUI was launched, no device
key was printed, no dependency was added, and no commit was attempted. The
starting tracked tree was clean; only this step's changes remain uncommitted.

Changed files and behavior:

- `lite/server.py`, `lite/tools.json`, `lite/agent_tools.py`: ordinary turns
  send the five OpenAI function schemas, assemble streamed tool-call fragments,
  execute each call and send its result back to the model. The loop permits six
  tool rounds, then requests a final answer with tools disabled. Final text is
  streamed through the existing transcript updates. Receipts use the console's
  existing `system`, `text`, `detail` shape, with tool-call IDs; refusals are
  visible both to the model and in the transcript. Thinking starts off; two
  empty replies trigger one retry with thinking enabled. Error 150004 and
  HTTP 502/503/504 retain the existing lane and backoff, without replaying text
  already emitted.
- Read and Write accept only paths inside `files/`, reject traversal and
  symlinks, and use the existing atomic writer. Uploaded file paths reach the
  model so it can read uploaded text. Public URL retrieval has a 10-second
  timeout and 200,000-byte body cap, accepts text only, refuses redirects and
  compressed responses, rejects non-public addresses, and connects directly
  to the checked IP without another DNS lookup or ambient proxy. Page contents
  are marked as untrusted information.
- Memory uses one normalized, dated fact per line. More than 500 characters
  is refused with an explanation, never sliced. Default facts go to
  `memory/log/YYYY-MM.md`; profile facts go to `memory/profile.md`. Every turn
  includes all profile facts and the most recent 40 log facts. Duplicate
  facts are not added again; forgetting uses the existing memory writer path.
  Routine tools can save, update, pause and delete disabled drafts with valid
  five-field cron schedules; resume and execution remain unavailable until
  Step 4.
- `lite/seeds/persona.md` and four `lite/seeds/*/SKILL.md` files seed new data
  directories without overwriting owner edits. Never-ask, plain-words and
  onboarding were trimmed from the original source seed files at the location
  documented in `docs/agent-pieces.md`; those seeds were not present in this
  checkout's `vendor/`. The capability handbook was rewritten for this device.
  The persona copies the supplied block, including BEFORE, never-ask and the
  first-question rule. The prompt clarifies the current local credential
  configuration, since a masked Settings credential box is not yet built.
  A first-run greeting immediately asks “What should I call you?” and is
  persisted once; subsequent interview turns use the model and onboarding skill.
  The greeting itself is locally seeded and does not require inference.
- Skill catalogs include names, descriptions, paths and disabled status.
  `run_skill` inserts an enabled skill's body into the conversation. The reader
  supports folded descriptions, the documented field limits, and the 16,000
  character inlining limit. Onboarding retains the five owner slots and saves
  profile facts through `update_state`, without unavailable onboarding tools.
- `lite/console/app.js`, `styles.css`, `settings.js`: the roster name and status
  have separate layout classes; transcript avatars use the coloured Titan
  mascot kit sprite. Settings > General retains the persona editor, and About
  states which capabilities belong to full Titanium Bot.
- `tests/test_agent_tools.py`, `tests/test_seeded_persona.py` add the Step 3
  regressions. `tests/test_server.py` explicitly starts existing route fixtures
  after the separately tested greeting. `tests/test_config.py` follows the
  version bump in `lite/VERSION`. `README.md` describes the working tools and
  current limits. This report was renamed to `docs/REPORT.md`, and references
  in README and the Step 1/1B/1C/1D/1E/3 briefs were updated.

Simplifications: retained one serialized worker and five tools, reused atomic
writes, memory validation and existing receipt rendering, and added no shell,
browser runtime, framework or third-party dependency.

Verification:

- `python3 -m unittest`: **56 tests, 52 passed, 4 skipped**, exit 0. The skips
  are existing live-socket tests denied by the sandbox. Offline coverage includes
  a fake device tool call followed by a final answer, fragmented streamed tool
  calls, receipts, retry/backoff, thinking recovery, round limits, traversal and
  symlink refusals, memory cap/refusal feedback, latest-40 recall, catalogs,
  run_skill, seeding/restart/persona edits, routine drafts and fetch restrictions.
- `python3 -m compileall -q lite tests` and `git diff --check` passed. The suite
  checks all console JavaScript with Node. No separate linter or typechecker is
  configured. `python3 -m lite --version` printed `0.1.5`.
- CLI echo selfcheck passed: **29.88 MB** idle high-water RSS, **23,490 bytes**
  of initial door resources, **58.16 ms** fresh-process initialization,
  **1.98 ms** to first token and **43.66 ms** for the turn. All local budgets
  passed; these are echo measurements, not device-inference measurements.

Remaining verification limits: live device inference, public-network fetching
and socket integration were not verified here. Console fixes were checked from
source, without rendered visual inspection as instructed. Routines still do not
run on a clock, voice is not connected, and pictures/PDFs are not decoded for the
model; those remain later-step capabilities. Owner-edited existing personas and
skills are preserved rather than overwritten on restart.

## Step 4

Implemented routines on cron and recognition of an already-running Lite process.
Version: **0.1.6** (last component incremented from 0.1.5).

Changes, in the requested order:

1. `lite/cron.py`, `lite/routines.py`, `lite/server.py` and
   `lite/agent_tools.py`: added a stdlib five-field cron parser/matcher with
   wildcards, steps, ranges, lists, Sunday as 0 or 7, and traditional OR semantics
   when both day-of-month and weekday are restricted. Schedules use server-local
   time. A scheduler thread checks routine files every 30 seconds and feeds the
   existing serialized turn worker and device lane. Startup calculates strictly
   future occurrences, so downtime is never replayed. One occurrence per routine
   can be pending at a time; missed minutes and a full queue do not build a backlog.
   Accepted queued turns wait for the worker. Paused, deleted or rescheduled jobs
   are checked again before execution.

   Existing Step 3 storage is preserved: `routines/<id>/routine.json`, with
   `name`, `prompt`, `schedule`, `enabled`, `createdAt` and `lastRunAt`, beside
   `runs.json`. History holds the latest 20 records with a start time, finish
   time, running/ok/error status and result or error detail. Results and tool
   receipts use a separate `transcripts/routine-<id>.json` conversation named
   for the routine, available through the transcript API and View results.

2. `lite/console/app.js`, `lite/tools.json`, `lite/server.py`, `README.md` and
   the capability, plain-words and onboarding seed skills: wired Enable, Pause,
   Delete and View results in Routines; exposed actual enabled state and next
   run time. `update_state` supports enable/resume, pause, update and delete.
   Creation always saves disabled, even with `enabled: true`. Successful tool
   turns that create routines include a switched-off notice in Titan's reply.
   The same turn cannot immediately enable its new draft, and scheduled prompts
   cannot enable routines. Existing owner-edited skills and personas remain intact;
   the live prompt supplies the current routine capability and owner-enable rule.

3. `lite/server.py`: added `GET /api/health` with Lite's identity and version.
   On a busy port, a bounded loopback health probe recognizes this version of Lite,
   prints exactly `Titanium Tiiny Bot is already running at http://localhost:<port>`
   and exits 0. Other listeners retain the busy-port sentence and exit 1.

4. `tests/test_routines.py` adds the twenty-row cron expression/time table,
   next-date checks, due-once behavior, disabled and missed-run checks, restart
   scheduling, lifecycle HTTP routes, separate transcripts and tool receipts,
   failure history and worker survival, queued pause and serialization, capped
   history, running status, actual device-lane acquisition with mocked transport,
   creation notices and health identity checks. Updated obsolete Step 3 assertions
   in `tests/test_agent_tools.py`, `tests/test_server.py` and
   `tests/test_config.py`; added the already-running sentence/exit regression.
   `lite/VERSION` contains 0.1.6. This section records the completed step.

Simplifications: reused the existing queue, tool loop, device lane, transcript
format, atomic writer and library mutation route. Cron validation and execution
share one parser. No third-party dependencies or separate routine executor.

Verification:

- `python3 -m unittest`: **68 tests, 64 passed, 4 skipped**, exit 0.
  The four existing skips are sandbox-denied live-loopback tests; offline HTTP
  wire contracts and mocked health/device transport checks passed.
- `python3 -m compileall -q lite tests`: passed.
- Console JavaScript syntax checks with Node: passed as part of the suite.
- `git diff --check`: passed, exit 0. macOS emitted sandbox cache/FSEvents
  diagnostics during Git startup, without a diff-check failure.
- `python3 -m lite --version`: **0.1.6**.
- No separate linter or typechecker is configured. No browser or GUI was launched.

Remaining verification limits: live device inference and real-socket startup
recognition were not exercised in this sandbox. Console controls were checked
through source/syntax and HTTP contracts, without rendered visual inspection.
A pause stops future/queued work; a turn already executing can finish. Schedules
follow the server's local timezone, and queue saturation skips occurrences rather
than accumulating unbounded work. Voice and model start/stop remain later steps.
No commit was attempted; the initially clean tree contains only this step's changes.

## Step 3b

Cause: the captured device call uses `update_state({"target":"memory","text":"…"})`, but Lite required `action` and `fact`, so it refused the assembled call instead of saving the memory.

Version: **0.1.7**, incremented from 0.1.6.

Changed files:

- `lite/server.py`: accepts the device's shorthand memory write, mapping `text`
  to the existing fact validator and defaulting a missing action to `write` only
  when `text` is present. Explicit actions and canonical `fact` values retain
  precedence; memory length, type, path and tier checks still apply.
- `lite/server.py`: adds stdlib file logging. Start with `LITE_DEBUG=1` for loop
  request/round/options, lane wait/release, request sent, cumulative stream chunk
  kinds, finish reasons, assembled tool name and argument length, executed tool
  result length, and final transcript text start/finish/status/length. Diagnostics
  go to `<data dir>/lite.log`; exception tracebacks are written there even when
  debug is off. The configured API key is redacted, and ordinary progress records
  contain lengths rather than prompt, argument or result contents. File handlers
  close on shutdown and configuration replacement.
- `tests/test_device_turn.py`: replays the unchanged
  `tests/fixtures/device-stream-tool-call.sse` through `App.send`, the queued
  worker, real `Device.chat`/SSE parsing, real OneLane lock, tool execution and
  transcript persistence. Only HTTP transport is faked. With the first-run
  greeting and seed setup still present, it asserts the Biscuit fact is saved,
  the tool-call ID and successful result reach the second request, and the final
  streamed answer reaches the persisted transcript within one second. It also
  checks lane reacquisition, debug milestones, shorthand validation, refusal
  tracebacks, debug-off error logging, key redaction and recovery on the next turn.
- `tests/test_config.py` and `lite/VERSION`: update version assertions and the
  release number. `docs/REPORT.md`: this section.

Regression evidence: before the fix, the captured-stream test failed with an
empty memory list. After the fix it passes, including the one-second bound.
Fragment assembly, `[DONE]` handling, the second request and lane release all
worked with this fixture; no lock or stream-parser rewrite was needed.

Simplifications: reused the existing memory validator/writer, tool-result
feedback, serialized worker and transcript path. No new dependencies.

Verification:

- `python3 -m unittest -q`: **72 tests, 68 passed, 4 skipped**, exit 0.
  The skips are the existing sandbox-denied live-loopback tests. The suite also
  checks console JavaScript syntax using Node without a browser.
- `python3 -m compileall -q lite tests`: passed.
- `python3 -m lite --version`: **0.1.7**.
- `git diff --check`: passed. Git's macOS startup emitted sandbox cache/FSEvents
  diagnostics without failing the check.
- No separate linter or typechecker is configured. No browser or GUI was launched,
  and no commit was attempted.

Remaining limits: the fixture proves and fixes the refused memory write, but it
cannot reproduce or establish the complete cause of the observed 270-second
live-device silence. With the fake final response, the pre-fix loop still reached
that answer after refusing the tool. Live inference and device timing remain
unverified; the new log milestones expose where a future device turn waits or
fails. Debug logging is opt-in and appends to `lite.log` without rotation.

## Step 5

Version: **0.1.8**, incremented from 0.1.7. Completed in the requested order:
server, console transport, General settings, tests and release/report updates.

Changed files:

- `lite/voice.py` and `lite/server.py`: multipart voice turns select the first
  ASR/type-or-capability match and first TTS type match, transcribe on the device,
  enqueue an ordinary tool-loop turn, persist the person's Spoken line and Titan's
  reply, and return `{heard, said, audio}`. Speech settings expose the four requested
  fields. All device requests hold OneLane. TTS requests contain model and input,
  with no voice field. Private WAV files expire after one hour. TTS loads once per
  active session, releases after five idle minutes or shutdown/configuration change,
  and its remembered model can reload even when absent from the loaded-model list.
- `lite/console/voice.js`: replaces the WebSocket transport with MediaRecorder
  uploads and WAV playback. Push-to-talk posts on release. Always-listening uses
  eight-second recording windows, an energy gate and 700 ms of quiet. Playback and
  microphone analysers feed the existing avatar seam; playback plus a 350 ms echo
  tail suppresses recording. Mute, stop and cancelled microphone acquisition release
  resources. The five call-screen words, desktop strip and vendored avatar remain.
- `lite/console/settings.js`: General offers Off, Push to talk and Always listening,
  with read-only device speech-model names.
- `tests/test_voice.py`, `tests/voice-contract.cjs`, `tests/test_console.py`,
  `tests/test_server.py` and `tests/test_config.py`: cover fake-device HTTP, ordinary
  tools and persisted speech, exact missing-ASR wording, model selection, expiry,
  lifecycle, settings, recording gates, playback, cancellation and updated version.
- `lite/VERSION` and `docs/REPORT.md`: release number and this report.

Simplifications: reused the existing queue, tool loop, transcript renderer,
Spoken chip, settings persistence and call-screen avatar. No new dependencies.

Verification:

- `python3 -m unittest`: **88 tests, 84 passed, 4 skipped**, exit 0. Skips are
  the existing sandbox-denied live-loopback tests; wire-level HTTP tests run.
- `node tests/voice-contract.cjs`: passed with fake audio objects, no browser.
- `python3 -m compileall -q lite tests`: passed. The suite also checks all console
  JavaScript syntax and verifies the unchanged avatar against its vendored source.
- `git diff --check`: passed despite macOS sandbox cache/FSEvents diagnostics.
- `python3 -m lite --version`: **0.1.8**. No separate linter/typechecker is configured.

Remaining limits: physical-device ASR/TTS and real microphone, speaker and rendered
console behavior are not measured here. Recording requires microphone access in a
secure browser context and MediaRecorder WebM or WAV support. The orchestrator owns
console measurement. No browser or GUI was launched, and no commit was attempted.

## Step 6a

Version: **0.1.10**, incremented from 0.1.9.

Changed files:

- `lite/__init__.py`: capture the monotonic start before the remaining package
  imports so the CLI measurement includes imports and App construction.
- `lite/server.py`: replace the child-process readiness probe with a temporary
  same-process HTTP server, served in a daemon thread on a loopback spare port.
  Measure through the first successful `GET /api/health`, bypass proxy settings,
  and shut down, join and close the probe before measuring the model turn.
  Preserve printed metrics and the RSS, first-paint and cold-start budget checks.
  The existing CLI constructs and closes the App; no second App is needed.
- `lite/VERSION`, `tests/test_config.py`: bump the release and version assertions.
- `tests/test_server.py`: cover readiness, failed health responses, timeouts,
  over-budget startup, thread/socket cleanup and forbidden process-launch text.
  Retain the real CLI test, skipping only when loopback binding is denied.
- `docs/REPORT.md`: this section.

Simplifications: removed child-process, pipe and selector management; reused the
existing App, Server and health endpoint. No dependencies added.

Verification:

- `python3 -m unittest`: **101 tests, 96 passed, 5 skipped**, exit 0. The skips
  are sandbox-denied loopback tests, including the new HTTP startup probe.
  Mocked probe success/failure, cleanup and budget checks passed.
- `python3 -m compileall -q lite tests`: passed.
- `rg -n 'subprocess|os\.system' lite`: **zero matches** (exit 1).
- `python3 -m lite --version`: **0.1.10**.
- `git diff --check`: passed; macOS emitted sandbox cache/FSEvents diagnostics.
- No separate linter or typechecker is configured. The suite includes console
  JavaScript syntax checks. No browser or GUI was launched; no commit attempted.

Remaining limits: actual loopback readiness timing and physical-device inference
cannot be verified in this sandbox. The measurement begins at package import in
this process, excluding interpreter launch; direct embedded calls long after
import include that elapsed time and are not fresh CLI startup measurements.

## Audit, 2026-09-13

Version: **0.1.12**, incremented from 0.1.11. The full gap table, the method and every
measurement are in `docs/AUDIT-2026-09-13.md`; this section records only what changed.

This was the first pass run on a machine that could bind sockets and drive a real browser, so it
is also the first time the console was measured rather than read. `python3 -m unittest` ran
**101 tests, 101 passed, 0 skipped** before the changes: every loopback test the earlier steps had
to skip now runs. Lite was started on a spare port, one chat turn was sent through `POST /api/send`
and read back through `GET /api/transcript`, and the console was driven in headless WebKit at
1440x900 and 390x844 with screenshots in `docs/audit-shots/`.

Four defects, each its own commit with a test:

- **Voice shipped in step 5 and no page could reach it.** `door.js` never loaded `voice.js` or
  `voice-call-avatar.js`, and `app.js` held a click handler on the Talk button that raised a toast
  saying voice was not connected. Measured before the fix: `window.__voice` undefined at both
  sizes. Both modules now load before `app.js` and nothing intercepts the press.
- **No file row opened.** `app.js` writes `data-attachment-open` on every memory, skill and
  attachment and nothing read it, so `window.__filesViewer.open` was never called. One delegated
  listener routes them all, and the viewer reads the kind off the path rather than the label, so a
  skill filed under its frontmatter name opens as the markdown in its `SKILL.md`.
- **Two product names in the terminal.** The ready line said Titanium Bot Lite, `--stop` said
  Titanium Tiiny Bot, and the base prompt told the model a third thing. Everything a person reads
  now says Titanium Tiiny Bot; `titanium-bot-lite` stays as the package and health identity.
- **No microphone chooser.** `docs/console-pieces.md` section 4 keeps that row in General. The
  server has carried `micDeviceId` since step 1 and `voice.js` has exported the whole API; only
  the row was missing.

After: `python3 -m unittest` ran **105 tests, 105 passed, 0 skipped**, exit 0.
`python3 -m compileall -q lite tests` and `git diff --check` passed. The echo selfcheck passed at
**41.62 MB** RSS, **23.82 KB** of door resources and **1,998.61 ms** cold start, all inside the
budget. `python3 -m lite --version` printed 0.1.12.

Not fixed, briefed instead: `docs/STEP-7A.md` finishes SPEC step 2, the one numbered step with no
brief and no section above, so model start and stop, a LAN endpoint and a pasted cloud key all
still answer 501. `docs/STEP-7B.md` adds the second memory writer and ranked recall that
`docs/agent-pieces.md` section 1 asks for. `docs/STEP-7C.md` carries the install path, the
optional MCP connector and the 44 px sweep.

Remaining limits: a Tiiny is attached over USB and `lite.device.find_base()` found it in 0.9 s at
its USB address, but it answers `401 auth_failed` without a key and this audit had no access to
one. So no device inference, no device speech to text, no device text to speech and no model
lifecycle call was exercised against real firmware. Every model number above is the echo model.
