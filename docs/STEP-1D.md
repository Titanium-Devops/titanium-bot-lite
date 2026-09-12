# Step 1d: the name, the Tiiny mark, and the chat-model detection bug

1. NAME. The product is "Titanium Tiiny Bot" (the command and the Python package keep their
   names; nothing executable is ever named `tiiny`). Change the page title, the door headline
   area, the console header wordmark caption and About, README and SPEC to "Titanium Tiiny Bot".
2. BUILT FOR. `brand/tiiny-logo.svg` is Tiiny's own logo (from their store, 120x42). Under the
   "Brought to you by Titanium Bot" line on the door, add a second line: the words "Built for"
   then the Tiiny logo, same row, logo height 20 px, linking to https://tiiny.ai. The console
   header gets the same pair under or beside the Titanium Bot wordmark: "Titanium Tiiny Bot",
   and right below it "Built for" plus the logo at 16 px. Keep the contrast readable on Midnight
   (the logo may need a light variant: if the SVG is dark, wrap it in a light pill; measure the
   contrast). About in Settings shows both marks with both links.
3. THE BUG Jason hit: with Ornith-1.0-35B loaded, sending "Hello." answered "The device lists no
   chat models. Start a chat model on the device." The device's /v1/models rows look like:
   {"id":"deepreinforce-ai/Ornith-1.0-35B","type":"Image-Text-to-Text","supports_chat":true,
   "capabilities":["main"],"supported":["Reasoning","Tool Use"]}. A chat model is any row with
   supports_chat true (fall back to capabilities containing "main" or a type containing "Text-to-Text"
   when supports_chat is absent). `default` resolves to the first such row. Show the resolved model
   id in the Titan card and in Settings > Model. Add a unit test with that exact row shape. Then
   run the selfcheck against the device (TIINY_KEY is in the environment) and put the numbers
   in the report.
4. Bump lite/VERSION by one on the last number. `python3 -m unittest` green. Append a "Step 1d"
   section to docs/STEP-1-REPORT.md. Commit is not possible from your sandbox; leave the tree
   with only your changes.
