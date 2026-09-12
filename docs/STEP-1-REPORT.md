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
