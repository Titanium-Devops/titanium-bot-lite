# Step 7c: an install a stranger can follow, and the last of the port plan

Three leftovers, none of them large on its own, all of them about the day somebody who is not
Jason tries this.

## 1. The install path is not live

SPEC.md delivery step 6 says `pip install titanium-bot-lite`. There is no `pyproject.toml`,
`setup.py` or `setup.cfg` in the tree, so that command cannot work. README.md documents
`farm install titanium-tiiny-bot` instead, behind the sentence "Once the farm release is
published", and notes that a manifest whose checksum is `pending` cannot install yet. So neither
path is live and the only way in today is to copy the folder and run `python3 -m lite`, which the
README does document first and which is fine as the starting point.

Decide which one ships, then make it true, and say so in one place rather than two:

- If it is the farm, publish the release `scripts/release.py` builds, put the real checksum in the
  manifest, and cut the "once it is published" hedge out of the README.
- If it is pip as well, add a `pyproject.toml` that packages `lite/` and `brand/` with the same
  exclusions `scripts/release.py` already enforces, keeps `lite/VERSION` as the single source of
  the version, and installs a console entry point. Check that the name does not collide with the
  unrelated PyPI `tiiny-sdk` whose script is `tiiny`, which SPEC.md already warns about.

Either way the README ends with one install section, not two, and `farm update` keeping data is
tested rather than described.

## 2. The optional MCP connector

SPEC.md step 6 offers a second form: register Lite as a custom MCP connector in TiinyOS, so their
own chat can reach Titan's memory and skills. Nothing in the tree mentions it. It was written as
optional and it is still worth an afternoon, because it is the only way anything on the device
sees what Titan knows. Read docs/tiiny-platform.md before starting: it is the source for what
TiinyOS accepts, and the audit did not verify a connector registration against real firmware.

## 3. The 44 px sweep

docs/console-pieces.md section 3 keeps a floor of 44 by 44 on every visible control at two device
sizes, swept rather than listed. Measured in headless WebKit on 2026-09-13:

- At 390 by 844, one item is under: the "Built for Tiiny" brand link at 111 by 26. It is a brand
  lockup rather than a control, so decide whether the sweep counts it before moving it.
- At 1440 by 900, seven are under: `room-menu` at 29 by 29, `composer-plus` at 38 by 38,
  `shelf-settings` at 38 by 38, `voice-talk` at 74 by 38, `send-button` at 94 by 42, the composer
  textarea at 20 high, and the same brand link.

The textarea is the one to leave alone: the port plan's composer depends on that box having no
padding and no border so `scrollHeight` is the text's height, and the eight-line cap is wrong the
moment that changes. For the rest, take a before-and-after at both sizes rather than editing the
stylesheet from the numbers, because the shelf and the window bar are the two places this console
has already regressed once.

Tests: whichever of the three lands, `python3 -m unittest` green, `lite/VERSION` bumped by one on
the last number, and a "Step 7c" section appended to docs/REPORT.md.
