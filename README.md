# Titanium Tiiny Bot

A small, local assistant for the Tiiny AI Pocket Lab, brought to you by [Titanium Bot](https://titanium.bot).
Built for [Tiiny](https://tiiny.ai).

Titan talks to the model on your pocket device. This first version runs on a Mac or Linux computer
beside it and gives you chat, file tools, saved memories, an editable persona, a folder of skills and scheduled routines.
You can talk to it out loud, using the speech models on your device. Settings > Model lists the
models on your device, starts and stops them, and can point Titan at another computer on your
network or a cloud address instead.

Made by Titanium Computing. The full product, with a team of bots, mail, a browser and a computer of
its own, is at https://titanium.bot.

## Install Titan

This takes about ten minutes. You need your Tiiny with a chat model already running, and a Mac or
Linux computer on the same network. Keep that computer awake while you use Titan. No cloud account
or paid service is needed.
Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/) first; on Linux
your software manager can install it. Open Terminal and type `python3 --version` to check. Then
pick one of the three ways in.

**With the farm**, which keeps your data and settings in one place for every Tiiny app:

```sh
python3 -m pip install tiinyapp-farm
farm device
farm install titanium-tiiny-bot
farm start titanium-tiiny-bot
farm status
farm stop titanium-tiiny-bot
```

`farm device` asks for the address and key from the next paragraph and hides them as you type,
so steps 1 and 2 below are already done. Farm keeps your data in
`~/tiinyapps/titanium-tiiny-bot/data`, passes your device settings to Titan through `TIINY_BASE`
and `TIINY_KEY`, and uses one shared `ONELANE_DIR` for apps that take turns with the device.
`farm update titanium-tiiny-bot` keeps your data and stops the running process; start it again
when you are ready.

**With pip**, if you would rather have one command and no farm:

```sh
python3 -m pip install titanium-bot-lite
titanbot-lite
```

`titanbot-lite` and `python3 -m lite` are the same program, so every command in the rest of this
README works with either name.

**From a copy of this project**, which is what you want if you are changing the code:

```sh
python3 -m lite
```

Then, unless `farm device` already asked you:

1. Open TiinyOS Settings > API Key. Copy the OpenAI address and the API key shown there.
   In Terminal, set these two values. Replace the example address with the address you copied:

   ```sh
   export TIINY_BASE='http://192.168.1.50/v1'   # your device's address
   printf 'Paste your API key, then press Return: '
   read -rs TIINY_KEY
   export TIINY_KEY
   printf '\n'
   ```

   The key stays hidden as you paste. Do not put it in chat or a screenshot. These commands work
   in the usual Mac and Linux terminals. Set them again if you open a new terminal.
2. Start Titan with the command for the way you installed it.
3. On this computer, open `http://localhost:7788`. On your phone, join the same Wi-Fi and open
   `http://YOUR-COMPUTER-ADDRESS:7788`, replacing `YOUR-COMPUTER-ADDRESS` with the computer's local
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
description at the top. Four starter skills explain Titan’s abilities, plain words, private
information and first-time setup. Titan sees the catalog each turn and can open a skill when needed.

Ask Titan to read or write a text file in `data/files/`, read a public text page, or remember a
fact. Tool receipts show what happened. File tools cannot access anything outside `files/`;
file and page text is limited to 200 KB. URL fetching has a 10-second timeout and refuses private
addresses and redirects. Uploaded text files are available to the Read tool; pictures and PDFs
are stored and viewable but are not decoded for the model yet.

Press **Talk** beside the message box to speak instead of typing. Choose Off, Push to talk or
Always listening in Settings > General, along with the microphone to listen through. Your device
does the listening and the speaking, so nothing you say leaves your network, and a speech model
and a voice model both need to be loaded on the device. On a narrow screen the whole screen
becomes the call. Press any file, memory or skill in the Files panel to read it.

Profile facts are kept in every prompt. Dated log facts are ranked against what you just said,
up to forty of them and four thousand characters, and the list ends with a line saying how many
more are on disk. After a turn worth remembering, Titan makes one more short model call to write
down what it learned, so something you mention in passing is not lost when the conversation ends.
Greetings and one-word answers do not cost that second call. A fact over 500 characters is refused
rather than shortened, and a long one is split at a sentence boundary before it is saved.
First-time setup begins with “What should I call you?”; say “run first-time setup” to repeat the
interview. Change the persona in Settings > General.
Routines use five-field cron schedules in the server’s local time. New routines stay switched off
until you enable them in Routines or ask Titan to enable them. The panel also lets you pause or
delete a routine and view its results. Keep Lite running: it checks clocks every 30 seconds,
runs one turn at a time, and skips missed minutes instead of replaying them. Each routine keeps
its latest 20 run records in `routines/<id>/runs.json`, beside its existing `routine.json`.

On first run, the server creates `data/config.json` with every field below. Settings > Model
saves the API address (`base`) and model there, including when the device is unavailable.
Use `default` to choose the first chat model the device lists.

Settings > Model also lists the models on your device and starts or stops them. It refuses to stop
the one Titan is answering on: choose another model for Titan first. Whether a model shows as
running comes from what your device says about it. A device that says nothing marks the model Titan
is set to use and prints a line saying that is what it did.

The same page connects another computer on your network, such as Ollama or llama.cpp, or a cloud
address. It takes an address ending in `/v1`, the model name that computer serves, and its key in
the masked box. That box is the only place to type a credential. The key is written to
`data/keys.json` with permissions `0600` under that address, is never shown again, and never
reaches the page or the log. Your device's own key stays separate, so **Use this device** puts
Titan back on your Tiiny in one press. A saved computer is listed with its model, and **Remove**
forgets it and its key. A message already being answered finishes on the endpoint it started on;
the change lands on the next one.

| Field | Default | Meaning |
| --- | --- | --- |
| `base` | *empty, meaning "find the device"* | Your device's OpenAI API address. Leave it empty and Lite looks: `TIINY_BASE`, then `~/.tiinyapps/device.json`, then every attached USB link and this machine's own network, on port 39218. An address here or in `TIINY_BASE` wins. |
| `model` | `default` | The first chat model the device lists, or an exact model ID you choose. |
| `port` | `7788` | The port for this console. |
| `bind` | `0.0.0.0` | Listen on all network interfaces; use `127.0.0.1` for this computer only. |
| `name` | `Titan` | Your assistant's name. |
| `endpoints` | *empty* | The other computers saved in Settings > Model, each an address and a model. Their keys are not here; they are in `keys.json`. |
| `mcp` | `true` | Offer Titan's saved facts and skills to your device's own chat, read only. Set it to `false`, or start with `--no-mcp`, to close that door. |

Command-line options `--base`, `--model`, `--key`, `--port`, `--bind` and `--name` take priority
over environment values (`TIINY_BASE`, `TIINY_MODEL`, `TIINY_KEY`, `TIINY_PORT`), then
`config.json`, then the defaults. Environment and command-line overrides still take priority
over values saved through Settings. The API key stays separately in `data/keys.json`, with
permissions `0600` (only your computer account can read or write it), and never in `config.json`
or the page. Back up `data/` to keep your conversation. To choose another folder, use
`python3 -m lite --data-dir ./my-data`.

To inspect the effective settings with the key masked:

```sh
python3 -m lite --show-config
```

Port 7788 keeps Lite separate from the full product's local relay on 7777. If the selected port
is busy, choose another with `python3 -m lite --port 7789` or change `port` in `config.json`.

## Let your device's chat read what Titan knows

TiinyOS can add a custom MCP connector, which is its way of reaching a program running on
your computer. Titan offers one, so a conversation in TiinyOS can look up a fact you told
Titan or read one of its skills. It reads only: nothing the device asks can change a
memory, a skill or a file.

Open `http://localhost:7788/api/mcp` while Titan is running. It prints the address to add,
which is your computer's address with `/mcp` on the end, like
`http://192.168.1.20:7788/mcp`. In TiinyOS, open Settings > Connectors, add a custom MCP
connector over HTTP and paste that address. Their connector actions run inside TiinyOS
Task Mode. Set `mcp` to `false` in `config.json`, or start Titan with `--no-mcp`, if you
would rather your device could not read any of this.

## Version numbers

The current version is `0.1.12`, stored in `lite/VERSION`, shown in Settings > About and printed
by `python3 -m lite --version`. Every change increments the last number: `0.1.1`, `0.1.2`,
`0.1.3`. The middle number changes only when Jason says so.

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
`docs/REPORT.md` for delivery evidence and current limits.

## Stopping, and building a release

Stop the server using the same data directory it started with:

```sh
python3 -m lite --stop
# Or, for a farm launch:
python3 -m lite --stop --data-dir ~/tiinyapps/titanium-tiiny-bot/data
```

`lite.pid` is stored inside that data directory; a held `.lite.lock` distinguishes a
running process from a stale PID. Ctrl-C and `--stop` allow one second for cleanup,
then exit even while a device request is in progress. An unfinished turn is marked
failed on the next start. Device-side inference may finish after the host exits, and
best-effort voice-model release may not complete; check TiinyOS if a model stays loaded.

Build the farm archive with `python3 scripts/release.py`. It writes
`dist/titanium-tiiny-bot-0.1.12.tar.gz` and prints its SHA-256, which are the URL target
and the checksum the farm manifest carries. Only `lite/`, `brand/` and this README are
packaged, including `lite/VERSION`; developer dependencies, tests, caches and user data
are excluded. The archive is reproducible for identical source bytes and executable
permissions.

Build the pip package from the same tree with `python3 -m build`, which writes a wheel and
a source archive into `dist/`. `lite/VERSION` is the only place the version is written, so
both packages and `--version` always agree.
