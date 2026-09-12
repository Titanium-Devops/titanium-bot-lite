"""Headless packaging and real-process shutdown regressions; no network required."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

from lite.server import Refusal, running_pid, stop_running

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / 'scripts/release.py'))['build_release']

# Run the real CLI and App worker with only the HTTP listener replaced. This
# remains runnable in sandboxes that cannot bind even a loopback TCP socket.
BLOCKED_TURN = '''import os, sys, threading, time
from pathlib import Path
from unittest.mock import patch
from lite.server import main
class HeadlessServer:
    def __init__(self, address, app):
        self.server_port = address[1]
        self.app = app
    def serve_forever(self):
        def stuck(*args):
            with self.app.lock:
                Path(self.app.root, 'mid-turn').write_text('ready')
                threading.Event().wait(120)
        self.app.tool_loop = stuck
        self.app.send({'agentId': 'titan', 'text': 'hold this turn'})
        while True: time.sleep(0.05)
    def server_close(self): pass
sys.argv = ['lite', '--model', 'echo', '--data-dir', os.environ['TIINY_DATA_DIR']]
with patch('lite.server.Server', HeadlessServer), patch('socket.create_connection', side_effect=OSError):
    main()
'''


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lite-stop-')
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name)
        self.env = os.environ | {'TIINY_DATA_DIR': str(self.data), 'TIINY_MODEL': 'echo',
                                 'ONELANE_DIR': str(self.data / '.onelane')}

    def launch(self, ignore_sigint=False):
        log = (self.data / 'process.log').open('w')
        self.addCleanup(log.close)
        process = subprocess.Popen([sys.executable, '-c', BLOCKED_TURN], cwd=ROOT, env=self.env,
                                   stdout=log, stderr=log,
                                   preexec_fn=(lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)) if ignore_sigint else None)
        def reap():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        self.addCleanup(reap)
        deadline = time.monotonic() + 5
        while not (self.data / 'mid-turn').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                self.fail('Headless CLI did not reach a real blocked turn: ' + (self.data / 'process.log').read_text())
            time.sleep(0.02)
        self.assertEqual(int((self.data / 'lite.pid').read_text()), process.pid)
        return process

    def test_sigint_exits_within_two_seconds_mid_turn(self):
        process = self.launch()
        started = time.monotonic()
        process.send_signal(signal.SIGINT)
        self.assertEqual(process.wait(timeout=2), 0)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse((self.data / 'lite.pid').exists())

    def test_stop_command_exits_within_two_seconds_mid_turn(self):
        process = self.launch()
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-m', 'lite', '--stop'], cwd=ROOT,
                                env=self.env, text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Stopped', result.stdout)
        self.assertEqual(process.wait(timeout=0.3), 0)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse((self.data / 'lite.pid').exists())

    def test_stop_works_when_shell_ignored_sigint(self):
        process = self.launch(ignore_sigint=True)
        result = subprocess.run([sys.executable, '-m', 'lite', '--stop'], cwd=ROOT,
                                env=self.env, text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(process.wait(timeout=0.3), 0)

    def test_duplicate_data_directory_is_refused(self):
        process = self.launch()
        result = subprocess.run([sys.executable, '-m', 'lite'], cwd=ROOT, env=self.env,
                                text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 1)
        self.assertIn('already running', result.stderr)
        self.assertEqual(int((self.data / 'lite.pid').read_text()), process.pid)

    def test_stale_pid_does_not_signal_this_test_process(self):
        (self.data / '.lite.lock').touch()
        (self.data / 'lite.pid').write_text(str(os.getpid()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            stop_running(self.data)
        self.assertIn('not running', output.getvalue())
        self.assertFalse((self.data / 'lite.pid').exists())

    def test_stop_needs_no_configuration_or_data_directory(self):
        missing = self.data / 'missing'
        result = subprocess.run([sys.executable, '-m', 'lite', '--stop', '--data-dir', str(missing)],
                                cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(missing.exists())

    def test_pid_file_is_private_and_removed_after_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'failure'):
            with running_pid(self.data):
                self.assertEqual((self.data / 'lite.pid').stat().st_mode & 0o777, 0o600)
                with self.assertRaises(Refusal):
                    with running_pid(self.data):
                        self.fail('Duplicate owner admitted')
                raise RuntimeError('failure')
        self.assertFalse((self.data / 'lite.pid').exists())
        self.assertTrue((self.data / '.lite.lock').exists())


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lite-release-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ('lite', 'brand', 'data', 'vendor', 'tests', 'lite/__pycache__', 'lite/data'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name, data in {'lite/VERSION': '0.1.9\n', 'lite/__main__.py': 'print("ready")\n',
                           'brand/mark.svg': '<svg/>', 'README.md': 'Install with farm.',
                           'vendor/private': 'no', 'data/keys.json': 'secret',
                           'lite/__pycache__/cached.pyc': 'no', 'lite/data/secret': 'no',
                           'tests/test.py': 'no'}.items():
            (self.root / name).write_text(data)

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return BUILD(self.root)

    def test_archive_contains_only_release_sources(self):
        archive, digest = self.build()
        self.assertEqual(archive.name, 'titanium-tiiny-bot-0.1.9.tar.gz')
        self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
        with tarfile.open(archive) as tar:
            names = tar.getnames()
            prefix = 'titanium-tiiny-bot-0.1.9/'
            self.assertIn(prefix + 'lite/VERSION', names)
            self.assertIn(prefix + 'README.md', names)
            self.assertIn(prefix + 'brand/mark.svg', names)
            for name in names:
                self.assertFalse(set(Path(name).parts) & {'data', 'vendor', 'tests', '__pycache__'})
            self.assertEqual(tar.extractfile(prefix + 'lite/VERSION').read(), b'0.1.9\n')

    def test_archive_is_reproducible_despite_timestamps(self):
        archive, first = self.build()
        os.utime(self.root / 'lite/VERSION', (12345, 12345))
        _, second = self.build()
        self.assertEqual(first, second)

    def test_symlinks_cannot_leak_user_data(self):
        (self.root / 'lite/leak').symlink_to(self.root / 'data/keys.json')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.build()

    def test_invalid_version_is_refused(self):
        (self.root / 'lite/VERSION').write_text('../outside')
        with self.assertRaisesRegex(ValueError, 'three-part'):
            self.build()
