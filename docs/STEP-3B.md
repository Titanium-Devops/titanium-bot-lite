# Step 3b: a real turn on the device never answers

Measured by the orchestrator 2026-09-11 22:00 to 22:12 CDT against Jason's unit, twice: with
TIINY_MODEL=deepreinforce-ai/Ornith-1.0-35B, the console sent "Remember that my dog is named
Biscuit and has a folded ear. Then tell me in one sentence what you remembered." The transcript
holds Titan's first-run greeting and the person's line and nothing else after 270 s; no memory
file appears; the server log carries only the "ready" line. The same turn with TIINY_MODEL=echo
answers at once. The device itself answers this prompt with a streamed tool call in about 2 s:
the exact bytes are in tests/fixtures/device-stream-tool-call.sse (SSE lines: the first
tool_calls fragment carries index, id, type and function.name with arguments "{", later
fragments carry only function.arguments pieces, then a chunk with finish_reason "tool_calls",
then data: [DONE]). So the fault is in Lite's loop: the fragment assembly, the finish handling,
the tool execution, the second call, the streaming of the final text to the transcript, or a
lock (OneLane) that is never released. Note the device's session may also be inside the
first-run interview when the turn starts.

Do: (1) add a stdlib logging line per loop step (request sent, chunk kinds counted, tool call
assembled with name and argument length, tool executed with its result length, final text
started and finished, and every exception with its traceback), on by LITE_DEBUG=1 and written to
<data dir>/lite.log always; (2) a unit test that feeds tests/fixtures/device-stream-tool-call.sse
through the real loop with a fake device that then returns a short final answer, asserting the
memory fact is written and the final text reaches the transcript within a second; (3) fix what
that test finds; (4) run every test; bump lite/VERSION by one on the last number; append a
"Step 3b" section to docs/REPORT.md naming the cause in one sentence. You cannot reach the device
from your sandbox; the fixture is the device. Commit is not possible from your sandbox.
