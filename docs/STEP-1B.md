# Step 1b: a config file, a port that does not collide, and the version scheme

1. Port: the default port becomes 7788. On this Mac 7777 is the full product's local relay,
   so `python3 -m lite` on 7777 showed Jason the wrong console. If the chosen port is busy,
   say so in one plain sentence naming what to do (`--port` or the config file) and exit 1.
2. Config file: `<data dir>/config.json` (default data dir `./data`), created on first run with
   every field present and commented in the README: `base` (default http://openai.api.tiiny/v1),
   `model` (default `default`, meaning "the first chat model the device lists"), `port` (7788),
   `bind` (0.0.0.0), `name` ("Titan"). The key stays in `keys.json` at mode 0600 and never in
   config.json. Precedence: command line, then environment (TIINY_BASE, TIINY_MODEL, TIINY_KEY,
   TIINY_PORT), then config.json, then the defaults. `python3 -m lite --show-config` prints the
   effective values with the key masked. Settings > Model writes base and model into config.json
   so the owner never edits JSON by hand.
3. Version: add `lite/VERSION` holding `0.1.1` and `python3 -m lite --version`. The scheme is
   0.1.1, 0.1.2, 0.1.3 for every change; the middle number moves only when Jason says so. The
   About row shows it. Write the rule into README.
4. Tests for the precedence order, the busy-port sentence and the masked --show-config.
   `python3 -m unittest` must stay green. Commit as you go; finish by appending a "Step 1b"
   section to docs/REPORT.md.
