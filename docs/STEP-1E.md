# Step 1e: the faded Tiiny watermark

The console's stage carries Tiiny's logo (lite/console/brand/tiiny-logo.svg) dead centre, large
(40 percent of the viewport width, capped at 520 px, minimum 220 px), faded to opacity 0.08 on
the dark plates (0.12 on a light plate), no blur, on a fixed layer behind the transcript and above
the photograph, so it never moves when the chat scrolls and never intercepts pointer events. It
shows on every plate the picker offers. The door gets the same watermark at 24 percent width,
opacity 0.08, behind the headline. Add one test that the watermark element exists once on the
console page and once on the door with the expected class and inline sizes. Do NOT change
anything else about the plates. Bump lite/VERSION by one on the last number. `python3 -m unittest`
green. Append a "Step 1e" section to docs/REPORT.md with the computed opacity and the
bounding box you expect at 1280x800 and 390x844 (from the CSS arithmetic; rendered measurement
is done by the orchestrator afterwards).
