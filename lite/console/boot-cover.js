      (function bootCover() {
        "use strict";
        var cover = document.getElementById("boot-cover");
        if (!cover) return;
        var CEILING_MS = 8000;
        var startedAt = Date.now();
        var seen = { roster: false, rows: false, demo: false };

        // The whole lift decision, as one pure function of what has been seen and how long it has
        // been. Everything below only feeds it and acts on its answer.
        function shouldLiftCover(state) {
          if (state.demo) return true;
          if (state.elapsed >= CEILING_MS) return true;
          return Boolean(state.roster && state.rows);
        }

        var quiet = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var stepEl = cover.querySelector("[data-boot-step]");
        var step = function (words) { if (stepEl) stepEl.textContent = words; };
        var lifted = false;

        function removeCover() {
          if (cover && cover.parentNode) cover.parentNode.removeChild(cover);
          cover = null;
        }

        function lift() {
          if (lifted) return;
          lifted = true;
          if (observers) observers.forEach(function (o) { try { o.disconnect(); } catch (e) {} });
          // What the cover uncovers. Three cases, and the difference is the whole point of this
          // block:
          //
          //   - roster and rows both drawn: the real console. Nothing to write.
          //   - roster drawn, rows not: the page is real and one conversation is still opening.
          //   - neither: the ceiling fired before app.js reached its first render, so every field
          //     in the shell is still the empty markup index.html ships. It used to ship copy --
          //     "MSP Team", "3 members · ready", "2h 14m", "Atera Triage's desktop" -- and with
          //     /api stalled the cover came off that at 8.7 s and a person read a team, an agent
          //     and a routine that do not exist on their box, with nothing saying anything was
          //     wrong. Measured on console.titanium.bot 2026-09-08 with the calls stalled in the
          //     browser only. Now the shell is blank until app.js fills it, and this says why.
          var transcript = document.getElementById("transcript");
          var stalled = !seen.roster && !seen.rows && !seen.demo;
          if (!seen.rows && transcript && !transcript.querySelector(".message-row")) {
            transcript.innerHTML = stalled
              ? '<div class="empty-state">Still reaching this box. Nothing on this page has loaded yet.</div>'
              : '<div class="empty-state">Still opening this conversation…</div>';
          }
          if (stalled) {
            var stalledTitle = document.getElementById("room-title");
            var stalledSub = document.getElementById("room-subtitle");
            if (stalledTitle && !stalledTitle.textContent) stalledTitle.textContent = "Still connecting";
            if (stalledSub && !stalledSub.textContent) stalledSub.textContent = "this console has not reached your box yet";
          }
          if (quiet) { removeCover(); return; }
          cover.dataset.bootState = "lifting";
          cover.addEventListener("transitionend", removeCover, { once: true });
          // A transition that never fires (the node was display:none'd, the sheet did not load)
          // must not leave an opaque cover over the console for ever.
          window.setTimeout(removeCover, 900);
        }

        function settle() {
          if (shouldLiftCover({ roster: seen.roster, rows: seen.rows, demo: seen.demo, elapsed: Date.now() - startedAt })) lift();
        }

        var observers = [];
        function watch(target, fn) {
          if (!target) return;
          var o = new MutationObserver(fn);
          o.observe(target, { childList: true, subtree: true });
          observers.push(o);
          fn();
        }

        watch(document.getElementById("worker-stack"), function () {
          if (seen.roster) return;
          var card = document.querySelector("#worker-stack .worker-card");
          if (!card) return;
          seen.roster = true;
          var name = (card.querySelector("strong") || {}).textContent;
          step(name ? "Opening " + name : "Opening your conversation");
          // The roster and the transcript are drawn in one pass, so an empty transcript at this
          // moment is a conversation with nothing in it, not one that has not loaded yet.
          var transcript = document.getElementById("transcript");
          if (transcript && !transcript.querySelector(".message-row") && !transcript.querySelector("[data-load-older]")) seen.rows = true;
          settle();
        });

        watch(document.getElementById("transcript"), function () {
          if (seen.rows) return;
          if (!document.querySelector("#transcript .message-row")) return;
          seen.rows = true;
          settle();
        });

        // The gateway was unreachable and the demo factory is what is behind this cover. Say so
        // here, then get out of the way: a friendly "Setting up your console" sitting on top of the
        // red DEMO DATA bar is the cover lying about the page it is covering.
        var demoWatch = new MutationObserver(function () {
          if (!document.documentElement.dataset.demo || seen.demo) return;
          seen.demo = true;
          step("This console could not reach this box");
          cover.dataset.bootFault = "1";
          settle();
        });
        demoWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-demo"] });
        observers.push(demoWatch);

        window.setTimeout(settle, CEILING_MS);

        // The live crew face, once the kit has upgraded. The still above is what paints first --
        // it needs no script at all -- and this only swaps in the animated one when there is one to
        // swap in and the person has not asked for less motion.
        if (!quiet && window.customElements) {
          window.customElements.whenDefined("titan-mascot").then(function () {
            var still = cover && cover.querySelector("[data-boot-sprite]");
            if (!still) return;
            var live = document.createElement("titan-mascot");
            live.setAttribute("variant", "0");
            live.setAttribute("mood", "curious");
            live.setAttribute("tracking", "off");
            live.className = "boot-sprite-live";
            still.replaceWith(live);
          }).catch(function () {});
        }
      })();
    