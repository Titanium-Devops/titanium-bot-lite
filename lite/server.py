"""One owner, one conversation, standard-library HTTP and a serialized model worker."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import signal
import copy
import errno
import sys
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
import queue
import random
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import IMPORT_STARTED, __version__
from .routines import Scheduler, read_routines

CONSOLE = Path(__file__).parent / "console"
TOOLS = json.loads((Path(__file__).parent / "tools.json").read_text())
BASE_PROMPT = "You are Titan, the local assistant in Titanium Bot Lite. Speak in plain words."
SEEDS = Path(__file__).parent / "seeds"
PERSONA = (SEEDS / "persona.md").read_text()
HANDBOOK = (SEEDS / "handbook-what-i-can-do/SKILL.md").read_text().split("---", 2)[2].strip()



class Refusal(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def atomic_write(path: Path, content: str, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)


# An empty base means "find the device". It is deliberately not an address: a
# Tiiny's address is a DHCP lease, so writing today's address into config.json is
# how this stops working next week. The old default was http://openai.api.tiiny/v1,
# a name the TiinyOS desktop app puts in /etc/resolver, so it resolved on one Mac
# and nowhere on Linux, which this bot also runs on.
DEFAULTS = dict(base="", model="default", port=7788,
                bind="0.0.0.0", name="Titan")


def load_config(root, overrides=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.json"
    if not path.exists():
        atomic_write(path, json.dumps(DEFAULTS, indent=2) + "\n")
    saved = json.loads(path.read_text())
    if not isinstance(saved, dict) or set(saved) - DEFAULTS.keys():
        raise Refusal("Use only base, model, port, bind and name in config.json; keep the key in keys.json.")
    values = DEFAULTS | saved
    keys = root / "keys.json"
    if not keys.exists():
        atomic_write(keys, "{}\n", 0o600)
    keys.chmod(0o600)
    stored = json.loads(keys.read_text())
    if not isinstance(stored, dict):
        raise Refusal("Use an object with an apiKey field in keys.json.")
    values["key"] = stored.get("apiKey", "")
    for field in ("base", "model", "key", "port"):
        if "TIINY_" + field.upper() in os.environ:
            values[field] = os.environ["TIINY_" + field.upper()]
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    if isinstance(values.get("base"), str) and not values["base"].strip():
        from . import device as tiiny_device
        values["base"] = tiiny_device.find_base()
        if not values["base"]:
            raise Refusal(
                "No Tiiny found. Looked at TIINY_BASE, ~/.tiinyapps/device.json, "
                "the USB links and this machine's own network. Set --base or "
                "TIINY_BASE to the device's address.")
    try:
        values["port"] = int(values["port"])
        if not 1 <= values["port"] <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise Refusal("Choose a port from 1 to 65535 with --port or config.json.") from None
    for field in ("base", "model", "bind", "name", "key"):
        if not isinstance(values[field], str) or (field != "key" and not values[field].strip()):
            raise Refusal("Config values must be text, with a numeric port.")
    parsed = urllib.parse.urlsplit(values["base"])
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Refusal("Use a plain HTTP or HTTPS model address without embedded credentials.")
    return values


def read_persona(root):
    return (Path(root) / "persona.md").read_text(encoding="utf-8")


def read_memories(root):
    facts = {}
    for path in sorted((Path(root) / "memory").rglob("*.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"-\s+\((\d{4}-\d{2}-\d{2})\)\s+(.+?)\s*", line)
            if not match:
                continue
            date, text = match.groups()
            text = " ".join(text.split())
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                continue
            if not text or len(text) > 500:
                continue
            ident = hashlib.sha1(text.lower().encode()).hexdigest()[:16]
            facts.setdefault(ident, dict(id=ident, name=text, description=text,
                                        chars=len(text), updatedAt=date,
                                        path=str(path.relative_to(root))))
    return list(facts.values())


def read_skills(root):
    result = []
    for path in sorted((Path(root) / "skills").glob("*/SKILL.md")):
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
            continue
        text = path.read_text(encoding="utf-8")
        pieces = text.split("---", 2)
        if len(pieces) != 3 or pieces[0].strip():
            continue
        meta = {}
        rows = pieces[1].splitlines()
        for i, row in enumerate(rows):
            match = re.fullmatch(r"(name|description):[ \t]*(.*)", row)
            if not match:
                continue
            key, value = match.groups()
            if value.strip() in (">", ">-", "|", "|-"):
                continued = []
                for following in rows[i + 1:]:
                    if following and not following[0].isspace():
                        break
                    continued.append(following.strip())
                value = " ".join(continued).strip()
            meta[key] = value
        name = meta.get("name", "").strip("\"'")
        description = meta.get("description", "").strip("\"'")
        if not name or len(name) > 80 or not description or len(description) > 1536 or len(pieces[2].strip()) > 100000:
            continue
        result.append(dict(id=path.parent.name, name=name, description=description,
                           enabled=not (path.parent / "disabled").exists(),
                           path=str(path.relative_to(root)), body=pieces[2].strip()[:16000]))
    return result


def build_prompt(root, text="", name=None):
    settings_file = Path(root) / "settings.json"
    preferences = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    memories = read_memories(root)
    profile = [m for m in memories if m["path"] == "memory/profile.md"]
    recent = sorted((m for m in memories if m["path"].startswith("memory/log/")),
                    key=lambda m: m["updatedAt"])[-40:]
    recall = [f'- ({m["updatedAt"]}) {m["name"]}' for m in profile + recent]
    skills = read_skills(root)
    catalog = "\n".join(f'{s["name"]}: {s["description"]} ({s["path"]})' + (" [disabled]" if not s["enabled"] else "") for s in skills)
    return "\n\n".join((BASE_PROMPT, read_persona(root),
                          "The owner calls you " + (name or preferences.get("botName", "Titan")) + ".",
                          "Preferred reply language: " + preferences.get("language", "en") + ".",
                          "Ask the owner before: " + preferences.get("askBefore", ""),
                          f"Local time: {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}.",
                          HANDBOOK,
                          "Use run_skill to open handbook skills. Read and Write only see files/. "
                          "Credentials currently belong in local keys.json; no masked Settings box exists yet. "
                          "If profile memory says setup is complete, that overrides the seed’s initial setup status. "
                          "Routines now run on five-field cron in local time. Create them disabled and tell the owner "
                          "they are switched off until the owner enables them. Only enable or resume a routine "
                          "when the owner explicitly asks. Scheduled prompts cannot enable routines.",
                          "Saved routines:\n" + "\n".join(json.dumps(dict(id=p.parent.name, **r)) for p, r in read_routines(Path(root))),
                          "Saved memories:\n" + "\n".join(recall),
                          f"{len(memories) - len(recall)} more facts are saved on disk.",
                          "Available skills:\n" + catalog))


class LogFormatter(logging.Formatter):
    """Keep credentials out of diagnostics, including exception tracebacks."""
    def __init__(self, key):
        super().__init__("%(asctime)s %(levelname)s %(message)s")
        self.key = key

    def format(self, record):
        text = super().format(record)
        return text.replace(self.key, "[redacted]") if self.key else text


class Device:
    """All requests hold the same device lane; retries never replay emitted text."""
    def __init__(self, root, base, key, model):
        # Keep runtime files in the selected data directory unless the owner supplies
        # a shared lane directory for coordination with their other applications.
        os.environ.setdefault("ONELANE_DIR", str(root / ".onelane"))
        Path(os.environ["ONELANE_DIR"]).mkdir(parents=True, exist_ok=True)
        from .onelane import OneLane
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise Refusal("Use a plain HTTP or HTTPS model address without embedded credentials.")
        self.base, self.key, self.model = base.rstrip("/"), key, model
        self.resolved_model = None if model == "default" else model
        # Hand the lane the port the base already names. OneLane probes the
        # device for it when the port is left out, and it must not: we already
        # know, the lane has to agree with the rest of this class, and two HTTP
        # probes on every construction is not a thing to pay for an answer we
        # are holding.
        self.lane = OneLane(host=parsed.hostname, key=key,
                            port=parsed.port or (443 if parsed.scheme == "https" else 80),
                            owner="Titanium Bot Lite", settle_s=0)
        self.busy_budget = 90.0
        self.log = logging.Logger("lite", logging.DEBUG if os.getenv("LITE_DEBUG") == "1" else logging.WARNING)
        handler = logging.FileHandler(root / "lite.log", encoding="utf-8", delay=True)
        handler.setFormatter(LogFormatter(key))
        self.log.addHandler(handler)

    def request(self, path, body=None, on_token=None):
        if self.model == "echo" and path == "/models":
            return {"data": [{"id": "echo", "name": "Echo (development)"}]}
        started = time.monotonic()
        attempt = 0
        emitted = False
        while True:
            try:
                self.log.debug("lane waiting path=%s attempt=%d", path, attempt + 1)
                with self.lane.hold(why="Titan answering" if body else "Reading available models", wait=90):
                    request = urllib.request.Request(
                        self.base + path, data=json.dumps(body).encode() if body is not None else None,
                        headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
                    self.log.debug("request sent path=%s attempt=%d", path, attempt + 1)
                    with urllib.request.urlopen(request, timeout=120) as response:
                        if on_token and "text/event-stream" in response.headers.get("Content-Type", ""):
                            usage, calls, content = {}, {}, []
                            kinds = dict(content=0, tool_calls=0, reasoning=0, finish=0, usage=0, other=0)
                            def result():
                                message = dict(role="assistant", content="".join(content) or None)
                                self.log.debug("stream finished chunk kinds=%s", kinds)
                                if calls:
                                    message["tool_calls"] = [calls[i] for i in sorted(calls)]
                                return dict(usage, _message=message)
                            for raw in response:
                                if not raw.startswith(b"data:"):
                                    continue
                                data = raw[5:].strip()
                                if data == b"[DONE]":
                                    return result()
                                event = json.loads(data)
                                if event.get("code") == 150004 or (isinstance(event.get("error"), dict) and event["error"].get("code") == 150004):
                                    raise urllib.error.HTTPError(request.full_url, 503, "Busy", {}, None)
                                if event.get("error"):
                                    raise Refusal("The model could not finish this reply.", 502)
                                usage = event.get("usage") or usage
                                if event.get("usage"):
                                    kinds["usage"] += 1
                                for choice in event.get("choices", []):
                                    if choice.get("index", 0) != 0:
                                        continue
                                    delta = choice.get("delta") or {}
                                    kinds["content"] += bool(delta.get("content"))
                                    kinds["tool_calls"] += bool(delta.get("tool_calls"))
                                    kinds["reasoning"] += bool(delta.get("reasoning_content"))
                                    kinds["finish"] += bool(choice.get("finish_reason"))
                                    kinds["other"] += not any(delta.get(k) for k in ("content", "tool_calls", "reasoning_content"))
                                    if choice.get("finish_reason"):
                                        self.log.debug("stream finish reason=%s", choice["finish_reason"])
                                    for fragment in delta.get("tool_calls", []):
                                        call = calls.setdefault(fragment["index"], dict(id="", type="function", function=dict(name="", arguments="")))
                                        if fragment.get("id"):
                                            call["id"] += fragment["id"]
                                        for key in ("name", "arguments"):
                                            call["function"][key] += fragment.get("function", {}).get(key, "")
                                    token = delta.get("content")
                                    if token:
                                        emitted = True
                                        content.append(token)
                                        on_token(token)
                                self.log.debug("chunk kinds counted=%s", kinds)
                            return result()
                        payload = json.load(response)
                        if payload.get("code") == 150004 or (isinstance(payload.get("error"), dict) and payload["error"].get("code") == 150004):
                            raise urllib.error.HTTPError(request.full_url, 503, "Busy", {}, None)
                        if payload.get("error"):
                            raise Refusal("The device refused the request. Check its settings.", 502)
                        if on_token:
                            message = payload.get("choices", [{}])[0].get("message", {})
                            if message.get("content"):
                                on_token(message["content"])
                            return dict(payload.get("usage") or {}, _message=message)
                        return payload
            except urllib.error.HTTPError as error:
                self.log.exception("request HTTP exception path=%s", path)
                # Never expose an upstream response or URL: it may contain credentials.
                try:
                    raw = error.read(65536) if error.fp else b""
                finally:
                    error.close()
                busy = error.code in (502, 503, 504) or b"150004" in raw
                elapsed = time.monotonic() - started
                if not busy or emitted or elapsed >= self.busy_budget:
                    raise Refusal("The device is busy or unavailable. Please try again.", 503) from None
                delay = min(2 ** min(attempt, 4) + random.random(), self.busy_budget - elapsed)
                time.sleep(delay)
                attempt += 1
            except (urllib.error.URLError, TimeoutError, OSError):
                self.log.exception("request transport exception path=%s", path)
                raise Refusal("Cannot reach the device. Check its address and that its model is running.", 503) from None
            except Exception:
                self.log.exception("request exception path=%s", path)
                raise
            finally:
                self.log.debug("request attempt finished; lane released path=%s", path)

    @staticmethod
    def is_chat_model(row):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            return False
        if "supports_chat" in row:
            return row["supports_chat"] is True
        capabilities = row.get("capabilities")
        kind = row.get("type")
        return ((isinstance(capabilities, list) and "main" in capabilities)
                or (isinstance(kind, str) and "Text-to-Text" in kind))

    def resolve_model(self, rows=None):
        if self.model != "default":
            self.resolved_model = self.model
            return self.model
        self.resolved_model = None
        if rows is None:
            rows = self.request("/models").get("data", [])
        self.resolved_model = next((row["id"] for row in rows if self.is_chat_model(row)), None)
        if self.resolved_model is None:
            raise Refusal("The device lists no chat models. Start a chat model on the device.", 503)
        return self.resolved_model

    def chat(self, messages, on_token, *, thinking=False, allow_tools=True):
        if self.model == "echo":
            prompt = next(message["content"] for message in reversed(messages) if message["role"] == "user")
            answer = prompt[::-1]
            for index in range(0, len(answer), 8):
                on_token(answer[index:index + 8])
                time.sleep(0.01)
            return {"total_tokens": 0}  # No model tokens were spent.
        model = self.resolve_model()
        return self.request("/chat/completions", dict(model=model, messages=messages,
                            stream=True, stream_options={"include_usage": True}, max_tokens=1000,
                            chat_template_kwargs={"enable_thinking": thinking},
                            **({"tools": TOOLS} if allow_tools else {"tool_choice": "none", "tools": TOOLS})), on_token)


class App:
    def __init__(self, data_dir=None, overrides=None):
        self.started = time.monotonic()
        self.root = Path(data_dir or os.getenv("TIINY_DATA_DIR", "./data")).resolve()
        self.overrides = overrides or {}
        self.config = load_config(self.root, self.overrides)
        for name in ("memory/log", "skills", "routines", "files", "transcripts", "handbook"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name, content in (("persona.md", PERSONA), ("keys.json", "{}"),
                              ("memory/profile.md", '# About the user\n<!-- - (YYYY-MM-DD) fact -->\n'),
                              ("handbook/what-i-can-do.md", HANDBOOK)):
            if not (self.root / name).exists():
                atomic_write(self.root / name, content, 0o600 if name == "keys.json" else 0o644)
        for seed in SEEDS.glob("*/SKILL.md"):
            destination = self.root / "skills" / seed.parent.name / "SKILL.md"
            if not destination.exists():
                atomic_write(destination, seed.read_text())
        (self.root / "keys.json").chmod(0o600)
        self.settings = dict(theme="dusk", background="titan-nebula", language="en", botName="Titan",
                             askBefore="", talkEnabled=False, micDeviceId="", voice=dict(
                                 enabled=False, mode="off", vendor="device", voice="", minutesToday=0))
        if (self.root / "settings.json").exists():
            saved = json.loads((self.root / "settings.json").read_text())
            self.settings.update({k: v for k, v in saved.items() if k in self.settings})
        self.settings["botName"] = self.config["name"]
        self.device = Device(self.root, self.config["base"], self.config["key"], self.config["model"])
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.revision = 0
        self.messages = []
        if (self.root / "transcripts/main.json").exists():
            self.messages = json.loads((self.root / "transcripts/main.json").read_text())
        if not (self.root / "transcripts/main.json").exists():
            self.messages.append(self.message("titan", "I’m " + self.settings["botName"] + ", your assistant on this device. What should I call you?"))
            self.save_messages()
        self.jobs = queue.Queue(maxsize=16)
        # A stopped process cannot resume an unfinished inference. Retain its failure
        # in the transcript rather than leaving a permanent typing indicator.
        recovered = False
        for message in self.messages:
            if message.get("type") == "working":
                message.update(type="turn-failed", text="The server stopped before this reply finished. Please send your message again.")
                recovered = True
        if recovered:
            self.save_messages()
        self.stopping = threading.Event()
        self.active = False
        self.voice_waiters = {}
        from .voice import Voice
        self.voice = Voice(self)
        self.tokens = 0
        self.seconds = 0.0
        self.worker = threading.Thread(target=self._work, name="Titan turns", daemon=True)
        self.scheduler = Scheduler(self)
        self.worker.start()
        self.scheduler.thread.start()
        self.cold_start_ms = (time.monotonic() - self.started) * 1000

    def poke(self):
        with self.changed:
            self.revision += 1
            self.changed.notify_all()

    def save_messages(self, transcript=None, conversation="main"):
        atomic_write(self.root / "transcripts" / (conversation + ".json"),
                     json.dumps(self.messages if transcript is None else transcript, ensure_ascii=False))

    def close(self):
        self.stopping.set()
        self.poke()
        self.worker.join(timeout=2)
        self.scheduler.thread.join(timeout=2)
        self.voice.thread.join(timeout=2)
        self.voice.close()
        for handler in self.device.log.handlers:
            handler.close()

    def live(self):
        return dict(source="device", endpoint=self.device.base,
                    model=self.device.resolved_model or self.device.model, resolvedModel=self.device.resolved_model)

    def budget(self):
        import resource
        import sys
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
        return dict(rssMb=round(rss_mb, 2), firstPaintKb=round(first_paint_bytes() / 1000, 2),
                    coldStartMs=round(self.cold_start_ms, 2))

    def get_settings(self):
        return dict(copy.deepcopy(self.settings), base=self.device.base, model=self.device.model, resolvedModel=self.device.resolved_model, persona=read_persona(self.root), version=__version__,
                    budget=self.budget(), usage=dict(tokens=self.tokens, minutes=round(self.seconds / 60, 3)))

    def patch_settings(self, body):
        allowed = set(self.settings) | {"persona", "base", "model"}
        if set(body) - allowed:
            raise Refusal("One of these settings cannot be changed.")
        for key, value in body.items():
            if key == "voice":
                if not isinstance(value, dict) or set(value) - {"enabled", "mode", "vendor", "voice", "minutesToday"}:
                    raise Refusal("Voice settings must be an object with known fields.")
                if "enabled" in value and not isinstance(value["enabled"], bool):
                    raise Refusal("Voice must be on or off.")
                if any(k in value and not isinstance(value[k], str) for k in ("vendor", "voice")):
                    raise Refusal("Voice choices must be text.")
                if "minutesToday" in value and value["minutesToday"] != self.settings["voice"]["minutesToday"]:
                    raise Refusal("Talking time is measured by the server.")
                if "mode" in value and value["mode"] not in ("off", "push", "always"):
                    raise Refusal("Choose off, push to talk or always listening.")
            elif key == "talkEnabled":
                if not isinstance(value, bool):
                    raise Refusal("Talk must be on or off.")
            elif not isinstance(value, str) or len(value) > 32000:
                raise Refusal("This setting needs a short piece of text.")
        if body.get("theme", "dusk") not in ("dusk", "mist", "ink", "light", "dark", "system"):
            raise Refusal("Choose a supported theme.")
        with self.lock:
            changes = {k: body[k] for k in ("base", "model") if k in body}
            if "botName" in body:
                changes["name"] = body["botName"]
            if changes:
                self.save_config(changes)
            for key, value in body.items():
                if key in ("base", "model", "botName"):
                    continue
                if key == "persona":
                    atomic_write(self.root / "persona.md", value)
                elif key == "voice":
                    self.settings[key].update(value)
                    mode = value.get("mode", self.settings[key].get("mode", "off"))
                    if "enabled" in value and "mode" not in value:
                        mode = "push" if value["enabled"] else "off"
                    self.settings[key].update(mode=mode, enabled=mode != "off")
                    self.settings["talkEnabled"] = mode != "off"
                else:
                    self.settings[key] = value
                    if key == "talkEnabled":
                        self.settings["voice"].update(enabled=value, mode="push" if value else "off")
            atomic_write(self.root / "settings.json", json.dumps(self.settings))
            self.poke()
            return self.get_settings()

    def save_config(self, changes):
        with self.lock:
            if self.active or not self.jobs.empty() or self.voice.busy:
                raise Refusal("Wait for Titan to finish before changing the configuration.", 409)
            self.voice.close()
            if self.voice.loaded:
                raise Refusal("The device could not release its speech model. Please try again.", 503)
            path = self.root / "config.json"
            saved = DEFAULTS | json.loads(path.read_text()) | changes
            if any(not isinstance(v, str) or not v.strip() for k, v in changes.items()):
                raise Refusal("Enter a nonempty address, model and name.")
            # Validate the saved address even when an environment override is
            # active. An empty base is legal and means "find the device", which is
            # the shipped default, so there is nothing to validate in that case.
            if str(saved.get("base") or "").strip():
                Device(self.root, saved["base"], self.device.key, saved["model"])
            atomic_write(path, json.dumps(saved, indent=2) + "\n")
            self.config = load_config(self.root, self.overrides)
            self.voice.tts_model = None
            for handler in self.device.log.handlers:
                handler.close()
            self.device = Device(self.root, self.config["base"], self.config["key"], self.config["model"])
            self.settings["botName"] = self.config["name"]
            self.poke()

    def library(self):
        skills = [{k: v for k, v in s.items() if k != "body"} for s in read_skills(self.root)]
        routines = []
        with self.lock:
            for path, item in read_routines(self.root):
                ident = path.parent.name
                next_run = self.scheduler.next_runs.get(ident, (None, None))[1]
                routines.append(dict(id=ident, name=item["name"], cron=item["schedule"],
                                     nextRunAt=int(next_run * 1000) if next_run else None,
                                     enabled=item.get("enabled") is True, lastRun=item.get("lastRunAt"),
                                     conversationId="routine-" + ident))
        return dict(memories=read_memories(self.root), skills=skills, routines=routines)

    def library_action(self, body):
        kind, verb = body.get("kind"), body.get("verb")
        with self.lock:
            if kind == "memory" and verb == "remember":
                self.update_state(dict(target="profile", action="write", fact=body.get("text", "")))
            elif kind == "memory" and verb == "forget":
                items = [m for m in read_memories(self.root) if m["id"] == body.get("id")]
                if not items:
                    raise Refusal("That memory was not found.", 404)
                name = items[0]["name"].lower()
                for path in (self.root / "memory").rglob("*.md"):
                    if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                        continue
                    lines = [line for line in path.read_text().splitlines()
                             if " ".join(re.sub(r"^-\s+\([0-9-]+\)\s+", "", line).split()).lower() != name]
                    atomic_write(path, "\n".join(lines) + "\n")
            elif kind == "skill" and verb in ("enable", "disable", "run"):
                skill = next((s for s in read_skills(self.root) if s["id"] == body.get("id")), None)
                if not skill:
                    raise Refusal("That skill was not found.", 404)
                if verb == "run":
                    if not skill["enabled"]:
                        raise Refusal("Switch this skill on first.")
                    self.send(dict(agentId="titan", text=f'Run skill {skill["name"]}:\n\n{skill["body"]}'))
                else:
                    marker = (self.root / skill["path"]).parent / "disabled"
                    if verb == "disable":
                        atomic_write(marker, "disabled\n")
                    else:
                        marker.unlink(missing_ok=True)
            elif kind == "routine" and verb in ("enable", "disable", "pause", "delete"):
                self.update_state(dict(target="routine", action={"disable": "pause"}.get(verb, verb), id=body.get("id")))
            else:
                raise Refusal("That library action is not supported.")
            self.poke()
            return dict(ok=True, library=self.library())

    def state(self):
        with self.lock:
            library = self.library()
            files = [dict(path=str(p.relative_to(self.root)), name=p.name, size=p.stat().st_size)
                     for p in (self.root / "files").glob("*") if p.is_file() and not p.is_symlink()]
            return dict(activeContext=dict(kind="worker", id="titan"), openContexts=[dict(kind="worker", id="titan")],
                        workers=[dict(id="titan", name=self.settings["botName"], role="Your local assistant",
                                      status="working" if self.active or not self.jobs.empty() else "idle",
                                      statusText="Answering" if self.active else "Ready", accent="cyan",
                                      model=self.device.resolved_model or self.device.model, messages=copy.deepcopy(self.messages[-100:]),
                                      files=files, hasOlder=len(self.messages) > 100)], rooms=[],
                        models=[dict(id=self.device.resolved_model or self.device.model,
                                     name=self.device.resolved_model or self.device.model)],
                        routines=library["routines"], skills=library["skills"])

    def send(self, body, attachments=None, *, spoken=False):
        text = body.get("text", "")
        if body.get("agentId") != "titan":
            raise Refusal("That conversation was not found.", 404)
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise Refusal("Write a message of between 1 and 32000 characters.")
        with self.lock:
            if self.jobs.full():
                raise Refusal("Please wait for the queued replies.", 429)
            message = self.message("you", text.strip())
            if spoken:
                message["spoken"] = True
            if attachments:
                message["attachments"] = attachments
            self.messages.append(message)
            self.save_messages()
            self.jobs.put_nowait(message["id"])
            self.poke()
            return dict(message=copy.deepcopy(message))

    def message(self, author, text, kind="text"):
        now = datetime.now()
        return dict(id=uuid.uuid4().hex, authorId=author, authorName="You" if author == "you" else self.settings["botName"],
                    type=kind, text=text, time=now.strftime("%H:%M"), timestampMs=int(now.timestamp() * 1000), status="sent")

    def tool_loop(self, messages, on_token, reply, transcript=None, conversation="main"):
        transcript = self.messages if transcript is None else transcript
        total, rounds, empty = 0, 0, 0
        created = set()
        def finish():
            if created:
                on_token("\n\nNew routines are switched off until you enable them in Routines.")
            return dict(total_tokens=total)
        while True:
            options = {}
            if empty == 2:
                options["thinking"] = True
            if rounds == 6:
                options["allow_tools"] = False
            self.device.log.debug("loop request round=%d empty=%d options=%s", rounds, empty, options)
            usage = self.device.chat(messages, on_token, **options) or {}
            count = usage.get("total_tokens")
            total = total + int(count) if total is not None and count is not None else None
            message = usage.get("_message")
            if message is None:  # Echo and simple test clients stream directly.
                return finish()
            calls = message.get("tool_calls") or []
            if not calls:
                if message.get("content"):
                    return finish()
                empty += 1
                if empty > 2:
                    raise Refusal("The model returned no text after retrying. Please try again.", 502)
                continue
            empty = 0
            if rounds == 6:
                raise Refusal("Titan reached the six-round tool limit. Please send a follow-up.")
            rounds += 1
            messages.append(dict(role="assistant", content=message.get("content"), tool_calls=calls))
            for call in calls:
                name = call.get("function", {}).get("name", "")
                self.device.log.debug("tool call assembled name=%s argument_length=%d", name, len(call.get("function", {}).get("arguments", "")))
                try:
                    arguments = json.loads(call.get("function", {}).get("arguments", "{}"))
                    if not isinstance(arguments, dict):
                        raise ValueError
                    if name == "update_state" and arguments.get("target") == "routine":
                        enables = arguments.get("action") in ("enable", "resume") or arguments.get("enabled") is True
                        if enables and (conversation != "main" or arguments.get("id") in created):
                            raise Refusal("The owner must enable this routine in a later request or in Routines.")
                    result = self.run_tool(name, arguments)
                    if name == "update_state" and arguments.get("target") == "routine" and arguments.get("action") == "create":
                        created.add(result.split()[2])
                except Refusal as error:
                    self.device.log.exception("tool refused name=%s", name)
                    result = "Refused: " + str(error)
                except (ValueError, TypeError, KeyError, OSError):
                    self.device.log.exception("tool exception name=%s", name)
                    result = "Refused: The tool arguments or file contents are invalid."
                # Never include the configured credential in tool results or receipts.
                if self.device.key:
                    result = result.replace(self.device.key, "[redacted]")
                self.device.log.debug("tool executed name=%s result_length=%d", name, len(result))
                messages.append(dict(role="tool", tool_call_id=call["id"], content=result))
                with self.lock:
                    receipt = self.message("titan", name + (" refused" if result.startswith("Refused:") else " completed"), "system")
                    receipt["detail"] = result
                    receipt["toolCallId"] = call["id"]
                    transcript.insert(transcript.index(reply), receipt)
                    self.save_messages(transcript, conversation)
                    self.poke()

    def update_state(self, args):
        target, action = args.get("target"), args.get("action")
        with self.lock:
            if target in ("memory", "profile"):
                # The device emits shorthand memory writes as {target, text}.
                # Explicit actions and canonical facts retain their existing meaning.
                if "action" not in args and "text" in args:
                    action = "write"
                if action not in ("write", "set", "forget"):
                    raise Refusal("Use write or forget for a memory.")
                fact = args.get("fact", args.get("text", ""))
                if not isinstance(fact, str):
                    raise Refusal("A memory must be text.")
                fact = " ".join(fact.split())
                tier = "profile" if target == "profile" else args.get("tier", "log")
                if tier not in ("profile", "log", "note"):
                    raise Refusal("Choose profile, log or note for this memory.")
                if fact and tier == "note" and not fact.startswith("[note] "):
                    fact = "[note] " + fact
                if not fact or len(fact) > 500:
                    raise Refusal("A memory needs between 1 and 500 characters. Split a long fact first.")
                existing = next((m for m in read_memories(self.root) if m["name"].lower() == fact.lower()), None)
                if action == "forget":
                    if not existing:
                        raise Refusal("That memory was not found.", 404)
                    self.library_action(dict(kind="memory", verb="forget", id=existing["id"]))
                    return "Forgot the fact."
                if existing:
                    return "That fact is already saved."
                path = self.root / ("memory/profile.md" if tier == "profile" else f"memory/log/{datetime.now():%Y-%m}.md")
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    raise Refusal("The memory path is not safe.")
                content = path.read_text() if path.exists() else '# Memory log\n<!-- - (YYYY-MM-DD) fact -->\n'
                atomic_write(path, content.rstrip() + f"\n- ({datetime.now():%Y-%m-%d}) {fact}\n")
                self.poke()
                return "Remembered: " + fact
            if target == "routine":
                from .agent_tools import validate_cron
                if action not in ("create", "update", "pause", "delete", "enable", "resume"):
                    raise Refusal("Choose create, update, enable, pause or delete for a routine.")
                if "enabled" in args and type(args["enabled"]) is not bool:
                    raise Refusal("Enabled must be true or false.")
                ident = uuid.uuid4().hex if action == "create" else args.get("id", "")
                if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", ident):
                    raise Refusal("Choose a routine from the library.")
                folder = self.root / "routines" / ident
                if folder.is_symlink() or not folder.resolve().is_relative_to(self.root):
                    raise Refusal("The routine path is not safe.")
                path = folder / "routine.json"
                if path.is_symlink():
                    raise Refusal("The routine path is not safe.")
                if action == "create":
                    if len(list((self.root / "routines").glob("*/routine.json"))) >= 50:
                        raise Refusal("The device can hold at most 50 routines.")
                    item = dict(createdAt=int(time.time() * 1000), lastRunAt=None)
                else:
                    if not path.is_file():
                        raise Refusal("That routine was not found.", 404)
                    item = json.loads(path.read_text())
                if action == "delete":
                    path.unlink()
                    (folder / "runs.json").unlink(missing_ok=True)
                    self.scheduler.next_runs.pop(ident, None)
                    self.poke()
                    return "Deleted the routine."
                for key in ("name", "prompt", "schedule"):
                    if key in args:
                        item[key] = args[key]
                if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("name", "prompt", "schedule")):
                    raise Refusal("A routine needs a name, prompt and five-field cron schedule.")
                item["schedule"] = validate_cron(item["schedule"])
                item["enabled"] = (False if action in ("create", "pause") else
                                   True if action in ("enable", "resume") else args.get("enabled", item.get("enabled", False)))
                atomic_write(path, json.dumps(item, indent=2) + "\n")
                if action == "create":
                    atomic_write(folder / "runs.json", "[]\n")
                self.scheduler.next_runs.pop(ident, None)
                self.scheduler.refresh(time.time())
                self.poke()
                return "Saved routine " + ident + (" enabled." if item["enabled"] else " switched off. The owner must enable it before it runs.")
        raise Refusal("Choose memory, profile or routine as the target.")

    def run_tool(self, name, args):
        from .agent_tools import file_tool, fetch_url
        if name in ("Read", "Write"):
            return file_tool(self.root, name, args)
        if name == "fetch_url":
            return fetch_url(args["url"])
        if name == "run_skill":
            skill = next((s for s in read_skills(self.root) if s["name"] == args["name"]), None)
            if not skill or not skill["enabled"]:
                raise Refusal("That skill is unavailable. Choose an enabled skill from the catalog.")
            return skill["body"]
        if name == "update_state":
            return self.update_state(args)
        raise Refusal("That tool is not available on this device.")

    def _work(self):
        while not self.stopping.is_set():
            try:
                job = self.jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            started = time.monotonic()
            run = None
            reply = None
            conversation = "main"
            transcript = self.messages
            try:
                with self.lock:
                    if isinstance(job, tuple):
                        _, ident, due, signature = job
                        row = next(((p, r) for p, r in read_routines(self.root) if p.parent.name == ident), None)
                        if not row or row[1].get("enabled") is not True:
                            continue
                        path, routine = row
                        if signature != (routine["schedule"], routine.get("createdAt")):
                            continue
                        conversation = "routine-" + ident
                        transcript_path = self.root / "transcripts" / (conversation + ".json")
                        transcript = json.loads(transcript_path.read_text()) if transcript_path.exists() else []
                        user = self.message("you", routine["prompt"])
                        user["conversationName"] = routine["name"]
                        transcript.append(user)
                        run = dict(id=uuid.uuid4().hex, trigger="cron", startedAt=int(time.time() * 1000),
                                   finishedAt=None, status="running", detail="", conversationId=conversation)
                        runs_path = path.parent / "runs.json"
                        runs = json.loads(runs_path.read_text()) if runs_path.exists() else []
                        runs = (runs + [run])[-20:]
                        atomic_write(runs_path, json.dumps(runs))
                        routine["lastRunAt"] = run["startedAt"]
                        atomic_write(path, json.dumps(routine, indent=2) + "\n")
                        end = len(transcript) - 1
                    else:
                        end = next(i for i, m in enumerate(transcript) if m["id"] == job)
                        user = transcript[end]
                    self.active = True
                    history = [m for m in transcript[:end + 1] if m["type"] == "text"][-40:]
                    reply = self.message("titan", "", "working")
                    transcript.insert(end + 1, reply)
                    self.save_messages(transcript, conversation)
                    self.poke()
                def token(chunk):
                    with self.lock:
                        if not reply["text"]:
                            self.device.log.debug("final text started conversation=%s", conversation)
                        reply["text"] += chunk
                        self.poke()
                try:
                    messages = [dict(role="system", content=build_prompt(self.root, user["text"], self.settings["botName"]))]
                    messages += [dict(role="user" if m["authorId"] == "you" else "assistant", content=m["text"] + ("\nAttached files: " + ", ".join(a["path"] for a in m["attachments"]) if m.get("attachments") else "")) for m in history]
                    usage = self.tool_loop(messages, token, reply, transcript, conversation)
                    with self.lock:
                        reply["type"] = "text"
                        count = (usage or {}).get("total_tokens")
                        self.tokens = self.tokens + int(count) if self.tokens is not None and count is not None else None
                except Exception as error:
                    self.device.log.exception("turn exception conversation=%s", conversation)
                    with self.lock:
                        reply["type"] = "turn-failed"
                        reply["text"] = str(error) if isinstance(error, Refusal) else "Titan could not finish this reply. Please try again."
                with self.lock:
                    self.save_messages(transcript, conversation)
                    self.device.log.debug("final text finished conversation=%s status=%s length=%d", conversation, reply["type"], len(reply["text"]))
                    if run is not None and path.exists():
                        run.update(finishedAt=int(time.time() * 1000), status="error" if reply["type"] == "turn-failed" else "ok", detail=reply["text"])
                        atomic_write(runs_path, json.dumps(runs))
            except (OSError, ValueError, TypeError):
                # A malformed routine file cannot kill the shared turn worker.
                self.device.log.exception("worker exception conversation=%s", conversation)
            finally:
                with self.lock:
                    if isinstance(job, tuple):
                        self.scheduler.pending.discard(job[1])
                    self.seconds += time.monotonic() - started
                    self.active = False
                    self.poke()
                with self.lock:
                    waiter = self.voice_waiters.pop(job, None) if isinstance(job, str) else None
                    if waiter:
                        waiter[1].update(reply or dict(type="turn-failed", text="Titan could not finish this reply."))
                        waiter[0].set()
                self.jobs.task_done()


def first_paint_bytes(base_url=None):
    """Read the door's resource graph with urllib, without launching a browser.

    A supplied HTTP base measures served bytes. Otherwise file URLs measure the
    same resources offline; this is a byte budget, not a rendered paint timing.
    """
    from html.parser import HTMLParser

    base_url = (base_url or CONSOLE.resolve().as_uri()).rstrip("/") + "/"

    def read(name):
        with urllib.request.urlopen(urllib.parse.urljoin(base_url, name), timeout=10) as response:
            return response.read()

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = {"index.html"}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in ("script", "img") and attrs.get("src"):
                self.paths.add(attrs["src"])
            if tag == "link" and attrs.get("rel") in ("stylesheet", "icon", "preload"):
                self.paths.add(attrs["href"])

    parser = Assets()
    parser.feed(read("index.html").decode("utf-8"))
    pending, seen, total = list(parser.paths), set(), 0
    while pending:
        name = pending.pop()
        if name in seen or name.startswith("data:"):
            continue
        target = (CONSOLE / name).resolve()
        if not target.is_relative_to(CONSOLE.resolve()) or not target.is_file():
            raise ValueError("The door references an absent or external asset.")
        seen.add(name)
        data = read(name)
        total += len(data)
        if target.suffix == ".css":
            urls = re.findall(r"url\(\s*['\"]?([^)'\"]+)", data.decode("utf-8"))
            for url in urls:
                if not url.startswith("data:"):
                    pending.append(str(Path(name).parent / url.strip()))
    return total


def selfcheck(app):
    """Measure import-to-HTTP readiness, then one real configured-model turn."""
    try:
        server = Server(("127.0.0.1", 0), app)
    except OSError as error:
        raise Refusal("The cold-start probe could not bind a spare port.", 500) from error
    thread = threading.Thread(target=server.serve_forever, name="Titan startup probe", daemon=True)
    try:
        thread.start()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{server.server_port}/api/health", timeout=10) as response:
                if response.status != 200 or json.load(response).get("app") != "titanium-bot-lite":
                    raise Refusal("The cold-start probe failed.", 500)
            cold_ms = (time.monotonic() - IMPORT_STARTED) * 1000
        except (OSError, ValueError, HTTPException) as error:
            raise Refusal("The cold-start probe failed or timed out.", 500) from error
    finally:
        if thread.ident is not None:
            server.shutdown()
            thread.join()
        server.server_close()
    app.cold_start_ms = cold_ms
    budget = app.budget()  # Idle high-water RSS, before inference; an upper bound.
    started, first, parts = time.monotonic(), None, []
    def token(chunk):
        nonlocal first
        if first is None:
            first = time.monotonic()
        parts.append(chunk)
    error = None
    try:
        prompt = "Say hello in five words"
        app.device.chat([{"role": "system", "content": build_prompt(app.root, prompt, app.settings["botName"])},
                         {"role": "user", "content": prompt}], token)
    except Exception as failure:
        error = str(failure) if isinstance(failure, Refusal) else "The configured model check failed."
    if not parts and error is None:
        error = "The configured model returned no text."
    passed = budget["rssMb"] < 200 and budget["firstPaintKb"] < 250 and cold_ms < 5000
    result = dict(ok=error is None and passed, mode="echo" if app.device.model == "echo" else "configured device",
                  budget=budget, firstPaintBytes=first_paint_bytes(),
                  timings=dict(firstTokenMs=round((first - started) * 1000, 2) if first else None,
                               turnMs=round((time.monotonic() - started) * 1000, 2)),
                  replyCharacters=sum(map(len, parts)), budgetPassed=passed)
    if error:
        result["error"] = error
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["ok"] else 1


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, app):
        self.app = app
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # URLs, payloads and upstream errors never enter access logs.

    def respond(self, value, status=200, content_type="application/json; charset=utf-8", headers=None):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if not headers or "Cache-Control" not in headers:
            self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def body(self, voice=False):
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
            raise Refusal("Open the console on this server before making changes.", 403)
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Refusal("Invalid request length.") from None
        if size < 0 or size > 10 * 1024 * 1024:
            raise Refusal("This upload is too large. Keep it below 10 MB.", 413)
        raw = self.rfile.read(size)
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            mail = BytesParser(policy=default).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
            fields, attachments = {}, []
            for part in mail.iter_parts():
                name = part.get_param("name", header="content-disposition")
                data = part.get_payload(decode=True) or b""
                if part.get_filename():
                    filename = Path(part.get_filename()).name
                    suffix = Path(filename).suffix.lower()
                    if voice:
                        if name != "file" or suffix not in (".webm", ".wav") or not data or attachments:
                            raise Refusal("Send one WebM or WAV recording.")
                        attachments.append(dict(data=data, suffix=suffix, mime="audio/webm" if suffix == ".webm" else "audio/wav"))
                        continue
                    if suffix not in (".txt", ".md", ".csv", ".json", ".png", ".jpg", ".jpeg", ".webp", ".pdf"):
                        raise Refusal("Use a text, picture or PDF file.")
                    path = self.server.app.root / "files" / (uuid.uuid4().hex + suffix)
                    path.write_bytes(data)
                    attachments.append(dict(type="file", name=filename, path=str(path.relative_to(self.server.app.root)),
                                            url="/api/file?path=" + urllib.parse.quote(str(path.relative_to(self.server.app.root))),
                                            mimeType=mimetypes.guess_type(filename)[0] or "application/octet-stream"))
                elif name in ("agentId", "text"):
                    fields[name] = data.decode("utf-8")
            return fields, attachments
        if not content_type.startswith("application/json"):
            raise Refusal("Send a JSON object.", 415)
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise Refusal("Send a valid JSON object.") from None
        if not isinstance(body, dict):
            raise Refusal("Send an object, not a list.")
        return body, []

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_PATCH(self):
        self.handle_request()

    def handle_request(self):
        try:
            self.route()
        except Refusal as error:
            self.respond(dict(error=str(error)), error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            self.respond(dict(error="The request or stored file has an invalid value."), 400)
        except Exception:
            self.respond(dict(error="The request could not be completed."), 500)

    def route(self):
        app = self.server.app
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        verb = self.command
        if verb == "GET" and path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            revision = -1
            while not app.stopping.is_set():
                with app.changed:
                    if revision == app.revision:
                        app.changed.wait(timeout=15)
                    changed = revision != app.revision
                    revision = app.revision
                self.wfile.write(b'data: {"channel":"changed"}\n\n' if changed else b": heartbeat\n\n")
                self.wfile.flush()
            self.close_connection = True
            return
        if verb == "GET" and path == "/api/voice/settings":
            return self.respond(app.voice.settings())
        if verb == "GET" and path.startswith("/api/voice/say/"):
            return self.respond(app.voice.audio(path.removeprefix("/api/voice/say/")), content_type="audio/wav", headers={"Cache-Control": "private, no-store"})
        if verb == "POST" and path == "/api/voice/turn":
            _, recordings = self.body(voice=True)
            if len(recordings) != 1:
                raise Refusal("Send one WebM or WAV recording.")
            return self.respond(app.voice.turn(recordings[0]))
        if verb == "GET" and path == "/api/health":
            return self.respond(dict(app="titanium-bot-lite", version=__version__))
        if verb == "GET" and path == "/api/state":
            return self.respond(app.state())
        if verb == "GET" and path == "/api/settings":
            return self.respond(app.get_settings())
        if verb == "GET" and path == "/api/library":
            return self.respond(app.library())
        if verb == "GET" and path == "/api/transcript":
            conversation = params.get("agentId", [""])[0]
            transcript = app.messages
            if conversation != "titan":
                if not re.fullmatch(r"routine-[a-zA-Z0-9_-]{1,80}", conversation):
                    raise Refusal("That conversation was not found.", 404)
                target = app.root / "transcripts" / (conversation + ".json")
                if not target.is_file() or target.is_symlink():
                    raise Refusal("That conversation was not found.", 404)
                transcript = json.loads(target.read_text())
            limit = max(1, min(200, int(params.get("limit", ["100"])[0])))
            with app.lock:
                end = len(transcript)
                before = params.get("before", [""])[0]
                if before:
                    end = next((i for i, m in enumerate(transcript) if m["id"] == before), -1)
                    if end < 0:
                        raise Refusal("That message was not found.", 404)
                start = max(0, end - limit)
                return self.respond(dict(messages=transcript[start:end], hasOlder=start > 0))
        if verb == "GET" and path == "/api/models":
            payload = app.device.request("/models")
            try:
                app.device.resolve_model(payload.get("data", []))
            except Refusal:
                pass  # Keep the model list available when no chat model is loaded.
            app.poke()
            models = [dict(id=m["id"], name=m.get("name", m["id"]), running=m["id"] == app.device.resolved_model)
                      for m in payload.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
            return self.respond(dict(live=app.live(), device=models, lan=[], note="Start and stop models in the device's settings."))
        if verb in ("POST", "PATCH"):
            body, attachments = self.body()
            if verb == "POST" and path == "/api/send":
                return self.respond(app.send(body, attachments))
            if verb == "PATCH" and path == "/api/settings":
                return self.respond(app.patch_settings(body))
            if verb == "POST" and path == "/api/library":
                return self.respond(app.library_action(body))
            if verb == "POST" and path == "/api/decide":
                if body.get("decision") not in ("approve", "deny", "always"):
                    raise Refusal("Choose approve, deny, or always.")
                raise Refusal("There is no pending approval with that identifier.", 404)
            if verb == "POST" and path == "/api/model":
                if body.get("action") in ("start", "stop"):
                    raise Refusal("Start and stop models in the device's settings for now.", 501)
                if body.get("action") != "use":
                    raise Refusal("Choose a supported model action.")
                if any(k in body for k in ("baseUrl", "apiKey")):
                    raise Refusal("Other connections are not available here yet. Change the local configuration before starting Lite.", 501)
                ident = body.get("id")
                if not isinstance(ident, str) or not ident or len(ident) > 200:
                    raise Refusal("Choose a model first.")
                app.save_config({"model": ident})
                return self.respond(dict(live=app.live()))
        if verb == "GET" and path == "/api/file":
            requested = params.get("path", [""])[0]
            target = (app.root / requested).resolve()
            relative = target.relative_to(app.root) if target.is_relative_to(app.root) else None
            if relative is None or not relative.parts or (relative.parts[0] not in ("files", "memory", "skills", "handbook") and str(relative) != "persona.md"):
                raise Refusal("That file is private or outside this folder.", 403)
            if not target.is_file():
                raise Refusal("That file was not found.", 404)
            data = target.read_bytes()
            tag = '"' + hashlib.sha256(data).hexdigest() + '"'
            headers = {"ETag": tag, "Cache-Control": "private, no-cache", "Content-Security-Policy": "default-src 'none'; sandbox"}
            if self.headers.get("If-None-Match") == tag:
                return self.respond(b"", 304, headers=headers)
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if mime in ("text/html", "image/svg+xml", "application/javascript"):
                mime = "text/plain; charset=utf-8"
            return self.respond(data, content_type=mime, headers=headers)
        if verb == "GET" and not path.startswith(("/api/", "/voice/")):
            target = (CONSOLE / (urllib.parse.unquote(path).lstrip("/") or "index.html")).resolve()
            if target.is_relative_to(CONSOLE.resolve()) and target.is_file():
                return self.respond(target.read_bytes(), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            if path == "/" and not CONSOLE.exists():
                return self.respond(b'<!doctype html><title>Titanium Bot Lite</title><h1>Titanium Bot Lite</h1><p>The server is ready. The console is the next checkpoint.</p>', content_type="text/html")
        raise Refusal("That page was not found.", 404)


def lite_is_running(port):
    # Bypass ambient proxies and inspect only bounded loopback responses.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for host in ("127.0.0.1", "[::1]"):
        try:
            with opener.open(f"http://{host}:{port}/api/health", timeout=0.5) as response:
                payload = json.loads(response.read(4096))
                if response.status == 200 and isinstance(payload, dict) and payload.get("app") == "titanium-bot-lite" and payload.get("version") == __version__:
                    return True
        except (OSError, ValueError, HTTPException):
            pass
    return False


def close_for_exit(app):
    """Give cleanup one shared second; device I/O must not delay process exit.

    All app and HTTP workers are daemon threads. Normal close still runs in full
    when used by tests/embedded callers; only the exiting CLI bounds its wait.
    An unfinished turn is recovered from the saved transcript on the next start.
    """
    app.stopping.set()
    cleanup = threading.Thread(target=app.close, name="Titan shutdown", daemon=True)
    cleanup.start()
    cleanup.join(timeout=1.0)


@contextmanager
def running_pid(root):
    # Keep the lock inode stable; deleting/recreating it could admit two owners.
    fd = os.open(root / ".lite.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refusal("Titanium Tiiny Bot is already running with this data directory.") from None
        pid = root / "lite.pid"
        atomic_write(pid, str(os.getpid()) + "\n", 0o600)
        try:
            yield
        finally:
            pid.unlink(missing_ok=True)


def stop_running(root):
    pid_file = root / "lite.pid"
    try:
        fd = os.open(root / ".lite.lock", os.O_RDWR | os.O_NOFOLLOW)
    except FileNotFoundError:
        print("Titanium Tiiny Bot is not running.")
        return
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                pid = int(pid_file.read_text())
                if pid <= 1:
                    raise ValueError()
            except (OSError, ValueError):
                raise Refusal("Cannot read the running process ID; try --stop again.") from None
            try:
                os.kill(pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(0.02)
            else:
                raise Refusal("The process has not stopped yet; try farm stop or inspect lite.pid.")
            pid_file.unlink(missing_ok=True)
            print("Stopped Titanium Tiiny Bot.")
        else:
            pid_file.unlink(missing_ok=True)
            print("Titanium Tiiny Bot is not running.")


def main():
    parser = argparse.ArgumentParser(description="Titanium Bot Lite")
    parser.add_argument("--bind", "--host", dest="bind")
    parser.add_argument("--port", type=int)
    for field in ("base", "model", "key", "name"):
        parser.add_argument("--" + field)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--stop", action="store_true", help="Stop the process using this data directory")
    parser.add_argument("--data-dir")
    parser.add_argument("--selfcheck", action="store_true", help="Measure startup, memory, door bytes and one reply")
    parser.add_argument("--boot-probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    overrides = {k: getattr(args, k) for k in (*DEFAULTS, "key")}
    root = Path(args.data_dir or os.getenv("TIINY_DATA_DIR", "./data")).resolve()
    if args.stop:
        try:
            stop_running(root)
        except (Refusal, OSError) as error:
            print(str(error) if isinstance(error, Refusal) else "Cannot stop the saved process.", file=sys.stderr)
            raise SystemExit(1) from None
        return
    try:
        config = load_config(root, overrides)
    except (Refusal, ValueError, OSError):
        print("Cannot read configuration; check config.json and your command-line settings.", file=sys.stderr)
        raise SystemExit(1)
    if args.show_config:
        print(json.dumps(config | {"key": "********" if config["key"] else ""}, indent=2))
        return
    # Shell background jobs can inherit SIG_IGN; --stop must still work.
    previous_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        if args.boot_probe or args.selfcheck:
            run_cli(args, root, overrides, config)
            return
        with running_pid(root):
            run_cli(args, root, overrides, config)
    except Refusal as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, previous_sigint)


def run_cli(args, root, overrides, config):
    app = App(root, overrides)
    if args.boot_probe:
        print("ready", flush=True)
        close_for_exit(app)
        return
    if args.selfcheck:
        try:
            code = selfcheck(app)
        finally:
            close_for_exit(app)
        raise SystemExit(code)
    try:
        # A wildcard bind can succeed beside a loopback listener on macOS.
        for host in ("127.0.0.1", "::1"):
            try:
                with socket.create_connection((host, config["port"]), timeout=0.2):
                    pass
            except OSError:
                continue
            raise OSError(errno.EADDRINUSE, "Loopback port is busy")
        server = Server((config["bind"], config["port"]), app)
    except OSError as error:
        close_for_exit(app)
        if error.errno == errno.EADDRINUSE:
            if lite_is_running(config["port"]):
                print(f"Titanium Tiiny Bot is already running at http://localhost:{config['port']}")
                return
            print(f"Port {config['port']} is busy; choose another with --port or in {root / 'config.json'}.", file=sys.stderr)
        else:
            print("Cannot bind the server; check --bind and --port or config.json.", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Titanium Bot Lite is ready at http://localhost:{server.server_port}. Budget: {json.dumps(app.budget())}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        close_for_exit(app)
        server.server_close()
