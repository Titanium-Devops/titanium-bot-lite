# Step 7b: memory that fills itself, and recall that chooses

docs/agent-pieces.md section 1 names two memory writers: the tool mid-turn, and a cheap second
model call after the turn. Lite has only the first. Grep lite/server.py and lite/agent_tools.py
for extraction, relevance or importance and there is no match. So a person tells Titan something
in passing, Titan does not happen to call `update_state`, and the fact is gone by the next
session. The same section calls that second call "the difference between memory that fills up and
memory that stays true".

Recall has the matching gap. lite/server.py:186 puts every profile fact plus the latest 40 log
facts into the prompt, unranked and unselected. That is fine at ten facts and wrong at four
hundred.

Read docs/agent-pieces.md sections 1, 5 and 9, and the memory reader and writer in lite/server.py.

1. The second call. After a turn whose exchange is worth remembering, run one more model request
   with a short extraction prompt that emits `profile:`, `log:`, `note:` and
   `remove: <exact existing fact>` lines, or the single word NONE. Apply the result through the
   memory writer that already exists, so the 500-character refusal, the whitespace normalisation
   and the dedupe are the same code. Nothing is sliced: a fact over the cap is refused and split
   at a sentence boundary before writing, never shortened silently.
2. Keep it off the person's clock. The extraction holds the lane like any other device request and
   runs after the reply has reached the transcript, so a turn is never slower because of it. A
   failed extraction is a log line, not a failed turn.
3. Do not run it on every turn. agent-pieces section 1 points at the host's own `is_memorable`
   check. A greeting, a thank you and a one-word answer are not worth a second inference on a
   device this size.
4. Recall that chooses. Add the keyword-overlap scorer from agent-pieces section 1: rank log facts
   against the person's message, keep the profile facts in full, hold the recent block inside a
   4,000-character budget, and end the section with one line saying how many more facts are on
   disk and that the folder can be read. That last line is what lets a small prompt sit over a
   large memory.
5. Keep the render frozen per conversation and rebuilt only when memory changed. The base prompt
   being byte-identical turn to turn is the whole prefix-cache story on this device.

Tests: a fake device whose second response emits one profile line, one log line and one remove,
asserted against the files afterwards; NONE writing nothing; an over-long extracted fact refused
rather than sliced; the extraction skipped for an unmemorable exchange; the ranker preferring an
overlapping fact over a newer one; the budget line naming the remaining count. `python3 -m
unittest` green. Bump lite/VERSION by one on the last number. Append a "Step 7b" section to
docs/REPORT.md.
