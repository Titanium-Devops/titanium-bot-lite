# Step 1c: the busy-port check must see a listener on 127.0.0.1

Measured 2026-09-11 20:52: with the product's relay listening on 127.0.0.1:7777, `python3 -m lite
--port 7777` printed "ready at http://localhost:7777" and bound 0.0.0.0:7777 beside it, because
macOS allows a 0.0.0.0 bind next to a 127.0.0.1 one. A browser at localhost:7777 then reaches the
other server. Fix: before binding, try a TCP connect to 127.0.0.1:<port> and to ::1:<port> with a
200 ms timeout; if either accepts, refuse with the one plain sentence and exit 1. Also bind with
SO_REUSEADDR off for the check. Add a test that starts a throwaway listener on 127.0.0.1 on a spare
port and asserts the refusal sentence and exit code. `python3 -m unittest` stays green. Commit is
not possible from your sandbox; leave the tree clean apart from your change and append a "Step 1c"
line to docs/STEP-1-REPORT.md.
