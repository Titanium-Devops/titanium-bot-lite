/* Named extraction from machine-room/app.js; host-only surfaces are omitted. */
(async function () {
  "use strict";
  const adapter = await window.createLiteAdapter();
  window.__machineRoomAdapter = adapter;
  let state = adapter.getSnapshot();
  let toastTimer = null;
  const elements = Object.fromEntries(Object.entries({transcript:'transcript',messageInput:'message-input',composer:'composer',toast:'toast',panelDialog:'panel-dialog',panelTitle:'panel-title',panelEyebrow:'panel-eyebrow',panelContent:'panel-content'}).map(([key,id]) => [key,document.getElementById(id)]));
  const activeContext = () => state.activeContext;
  const contextRecord = () => state.workers[0];
  const contextMessages = () => contextRecord().messages;
  const workerById = id => state.workers.find(w => w.id === id);
  const contextLead = contextRecord;
  const SECRETISH = /(?:sk-|xai-|gsk_|ghp_|AIza|xox[abprs]-)[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,}|[A-Za-z0-9_\-+/=]{32,}/g;
  const maskSecrets = (value) => String(value ?? "").replace(SECRETISH, (hit) => `${hit.slice(0, 4)}…[redacted, ${hit.length} chars]`);
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
  function avatarMarkup(worker, className, title) {
    if (!worker) return "";
    if (className === "message-avatar") {
      const mood = window.TitanCrew?.moodFor(worker) || "calm";
      const sprite = window.TitanCrew?.stillFor(0, mood) || "assets/characters/titan-calm.png";
      return `<img class="message-avatar titan-sprite" src="${escapeHtml(sprite)}" alt="${escapeHtml(title || worker.name)}" />`;
    }
    // AVATAR-1. Every face on this page comes through here, so this is the one place the Titan
    // crew has to be taught about: mascots.js answers with a live <titan-mascot> at the size the
    // static mark had, and answers with nothing when it should not draw one -- an agent whose own
    // avatar the host is serving, an operator who chose the classic mark, or a browser that cannot
    // run the canvas. The <img> below is what is left in every one of those cases.
    const crewFace = typeof window.titanAvatarMarkup === "function" ? window.titanAvatarMarkup(worker, className, title) : "";
    if (crewFace) return crewFace;
    return `<img class="${className}" src="${escapeHtml(worker.avatar)}" alt="${escapeHtml(title || worker.name)}" />`;
  }
  function showToast(message) {
    window.clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.remove("is-visible");
    void elements.toast.offsetWidth;
    elements.toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2800);
  }
  function inlineMarkup(line) {
    // CONSOLE-5: a backticked span is a chip a person can copy, not just monospace text. The class
    // is what the stylesheet hangs on; role and tabindex are what put the copy within reach of a
    // keyboard, and the delegated keydown handler further down answers them.
    //
    // THE CODE COMES OUT OF THE LINE BEFORE THE EMPHASIS PASSES AND GOES BACK AFTER THEM. Running
    // the chip replace first left the chip's own contents in front of the bold and italic patterns,
    // so `chmod +x *.sh *.py` came out as <code>chmod +x <em>.sh </em>.py</code> and the click
    // copied "chmod +x .sh .py" -- a command a person would paste and run. Two globs in one command
    // and a quoted draft holding **bold** are exactly what the persona sentence asks an agent to
    // backtick, so this was the common case, not a corner. A chip's text is the agent's text.
    //
    // The placeholder is a NUL either side of the index, and any NUL the agent wrote is dropped
    // first: a sentence that already held one could otherwise name a chip that is not there.
    const codes = [];
    return escapeHtml(line)
      .replace(/\u0000/g, "")
      .replace(/`([^`]+)`/g, (whole, code) => `\u0000${codes.push(code) - 1}\u0000`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      // The label is built from the code itself. "Copy this" was the element's whole accessible
      // name, which replaced its contents -- so every chip in a transcript announced itself as the
      // same anonymous button and the address, channel or hostname inside it was unreachable.
      .replace(/\u0000(\d+)\u0000/g, (whole, index) => {
        const code = codes[Number(index)] ?? "";
        return `<code class="code-chip" tabindex="0" role="button" aria-label="Copy ${code}">${code}</code>`;
      });
  }
  function paragraphMarkup(text) {
    // Line by line, not block by block. The block form required EVERY line in a paragraph to be a
    // bullet, so an agent that writes a lead sentence and then a list -- which is how they all
    // write -- got the whole thing rendered as literal dashes.
    const lines = String(text || "").split("\n");
    let html = "";
    let list = null;
    const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
    for (const raw of lines) {
      const line = raw.trimEnd();
      const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
      const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      const heading = /^\s{0,3}(#{1,4})\s+(.*)$/.exec(line);
      if (bullet) {
        if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
        html += `<li>${inlineMarkup(bullet[1])}</li>`;
      } else if (numbered) {
        if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
        html += `<li>${inlineMarkup(numbered[1])}</li>`;
      } else if (heading) {
        closeList();
        html += `<p class="message-heading"><strong>${inlineMarkup(heading[2])}</strong></p>`;
      } else if (!line.trim()) {
        closeList();
      } else {
        closeList();
        html += `<p>${inlineMarkup(line)}</p>`;
      }
    }
    closeList();
    return html;
  }
  const CHIP_TICK_MS = 1200;

  // A screen reader hears the tick because the tick itself is generated content, which not every
  // reader announces. One polite region, made once, off screen, shared by every chip.
  let chipSpeaker = null;
  function announceChipCopy(said) {
    if (!chipSpeaker) {
      chipSpeaker = document.createElement("div");
      chipSpeaker.className = "chip-copy-live";
      chipSpeaker.setAttribute("role", "status");
      chipSpeaker.setAttribute("aria-live", "polite");
      document.body.appendChild(chipSpeaker);
    }
    // Set NOW when the word is changing, because a region that is empty for even a frame is a
    // region something else can read as nothing said -- the gate caught exactly that. Only a repeat
    // needs the clear first, since a reader announces a change and the same identifier copied twice
    // in a row is the ordinary case.
    if (chipSpeaker.textContent === said) {
      chipSpeaker.textContent = "";
      window.setTimeout(() => { if (chipSpeaker) chipSpeaker.textContent = said; }, 30);
      return;
    }
    chipSpeaker.textContent = said;
  }

  // navigator.clipboard needs a secure context. https and 127.0.0.1 have one; a relay reached over
  // plain http on a LAN address does not, and there the promise never arrives. This is the fallback
  // the composer's own paste path uses, and it works in both.
  function copyThroughSelection(text) {
    try {
      const pad = document.createElement("textarea");
      pad.value = text;
      pad.setAttribute("readonly", "readonly");
      pad.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
      document.body.appendChild(pad);
      pad.select();
      const done = document.execCommand("copy");
      pad.remove();
      return done === true;
    } catch { return false; }
  }

  function markChipCopied(chip, ok) {
    const flag = ok ? "data-copied" : "data-copy-failed";
    chip.setAttribute(flag, "");
    window.setTimeout(() => chip.removeAttribute(flag), CHIP_TICK_MS);
    // Said, not shouted: no global toast for a copy the person just asked for by clicking the
    // thing they wanted. The failure says what happened rather than showing a tick that lied.
    announceChipCopy(ok ? "Copied" : "This browser would not let the page copy that");
  }

  function copyCodeChip(chip) {
    // textContent, never a data attribute: escapeHtml runs before the backtick pass, so the markup
    // holds &amp; and &lt; while textContent is the original the agent wrote.
    const text = chip?.textContent ?? "";
    if (!text) return;
    const fallback = () => markChipCopied(chip, copyThroughSelection(text));
    if (navigator.clipboard?.writeText) {
      Promise.resolve(navigator.clipboard.writeText(text))
        .then(() => markChipCopied(chip, true), fallback);
      return;
    }
    fallback();
  }

  const chipFromEvent = (event) => event.target?.closest?.("code.code-chip") ?? null;
  const isActivationKey = (event) => event.key === "Enter" || event.key === " " || event.key === "Spacebar";


  function attachmentAgentId() {
    const context = activeContext();
    if (context.kind === "worker") return context.id;
    return (contextRecord()?.memberIds ?? [])[0] ?? "";
  }
  function attachmentMarkup(message) {
    const a = message.attachment;
    const body = (a.kind === "image" || a.mimeType?.startsWith("image/"))
      ? `<div class="attachment-slot" data-attachment-slot>Reading ${escapeHtml(a.name)} from the host…</div>`
      : `<pre class="attachment-preview" data-attachment-slot>Reading ${escapeHtml(a.name)} from the host…</pre>`;
    // CONSOLE-4 seam: Open and Download, beside the caption. Jason, 2026-09-08: "I can't click,
    // open, or view it." Both route to the file viewer (files-viewer.js, item D) through the same
    // delegated funnel as the desktop's file tiles, so one place decides what opening a file means.
    const controls = `<span class="attachment-controls">`
      + `<button class="ghost-button attachment-open" type="button" data-attachment-open="${escapeHtml(a.path)}" data-attachment-agent="${escapeHtml(attachmentAgentId())}" data-attachment-name="${escapeHtml(a.name)}">Open</button>`
      + `<button class="ghost-button attachment-download" type="button" data-attachment-download="${escapeHtml(a.path)}" data-attachment-agent="${escapeHtml(attachmentAgentId())}" data-attachment-name="${escapeHtml(a.name)}">Download</button>`
      + `</span>`;
    return `<figure class="message-attachment" data-attachment="${escapeHtml(a.path)}" data-attachment-kind="${escapeHtml(a.kind || (a.mimeType?.startsWith("image/") ? "image" : "file"))}" data-attachment-name="${escapeHtml(a.name)}"><figcaption><span class="tag">▱ ${escapeHtml(a.name)}</span>${controls}</figcaption>${body}</figure>`;
  }
  function roomSpeakerMarkup(author, message) {
    const face = avatarMarkup(author, "message-avatar");
    if (activeContext()?.kind !== "room" || message.type === "working") return face;
    const who = message.authorName || (author && author.name) || "";
    if (!who) return face;
    return `<div class="message-side">${face}<small class="message-who">${escapeHtml(who)}</small></div>`;
  }
  function foldRepeatedRows(messages) {
    const out = [];
    for (const message of messages) {
      const last = out[out.length - 1];
      const foldable = message.type === "system" && !message.detail && !message.exchange;
      if (foldable && last && last.type === "system" && !last.detail && !last.exchange && last.text === message.text) {
        out[out.length - 1] = { ...message, count: (last.count ?? 1) + 1 };
      } else {
        out.push(message);
      }
    }
    return out;
  }
  function messageMarkup(message) {
    // UX-ERR-1. A failed turn, in one quiet line under the message it failed on.
    //
    // Jason's report was "it popped up like he was talking, then it went away. I don't see any
    // errors" -- the failure existed only in the host log. This is deliberately not a toast and
    // not a red banner: it stays in the transcript where the conversation is, so it is still there
    // when he scrolls back tomorrow. The host wrote the sentence; nothing is composed here, and
    // there is no stack to reveal.
    if (message.type === "turn-failed") {
      return `<article class="message-row is-turn-failed" data-message-id="${escapeHtml(message.id)}" data-turn-failed="1"><div class="message-bubble turn-failed-note">${escapeHtml(message.text)}</div></article>`;
    }
    if (message.type === "system") {
      // SHOT-4: a tool row the adapter summarised in words carries the verbatim command and output
      // as its detail. The row opens to show them, so the receipt is one click away and never gone.
      if (message.detail) {
        return `<article class="message-row is-system" data-message-id="${escapeHtml(message.id)}"><details class="message-bubble tool-receipt"><summary>${escapeHtml(message.text)}</summary><pre>${escapeHtml(message.detail)}</pre></details></article>`;
      }
      return `<article class="message-row is-system${message.exchange ? " is-exchange" : ""}" data-message-id="${escapeHtml(message.id)}"${message.exchange ? ' data-exchange="1" role="button" tabindex="0"' : ""}><div class="message-bubble">${escapeHtml(message.count > 1 ? `${message.text} · ${message.count} steps` : message.text)}</div></article>`;
    }
    const isUser = message.authorId === "you";
    const author = workerById(message.authorId);
    const isWorking = message.type === "working";
    const body = isWorking && !message.text ? `<div class="typing-dots" aria-label="${escapeHtml(message.authorName)} is working"><i></i><i></i><i></i></div>`
      // CONSOLE-4: a message can carry more than one file. Ten of Titan's eleven transcript files
      // ride the {type:"text", images:[…]} carrier that SendMessage's own tool description tells
      // the model to use, and that carrier is a LIST. Each figure gets its own [data-attachment]
      // path, which is what fillAttachments and the file viewer key off, so nothing else changes.
      : message.type === "attachment" && message.attachment
        ? `${paragraphMarkup(message.text)}${(message.attachments ?? [message.attachment]).map((a) => attachmentMarkup({ ...message, attachment: a })).join("")}`
      : `${paragraphMarkup(message.text)}${specialMessageMarkup(message)}`;
    return `<article class="message-row${isUser ? " is-user" : ""}${isWorking ? " working-message" : ""}" data-message-id="${escapeHtml(message.id)}">${!isUser ? roomSpeakerMarkup(author, message) : ""}<div class="message-block"><div class="message-meta"><strong>${escapeHtml(message.authorName || (author && author.name) || "Worker")}</strong><time>${escapeHtml(message.time || "now")}</time></div><div class="message-bubble">${body}</div>${message.spoken ? `<span class="voice-spoken-chip">Spoken</span>` : ""}</div></article>`;
  }
  const DECISION_ACTIONS = {"auto-review": [["approved", "✓ Allow", true], ["always", "↗ Always allow", false], ["denied", "✕ Refuse", false]]};
  const APPROVAL_COMMAND_CAP = 400;

  // The host's surface tokens are snake_case at the request sites (host_shell, box_shell, mcp,
  // computer, browser, automation_write, cloud_agent, subagent) whatever the type union says, and
  // none of them is a word to put on a customer's screen.
  const APPROVAL_WANTS = {
    host_shell: "wants to run a command",
    box_shell: "wants to run a command",
    mcp: "wants to use a connector",
    computer: "wants to use the computer",
    browser: "wants to use the browser",
    automation_write: "wants to change a routine",
    cloud_agent: "wants to run a cloud agent",
    subagent: "wants to start a task",
  };
  const approvalWants = (surface) => APPROVAL_WANTS[String(surface ?? "")] ?? "wants your review";

  // host_shell is the person's own machine; everything else is the box the agent lives on.
  const approvalWhere = (surface, who) => (String(surface ?? "") === "host_shell"
    ? "Runs on your computer"
    : `Runs on ${who}'s computer`);

  // The host writes the location into its own summary, and it writes it with the OLD product's name
  // in it -- "… on Grok Bot's computer" appears five times in
  // source/host/runner/sand-auto-review-summaries.ts, and it lands in this card's title and in the
  // title a push notification puts on a lock screen. The clause is the grey line's job here, so it
  // comes off the sentence, which both restores the original's shape and takes a dead vendor's name
  // off a customer's screen. The five host strings are their own row; this is the console half.
  // Not end-anchored: TWO of the host's summaries write the location mid-sentence. The subagent one
  // writes "Run a task on Grok Bot's computer: “<instruction>”", and the shell one appends the working
  // directory AFTER the clause -- describeSandShellAutoReviewAction builds `${head} ${location} from
  // ${cwd}` whenever the agent passed a cwd, which is the ordinary shell call, so the commonest card
  // of all read "Echo hello on Grok Bot's computer from /workspace" while an end anchor, and then an
  // anchor that only looked for a colon or a comma, both walked past it. The clause comes off at the
  // end of the sentence (taking its full stop with it), before a colon or a comma, and before the
  // " from <cwd>" the host writes after it. Those are the three shapes the host has; a following word
  // it does NOT write is left alone, so "Walk on Titan's computer floor" keeps every word.
  const APPROVAL_WHERE_CLAUSE = /\s+on\s+(?:your local computer|[A-Za-z0-9 ._-]{1,40}'s computer)(?:\.?$|(?=\s*[:,])|(?=\s+from\s))/i;
  const approvalRequestSentence = (card) => String(card.title ?? "").replace(APPROVAL_WHERE_CLAUSE, "").trim()
    || "This action needs your review";

  // What goes on a lock screen. Only the auto-review card has a clause to strip; every other kind
  // keeps the title the relay already pushes for it.
  const cardPushTitle = (card) => (card.kind === "auto-review" ? approvalRequestSentence(card) : card.title);

  // The original elides the middle and counts what it dropped: "...[353 chars omitted]...". The cap
  // is what is SHOWN, so the count is the real remainder and adding the two back gives the command.
  function approvalCommandShown(command) {
    const text = String(command ?? "");
    if (text.length <= APPROVAL_COMMAND_CAP) return text;
    const head = Math.ceil(APPROVAL_COMMAND_CAP / 2);
    const tail = APPROVAL_COMMAND_CAP - head;
    return `${text.slice(0, head)}\n...[${text.length - APPROVAL_COMMAND_CAP} chars omitted]...\n${text.slice(text.length - tail)}`;
  }

  // Five states, and the two green ones are not the same sentence. "Always allowed" is claimed only
  // when a standing rule really is in the person's Auto-review settings -- the adapter hands the
  // saved allow list in, and the claim is that this approval's own proposed rule is on it. Anything
  // else that was approved was approved by hand, once.
  //
  // ONLY "denied" READS REFUSED. "expired" is a status the HOST writes by itself and in bulk:
  // expireAllPendingAutoReviewApprovalCards() runs at host start, so a bundle swap, a restart, a
  // session end, a settings change or a cancel all turn every unanswered card in a transcript into
  // one -- and telling a person they refused something they never saw is a lie the page tells about
  // them. Everything that is not pending, approved or denied is the host closing the question.
  function approvalPill(status, ruleSaved) {
    if (status === "pending") return '<span class="status-pill attention" data-approval-pill>Needs your yes</span>';
    if (status === "approved") {
      return ruleSaved
        ? '<span class="status-pill success" data-approval-pill>Always allowed</span>'
        : '<span class="status-pill success" data-approval-pill>Allowed once</span>';
    }
    if (status === "denied") return '<span class="status-pill muted" data-approval-pill>Refused</span>';
    return '<span class="status-pill muted" data-approval-pill>No longer waiting</span>';
  }

  // The whole card, in every state. A settled card keeps the request, the rule and the command:
  // the branch this replaced threw all three away and left "You approved this", so a person had no
  // way to see afterwards what it was they had allowed.
  function approvalCardMarkup(message, card, hook, allowRules, escapeHtml) {
    const status = String(card.status ?? "pending");
    const pending = status === "pending";
    const who = String(message.authorName ?? "").trim() || "your agent";
    const rule = typeof card.rule === "string" && card.rule.trim().length > 0 ? card.rule.trim() : "";
    const ruleSaved = rule.length > 0 && (allowRules ?? []).some((entry) => String(entry).trim() === rule);
    const accent = pending ? "var(--amber-500)" : status === "approved" ? "var(--green-500)" : "var(--stone-500)";
    const command = typeof card.command === "string" ? card.command : "";
    // The other half of the pill above: a card the host closed says so in words, the way the
    // sibling kinds in decisionMarkup have always said "Closed by the host".
    const closed = !pending && status !== "approved" && status !== "denied"
      ? '<p class="approval-closed">The host closed this without an answer.</p>'
      : "";
    // Only while it is still a question. Once it is settled the reason is why it was ASKED, and on a
    // card the person already answered it reads as a complaint about their answer.
    const reason = pending && typeof card.reason === "string" ? card.reason.trim() : "";
    // No script behind the toggle: <details> already opens and closes, and the two words swap on
    // [open] in the stylesheet. The transcript wipes its own innerHTML on every render, so a handler
    // bound to this element would not survive anyway.
    const disclosure = command.length === 0 ? ""
      : `<details class="tool-receipt approval-command"><summary><span class="approval-more-show">Show the command</span><span class="approval-more-hide">Hide the command</span></summary><pre>${escapeHtml(approvalCommandShown(command))}</pre></details>`;
    // Past tense only when it is true. A pending card says what the button WOULD do; a settled card
    // whose rule was never saved says nothing at all, rather than implying a standing rule exists.
    const rulePara = rule.length === 0 ? ""
      : ruleSaved
        ? `<p class="approval-rule">A rule always allowing this was added to your Auto-review settings: “${escapeHtml(rule)}”</p>`
        : pending
          ? `<p class="approval-rule">Always allow adds this rule to your Auto-review settings: “${escapeHtml(rule)}”</p>`
          : "";
    const actions = !pending ? ""
      : `<div class="inline-card-actions">${DECISION_ACTIONS["auto-review"]
        .filter(([value]) => value !== "always" || rule.length > 0)
        .map(([value, label, primary]) => `<button class="card-action${primary ? " primary" : ""}" type="button" data-decide="${escapeHtml(value)}" data-message-id="${escapeHtml(message.id)}">${escapeHtml(label)}</button>`)
        .join("")}</div>`;
    return `<div class="inline-card approval-card"${hook} data-approval-card data-approval-state="${escapeHtml(status)}" data-approval-surface="${escapeHtml(String(card.surface ?? ""))}" style="--card-accent:${accent}">`
      + `<div class="approval-card-head"><strong>${escapeHtml(`${who} ${approvalWants(card.surface)}`)}</strong>${approvalPill(status, ruleSaved)}</div>`
      + `<p class="approval-where">${escapeHtml(approvalWhere(card.surface, who))}</p>`
      + `<p class="approval-request">${escapeHtml(approvalRequestSentence(card))}</p>`
      + (reason.length > 0 ? `<p class="approval-why">${escapeHtml(reason)}</p>` : "")
      + closed + rulePara + disclosure + actions
      + `</div>`;
  }
  function specialMessageMarkup(message) {
    if(message.card) { const card={...message.card,title:message.card.summary||message.card.title,rule:message.card.proposedRule||message.card.rule}; return approvalCardMarkup(message,card,'',[],escapeHtml); }

    if (message.attachments?.length) return message.attachments.map(a => attachmentMarkup({...message,attachment:a})).join('');
    return '';
  }
  function transcriptMarkup() {
    const older = contextRecord().hasOlder ? '<div class="transcript-older"><button class="ghost-button" type="button" data-load-older>Show earlier messages</button></div>' : '';
    return older + foldRepeatedRows(contextMessages()).map(messageMarkup).join('');
  }
  let holdScrollUntil = 0, pinToBottomOnce = true;
  const pinTranscriptToBottom = () => { pinToBottomOnce = true; };
  function renderTranscript(keepScroll, pinToRevealed) {
    const box = elements.transcript;
    const wasNearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
    box.innerHTML = transcriptMarkup();
    fillAttachments();
    // A revealed row, or a flash still holding: the reader is being held on a line on purpose, so
    // the pin is spent rather than fired under them.
    if (pinToRevealed || Date.now() < holdScrollUntil) { pinToBottomOnce = false; return; }
    const pin = pinToBottomOnce;
    pinToBottomOnce = false;
    if (pin || wasNearBottom) requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
  }
  function renderTranscriptKeepingOffset() {
    const box = elements.transcript;
    const previousHeight = box.scrollHeight;
    const previousTop = box.scrollTop;
    box.innerHTML = transcriptMarkup();
    fillAttachments();
    box.scrollTop = box.scrollHeight - previousHeight + previousTop;
  }
  function fillAttachments() {
    elements.transcript.querySelectorAll('[data-attachment]').forEach(figure => {
      const path = figure.dataset.attachment, slot = figure.querySelector('[data-attachment-slot]');
      if (figure.dataset.attachmentKind === 'image') { const img = document.createElement('img'); img.src=adapter.fileUrl(path); img.alt=figure.dataset.attachmentName; slot.replaceChildren(img); }
      else adapter.readAttachmentText('titan',path).then(answer=>{ if(slot.isConnected) slot.textContent=maskSecrets(answer.text).slice(0,3000); }).catch(()=>{slot.textContent='Open this file to read it.';});
    });
  }
  function openPanel(eyebrow,title,content) {
    elements.panelDialog.classList.remove('is-settings'); elements.panelEyebrow.textContent=eyebrow; elements.panelTitle.textContent=title;
    elements.panelContent.innerHTML=content;
    if(!elements.panelDialog.open) elements.panelDialog.showModal();
  }
  function renderAll(older = false) {
    const worker=contextRecord();
    document.getElementById('worker-stack').innerHTML=`<button class="worker-card is-selected" data-context-id="${escapeHtml(worker.id)}" data-status="${escapeHtml(worker.status)}">${avatarMarkup(worker,'worker-avatar')}<span class="worker-copy"><strong class="worker-name">${escapeHtml(worker.name)}</strong><small class="worker-status">${escapeHtml(worker.statusText)}</small></span></button>`;
    document.getElementById('room-title').textContent=worker.name;
    document.getElementById('room-subtitle').textContent=worker.statusText;
    document.getElementById('participant-cluster').innerHTML=avatarMarkup(worker,'participant-avatar');
    document.getElementById('context-card').innerHTML=`<div class="island-heading"><strong>${escapeHtml(worker.name)}</strong></div><p>${escapeHtml(worker.role)}</p><small>${escapeHtml(worker.model)}</small>`;
    elements.messageInput.placeholder=`Ask ${worker.name}…`;
    if(older) renderTranscriptKeepingOffset(); else renderTranscript();
    window.__titanMascots?.afterRender();
  }
  function isPhoneWidth() {
    return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 690px)").matches;
  }

  // THE + MENU. The capability dock is the same markup at both widths (styles.css draws it as a
  // sheet above the shelf on a phone), so there is no second set of buttons to wire: all this owns
  // is whether the sheet is open.
  function setCapabilityMenu(open) {
    if (open) document.body.dataset.capabilityMenu = "open";
    else delete document.body.dataset.capabilityMenu;
    document.getElementById("composer-plus")?.setAttribute("aria-expanded", String(Boolean(open)));
  }
  // A press acts and the sheet goes: one left standing over the composer, behind the panel it just
  // opened, is one more thing to dismiss by hand.
  document.querySelector(".capability-dock")?.addEventListener("click", (event) => {
    if (event.target.closest("[data-capability]")) setCapabilityMenu(false);
  });
  document.getElementById("drawer-scrim")?.addEventListener("click", () => setCapabilityMenu(false));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") setCapabilityMenu(false); });

  // The same 90 px CONSOLE-4's renderTranscript uses, so the two agree on what "at the bottom" is.
  const NEAR_NEWEST = 90;
  // What the conversation keeps whatever the keyboard and the composer do to it. 180 px is five
  // lines of chat at this font, which is the least that is worth reading.
  const TRANSCRIPT_FLOOR = 180;
  const KEYBOARD_COMPOSER_LINES = 3;
  let transcriptPinned = true;
  let unseenWhileParked = 0;
  let transcriptRowCount = 0;
  let lastScrollTop = 0;
  let repinFrame = 0;

  const atNewest = () => {
    const box = elements.transcript;
    return box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_NEWEST;
  };
  const keyboardTaken = () => parseFloat(document.documentElement.style.getPropertyValue("--kb")) || 0;
  function keyboardUp() { return keyboardTaken() > 0; }

  // A WAY BACK TO THE NEWEST LINE, which this console has never had. In .conversation-space, which
  // is position: relative and which renderTranscript never rebuilds -- and NOT in .voice-overlay,
  // which is pointer-events: none and could not be pressed.
  const jumpNewest = document.createElement("button");
  jumpNewest.className = "jump-newest";
  jumpNewest.type = "button";
  jumpNewest.dataset.jumpNewest = "";
  jumpNewest.hidden = true;
  jumpNewest.textContent = "Newest";
  document.querySelector(".conversation-space")?.appendChild(jumpNewest);

  // `hidden`, never style.display, and written only when it changes: this is called from inside an
  // observer's callback, and an unguarded write there is the 60 Hz loop console-flicker paid for.
  function paintJumpNewest() {
    const wanted = !transcriptPinned && unseenWhileParked > 0;
    if (jumpNewest.hidden === !wanted) return;
    jumpNewest.hidden = !wanted;
  }

  function repinTranscript() {
    if (!transcriptPinned || repinFrame) return;
    repinFrame = requestAnimationFrame(() => {
      repinFrame = 0;
      const box = elements.transcript;
      box.scrollTop = box.scrollHeight;
    });
  }

  // HOW MUCH OF THE SCREEN THE KEYBOARD MAY TAKE: whatever leaves the conversation its floor with
  // the composer at its own keyboard cap. It reads the band as it stands and adds back what it has
  // already taken, so repeated calls settle rather than ratchet.
  function keyboardCeiling() {
    const box = elements.transcript;
    if (!box) return Infinity;
    const input = elements.messageInput;
    const line = input ? parseFloat(getComputedStyle(input).lineHeight) || 22 : 22;
    const room = input ? Math.max(0, Math.round(line * KEYBOARD_COMPOSER_LINES) - input.getBoundingClientRect().height) : 0;
    return Math.max(0, Math.round(box.getBoundingClientRect().height + keyboardTaken() - TRANSCRIPT_FLOOR - room));
  }

  // A SCROLL EVENT IS NOT ALWAYS THE READER MOVING, and reading it as one is what made the first cut
  // of this fail. MEASURED in WebKit at 390x844: typing a long message fired 22 scroll events and 26
  // re-pins that each landed at 0 px from the bottom, and the reader still ended 132 px away. The
  // box shrinks under him as the composer grows, which leaves his scrollTop where it was and the
  // bottom further down; the scroll event that follows reports a gap, the first cut read that as
  // "he scrolled up", and every re-pin after it was skipped.
  //
  // SO THE ONLY WAY TO LOSE THE PIN IS TO SCROLL UP. scrollTop going DOWN is the reader's own drag
  // and nothing else does it; a gap that opens while scrollTop stands still is the floor moving,
  // and the answer to that is to take him back rather than to leave him behind.
  elements.transcript.addEventListener("scroll", () => {
    const box = elements.transcript;
    const top = box.scrollTop;
    const draggedUp = top < lastScrollTop - 1;
    lastScrollTop = top;
    if (draggedUp) transcriptPinned = atNewest();
    else if (atNewest()) transcriptPinned = true;
    else if (transcriptPinned) repinTranscript();
    if (transcriptPinned) unseenWhileParked = 0;
    paintJumpNewest();
  }, { passive: true });

  jumpNewest.addEventListener("click", () => {
    const box = elements.transcript;
    box.scrollTop = box.scrollHeight;
    transcriptPinned = true;
    unseenWhileParked = 0;
    paintJumpNewest();
  });

  // A row that ARRIVED while the reader was parked up is what the button counts. renderTranscript
  // rewrites the whole list on every tick, so the count of rows is the only honest signal: a rebuild
  // that lands the same rows is not news.
  if (typeof MutationObserver === "function") {
    new MutationObserver(() => {
      const rows = elements.transcript.querySelectorAll(".message-row").length;
      const grew = rows - transcriptRowCount;
      transcriptRowCount = rows;
      if (grew > 0 && !transcriptPinned) unseenWhileParked += grew;
      paintJumpNewest();
    }).observe(elements.transcript, { childList: true });
  }

  // THE BOX'S OWN HEIGHT, watched rather than a list of the things that change it: the composer
  // growing, the keyboard arriving, a furniture row appearing in the shelf and a rotation all come
  // through here. The re-pin is a frame later and writes scrollTop only, which resizes nothing --
  // WebKit throws "ResizeObserver loop completed with undelivered notifications" at a callback that
  // resizes anything, and the deferral plus the repinFrame guard keep this out of that class.
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => repinTranscript()).observe(elements.transcript);
  }
  // ---- end PHONE-CONSOLE-1 ---------------------------------------------------------------------

  // Eight lines is where a composer stops being a composer; past that the box scrolls itself.
  const COMPOSER_MAX_LINES = 8;
  function autosizeComposer() {
    const el = elements.messageInput;
    if (!el || el.tagName !== "TEXTAREA") return;
    // The stylesheet gives this box no padding and no border, so scrollHeight is the text's own
    // height and the cap is a plain multiple of the line box.
    const line = parseFloat(getComputedStyle(el).lineHeight) || 20;
    el.style.height = "auto";
    // PHONE-CONSOLE-1: eight lines is the cap with the keyboard down. With it up there is no room
    // for eight -- growing 44 to 176 px took the reader 132 px away from the newest line and left
    // the band under the floor -- so the box stops at KEYBOARD_LINES and scrolls itself.
    const lines = keyboardUp() ? KEYBOARD_COMPOSER_LINES : COMPOSER_MAX_LINES;
    el.style.height = `${Math.min(el.scrollHeight, Math.round(line * lines))}px`;
    repinTranscript();
  }
  elements.messageInput.addEventListener("input", autosizeComposer);
  // After the submit handler above has cleared the value, not before it.
  elements.composer.addEventListener("submit", () => { requestAnimationFrame(autosizeComposer); });
  autosizeComposer();

  // ---- MOBILE-1: the two drawers, and the keyboard ---------------------------------------------
  // The rails are off-canvas panels at phone widths and ordinary columns above the breakpoint, and
  // the stylesheet does the sliding, the scrim and the visibility. What is here is only what CSS
  // cannot do: which drawer is open, Escape and a scrim tap closing it, and handing the keyboard
  // back to the button that opened it.
  let drawerOpener = null;
  const drawerButtons = () => document.querySelectorAll("[data-drawer-toggle]");
  function setDrawer(name) {
    const open = name && document.body.dataset.drawer !== name ? name : "";
    if (open) document.body.dataset.drawer = open; else delete document.body.dataset.drawer;
    for (const button of drawerButtons()) button.setAttribute("aria-expanded", String(button.dataset.drawerToggle === open));
    if (open) drawerOpener = document.querySelector(`[data-drawer-toggle="${open}"]`);
    else if (drawerOpener) { drawerOpener.focus(); drawerOpener = null; }
  }
  for (const button of drawerButtons()) button.addEventListener("click", () => setDrawer(button.dataset.drawerToggle));
  document.getElementById("drawer-scrim")?.addEventListener("click", () => setDrawer(""));
  // Choosing a conversation is the reason the roster drawer was opened, so it closes behind you.
  document.getElementById("worker-roster")?.addEventListener("click", (event) => {
    if (event.target.closest("[data-context-id]")) setDrawer("");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.dataset.drawer) setDrawer("");
  });

  // The composer above the keyboard. Chrome honours interactive-widget=resizes-content in the
  // viewport meta and shrinks the layout viewport for it; iOS Safari does not, so the shelf reads
  // the visual viewport itself and pads by the difference. THE IPHONE'S OWN KEYBOARD IS UNMEASURED
  // -- Chrome cannot raise one -- so this is built to the platform rule and asserted against a
  // simulated visualViewport resize, and docs/CONSOLE.md section 7 says exactly that.
  if (typeof window !== "undefined" && window.visualViewport) {
    const trackKeyboard = () => {
      const view = window.visualViewport;
      const kb = Math.max(0, Math.round(window.innerHeight - view.height - view.offsetTop));
      // PHONE-CONSOLE-1: never more than the conversation can spare. Unclamped this wrote 336 px of
      // shelf padding on a 390x844 phone and left a 54 px band of chat.
      document.documentElement.style.setProperty("--kb", `${Math.min(kb, keyboardCeiling())}px`);
    };
    window.visualViewport.addEventListener("resize", trackKeyboard);
    window.visualViewport.addEventListener("scroll", trackKeyboard);
    trackKeyboard();
  }
  // ---- end MOBILE-1 ----------------------------------------------------------------------------

  elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    // An IME candidate window takes the same Enter to commit a character; that is not a send.
    if (event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (typeof elements.composer.requestSubmit === "function") elements.composer.requestSubmit();
    else elements.composer.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });


  document.addEventListener('click',event=>{const chip=chipFromEvent(event);if(chip)copyCodeChip(chip);});
  document.addEventListener('keydown',event=>{if(!isActivationKey(event))return;const chip=chipFromEvent(event);if(chip){event.preventDefault();copyCodeChip(chip);}});
  adapter.getSettings().then(settings=>{document.documentElement.dataset.theme=settings.theme;if(settings.background&&!settings.background.startsWith('custom-'))window.__mrBg?.apply(settings.background);}).catch(error=>showToast(error.message));
  let stagedFiles=[], sending=false;
  const fileInput=document.getElementById('composer-file');
  function paintFiles() { const tray=document.getElementById('attachment-tray'); tray.hidden=!stagedFiles.length; tray.textContent=stagedFiles.map(f=>f.name).join(', '); if(stagedFiles.length) { const clear=document.createElement('button'); clear.type='button'; clear.className='ghost-button'; clear.textContent='Remove files'; clear.onclick=()=>{stagedFiles=[];fileInput.value='';paintFiles();};tray.append(clear); } }
  fileInput.addEventListener('change',()=>{stagedFiles=Array.from(fileInput.files);paintFiles();});
  document.getElementById('composer-plus').onclick=()=>isPhoneWidth()?setCapabilityMenu(!document.body.dataset.capabilityMenu):fileInput.click();
  elements.composer.addEventListener('submit',async event=>{
    event.preventDefault(); const text=elements.messageInput.value;
    if(sending || (!text.trim()&&!stagedFiles.length))return;
    sending=true;
    const button=elements.composer.querySelector('.send-button');button.disabled=true;
    try { pinTranscriptToBottom(); await adapter.sendMessage(activeContext(),text,stagedFiles); elements.messageInput.value='';stagedFiles=[];fileInput.value='';paintFiles();autosizeComposer(); }
    catch(error){showToast(error.message);} finally{sending=false;button.disabled=false;}
  });
  document.addEventListener('dragover',e=>{if(Array.from(e.dataTransfer?.types||[]).includes('Files'))e.preventDefault();});
  document.addEventListener('drop',e=>{if(e.dataTransfer?.files.length){e.preventDefault();stagedFiles.push(...e.dataTransfer.files);paintFiles();}});
  elements.messageInput.addEventListener('paste',e=>{const files=Array.from(e.clipboardData?.files||[]);if(files.length){e.preventDefault();stagedFiles.push(...files);paintFiles();}});
  document.querySelectorAll('[data-close-dialog]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
  document.getElementById('shelf-settings').onclick=()=>window.__mrSettings.open('general');
  document.getElementById('room-menu').onclick=()=>window.__mrSettings.open('general');
  document.querySelectorAll('[data-capability]').forEach(button=>button.addEventListener('click',()=>{
    const name=button.dataset.capability;
    if(name==='attach')fileInput.click();
    else if(name==='settings')window.__mrSettings.open('general');
    else openLibrary(name).catch(error=>showToast(error.message));
  }));
  document.addEventListener('click',event=>{const decision=event.target.closest('[data-decide]');if(decision)adapter.decideApproval(activeContext(),decision.dataset.messageId,decision.dataset.decide).catch(error=>showToast(error.message));if(event.target.closest('[data-load-older]')) adapter.loadOlderMessages(activeContext()).catch(error=>showToast(error.message));});
  // The Talk button belongs to voice.js, which wires it in its own boot(). app.js used to stand in
  // front of it with a toast saying voice was not connected, written when step 5 had not landed. It
  // has: the button, the call screen and the device's own speech are all here, so nothing here
  // intercepts the press.
  async function openLibrary(kind){
    const library=await adapter.getLibrary();
    if(kind==='files') {
      const files=[...contextRecord().files,...library.memories.map(m=>({name:m.name,path:m.path})),...library.skills.map(m=>({name:m.name,path:m.path}))];
      openPanel('Library','Files','<p><button class="secondary-button" data-memory-panel>Saved memories</button></p>'+files.map(f=>`<p><button class="secondary-button" data-attachment-open="${escapeHtml(f.path)}" data-attachment-name="${escapeHtml(f.name)}" data-attachment-agent="titan">${escapeHtml(f.name)}</button></p>`).join('')||'<p>No files yet. Add a file beside your message.</p>');
    } else if(kind==='routines') openPanel('Library','Routines','<p>Routines use local time. New routines stay paused until you enable them.</p>'+library.routines.map(r=>`<article class="routine-card"><strong>${escapeHtml(r.name)}</strong><p>${escapeHtml(r.cron)} · ${r.enabled?'Enabled':'Paused'}</p><p>${r.nextRunAt?'Next: '+escapeHtml(new Date(r.nextRunAt).toLocaleString()):'No upcoming run'}</p><button class="secondary-button" data-routine-id="${escapeHtml(r.id)}" data-routine-action="${r.enabled?'pause':'enable'}">${r.enabled?'Pause':'Enable'}</button><button class="ghost-button" data-routine-id="${escapeHtml(r.id)}" data-routine-action="delete">Delete</button><button class="secondary-button" data-routine-transcript="${escapeHtml(r.conversationId)}" data-routine-name="${escapeHtml(r.name)}">View results</button></article>`).join(''));
    else openPanel('Library','Skills','<p>Skills saved on this device.</p>'+library.skills.map(s=>`<article class="skill-card"><strong>${escapeHtml(s.name)}</strong><p>${escapeHtml(s.description)}</p><button class="secondary-button" data-skill-id="${escapeHtml(s.id)}" data-enabled="${s.enabled}">${s.enabled?'Disable':'Enable'}</button><button class="primary-button" data-run-skill="${escapeHtml(s.id)}"${s.enabled?'':' disabled'}>Run now</button></article>`).join(''));
  }
  async function openMemories() {
    const library=await adapter.getLibrary();
    openPanel('Library','Saved memories',`<form data-memory-form><label class="field">Something Titan should remember<textarea name="text" rows="3" required></textarea></label><button class="primary-button" type="submit">Remember</button></form>`+library.memories.map(m=>`<article class="routine-card"><div><strong>${escapeHtml(m.name)}</strong><p>${escapeHtml(m.description)}</p></div><button class="ghost-button" data-forget-memory="${escapeHtml(m.id)}">Forget</button></article>`).join(''));
  }
  elements.panelContent.addEventListener('submit',async event=>{if(!event.target.matches('[data-memory-form]'))return;event.preventDefault();try{await adapter.libraryAction({kind:'memory',verb:'remember',text:new FormData(event.target).get('text')});await openMemories();}catch(error){showToast(error.message);}});
  elements.panelContent.addEventListener('click',async event=>{
    const memory=event.target.closest('[data-memory-panel]'),forgot=event.target.closest('[data-forget-memory]'),run=event.target.closest('[data-run-skill]');
    try{
      const routine=event.target.closest('[data-routine-action]'),results=event.target.closest('[data-routine-transcript]');
      if(routine){await adapter.libraryAction({kind:'routine',verb:routine.dataset.routineAction,id:routine.dataset.routineId});await openLibrary('routines');return;}
      if(results){const response=await fetch('/api/transcript?agentId='+encodeURIComponent(results.dataset.routineTranscript));const data=await response.json();if(!response.ok)throw new Error(data.error);openPanel('Routines',results.dataset.routineName,data.messages.map(m=>`<article class="routine-card"><strong>${escapeHtml(m.authorName)}</strong><p>${escapeHtml(m.text)}</p></article>`).join(''));return;}
      if(memory){await openMemories();return;}
      if(forgot){await adapter.libraryAction({kind:'memory',verb:'forget',id:forgot.dataset.forgetMemory});await openMemories();return;}
      if(run){await adapter.libraryAction({kind:'skill',verb:'run',id:run.dataset.runSkill});showToast('Skill started');return;}
    }catch(error){showToast(error.message);return;}
    const button=event.target.closest('[data-skill-id]');if(!button)return;try{await adapter.setSkillEnabled(button.dataset.skillId,button.dataset.enabled!=='true');await openLibrary('skills');}catch(error){showToast(error.message);}});
  window.__mrUi={openPanel,paragraphMarkup,maskSecrets,escapeHtml,renderAll,showToast,openSettings:id=>window.__mrSettings.open(id)};
  adapter.subscribe(event=>{state=event.snapshot;if(event.type==='connection:error'){showToast(event.detail.message);return;}renderAll(event.type==='transcript:older');});
  renderAll();
  window.addEventListener('pagehide',()=>adapter.destroy());
})().catch(error=>{const box=document.getElementById('transcript');box.textContent='Could not open this conversation: '+error.message;});
