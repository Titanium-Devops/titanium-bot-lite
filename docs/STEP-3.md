# Step 3: Titan can do things (the tool loop, memory, skills, persona)

Read SPEC.md, docs/agent-pieces.md (the formats, the five tool schemas, the prompt-assembly
pseudocode, the persona.md block, the guardrail quotes, the pack table) and the current
lite/server.py. Jason asked Titan on the device what he can do and Titan answered honestly that he
can only chat, read files and edit his persona. This step gives him hands.

1. THE TOOL LOOP. Ordinary turns call the device with the five tools from docs/agent-pieces.md as
   OpenAI function schemas: Read, Write, fetch_url, update_state (memory, routine, profile),
   run_skill. Loop: send, if the reply carries tool_calls run each (sandboxed to the data
   directory's files/ folder for Read and Write; fetch_url with a 10 s timeout, 200 KB cap, text
   only, no private addresses), append the tool result messages, send again, up to 6 rounds, then
   answer. Stream the final text. Show each tool call in the transcript as a receipt row (the
   console already renders tool receipts; use that shape). Keep `chat_template_kwargs:
   {"enable_thinking": false}` on the first call; if a tool round comes back empty twice, retry
   once with thinking on. Device error 150004 and 502 keep their backoff.
2. MEMORY. update_state target memory writes one fact per line, 500 characters max, refused over
   that with the sentence to the model, into memory/log/YYYY-MM.md (profile facts into
   memory/profile.md). Every turn's prompt carries the profile and the last 40 log facts.
3. SKILLS. The catalog (name and description of every skills/<name>/SKILL.md) is in the prompt;
   run_skill reads the body into the conversation. Seed on first run: handbook-never-ask,
   handbook-plain-words and onboarding from vendor's seeds (trimmed as docs/agent-pieces.md says),
   handbook-what-i-can-do rewritten for THIS device (chat, files, memory, skills, routines soon,
   voice soon, and one line: mail, browser, a crew and a computer are the full Titanium Bot).
4. PERSONA. Seed persona.md from the block in docs/agent-pieces.md, with the never-ask sentence and
   the handbook pointer; the first-run interview asks its first question in the same message.
   The owner edits persona.md from Settings > General.
5. TWO COSMETIC BUGS from Jason's screenshot: the roster card reads "TitanReady" with no space
   (the status needs a separator or its own line); Titan's avatar in the transcript is a flat grey
   blob while the header shows the coloured Titan (use the same mascot sprite).
6. Tests with unittest: the loop against a fake device that returns a tool call then a final
   answer; the Read and Write sandbox refusing a path outside files/; the memory cap; the catalog
   in the prompt; run_skill. `python3 -m unittest` green. Bump lite/VERSION by one on the last
   number. Append a "Step 3" section to docs/REPORT.md (the consolidated report, renamed from the Step 1 report). Commit is not possible from your sandbox; leave the tree
   with only your changes.
