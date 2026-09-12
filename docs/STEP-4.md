# Step 4: routines on cron, and "already running"

Read SPEC.md, docs/agent-pieces.md (routines: a real five-field cron or nothing, created disabled,
the stored shape) and the current lite/server.py and lite/agent_tools.py (step 3 already stores
routine drafts through update_state). Now they run.

1. A scheduler thread in the same process: every 30 s it reads routines/*.json, computes each
   enabled routine's next run from its five-field cron (write a small stdlib cron matcher: minute,
   hour, day of month, month, day of week, with */n, ranges and lists; no third-party library),
   and when due it runs the routine's prompt as a turn through the same tool loop, under the
   device lane, writing the result as a transcript entry in a conversation named for the routine
   and a line in routines/runs.json (started, finished, ok or the error). Missed runs while the
   process was down are skipped, not replayed. One routine at a time.
2. Enable, pause and delete from the console's Routines panel (the console already lists them;
   wire the buttons) and from update_state. A routine created by Titan stays disabled until the
   owner enables it, and Titan says so in his reply.
3. "Already running": when the port is held by Lite itself (GET /api/health answers with our
   version), say "Titanium Tiiny Bot is already running at http://localhost:<port>" and exit 0,
   instead of the busy sentence.
4. Tests: the cron matcher against a table of twenty expressions and times; a routine that is due
   runs once and not twice; a disabled routine never runs; a missed run is skipped; the
   already-running sentence. `python3 -m unittest` green. Bump lite/VERSION by one on the last
   number. Append a "Step 4" section to docs/REPORT.md. Commit is not possible from your sandbox;
   leave the tree with only your changes.
