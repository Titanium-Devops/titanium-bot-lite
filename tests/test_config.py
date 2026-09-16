"""CLI and persistence contracts without a browser or GUI."""
import contextlib
import errno
import io
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lite import __version__
from lite.server import App, DEFAULTS, Device, Refusal, load_config, main
from tests.test_server import wire


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        # clear=True so no ambient TIINY_* can reach the code under test. The few
        # variables the operating system itself needs to start a process have to survive
        # it: a Windows child with no SystemRoot cannot initialise Winsock, so every
        # socket call in it fails with WSAEPROVIDERFAILEDINIT before this app runs a line,
        # and a test about refusing a busy port measured that instead.
        keep = {name: os.environ[name] for name in
                ('SystemRoot', 'windir', 'SystemDrive', 'PATH', 'PATHEXT', 'COMSPEC', 'TEMP', 'TMP')
                if name in os.environ}
        env = patch.dict(os.environ, keep | {'ONELANE_DIR': str(self.root / '.onelane')}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        # An empty base in config.json means "find the device". Stub the search
        # rather than setting TIINY_BASE: the environment outranks config.json,
        # which is exactly what test_precedence_all_layers is here to measure.
        found = patch('lite.device.find_base', return_value='http://192.0.2.10/v1')
        found.start()
        self.addCleanup(found.stop)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['lite', '--data-dir', str(self.root), *args]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                main()
                code = 0
            except SystemExit as exit:
                code = exit.code
        return code, out.getvalue(), err.getvalue()

    def test_defaults_complete_config_and_private_key(self):
        # The shipped base is empty and means "find the device", so config.json
        # keeps it empty and the effective config carries whatever was found.
        # Writing today's address into the file is how this breaks next week.
        self.assertEqual(DEFAULTS['base'], '')
        self.assertEqual(load_config(self.root),
                         DEFAULTS | {'base': 'http://192.0.2.10/v1', 'key': ''})
        self.assertEqual(json.loads((self.root / 'config.json').read_text(encoding='utf-8')), DEFAULTS)
        # POSIX mode bits only. A Windows file has none: it inherits the ACL of the
        # directory it was made in, which under a user's profile already keeps other
        # users out, and os.chmod there can only toggle the read-only flag.
        if os.name == 'posix':
            self.assertEqual((self.root / 'keys.json').stat().st_mode & 0o777, 0o600)

    def test_precedence_all_layers(self):
        load_config(self.root)
        saved = dict(base='http://config/v1', model='config-model', port=8001, bind='127.0.0.1', name='Ada', mcp=True)
        (self.root / 'config.json').write_text(json.dumps(saved), encoding='utf-8')
        (self.root / 'keys.json').write_text(json.dumps({'apiKey': 'stored-secret'}), encoding='utf-8')
        self.assertEqual(load_config(self.root), saved | {'endpoints': [], 'key': 'stored-secret'})
        env = dict(TIINY_BASE='http://env/v1', TIINY_MODEL='env-model', TIINY_PORT='8002', TIINY_KEY='env-secret')
        with patch.dict(os.environ, env):
            effective = load_config(self.root)
            self.assertEqual(effective, saved | dict(base='http://env/v1', model='env-model', port=8002, endpoints=[], key='env-secret'))
            code, out, err = self.cli('--base', 'http://cli/v1', '--model', 'cli-model', '--port', '8003', '--bind', 'localhost', '--name', 'CLI', '--key', 'cli-secret', '--no-mcp', '--show-config')
            self.assertEqual((code, err), (0, ''))
            self.assertEqual(json.loads(out), dict(base='http://cli/v1', model='cli-model', port=8003, bind='localhost', name='CLI', endpoints=[], mcp=False, key='********'))
            self.assertNotIn('secret', out)
        self.assertEqual(json.loads((self.root / 'config.json').read_text(encoding='utf-8')), saved)

    def test_show_config_masks_stored_and_environment_key_without_starting_app(self):
        load_config(self.root)
        (self.root / 'keys.json').write_text('{"apiKey":"stored-secret"}', encoding='utf-8')
        for env in ({}, {'TIINY_KEY': 'environment-secret'}):
            with patch.dict(os.environ, env), patch('lite.server.App') as app:
                code, out, err = self.cli('--show-config')
                app.assert_not_called()
            self.assertEqual((code, err), (0, ''))
            self.assertEqual(json.loads(out)['key'], '********')
            self.assertNotIn('secret', out)
            self.assertNotIn('secret', (self.root / 'config.json').read_text(encoding='utf-8'))

    def test_busy_port_one_sentence_and_exit_one(self):
        with patch('lite.server.lite_is_running', return_value=False), patch('lite.server.Server', side_effect=OSError(errno.EADDRINUSE, 'Address in use')):
            code, out, err = self.cli('--port', '8123', '--model', 'echo')
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertEqual(err, f'Port 8123 is busy; choose another with --port or in {self.root / "config.json"}.\n')
        self.assertNotIn('Traceback', err)

    def test_already_running_sentence_and_exit_zero(self):
        with patch('lite.server.lite_is_running', return_value=True), patch('socket.create_connection', side_effect=ConnectionRefusedError), patch('lite.server.Server', side_effect=OSError(errno.EADDRINUSE, 'busy')):
            code, out, err = self.cli('--port', '8123', '--model', 'echo')
        self.assertEqual((code, out, err), (0, 'Titanium Tiiny Bot is already running at http://localhost:8123\n', ''))

    def test_one_product_name_in_everything_a_person_reads(self):
        # The startup line said "Titanium Bot Lite is ready" while --stop and the already-running
        # line said "Titanium Tiiny Bot", and the model's own base prompt said a third thing. The
        # package and the health identity stay titanium-bot-lite; those are identifiers, not copy.
        source = (Path(__file__).resolve().parents[1] / 'lite' / 'server.py').read_text(encoding='utf-8')
        self.assertNotIn('Titanium Bot Lite', source)
        self.assertIn('Titanium Tiiny Bot is ready at', source)
        self.assertIn('the local assistant in Titanium Tiiny Bot', source)
        self.assertEqual(source.count('titanium-bot-lite'), 3)

    def test_loopback_listener_refuses_before_binding(self):
        for host in ('127.0.0.1', '::1'):
            with self.subTest(host=host):
                def connect(address, timeout):
                    self.assertEqual(timeout, 0.2)
                    if address[0] != host:
                        raise ConnectionRefusedError()
                    return contextlib.nullcontext()

                with patch('lite.server.lite_is_running', return_value=False), patch('socket.create_connection', side_effect=connect), patch('lite.server.Server') as server:
                    code, out, err = self.cli('--port', '8123', '--model', 'echo')
                server.assert_not_called()
                self.assertEqual((code, out, err), (1, '', f'Port 8123 is busy; choose another with --port or in {self.root / "config.json"}.\n'))

    def test_real_loopback_listener_refuses_cli(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(('127.0.0.1', 0))
            except PermissionError:
                self.skipTest('Sandbox denies binding a loopback socket')
            listener.listen()
            port = listener.getsockname()[1]
            result = subprocess.run(
                [sys.executable, '-m', 'lite', '--port', str(port), '--bind', '0.0.0.0',
                 '--model', 'echo', '--data-dir', str(self.root)],
                capture_output=True, text=True, timeout=5,
                # A child process cannot see the patched search, and this test is
                # about refusing a busy port, not about finding a device.
                env=os.environ | {'TIINY_BASE': 'http://192.0.2.10/v1'},
                cwd=Path(__file__).resolve().parents[1])
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (1, '', f'Port {port} is busy; choose another with --port or in {self.root / "config.json"}.\n'))

    def test_unoccupied_loopbacks_allow_startup_without_address_reuse(self):
        from lite.server import Server
        self.assertFalse(Server.allow_reuse_address)
        with patch('socket.create_connection', side_effect=ConnectionRefusedError()) as connect, patch('lite.server.Server') as server:
            code, out, err = self.cli('--port', '8123', '--model', 'echo')
        self.assertEqual((code, err), (0, ''))
        self.assertIn('is ready', out)
        self.assertEqual([call.args[0] for call in connect.call_args_list],
                         [('127.0.0.1', 8123), ('::1', 8123)])
        server.assert_called_once()

    def test_malformed_configuration_exits_without_traceback(self):
        load_config(self.root)
        for filename, contents in (("keys.json", "[]"), ("config.json", "not json")):
            (self.root / filename).write_text(contents, encoding='utf-8')
            code, out, err = self.cli("--show-config")
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertNotIn("Traceback", err)
            self.assertIn("configuration", err)
            (self.root / filename).write_text("{}", encoding='utf-8')

    def test_version_needs_no_data_or_server(self):
        code, out, err = self.cli('--version')
        self.assertEqual((code, out, err), (0, __version__ + '\n', ''))
        self.assertFalse((self.root / 'config.json').exists())
        self.assertEqual(__version__,
                         (Path(__file__).resolve().parents[1] / 'lite/VERSION')
                         .read_text(encoding='utf-8').strip())

    def test_settings_model_and_name_survive_restart(self):
        app = App(self.root)
        self.addCleanup(app.close)
        status, _, result = wire(app, 'PATCH', '/api/settings', {'base': 'http://new/v1', 'model': 'chosen', 'botName': 'Ada'})
        self.assertEqual(status, 200)
        self.assertEqual((result['base'], result['model'], result['botName'], result['version']), ('http://new/v1', 'chosen', 'Ada', __version__))
        app.close()
        restarted = App(self.root)
        self.addCleanup(restarted.close)
        self.assertEqual((restarted.device.base, restarted.device.model, restarted.settings['botName']), ('http://new/v1', 'chosen', 'Ada'))
        self.assertEqual(json.loads((self.root / 'keys.json').read_text(encoding='utf-8')), {})
        old = (self.root / 'config.json').read_text(encoding='utf-8')
        self.assertEqual(wire(restarted, 'PATCH', '/api/settings', {'base': 'http://user:secret@host/v1'})[0], 400)
        self.assertEqual((self.root / 'config.json').read_text(encoding='utf-8'), old)

    def test_default_resolves_first_chat_model_and_explicit_skips_discovery(self):
        device = Device(self.root, 'http://192.0.2.10/v1', '', 'default')
        with patch.object(device, 'request', side_effect=[{'data': [{'id': 'embed-a', 'supports_chat': False}, {'id': 'chat-a', 'supports_chat': True}, {'id': 'chat-b', 'capabilities': ['main']}]}, {}]) as request:
            device.chat([], lambda token: None)
            self.assertEqual(request.call_args_list[0].args, ('/models',))
            self.assertEqual(request.call_args_list[1].args[1]['model'], 'chat-a')
        self.assertEqual(device.model, 'default')
        with patch.object(device, 'request', return_value={'data': []}):
            with self.assertRaises(Refusal):
                device.chat([], lambda token: None)
        device.model = 'explicit'
        with patch.object(device, 'request', return_value={}) as request:
            device.chat([], lambda token: None)
            request.assert_called_once()
            self.assertEqual(request.call_args.args[1]['model'], 'explicit')

    def test_ornith_chat_discovery_and_resolved_model_surfaces(self):
        row = {"id": "deepreinforce-ai/Ornith-1.0-35B", "type": "Image-Text-to-Text",
               "supports_chat": True, "capabilities": ["main"],
               "supported": ["Reasoning", "Tool Use"]}
        app = App(self.root)
        self.addCleanup(app.close)
        with patch.object(app.device, 'request', side_effect=[{'data': [row]}, {}]) as request:
            app.device.chat([{'role': 'user', 'content': 'Hello.'}], lambda token: None)
            self.assertEqual(request.call_args_list[1].args[1]['model'], row['id'])
        self.assertEqual(app.state()['workers'][0]['model'], row['id'])
        self.assertEqual(app.get_settings()['resolvedModel'], row['id'])
        self.assertEqual(app.get_settings()['model'], 'default')
        app.device.resolved_model = None
        with patch.object(app.device, 'request', return_value={'data': [row]}):
            status, _, result = wire(app, 'GET', '/api/models')
        self.assertEqual(status, 200)
        self.assertEqual(result['live']['model'], row['id'])
        self.assertTrue(result['device'][0]['running'])
        self.assertEqual(app.state()['workers'][0]['model'], row['id'])
        with patch.object(app.device, 'request', return_value={'data': []}):
            status, _, result = wire(app, 'GET', '/api/models')
        self.assertEqual(status, 200)
        self.assertIsNone(result['live']['resolvedModel'])
        self.assertIsNone(app.get_settings()['resolvedModel'])
        app.device.resolved_model = row['id']
        app.patch_settings({'base': 'http://new/v1'})
        self.assertIsNone(app.get_settings()['resolvedModel'])

    def test_chat_discovery_fallbacks_and_explicit_false(self):
        device = Device(self.root, 'http://192.0.2.10/v1', '', 'default')
        for row, accepted in [
            ({'id': 'yes', 'supports_chat': True, 'type': 'embedding'}, True),
            ({'id': 'no', 'supports_chat': False, 'capabilities': ['main'], 'type': 'Text-to-Text'}, False),
            ({'id': 'main', 'capabilities': ['main']}, True),
            ({'id': 'text', 'type': 'Text-to-Text'}, True),
            ({'id': 'image-text', 'type': 'Image-Text-to-Text'}, True),
            ({'id': 'unknown'}, False),
            ({'id': 'embedding', 'type': 'embedding'}, False),
        ]:
            with self.subTest(row=row), patch.object(device, 'request', side_effect=[{'data': [row]}, {}]) as request:
                if accepted:
                    device.chat([], lambda token: None)
                    self.assertEqual(request.call_args_list[1].args[1]['model'], row['id'])
                else:
                    with self.assertRaises(Refusal):
                        device.chat([], lambda token: None)
                    self.assertIsNone(device.resolved_model)

class DefaultDataDirTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix',
                         'chmod 0o500 does not take write access away from a Windows directory')
    def test_falls_back_under_home_when_the_app_folder_cannot_be_written(self):
        import os, tempfile
        from unittest import mock
        from lite import server
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as app:
            os.chmod(app, 0o500)
            cwd = os.getcwd()
            try:
                os.chdir(app)
                with mock.patch.dict(os.environ, {"HOME": home}):
                    chosen = server.default_data_dir()
            finally:
                os.chdir(cwd)
                os.chmod(app, 0o700)
        self.assertEqual(chosen, os.path.join(home, ".titanium-tiiny-bot"))

    def test_uses_data_beside_the_app_when_it_can(self):
        import os, tempfile
        from lite import server
        with tempfile.TemporaryDirectory() as app:
            cwd = os.getcwd()
            try:
                os.chdir(app)
                self.assertEqual(server.default_data_dir(), "data")
            finally:
                os.chdir(cwd)

class EchoNeedsNoDeviceTests(unittest.TestCase):
    def test_echo_model_with_no_base_never_searches_for_a_device(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from lite import server, device
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(device, "find_base", side_effect=AssertionError("searched")):
                with mock.patch.dict(os.environ, {"TIINY_BASE": "", "TIINY_MODEL": ""}, clear=False):
                    for name in ("TIINY_BASE", "TIINY_MODEL"):
                        os.environ.pop(name, None)
                    config = server.load_config(Path(root), {"model": "echo"})
        self.assertEqual(config["model"], "echo")
        self.assertTrue(config["base"].startswith("http://127.0.0.1:1"))

