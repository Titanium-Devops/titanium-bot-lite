# Which console pieces port to the lite app

Reader 1, 2026-09-11. Read-only pass over `/Users/sem/orca/workspaces/grok-bot-0.18-reconstructed/gb`
at `webdevtodayjason/gb`, tip `5ca94c2`. Paths are relative to `ui/machine-room/`; line numbers are that tree's.

33,162 lines over 38 files, no build step, classic scripts only. Every module after `app.js` follows one published pattern: an IIFE that hangs one object on `window`, reads `window.__machineRoomAdapter` and `window.__mrUi` lazily, finds its own hosts in the DOM, injects its own stylesheet (`voice.js:1132`, `push-settings.js:282`), and no-ops when a seam is absent. That is why pieces can be taken at all; the seams are listed in `docs/CONSOLE.md` §1.

The one piece that is not separable is `app.js`: 8,325 lines holding the transcript renderer we want plus the marketplace, the job bus, mail, the VNC desktop, the box hand-off and teach mode. Splitting it is the largest job in this port, and §10 puts a number on it.

## 1. The transcript renderer — KEEP

| Piece | File | Verdict |
|---|---|---|
| `inlineMarkup` (backticks, bold, italic) | `app.js:1495` | as is |
| `paragraphMarkup` (line-by-line lists, headings) | `app.js:1524` | as is |
| `foldRepeatedRows` | `app.js:2121` | as is |
| `messageMarkup` | `app.js:2135` | named change below |
| `transcriptMarkup` | `app.js:2170` | named change below |
| `renderTranscript` (the scroll rule) | `app.js:2223` | as is |

**Message shapes**, one flat object: `id`, `authorId` (`"you"` is the person), `authorName`, `time` (already formatted, cannot be subtracted), `timestampMs`, `text`, and `type` from `text`, `working`, `system`, `attachment`, `decision`, `handoff`, `skill`, `turn-failed`. Optional: `detail` (a verbatim command and output, drawn as a `<details>` tool receipt, `app.js:2149`), `exchange`, `count` (set by the fold), `attachment` / `attachments` (a list — ten of eleven files ride the `{type:"text",images:[…]}` carrier), `card`, `evidence`, `spoken`.

**The code chips.** `app.js:1495` emits `<code class="code-chip" tabindex="0" role="button" aria-label="Copy <the code>">`. Order is load-bearing: backticked spans leave the line as NUL-wrapped indices **before** the bold and italic passes and return after them, or a click on `` `chmod +x *.sh *.py` `` copies `chmod +x .sh .py`. Colour `--code-chip-fg: #8fd9e6` in ink, `#065561` on light plates, local to the CONSOLE-5 block in `styles.css` and deliberately not in `tokens.css`. Copy is `navigator.clipboard.writeText` with a `document.execCommand("copy")` fallback, because plain http on a LAN address is not a secure context — **the lite app's normal case**, so keep the fallback.

**The Spoken chip** is one conditional in the row template, `app.js:2165`, styled at `styles.css:5449`, reading `message.spoken`. Keep.

**Named change:** drop the `window.__gapBadge` seam (`app.js:2183`, with a delegated toggle at `:8264`), `withFoldedReportRows` (`:1136`) and `evidenceChipMarkup` (`:2093`). A gap badge folds tool rows on a 1,578-item conversation; the evidence chip is a claim-provenance verdict off the host's attestation machinery. Neither exists for one owner, and both already fall back — `transcriptMarkup` ends in `rows.map(messageMarkup).join("")` with the module absent. Deletion, not rework.

## 2. The composer — KEEP

`index.html:232-251`, wired at `app.js:7287-7546`.

- A `<textarea>`: Enter sends, Shift+Enter opens a line. `autosizeComposer` (`app.js:7527`) grows it to `COMPOSER_MAX_LINES = 8`, and to 3 while `--kb` says the keyboard is up. The stylesheet gives the box no padding and no border, so `scrollHeight` is the text's height. **Keep that constraint or the cap is wrong.**
- `#composer-plus` (`index.html:233`) opens the phone's + menu; `setCapabilityMenu` (`app.js:7400`) only sets `body[data-capability-menu]`, the sheet is CSS.
- `#voice-talk` (`:249`) carries `data-talk-button` in static markup, so it exists before `voice.js` boots and survives `probe()` disabling the button. Keep; it costs nothing.
- The shelf's furniture band (`:214-231`) is four full-width grid rows that collapse when empty. **Named change:** drop `composer-aside` (Report a problem, Run a self-test, both posting to the control plane) and `workspace-list` (open rooms). `composer-aside` is also the one row that never collapses, which is the 31.94 px desktop regression `docs/FEEDBACK.md` §6 records.

## 3. The phone layout — KEEP AS IS, the strongest piece in the set

Landed today. `styles.css` has phone blocks at `:3183`, `:4691`, `:5055`, `:5490`, `:5629`, all `@media (max-width: 690px)`, plus a landscape block at `:3319` for `max-height: 500px`.

- **One rule is outside the breakpoint** and `tests/machine-room-mobile.test.mjs` fails if a second appears: `.icon-button.drawer-toggle, .drawer-scrim { display: none }`. Keep the test.
- **The insets are read once into properties** (`styles.css:5062-5065`): `--sat`, `--sab`, `--sal`, `--sar`, because `env()` cannot be set from a test and a headless browser reports 0 for all four. The bar's floor is `max(calc(8px + var(--sat)), 59px)`: 67 on a phone reporting 59, and 59 on one reporting nothing, so controls clear the status band either way. `index.html:10` carries `viewport-fit=cover`, without which every inset resolves to 0. `--kb` comes from a `visualViewport` listener in `app.js` because iOS Safari ignores `interactive-widget=resizes-content`; the shelf pads by it and the composer's cap reads it.
- **`.app-shell { grid-template-columns: minmax(0, 1fr) }` must stay inside the breakpoint.** Without it the implicit column sized to `.window-bar`'s min-content, 515.406 px, and `overflow: hidden` clipped 125 px off a 390 px phone. Written in the base rule it moved five desktop rects.
- **The drawers** are the two rails off-canvas: handles at `index.html:70` and `:118`, scrim at `:211`, which must sit **inside** `.stage` (a stacking context at `z-index: 2`) or the drawer opens under its own scrim. `app.js:7553` is 27 lines — which drawer is open, Escape, scrim tap, keyboard handed back — and a unit test caps that block's line count.
- **Jump-newest** (`app.js:7435`; CSS `styles.css:5249` phone, `:5269` desktop) is created in JS and appended to `.conversation-space`, which `renderTranscript` never rebuilds. Shown only when the reader is parked up **and** rows arrived since. It writes `hidden`, never `style.display`, and only on change: an unguarded write there is the 60 Hz repaint loop this console already paid for.
- **44 px floor**, swept rather than listed: 42 and 48 visible controls at two device sizes, 0 under 44x44. Keep the sweep, not a selector list.
- **Named change, small:** the capability dock becomes the + menu sheet (`styles.css:5095`). Lite has fewer capabilities (files, routines, skills, settings; no browser, no plugins, no add-agent), so the dock shrinks and the mechanism is unchanged.

## 4. Settings — KEEP THE SHELL, CUT TO FOUR SECTIONS

`settings.js` (1,372 lines) + `settings.css` (637). Already the right shape: a wide panel, a left nav, one section at a time, every row a label plus one grey line plus exactly one control. Four rules it enforces by test, all of which lite wants: no customer-visible label or line may carry key, token, secret, endpoint, relay, proxy, webhook or a vendor name (`settings.js:95-97`); a fact the machine could not answer **omits its row**; contributed rows register by id (`register()`, `:112`) with `markup()` and `fill(root)`, which is how `backgrounds.js` reaches General → Appearance through the `titanbot:settings-section` event rather than by hunting a panel title; and it holds no credential. `SECTIONS` is at `settings.js:172`.

| Section | Verdict |
|---|---|
| **General** | keep. Drop Sign out and Devices (`:258-272`). Keep Theme, Language, Background, Microphone, Talk mode, Voice, Bot name |
| **Computer** → **Model** | keep the shell, replace all four rows. Drop "Titan's computer" (a Docker box), "Execution on this computer" (`localToolPermission` on the host gateway), "How Titan answers" (a plan's model list). Add the Tiiny's own models with start and stop, a LAN endpoint, a pasted cloud key. Keep "Ask me before…" (`:394`) as is, a textarea over one string |
| **Usage** | keep the shell, one row: tokens and minutes this process spent. Drop Plan and Billing |
| **Updates** | drop. No console version, no box to upgrade |
| **Notifications** | drop. A pure mount for `push-settings.js`, which is APNs and Firebase |
| **Operator** | drop. It is `app.js`'s own `settingsPanel()`: job bus, mail, providers |
| **About** (new) | "Brought to you by Titanium Bot", the Ti mark, the link, the version, the measured budget line |

One dependency to repoint: `ask(method, pathname, body)` at `settings.js:71`, same-origin with a 12 s `AbortSignal.timeout`. Point it at the lite routes and the module is unchanged.

## 5. The Titan mascot kit — KEEP ALL OF IT

`assets/titan-mascot.js` is the kit, vendored byte for byte: it defines `<titan-mascot>` and freezes 13 characters on `window.TitanCharacters`. `mascot-crew.js` is pure, no DOM, and publishes `window.TitanCrew` (who is who, what mood) mirroring the kit's own `agents.json`. `mascots.js` is the wiring: it hooks `app.js` at exactly one point, where `avatarMarkup` consults `window.titanAvatarMarkup`, and publishes `window.__titanMascots` at `:335`. `mascots.css` is the frame: a circle with the mascot laid over it at `--titan-fill` times its width, pulled up 46% of its own height.

**How one is drawn:** four observed attributes, `mood`, `paused`, `tracking`, `variant` (`titan-mascot.js:354`), where `variant` is the character index. Three moods only, `calm`, `curious`, `excited`, and a fourth name **throws a `RangeError`** (`:377`). The canvas sizes from `getBoundingClientRect().width`, dpr clamped at 2 (`:294`), body 0.422 of the canvas at every size. **The size cap is the kit's own 430 px canvas height**, reached at an element width of 632 px, giving 266.5 x 244 CSS px: 68% of a 390 px phone and the largest the kit can draw.

**The rule that must travel with it:** nothing in the ancestor chain is ever scaled. The kit measures transform-aware and fires from a `ResizeObserver` that is not, so a scale on an ancestor left Titan 5.6% vertically stretched for a whole call. Halos are siblings taking the transform; the mascot takes opacity and a drop-shadow only.

**Roster and boot cover.** `mascots.js` derives the crew from the roster — the oldest agent is Titan, and a stored choice lives in the host profile's `avatarShape` as `titan:<name>`. **Named change:** one agent, so this collapses to "Titan, always" and the `avatarShape` round-trip goes. The cover (`#boot-cover`, static first child of `<body>`, `boot.css`) holds the kit's still PNG and upgrades to a live element once it is defined and motion is wanted. Keep it exactly, including the 8,000 ms ceiling armed at parse time, `shouldLiftCover({roster, rows, demo, elapsed})`, and the rule that **every field a person reads ships empty in the markup** (a test pins that none of the nine ships words). Ship Titan's sprite pair only, not the 39 in `assets/characters/`.

## 6. Voice — KEEP, repoint two paths

`voice.js`, 2,900 lines. 24 kHz mono PCM16 over `${scheme}//${location.host}/voice/socket` (`:2119`), 4,800-byte / 100 ms frames, playback through Web Audio with buffers scheduled off the socket's `onmessage` path, and an echo gate that holds the microphone shut while the speaker plays plus a 350 ms tail booked **from bytes**, never from "is the queue empty". Public API `window.__voice` at `:2728`: `start`, `stop`, `toggle`, `getSettings`, `setEnabled`, mic choice, `usage`, `minutes`, `readSettings`, `saveSettings`, `openSettings`, `stats()`.

**The page never talks to a vendor**, and that seam is why the vendor difference never reaches it. The relay holds the key and writes the session frame, and the orb's four states arrive as words because only the relay knows when the agent is working. xAI takes a flat frame (`session.voice`, `session.turn_detection` at top level) and OpenAI **refuses it** (`Unknown parameter: 'session.voice'`); xAI streams a cumulative self-correcting transcript only when the transcription model is `grok-transcribe`, OpenAI streams revisable deltas. Both are normalised to replace-the-whole-line before the page sees them (`docs/VOICE.md` §3). So lite keeps `voice.js` unchanged and puts the same small socket behind it, writing whichever frame the owner's pasted key needs, or bridging on-device speech if TiinyOS exposes it (reader 3). Two one-line changes: the settings path at `voice.js:2258`, and the vendor table moving out of `cp/voice.mjs` into the lite server.

**The call screen is merged in this tree**, not pending — `70a9b62`, `e07d6b9`, with `voice-call.css` (280 lines) and `voice-call-avatar.js` (239). Keep all of it.

- `callWanted()` (`:1120`) is a shell naming its platform, **or** 690 px of width, **or** 500 px of height, read live on every press and never cached. `voice-call.css` carries **no breakpoint**: the module decides the screen exists and the sheet sizes itself in `vw` and `min()`. `LINE_SHELF_WIDTH = 900` (`:136`) answers a different question and must not be conflated.
- **Not a new talk mode:** no frame, no field, no relay change. The only difference from push-to-talk is the page's own `muted()` callback.
- **Five words, no sixth:** Connecting, Listening, Thinking, Talking, Muted. The reply is never drawn on the screen; the footer line is refusals only. A refusal takes the screen away through `stop()`, the one close funnel, which is what makes opening it optimistically safe, and the sentence lands in its one existing home on the shelf.
- A plain fixed div on `document.body` at `z-index: 80`, above the drawers at 70 and below the toast at 100. Not a `<dialog>`: the page refuses to act on Escape while any `dialog[open]` stands.
- A typed line fills the console's own message box and submits the composer, so the pin and the attachments are kept once. Its answer is **not** spoken, and that is a stated limit.

## 7. Backgrounds — KEEP, ship three plates

`bg-boot.js` (132), `backgrounds.js` (267), `backgrounds.css` (174), and 1.1 MB of WebP over 17 plates with thumbnails. Load order is the point: `bg-boot.js` is a classic blocking script in `<head>` **before the first stylesheet link** (`index.html:24`), because a classic script after a `<link>` waits for that sheet. It reads `machineRoom.background` in a try/catch and stamps `data-bg` and `--machine-room-bg` on `<html>` before anything paints. Three rules:

- The default, the built-in list and the id-to-file rule live **only** in `bg-boot.js` (`BUILT_IN` at `:38`, the default read off the entry marked `default: true`). `backgrounds.js` reads them off `window.__mrBg` and **guards it before destructuring**: without the guard the picker vanished with no error and no tiles.
- `machineRoom.backgrounds.custom` is parsed **only** when the chosen id starts with `custom-`. It holds data URLs up to 4,000,000 bytes, and parsing it unconditionally in `<head>` costs the whole saving.
- `apply()` sets `data-bg` for every id including `original`, or a browser with nothing stored opens on the stylesheet's fallback photograph. Series headings span the grid with `grid-column: 1 / -1` in `backgrounds.css`; `.bg-grid` is a grid, where an inline `flex-basis` does nothing and a heading takes one tile's cell.

**Named change:** Titan Nebula plus two, per BRAND.md. `BUILT_IN` is a literal array, so it is one edit. Dropping `original` also drops `assets/warmwind-landscape.svg` and the 1.7 MB `design-reference.png`.

## 8. The adapter seam — WRITE A NEW ONE, DROP BOTH OLD ONES

`adapter.js` (603 lines) is the in-memory demo; `gateway-adapter.js` (5,326 lines, 344 KB) is live. `app.js` builds its adapter synchronously at `:441`, so `index.html:476` awaits `window.__bootMachineRoom()` and only then appends `app.js`; an unreachable gateway sets `documentElement.dataset.demo` and the demo adapter runs behind a red bar.

**The contract** (the directory's own README; live list at `adapter.js:216`): `getSnapshot`, `subscribe`, `destroy`, `selectContext`, `sendMessage`, `addMessage`, `removeMessage`, `setWorkerStatus`, `decideApproval`, `addMember`, `removeMember`, `addWorker`, `addRoom`, `runRoutine`, `setPluginState`, `togglePluginTool`, `submitSecret`, `setModel`, `setAutoReview`, `getWorkspaceIdentity`, `getLocalToolPermission`, `setLocalToolPermission`, `startTeaching`, `finishTeaching`, `setRunPaused`, `getEvidence`, plus job-bus, mail and onboarding groups. `subscribe` receives `{type, detail, snapshot}`, and the snapshot shape is `initialState` at `app.js:6`. A lite adapter needs about a third and can no-op the rest.

**What the console asks for today:** `POST /api/<method>` with JSON args (`gateway-adapter.js:131`) over **about 80 method names** — `listAgents`, `sendPrompt`, `getAgentTranscriptTail`, `getConversationOutline`, `getAgentMemories`, `getAgentAutomations`, `resolveAutoReviewApproval`, `getForeverBoxStatus` and the rest — plus REST at `/auth/state`, `/logout`, `/endpoints`, `/endpoints/use`, `/model`, `/connectors`, `/subscriptions`, `/voice/settings`, `/mail/settings`, `/job-bus/status`, `/feedback`, `/box/launch` and `/box/surface`.

**The stream is cheap, and that is the good news.** `new EventSource("/events")` at `gateway-adapter.js:3076`: a frame means nothing but "re-read", debounced at 900 ms (2,000 ms during boot) into one `reloadActive()`, with only `job-bus` frames carrying a payload and a 15 s heartbeat behind it. A lite server's SSE is a one-line poke. The data diet (`docs/APPS.md` §5) adds `x-titan-projection: lean` and `x-titan-if-digest` answered with `{"__unchanged":true}`; on loopback with one conversation the ceilings those exist for do not bite, so skip the headers and keep the budget line SPEC.md already asks for.

## 9. Drop list

| File | Lines | Why |
|---|---|---|
| `gateway-adapter.js` | 5,326 | 80 gateway methods for a multi-tenant host |
| `adapter.js` | 603 | demo fiction |
| `marketplace-bots.js` + `marketplace/` | 1,721 | a catalog of installable bots; lite has one |
| `screen-tile.js` + `.css` | 1,006 | a live thumbnail of a box's VNC seat |
| `cloud-browser.js` | 314 | a hosted browser session |
| `code-tasks.js` | 342 | per-task Docker sandboxes |
| `gap-badge.js` + `.css` | 589 | folds tool rows on a 1,578-item conversation |
| `push-settings.js` + `.css` | 360 | APNs, Firebase, quiet hours, devices |
| `account-menu.js` | 177 | workspace identity and sign-out |
| `bot-setup.js` | 124 | the bot catalog's first run |
| `components.html` + `.css` | 441 | the design guide page |
| `assets/design-reference.png` | 1.7 MB | the approved full-frame comp |

## 10. File list for the lite console

Eighteen files plus assets. **The `app.js` split below is an estimate by function range, not a measurement.**

```
index.html           trimmed: one conversation, no dock for browser or plugins
bg-boot.js           as is, BUILT_IN cut to three plates
tokens.css  motion.css  backgrounds.css  mascots.css  boot.css            as is
settings.css  files-viewer.css  voice-call.css                           as is
styles.css           TRIMMED, and this is the work: 5,652 lines, of which the phone blocks,
                     the shelf, the transcript, the chips and the cards are wanted
assets/titan-mascot.js   vendored, untouched
mascot-crew.js       collapsed to one character
mascots.js           as is
lite-adapter.js      NEW, about 300 lines: the contract in §8 over the routes in §11
app.js               SPLIT. About 3,500 of 8,325 lines port.
                     Keep  :510-2440  renderer, cards, roster
                           :2440-2620 routines and skills panels
                           :4140-4450 agent profile, settings shell
                           :7033-7790 composer, attachments, drawers, palette
                           :7925-8160 first-run onboarding with Titan
                     Drop  :6-440     demo data
                           :2619-4140 plugins, marketplace, BYO connectors
                           :4453-4950 host status, job bus, mail
                           :4959-5830 VNC desktop, box hand-off, screen tile
                           :5833-6090 teach mode
settings.js          four sections plus About; ask() repointed
files-viewer.js      as is. It draws markdown through paragraphMarkup off __mrUi, which is
                     exactly what a memories-and-skills folder wants
voice.js             as is; settings path repointed
voice-call-avatar.js as is
assets/backgrounds/  three plates plus thumbnails, about 200 KB
assets/characters/   Titan's still only
brand/               ti-mark.svg, titanium-bot-logo.svg, favicon.svg
```

## 11. The 12-route lite server contract

Same-origin JSON, no bearer: one owner, one device. Bodies and answers are objects, never bare arrays.

| # | Method, path | Request | Response |
|---|---|---|---|
| 1 | `GET /api/state` | — | `{activeContext:{kind:"worker",id}, openContexts:[…], workers:[{id,name,role,status,statusText,accent,model,messages:[…],files:[…],hasOlder}], rooms:[], models:[{id,name}], routines:[…], skills:[…]}` — `initialState` at `app.js:6` minus plugins |
| 2 | `GET /events` | SSE | `data: {"channel":"changed"}` per change, plus a comment heartbeat. A frame means "re-read"; nothing else is read off it |
| 3 | `POST /api/send` | `{agentId, text}`, multipart when a file rides along | `{message:{id, authorId:"you", authorName:"You", type:"text", text, time, status:"sent"}}`. The turn runs after; route 2 pokes |
| 4 | `GET /api/transcript?agentId=&before=&limit=` | — | `{messages:[…], hasOlder}` — §1's shapes, for "Show earlier messages" |
| 5 | `POST /api/decide` | `{agentId, entryId, decision:"approve"\|"deny"\|"always"}` | `{card:{kind, status, surface, summary, reason, command, proposedRule}}` — the approval card's fields, `docs/CONSOLE.md` §9 |
| 6 | `GET /api/models` | — | `{live:{source:"device"\|"lan"\|"cloud", endpoint, model, resolvedModel, hasKey}, device:[{id,name,running}], lan:[{baseUrl,model,hasKey}], note}`. `running` is what the device says about the row; when it says nothing, `note` says so and the model Lite picked is marked instead. `hasKey` is a yes or no, never the key |
| 7 | `POST /api/model` | `{action:"use"\|"start"\|"stop", id}`, `{action:"use", baseUrl, model, apiKey}`, `{action:"use", source:"device"}` to come back, or `{action:"forget", baseUrl}` | `{live:{…}}`, and route 6's whole answer after a start or stop, so one round trip repaints the page. The key goes to the 0600 file and is **never echoed**. Stopping the model Titan is answering on is refused in words |
| 8 | `GET /api/settings` | — | `{theme, background, language, botName, persona, askBefore, talkEnabled, micDeviceId, voice:{enabled, vendor, voice, minutesToday}, version, budget:{rssMb, firstPaintKb, coldStartMs}}` |
| 9 | `PATCH /api/settings` | any subset of route 8's keys | the **whole** object back, merged. A 200 that ignores a body is the worst shape a mismatch can take: `docs/APPS.md` §15 records a phone turning a customer's quiet hours off that way |
| 10 | `GET /api/library` | — | `{memories:[{id,name,description,chars,updatedAt}], skills:[{id,name,description,enabled}], routines:[{id,name,cron,nextRunAt,enabled,lastRun}]}` |
| 11 | `POST /api/library` | `{verb:"remember"\|"forget"\|"run"\|"enable"\|"disable", kind:"memory"\|"skill"\|"routine", id, text}` | `{ok:true, library:{…}}` — route 10's answer, so one read repaints the panel |
| 12 | `GET /api/file?path=` | — | the bytes, `content-type` from the extension, `private, no-cache`, strong `ETag`. Serves the files viewer, an attachment and a memory's markdown |

**And one socket, which is not a route:** `WS /voice/socket`, the frames `voice.js` already speaks — PCM16 up in 4,800-byte frames, PCM16 deltas down, orb state as words. It also wants `GET /voice/settings`; fold that into route 8 and change the one path at `voice.js:2258`.

Routes 1, 2, 3 and 8 are SPEC.md delivery step 1. Routes 6 and 7 are step 2. Routes 10 and 11 are steps 3 and 4. The socket is step 5.
