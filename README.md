# Titanium Bot Lite

A small, local assistant for the Tiiny AI Pocket Lab, brought to you by [Titanium Bot](https://titanium.bot).

Titan talks to the model on your pocket device. This first version runs on a Mac or Linux computer
beside it and gives you chat, saved memories, an editable persona and a folder of skills.
Model start and stop, scheduled routines and speech are coming in later steps.

Made by Titanium Computing. The full product, with a team of bots, mail, a browser and a computer of
its own, is at https://titanium.bot.

## Run it in ten minutes

You need your Tiiny with a chat model already running, and a Mac or Linux computer on the same
network. Keep that computer awake while you use Titan. No cloud account or paid service is needed.

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/).
   On Linux, your software manager can install Python 3.11 or newer. Nothing else needs installing.
2. Download this project and open Terminal in its folder. Type `python3 --version` to check Python.
3. Open TiinyOS Settings > API Key. Copy the OpenAI address and the API key shown there.
   In Terminal, set these two values. Replace the example address with the address you copied:

   ```sh
   export TIINY_BASE='http://openai.api.tiiny/v1'
   printf 'Paste your API key, then press Return: '
   read -rs TIINY_KEY
   export TIINY_KEY
   printf '\n'
   ```

   The key stays hidden as you paste. Do not put it in chat or a screenshot. These commands work
   in the usual Mac and Linux terminals. Set them again if you open a new terminal.
4. Start Titan:

   ```sh
   python3 -m lite
   ```

5. On this computer, open `http://localhost:7777`. On your phone, join the same Wi-Fi and open
   `http://YOUR-COMPUTER-ADDRESS:7777`, replacing `YOUR-COMPUTER-ADDRESS` with the computer's local
   IP address from its network settings. Press **Open your console** and send a message.

Leave Terminal open. Press Control+C there to stop. Allow local connections if your computer asks.
This console has one owner and no password, so use it on a trusted home network only.

If Titan cannot answer, check that TiinyOS is open and its chat model is running. If your device
needs a particular model name, copy its exact name from TiinyOS and set it before starting:

```sh
export TIINY_MODEL='the exact model name'
python3 -m lite
```

The address TiinyOS shows on your Mac may only work on that Mac. Use the device's local address
when running Lite from another computer. Your phone connects to the computer running Lite.

## Your files and settings

Settings lets you change Titan's name, appearance and persona. Your conversation and preferences
stay in `data/` beside this README. Memories live in `data/memory/`; each fact can have up to 500
characters. Skills are folders under `data/skills/`, each with a `SKILL.md` containing a name and
description at the top. Select a skill in the console to run its instructions as a chat prompt.
Uploaded files can be viewed; Titan does not yet read their contents automatically.

The server creates `data/keys.json` so that only your computer account can read or write it.
Your environment's API key is used by the server and is never sent to the page. Back up `data/`
to keep your conversation. To choose another folder, use `python3 -m lite --data-dir ./my-data`.

## Check it without a device

```sh
TIINY_MODEL=echo python3 -m lite
```

The development model reverses whatever you write. It needs no API key.

```sh
TIINY_MODEL=echo python3 -m lite --selfcheck
python3 -m lite --selfcheck
python3 -m unittest
```

The first check uses the echo model; the second uses your configured device. Each prints memory
use, door resource bytes, fresh-process initialization time and reply timings. Resource bytes
are read with Python's urllib, with no browser. They are not a visual paint measurement.
The limits are 200 MB RAM, 250 KB of door resources and five seconds to initialize.
Tests use Python's standard library. Node, if already installed, also tests the real JavaScript
adapter through an HTTP server using urllib. A restricted environment may skip socket tests;
those skips mean the live connection still needs checking.

If another local app also uses the device, set `ONELANE_DIR` to the same shared lock folder in
both apps before starting them. Lite otherwise keeps its lock inside its data folder.

See `SPEC.md` for the plan, `docs/console-pieces.md` for the route contract, and
`docs/STEP-1-REPORT.md` for delivery evidence and current limits.
