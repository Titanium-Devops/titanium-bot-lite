"""Offline wire contracts plus optional real loopback HTTP integration."""
import contextlib
import errno
import io
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace

TEST_ROOT = Path(__file__).resolve().parents[1] / 'data/tests'
TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ['ONELANE_DIR'] = str(TEST_ROOT / '.onelane')
from lite.server import (App, Device, Handler, Refusal, Server, build_prompt, endpoint_kind,
                         first_paint_bytes, selfcheck, read_memories, read_persona)


class WireSocket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, mode, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)


def wire(app, method, path, body=None, headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b''
    values = {'Host': 'localhost', 'Connection': 'close'}
    if body is not None:
        values.update({'Content-Type': 'application/json', 'Content-Length': str(len(raw))})
    values.update(headers or {})
    request = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in values.items()) + '\r\n'
    sock = WireSocket(request.encode() + raw)
    Handler(sock, ('127.0.0.1', 1), SimpleNamespace(app=app))
    head, payload = sock.output.getvalue().split(b'\r\n\r\n', 1)
    lines = head.decode().split('\r\n')
    status = int(lines[0].split()[1])
    result_headers = dict(line.split(': ', 1) for line in lines[1:])
    if payload and result_headers.get('Content-Type', '').startswith('application/json'):
        payload = json.loads(payload)
    return status, result_headers, payload


class AppCase(unittest.TestCase):
    ENVIRONMENT = dict(TIINY_BASE='http://localhost/v1', TIINY_KEY='test-private-key', TIINY_MODEL='echo')
    # Every credential this case knows about. No answer may ever contain one.
    KEYS = ('test-private-key',)

    def prepare(self, root):
        """Anything the data directory needs before the app first reads it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, self.ENVIRONMENT)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.prepare(Path(self.temp.name))
        self.app = App(self.temp.name)
        # Most route tests begin after the separately tested first-run greeting.
        self.app.messages.clear()
        self.app.save_messages()
        self.addCleanup(self.app.close)

    def request(self, method, path, body=None, status=200, headers=None):
        actual, response_headers, result = wire(self.app, method, path, body, headers)
        self.assertEqual(actual, status, result)
        for key in self.KEYS:
            self.assertNotIn(key, str(result))
        if status >= 400:
            self.assertIsInstance(result['error'], str)
            self.assertTrue(result['error'])
        return result

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.app.jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.app.jobs.unfinished_tasks, 0)


class RouteTests(AppCase):
    def test_state_settings_library_and_budget_shapes(self):
        state = self.request('GET', '/api/state')
        self.assertEqual(state['activeContext'], {'kind': 'worker', 'id': 'titan'})
        self.assertEqual(len(state['workers']), 1)
        self.assertEqual(state['rooms'], [])
        settings = self.request('GET', '/api/settings')
        self.assertIsInstance(settings['persona'], str)
        self.assertIsInstance(settings['version'], str)
        self.assertEqual(set(settings['usage']), {'tokens', 'minutes'})
        self.assertLess(settings['budget']['rssMb'], 200)
        self.assertGreater(settings['budget']['firstPaintKb'], 0)
        self.assertLess(settings['budget']['firstPaintKb'], 250)
        self.assertLess(settings['budget']['coldStartMs'], 5000)
        self.assertEqual(set(self.request('GET', '/api/library')), {'memories', 'skills', 'routines'})
        self.assertEqual((self.app.root / 'keys.json').stat().st_mode & 0o777, 0o600)

    def test_settings_write_restart_and_validation(self):
        result = self.request('PATCH', '/api/settings', {'botName': 'Ada', 'persona': 'Fresh persona é', 'theme': 'light'})
        self.assertEqual(result['botName'], 'Ada')
        self.assertEqual(read_persona(self.app.root), 'Fresh persona é')
        self.app.close()
        restarted = App(self.temp.name)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get_settings()['botName'], 'Ada')
        self.assertEqual(restarted.get_settings()['persona'], 'Fresh persona é')
        for body in ({'unknown': True}, {'theme': 'bad'}, {'botName': []}, {'voice': {'enabled': 'yes'}}):
            self.request('PATCH', '/api/settings', body, 400)
        self.request('PATCH', '/api/settings', {'talkEnabled': True})
        self.assertEqual(self.request('PATCH', '/api/settings', {'voice': {'enabled': True}})['voice']['mode'], 'push')

    def test_send_transcript_restart_and_pagination(self):
        sent = self.request('POST', '/api/send', {'agentId': 'titan', 'text': 'Hello é'})['message']
        for key in ('id', 'authorId', 'authorName', 'time', 'timestampMs', 'text', 'type'):
            self.assertIn(key, sent)
        self.wait_idle()
        transcript = self.request('GET', '/api/transcript?agentId=titan')
        self.assertEqual([m['text'] for m in transcript['messages']], ['Hello é', 'é olleH'])
        self.assertFalse(transcript['hasOlder'])
        tail = self.request('GET', '/api/transcript?agentId=titan&limit=1')
        self.assertTrue(tail['hasOlder'])
        older = self.request('GET', '/api/transcript?agentId=titan&before=' + tail['messages'][0]['id'])
        self.assertEqual(older['messages'], [sent])
        self.app.close()
        restarted = App(self.temp.name)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.messages, transcript['messages'])
        self.request('GET', '/api/transcript?agentId=missing', status=404)
        self.request('GET', '/api/transcript?agentId=titan&before=missing', status=404)
        self.request('POST', '/api/send', {'agentId': 'other', 'text': 'hello'}, 404)
        self.request('POST', '/api/send', {'agentId': 'titan', 'text': ' '}, 400)

    def test_models_and_refused_actions(self):
        with patch.object(self.app.device, 'request', return_value={'data': [{'id': 'echo'}]}):
            models = self.request('GET', '/api/models')
        self.assertEqual(models['device'], [{'id': 'echo', 'name': 'echo', 'running': True}])
        self.assertEqual(models['lan'], [])
        self.assertEqual(models['live']['source'], 'device')
        self.assertEqual(self.request('POST', '/api/model', {'action': 'use', 'id': 'another'})['live']['model'], 'echo')
        self.assertEqual(json.loads((self.app.root / 'config.json').read_text())['model'], 'another')
        self.request('POST', '/api/model', {'action': 'sideways', 'id': 'echo'}, 400)
        self.request('POST', '/api/model', {'action': 'use'}, 400)
        for action in ('start', 'stop'):
            self.request('POST', '/api/model', {'action': action, 'id': ' '}, 400)
        self.request('POST', '/api/model', {'action': 'use', 'model': 'echo',
                                            'baseUrl': 'ftp://elsewhere', 'apiKey': 'test-private-key'}, 400)
        self.request('POST', '/api/model', {'action': 'forget', 'baseUrl': 'http://nothing/v1'}, 404)
        for verb in ('enable', 'disable', 'pause', 'delete'):
            self.request('POST', '/api/library', {'kind': 'routine', 'verb': verb, 'id': 'daily'}, 404)
        for decision in ('approve', 'deny', 'always'):
            self.request('POST', '/api/decide', {'agentId': 'titan', 'entryId': 'missing', 'decision': decision}, 404)
        self.request('POST', '/api/decide', {'decision': 'invalid'}, 400)

    def test_library_memory_and_skill_actions(self):
        self.request('POST', '/api/library', {'kind': 'memory', 'verb': 'remember', 'text': '  Café\twith\n milk  '})
        result = self.request('POST', '/api/library', {'kind': 'memory', 'verb': 'remember', 'text': 'CAFÉ WITH MILK'})
        self.assertEqual(len(result['library']['memories']), 1)
        memory = result['library']['memories'][0]
        self.assertEqual(memory['name'], 'Café with milk')
        for text in ('', 'a' * 501, 42):
            self.request('POST', '/api/library', {'kind': 'memory', 'verb': 'remember', 'text': text}, 400)
        self.request('POST', '/api/library', {'kind': 'memory', 'verb': 'forget', 'id': memory['id']})
        self.assertEqual(read_memories(self.app.root), [])
        skill = self.app.root / 'skills/greeting/SKILL.md'
        skill.parent.mkdir()
        skill.write_text('---\nname: Greeting\ndescription: Say hello\n---\nHello from the skill', encoding='utf-8')
        self.request('POST', '/api/library', {'kind': 'skill', 'verb': 'disable', 'id': 'greeting'})
        self.request('POST', '/api/library', {'kind': 'skill', 'verb': 'run', 'id': 'greeting'}, 400)
        self.request('POST', '/api/library', {'kind': 'skill', 'verb': 'enable', 'id': 'greeting'})
        self.assertIn('Greeting: Say hello (skills/greeting/SKILL.md)', build_prompt(self.app.root))
        self.request('POST', '/api/library', {'kind': 'skill', 'verb': 'run', 'id': 'greeting'})
        self.wait_idle()
        self.assertIn('Hello from the skill', self.app.messages[0]['text'])

    def test_file_conditional_get_and_private_traversal(self):
        (self.app.root / 'files/note.txt').write_text('hello')
        status, headers, body = wire(self.app, 'GET', '/api/file?path=files/note.txt')
        self.assertEqual((status, body), (200, b'hello'))
        self.assertIn('sandbox', headers['Content-Security-Policy'])
        self.assertEqual(wire(self.app, 'GET', '/api/file?path=files/note.txt', headers={'If-None-Match': headers['ETag']})[0], 304)
        (self.app.root / 'files/leak.txt').symlink_to(self.app.root / 'keys.json')
        for name in ('keys.json', 'settings.json', '../outside', 'files/leak.txt'):
            self.request('GET', '/api/file?path=' + name, status=403)
        self.request('GET', '/api/file?path=files/absent', status=404)
        self.request('GET', '/api/unknown', status=404)
        self.request('POST', '/api/send', {'agentId': 'titan', 'text': 'hello'}, 403, {'Origin': 'http://foreign'})
        self.request('PATCH', '/api/settings', [], 400)

    def test_upload_and_invalid_request_bodies(self):
        raw = (b'--upload\r\nContent-Disposition: form-data; name="agentId"\r\n\r\ntitan\r\n'
               b'--upload\r\nContent-Disposition: form-data; name="text"\r\n\r\nRead this\r\n'
               b'--upload\r\nContent-Disposition: form-data; name="file"; filename="../note.txt"\r\n'
               b'Content-Type: text/plain\r\n\r\nA local note\r\n--upload--\r\n')
        result = self.request('POST', '/api/send', raw, headers={'Content-Type': 'multipart/form-data; boundary=upload'})
        attachment = result['message']['attachments'][0]
        self.assertEqual(attachment['name'], 'note.txt')
        self.assertEqual(attachment['type'], 'file')
        self.assertEqual(attachment['mimeType'], 'text/plain')
        self.assertEqual(self.request('GET', attachment['url']), b'A local note')
        self.wait_idle()
        self.request('PATCH', '/api/settings', b'{', 400)
        self.request('PATCH', '/api/settings', b'{}', 415, {'Content-Type': 'text/plain'})
        self.request('PATCH', '/api/settings', {}, 413, {'Content-Length': str(10 * 1024 * 1024 + 1)})

    def test_static_door_and_sse_poke(self):
        status, headers, body = wire(self.app, 'GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertIn(b'Titanium', body)
        # End the event loop after its first write, exercising the real wire frame.
        original = WireSocket.sendall
        def send_and_stop(sock, data):
            original(sock, data)
            if data.startswith(b'data:'):
                self.app.stopping.set()
        with patch.object(WireSocket, 'sendall', send_and_stop):
            status, headers, body = wire(self.app, 'GET', '/events')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/event-stream')
        self.assertEqual(body, b'data: {"channel":"changed"}\n\n')


class ReaderAndQueueTests(AppCase):
    def test_selfcheck_measures_http_readiness_and_budget(self):
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
        except OSError as error:
            if error.errno in (errno.EPERM, errno.EACCES):
                self.skipTest('Sandbox denies loopback binding')
            raise
        result = subprocess.run([sys.executable, '-m', 'lite', '--selfcheck',
                                 '--data-dir', str(self.app.root / 'selfcheck')],
                                cwd=TEST_ROOT.parents[1], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ok'])
        self.assertTrue(report['budgetPassed'])
        self.assertEqual(report['mode'], 'echo')
        self.assertEqual(report['firstPaintBytes'], first_paint_bytes())
        self.assertLess(report['firstPaintBytes'], 250000)
        self.assertLess(report['budget']['rssMb'], 200)
        self.assertGreater(report['budget']['coldStartMs'], 0)
        self.assertLess(report['budget']['coldStartMs'], 5000)
        self.assertIsNotNone(report['timings']['firstTokenMs'])

    def test_selfcheck_health_probe_cleanup_and_budget_failures(self):
        for failure in (None, OSError('timed out'), 'wrong app', 'over budget'):
            with self.subTest(failure=failure):
                stopped = threading.Event()
                server = MagicMock(server_port=12345)
                server.serve_forever.side_effect = stopped.wait
                server.shutdown.side_effect = stopped.set
                opener = MagicMock()
                response = opener.open.return_value.__enter__.return_value
                response.status = 200
                response.read.return_value = json.dumps({'app': 'wrong' if failure == 'wrong app'
                                                        else 'titanium-bot-lite'}).encode()
                if isinstance(failure, OSError):
                    opener.open.side_effect = failure
                out = io.StringIO()
                with patch('lite.server.Server', return_value=server) as factory, \
                     patch('lite.server.urllib.request.build_opener', return_value=opener), \
                     patch('lite.server.IMPORT_STARTED', time.monotonic() - (6 if failure == 'over budget' else .25)), \
                     contextlib.redirect_stdout(out):
                    if isinstance(failure, OSError) or failure == 'wrong app':
                        with self.assertRaises(Refusal):
                            selfcheck(self.app)
                    else:
                        self.assertEqual(selfcheck(self.app), 1 if failure else 0)
                        report = json.loads(out.getvalue())
                        self.assertEqual(report['budgetPassed'], failure is None)
                        self.assertGreaterEqual(report['budget']['coldStartMs'], 250)
                        self.assertGreater(report['replyCharacters'], 0)
                factory.assert_called_once_with(('127.0.0.1', 0), self.app)
                opener.open.assert_called_once_with('http://127.0.0.1:12345/api/health', timeout=10)
                server.shutdown.assert_called_once()
                server.server_close.assert_called_once()
                self.assertFalse(any(t.name == 'Titan startup probe' for t in threading.enumerate()))

    def test_lite_contains_no_process_launches(self):
        for path in (Path(__file__).resolve().parents[1] / 'lite').rglob('*.py'):
            source = path.read_text()
            self.assertNotIn('subprocess', source, str(path))
            self.assertNotIn('os.system', source, str(path))

    def test_memory_reader_validation_and_live_persona(self):
        path = self.app.root / 'memory/profile.md'
        path.write_text('- (2026-09-11) Café\t au  lait\n- (2026-09-12) CAFÉ AU LAIT\n- (2026-02-30) invalid date\n- (2026-09-11) ' + 'é' * 500 + '\n- (2026-09-11) ' + 'z' * 501 + '\nnot a fact\n')
        facts = read_memories(self.app.root)
        self.assertEqual([f['chars'] for f in facts], [12, 500])
        (self.app.root / 'files/facts.md').write_text('- (2026-09-11) Must not enter memory from symlink\n')
        (self.app.root / 'memory/leak.md').symlink_to(self.app.root / 'files/facts.md')
        self.assertEqual(read_memories(self.app.root), facts)
        (self.app.root / 'persona.md').write_text('Persona changed just now')
        self.assertIn('Persona changed just now', build_prompt(self.app.root))

    def test_queue_history_does_not_include_future_turns(self):
        entered, release = threading.Event(), threading.Event()
        histories = []
        def chat(messages, on_token):
            histories.append(messages)
            entered.set()
            if not release.wait(2):
                raise AssertionError('Test failed to release first reply')
            on_token('reply ' + messages[-1]['content'])
            return {}
        with patch.object(self.app.device, 'chat', chat):
            self.app.send({'agentId': 'titan', 'text': 'first'})
            self.assertTrue(entered.wait(2))
            self.app.send({'agentId': 'titan', 'text': 'second'})
            release.set()
            self.wait_idle()
        self.assertEqual([m['content'] for m in histories[0][1:]], ['first'])
        self.assertEqual([m['content'] for m in histories[1][1:]], ['first', 'reply first', 'second'])
        self.assertEqual([m['text'] for m in self.app.messages], ['first', 'reply first', 'second', 'reply second'])


class UpstreamTests(AppCase):
    def response(self, payload, streaming=False):
        response = io.BytesIO(payload if streaming else json.dumps(payload).encode())
        response.headers = {'Content-Type': 'text/event-stream' if streaming else 'application/json'}
        return response

    def test_busy_retries_and_ordinary_turn_parameters(self):
        device = self.app.device
        device.model = 'real-model'
        chunks = []
        replies = [self.response({'code': 150004}), urllib.error.HTTPError('http://localhost/v1/chat/completions', 502, 'busy', {}, io.BytesIO(b'upstream busy')), self.response({'choices': [{'message': {'content': 'ready'}}], 'usage': {'total_tokens': 9}})]
        with patch.object(device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()) as hold, patch('urllib.request.urlopen', side_effect=replies) as opened, patch('lite.server.time.sleep') as sleep:
            usage = device.chat([{'role': 'user', 'content': 'hello'}], chunks.append)
        self.assertEqual(chunks, ['ready'])
        self.assertEqual(usage['total_tokens'], 9)
        self.assertEqual(hold.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        body = json.loads(opened.call_args.args[0].data)
        self.assertEqual(body['chat_template_kwargs'], {'enable_thinking': False})
        self.assertGreaterEqual(body['max_tokens'], 800)
        self.assertTrue(body['stream'])

    def test_stream_hides_reasoning_and_does_not_retry_after_content(self):
        stream = b'data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\ndata: {"choices":[{"delta":{"content":"visible"}}]}\n\ndata: {"code":150004}\n\n'
        chunks = []
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), patch('urllib.request.urlopen', return_value=self.response(stream, True)) as opened:
            with self.assertRaises(Refusal):
                self.app.device.request('/chat/completions', {}, chunks.append)
        self.assertEqual(chunks, ['visible'])
        self.assertEqual(opened.call_count, 1)

    def models_answer(self, rows):
        """What the device sends back for /v1/models, which is exactly what it has loaded."""
        return self.response({'object': 'list', 'data': rows})

    # Recorded from a Tiiny on 2026-09-14: /v1/models lists the loaded models only, each with the
    # capability the device gives it and a supports_chat flag beside it.
    CHAT_ROW = dict(id='Qwen/Qwen3-8B', capabilities=['main'], type='Text Generation',
                    supports_chat=True)
    VOICE_ROW = dict(id='Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice', capabilities=['voice'],
                     type='Text-to-Speech', supports_chat=False)
    EMBED_ROW = dict(id='Qwen/Qwen3-Embedding-0.6B', capabilities=['embedding'],
                     type='Text Embedding', supports_chat=False)

    def test_a_reachable_tiiny_with_no_chat_model_is_not_called_unreachable(self):
        """Jason, 2026-09-14, from a screenshot: every message came back "Cannot reach the device"
        while the device was on the desk and simply had no chat model loaded."""
        self.app.device.model = 'real-model'
        dropped = urllib.error.URLError(OSError(errno.ECONNRESET, 'connection reset'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), \
                patch('urllib.request.urlopen',
                      side_effect=[dropped, self.models_answer([self.EMBED_ROW, self.VOICE_ROW])]):
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/chat/completions', {})
        self.assertEqual(str(caught.exception),
                         'Your Tiiny is reachable but no chat model is loaded. Load one in'
                         ' TiinyOS, or run: farm start --load titanium-tiiny-bot')
        self.assertEqual(caught.exception.status, 503)

    def test_a_device_that_really_did_not_answer_keeps_the_old_sentence(self):
        self.app.device.model = 'real-model'
        dropped = urllib.error.URLError(OSError(errno.ECONNRESET, 'connection reset'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), \
                patch('urllib.request.urlopen', side_effect=[dropped, dropped]):
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/chat/completions', {})
        self.assertIn('Cannot reach the device', str(caught.exception))

    def test_a_chat_model_that_is_loaded_leaves_the_sentence_alone(self):
        """Then the trouble is something else, and saying "no chat model" would send somebody to
        load one they already have."""
        self.app.device.model = 'real-model'
        dropped = urllib.error.URLError(OSError(errno.ECONNRESET, 'connection reset'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), \
                patch('urllib.request.urlopen',
                      side_effect=[dropped, self.models_answer([self.CHAT_ROW])]):
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/chat/completions', {})
        self.assertIn('Cannot reach the device', str(caught.exception))

    def test_a_model_that_is_not_loaded_is_not_reported_as_busy(self):
        """A model the device does not have loaded answers 404, and calling that busy sends
        somebody to wait for a device that is waiting for them."""
        self.app.device.model = 'real-model'
        self.app.device.busy_budget = 0
        gone = urllib.error.HTTPError('http://localhost', 404, 'Not Found', {},
                                      io.BytesIO(b'{"error": {"type": "model_not_found"}}'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), \
                patch('urllib.request.urlopen',
                      side_effect=[gone, self.models_answer([self.EMBED_ROW])]):
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/chat/completions', {})
        self.assertIn('no chat model is loaded', str(caught.exception))

    def test_the_question_that_picks_the_sentence_never_fails_a_turn(self):
        """It is asked after something has already gone wrong, so it has to be incapable of
        making things worse."""
        self.assertIsNone(self.app.device.loaded_models())  # The echo model asks nothing.
        self.app.device.model = 'real-model'
        with patch('urllib.request.urlopen', side_effect=ValueError('nonsense')):
            self.assertIsNone(self.app.device.loaded_models())
        with patch('urllib.request.urlopen', return_value=self.response(b'not json', True)):
            self.assertIsNone(self.app.device.loaded_models())
        with patch('urllib.request.urlopen', return_value=self.response({'data': 'wrong'})):
            self.assertEqual(self.app.device.loaded_models(), [])

    def test_what_counts_as_a_chat_model_and_what_counts_as_a_voice_one(self):
        chat, voice = self.app.device.is_chat_model, self.app.device.is_voice_model
        self.assertTrue(chat(self.CHAT_ROW))
        self.assertFalse(chat(self.VOICE_ROW))
        # Both answer with a bool. The capability test is a set intersection, and handing back
        # the set instead would be true enough for an if and wrong for anything that compares.
        self.assertIs(voice(self.VOICE_ROW), True)
        self.assertIs(voice(self.CHAT_ROW), False)
        self.assertIs(chat(self.CHAT_ROW), True)
        # Firmware that sends no supports_chat flag and no capability list still says the type,
        # and "Text Generation" is what a chat model's type is on a live Tiiny.
        self.assertTrue(chat(dict(id='x/y', type='Text Generation')))
        self.assertTrue(chat(dict(id='x/y', type='Image-Text-to-Text')))
        self.assertFalse(chat(dict(id='x/y', type='Text Embedding')))
        self.assertTrue(voice(dict(id='x/y', type='TTS')))
        self.assertFalse(chat(dict(id='', capabilities=['main'])))

    def test_the_model_page_says_the_same_thing_as_the_failed_turn(self):
        """The state belongs where somebody goes to fix it, not only in the reply that failed."""
        self.app.device.model = 'real-model'
        with patch.object(self.app.device, 'request',
                          return_value={'data': [self.EMBED_ROW, self.VOICE_ROW]}):
            payload = self.app.models_payload()
        self.assertTrue(payload['note'].startswith(
            'Your Tiiny is reachable but no chat model is loaded.'))
        with patch.object(self.app.device, 'request',
                          return_value={'data': [self.CHAT_ROW, self.EMBED_ROW]}):
            payload = self.app.models_payload()
        self.assertNotIn('no chat model is loaded', payload['note'])

    def test_retry_budget_and_errors_never_disclose_key(self):
        self.app.device.model = "real-model"
        self.app.device.busy_budget = 0
        error = urllib.error.HTTPError('http://localhost', 502, 'test-private-key', {}, io.BytesIO(b'test-private-key'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), patch('urllib.request.urlopen', side_effect=error) as opened:
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/models')
        # One attempt, and then the question that decides which sentence is true: what does the
        # device have loaded? It fails here too, so the old sentence stands.
        self.assertEqual(opened.call_count, 2)
        self.assertIn('busy or unavailable', str(caught.exception))
        self.assertNotIn('test-private-key', str(caught.exception))


class RealHTTPTests(AppCase):
    def start_server(self):
        try:
            server = Server(('127.0.0.1', 0), self.app)
        except PermissionError:
            self.skipTest('Sandbox denies binding a loopback socket; wire-level HTTP tests still run')
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:' + str(server.server_port)

    def test_echo_over_real_http(self):
        base = self.start_server()
        request = urllib.request.Request(base + '/api/send', data=json.dumps({'agentId': 'titan', 'text': 'spare port'}).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)['message']['text'], 'spare port')
        self.wait_idle()
        with urllib.request.urlopen(base + '/api/transcript?agentId=titan', timeout=3) as response:
            transcript = json.load(response)
        self.assertEqual(transcript['messages'][-1]['text'], 'trop eraps')

    def test_actual_javascript_adapter_over_real_http(self):
        base = self.start_server()
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed only to test the actual JavaScript adapter')
        result = subprocess.run([node, 'tests/adapter-contract.cjs', base, sys.executable],
                                cwd=TEST_ROOT.parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_door_resource_budget_and_events_over_urllib(self):
        base = self.start_server()
        self.assertEqual(first_paint_bytes(base), first_paint_bytes())
        self.assertLess(first_paint_bytes(base), 250000)
        with urllib.request.urlopen(base + '/events', timeout=3) as response:
            self.assertEqual(response.headers['Content-Type'], 'text/event-stream')
            self.assertEqual(response.readline(), b'data: {"channel":"changed"}\n')


class ModelRouteTests(AppCase):
    """Route 7 against a fake device, and route 6 against its model rows.

    The environment override is off here: these tests move the base between the
    device and another computer, and TIINY_BASE outranks config.json by design.
    """
    ENVIRONMENT = {}
    KEYS = ('device-private-key', 'lan-private-key', 'cloud-private-key')

    def prepare(self, root):
        root.mkdir(parents=True, exist_ok=True)
        (root / 'keys.json').write_text(json.dumps({'apiKey': 'device-private-key'}))

    def setUp(self):
        # An empty base in config.json means "find the device", so the search is
        # stubbed rather than reached for.
        found = patch('lite.device.find_base', return_value='http://192.0.2.10/v1')
        found.start()
        self.addCleanup(found.stop)
        super().setUp()
        self.calls = []
        self.answers = {}
        self.held = 0
        self.rows = [{'id': 'chat-model'}, {'id': 'other-model'}]
        self.app.device.model = 'chat-model'
        self.app.device.resolved_model = 'chat-model'
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.app.device.lane, 'hold', self.hold))
        self.stack.enter_context(patch('urllib.request.urlopen', self.upstream))

    @contextlib.contextmanager
    def hold(self, **kwargs):
        self.assertGreater(kwargs['wait'], 0)
        self.held += 1
        yield

    def upstream(self, request, **kwargs):
        self.assertGreater(self.held, 0, 'Device HTTP call bypassed OneLane')
        path = urllib.parse.urlsplit(request.full_url).path
        self.calls.append((path, request))
        status, payload = self.answers.get(path, (200, {'code': 0}))
        body = json.dumps(payload).encode()
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, 'refused', {}, io.BytesIO(body))
        response = io.BytesIO(body)
        response.headers = {'Content-Type': 'application/json'}
        response.status = status
        return response

    def lifecycle_calls(self):
        return [path for path, _ in self.calls if path.startswith('/api/v1/models/')]

    def models(self, rows=None):
        with patch.object(self.app.device, 'request', return_value={'data': self.rows if rows is None else rows}):
            return self.request('GET', '/api/models')

    def test_lifecycle_runs_on_the_device_and_repeats_its_refusal_in_its_own_words(self):
        self.request('POST', '/api/model', {'action': 'start', 'id': 'other-model'})
        path, sent = self.calls[0]
        self.assertEqual(path, '/api/v1/models/other-model/start')
        self.assertEqual(sent.data, b'{}')
        self.assertEqual(sent.get_header('Host'), 'p8800.api.tiiny')
        self.assertEqual(sent.get_header('Authorization'), 'Bearer device-private-key')
        self.request('POST', '/api/model', {'action': 'stop', 'id': 'other-model'})
        self.assertEqual(self.lifecycle_calls(),
                         ['/api/v1/models/other-model/start', '/api/v1/models/other-model/stop'])
        # A device that refuses says why. We do not paraphrase it.
        self.answers['/api/v1/models/other-model/start'] = (400, {'message': 'Not enough NPU memory for this model.'})
        refused = self.request('POST', '/api/model', {'action': 'start', 'id': 'other-model'}, 502)
        self.assertEqual(refused['error'], 'Not enough NPU memory for this model.')
        # A refusal wearing a success status is still a refusal, and a silent one
        # gets our sentence because the device offered none.
        self.answers['/api/v1/models/other-model/start'] = (200, {'code': 150004})
        self.assertIn('would not start', self.request(
            'POST', '/api/model', {'action': 'start', 'id': 'other-model'}, 502)['error'])
        # A one-word answer is a code, so ours carries it rather than standing aside,
        # and a device that somehow echoes the key back does not get to print it.
        self.answers['/api/v1/models/other-model/stop'] = (500, {'detail': 'device-private-key'})
        refused = self.request('POST', '/api/model', {'action': 'stop', 'id': 'other-model'}, 502)['error']
        self.assertIn('would not stop', refused)
        self.assertIn('[redacted]', refused)

    def test_stopping_the_model_titan_answers_on_is_refused_before_the_device_hears_it(self):
        refused = self.request('POST', '/api/model', {'action': 'stop', 'id': 'chat-model'}, 409)
        self.assertIn('Choose another model for Titan first', refused['error'])
        self.assertFalse(self.calls)
        self.app.device.model, self.app.device.resolved_model = 'default', None
        self.request('POST', '/api/model', {'action': 'stop', 'id': 'chat-model'})
        self.assertEqual(self.lifecycle_calls(), ['/api/v1/models/chat-model/stop'])

    def test_running_is_read_off_the_device_rows_not_the_model_lite_picked(self):
        answer = self.models([{'id': 'chat-model', 'running': False},
                              {'id': 'other-model', 'name': 'Other', 'running': True}])
        self.assertEqual([(row['id'], row['running']) for row in answer['device']],
                         [('chat-model', False), ('other-model', True)])
        self.assertIn('Start and stop', answer['note'])
        self.assertEqual(answer['device'][1]['name'], 'Other')
        answer = self.models([{'id': 'chat-model', 'status': 'stopped'},
                              {'id': 'other-model', 'status': 'Loaded'}])
        self.assertEqual([row['running'] for row in answer['device']], [False, True])
        # A device that says nothing about loading falls back to the model Lite
        # picked, and the answer says that is what it did.
        answer = self.models()
        self.assertEqual([row['running'] for row in answer['device']], [True, False])
        self.assertIn('does not say', answer['note'])
        self.assertIsNone(Device.loaded_flag({'id': 'x'}))
        self.assertIs(Device.loaded_flag({'id': 'x', 'loaded': True}), True)

    def test_another_computer_persists_across_a_restart_with_its_own_key(self):
        live = self.request('POST', '/api/model', {
            'action': 'use', 'baseUrl': 'http://192.168.7.5:11434/v1/',
            'model': 'llama3', 'apiKey': 'lan-private-key'})['live']
        self.assertEqual(live['endpoint'], 'http://192.168.7.5:11434/v1')
        self.assertEqual((live['source'], live['hasKey'], live['model']), ('lan', True, 'llama3'))
        saved = json.loads((self.app.root / 'config.json').read_text())
        self.assertEqual(saved['endpoints'], [{'baseUrl': 'http://192.168.7.5:11434/v1', 'model': 'llama3'}])
        self.assertEqual(saved['base'], 'http://192.168.7.5:11434/v1')
        self.assertNotIn('lan-private-key', json.dumps(saved))
        keys = self.app.root / 'keys.json'
        self.assertEqual(keys.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(keys.read_text()),
                         {'apiKey': 'device-private-key',
                          'endpoints': {'http://192.168.7.5:11434/v1': 'lan-private-key'}})
        self.assertEqual(self.models()['lan'],
                         [{'baseUrl': 'http://192.168.7.5:11434/v1', 'model': 'llama3', 'hasKey': True}])
        self.app.close()
        restarted = App(self.temp.name)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.device.base, 'http://192.168.7.5:11434/v1')
        self.assertEqual(restarted.device.key, 'lan-private-key')
        self.assertEqual(restarted.endpoint_source(), 'lan')

    def test_a_cloud_address_is_the_same_route_and_the_device_is_one_press_away(self):
        self.request('POST', '/api/model', {'action': 'use', 'baseUrl': 'https://api.example.com/v1',
                                            'model': 'cloud-model', 'apiKey': 'cloud-private-key'})
        self.assertEqual(self.app.device.key, 'cloud-private-key')
        self.assertEqual(self.app.endpoint_source(), 'cloud')
        live = self.request('POST', '/api/model', {'action': 'use', 'source': 'device'})['live']
        self.assertEqual((live['source'], live['endpoint'], live['model']),
                         ('device', 'http://192.0.2.10/v1', 'default'))
        # The device's key is still the device's, and the cloud key never went there.
        self.assertEqual(self.app.device.key, 'device-private-key')
        self.request('POST', '/api/model', {'action': 'forget', 'baseUrl': 'https://api.example.com/v1'})
        self.assertEqual(json.loads((self.app.root / 'keys.json').read_text()),
                         {'apiKey': 'device-private-key', 'endpoints': {}})
        self.assertEqual(self.models()['lan'], [])
        self.assertEqual(endpoint_kind('http://titan.local/v1'), 'lan')
        self.assertEqual(endpoint_kind('https://api.example.com/v1'), 'cloud')

    def test_a_refused_key_is_reported_as_a_key_and_not_as_weather(self):
        # Measured on the attached unit: with no key the firmware answers 401 with
        # this sentence, and calling it "busy" sent the owner to the wrong place.
        error = urllib.error.HTTPError('http://192.0.2.10/v1/models', 401, 'no', {}, io.BytesIO(
            json.dumps({'error': 'unauthorized',
                        'message': 'Missing bearer token: send Authorization.'}).encode()))
        with patch('urllib.request.urlopen', side_effect=error):
            refused = self.request('GET', '/api/models', status=502)
        self.assertEqual(refused['error'], 'Missing bearer token: send Authorization.')

    def test_no_answer_or_log_line_carries_a_key(self):
        self.request('POST', '/api/model', {'action': 'use', 'baseUrl': 'http://192.168.7.5:11434/v1',
                                            'model': 'llama3', 'apiKey': 'lan-private-key'})
        with patch.object(self.app, 'budget', return_value={}):
            for path in ('/api/state', '/api/settings', '/api/library'):
                self.request('GET', path)
        self.models()
        self.app.device.log.error('upstream said %s', 'lan-private-key')
        for handler in self.app.device.log.handlers:
            handler.flush()
        written = (self.app.root / 'lite.log').read_text()
        self.assertIn('[redacted]', written)
        self.assertNotIn('lan-private-key', written)

    def test_a_turn_in_flight_keeps_its_endpoint_and_never_blocks_the_switch(self):
        started = self.app.device
        reply = self.app.message('titan', '', 'working')
        self.app.active = True
        try:
            self.request('POST', '/api/model', {'action': 'use', 'baseUrl': 'http://192.168.7.5:11434/v1',
                                                'model': 'llama3'})
        finally:
            self.app.active = False
        switched = self.app.device
        self.assertIsNot(switched, started)
        with patch.object(started, 'chat', return_value={}) as before, \
                patch.object(switched, 'chat', return_value={}) as after:
            self.app.tool_loop([{'role': 'user', 'content': 'hello'}], lambda chunk: None, reply, device=started)
            self.assertEqual((before.call_count, after.call_count), (1, 0))
            self.app.tool_loop([{'role': 'user', 'content': 'hello'}], lambda chunk: None, reply)
            self.assertEqual((before.call_count, after.call_count), (1, 1))
            # The second memory writer belongs to the same exchange, so it reads the
            # exchange back on the computer that answered it, not on the new one.
            self.app.extract_memories('I moved to Dallas.', 'Noted.', started)
            self.assertEqual((before.call_count, after.call_count), (2, 1))
            self.app.extract_memories('I moved to Dallas.', 'Noted.')
            self.assertEqual((before.call_count, after.call_count), (2, 2))
