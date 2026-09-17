"""Start the app the way the farm starts it, and see it answer.

0.1.17 passed every check this repo had and still failed in the field on Windows. The
selfcheck runs in process with `--selfcheck`, which forces the echo model and therefore
never looks for a device. `farm start` does none of that: it hands the app a data
directory in the environment, a port on the command line, a working directory of the
version folder, and no device at all. On that path the app refused to start, and said
"Cannot read configuration" while config.json was perfectly readable.

So this is the farm's own path, run on whatever OS the job is on. It is the check that
was missing, and the reason it is a test rather than a workflow step is that a Mac
should fail it too if it ever breaks again.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The variables the farm sets, and the ones it must be able to leave unset. Anything
# TIINY_* inherited from the machine running the tests would hand the child a device and
# quietly stop this from testing what it says it tests.
FARM_CLEARS = ("TIINY_BASE", "TIINY_KEY", "TIINY_MODEL", "TIINY_DATA_DIR", "TIINY_HOST",
               "FARM_DATA_DIR", "ONELANE_DIR", "TIINYAPP_PORT")


def a_free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FarmStartTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="lite-farmstart-")
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "home"
        # The farm makes the data directory itself, before the app ever runs.
        self.data = Path(folder.name) / "app" / "data"
        self.data.mkdir(parents=True)
        self.home.mkdir()
        self.log = Path(folder.name) / "farm.log"

    def environment(self, port):
        """What farm.environment() hands an app, for somebody with no device saved."""
        env = os.environ.copy()
        for name in FARM_CLEARS:
            env.pop(name, None)
        # A home of its own, so no device.json from this machine is found. Windows reads
        # USERPROFILE where POSIX reads HOME, and Python's expanduser follows suit.
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   FARM_DATA_DIR=str(self.data), TIINY_DATA_DIR=str(self.data),
                   ONELANE_DIR=str(self.home / ".onelane"), PYTHONUNBUFFERED="1",
                   TIINYAPP_PORT=str(port))
        return env

    def health(self, port, deadline):
        """The app's health, once it answers, or None if it never does."""
        url = "http://127.0.0.1:%d/api/health" % port
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as answer:
                    return json.load(answer)
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(0.2)
        return None

    def test_the_app_starts_and_serves_the_way_the_farm_starts_it(self):
        port = a_free_port()
        with self.log.open("ab") as log:
            process = subprocess.Popen(
                # The manifest says this app takes its port on argv, so the farm rewrites
                # the value in place and runs the entry as it is written there.
                [sys.executable, "-m", "lite", "--port", str(port)],
                cwd=ROOT, env=self.environment(port), stdin=subprocess.DEVNULL,
                stdout=log, stderr=log)
        self.addCleanup(self.stop, process)
        deadline = time.monotonic() + 120
        health = self.health(port, deadline)
        written = self.log.read_text(encoding="utf-8", errors="replace")
        self.assertIsNone(process.poll(), "the app exited at startup:\n" + written)
        self.assertIsNotNone(health, "the app never answered /api/health:\n" + written)
        self.assertEqual(health.get("app"), "titanium-bot-lite", health)
        # Whatever it found or did not find, it has to say which in the log the farm
        # keeps, because that log is the only thing a person or an agent gets to read.
        self.assertTrue(written.strip(), "the app wrote nothing to the farm's log")

    def test_with_no_tiiny_it_still_serves_and_the_log_says_why(self):
        """The field failure exactly: no device saved, and none on the network either.

        The search is the one thing a test cannot arrange, because a real Tiiny on the
        machine running this would be found and the app would start for the ordinary
        reason. So the child is told to look and find nothing, which is what a stranger's
        machine looks like, and the farm's environment is otherwise untouched.
        """
        port = a_free_port()
        env = self.environment(port)
        # A sitecustomize on the path is the only way into a child that the farm starts
        # by name; nothing is patched in this process and the app is unmodified.
        blind = Path(self.home) / "blind"
        blind.mkdir()
        (blind / "sitecustomize.py").write_text(
            "import lite.device\n"
            "lite.device.find_base = lambda: ''\n", encoding="utf-8")
        env["PYTHONPATH"] = str(blind) + os.pathsep + str(ROOT)
        with self.log.open("ab") as log:
            process = subprocess.Popen([sys.executable, "-m", "lite", "--port", str(port)],
                                       cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log)
        self.addCleanup(self.stop, process)
        health = self.health(port, time.monotonic() + 120)
        written = self.log.read_text(encoding="utf-8", errors="replace")
        self.assertIsNone(process.poll(), "the app exited at startup:\n" + written)
        self.assertIsNotNone(health, "the app never answered /api/health:\n" + written)
        self.assertIn("No Tiiny found", written)
        self.assertIn("Settings > Model", written)
        self.assertNotIn("Cannot read configuration", written)

    def stop(self, process):
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)


if __name__ == "__main__":
    unittest.main()
