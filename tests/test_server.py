"""Offline wire contracts plus optional real loopback HTTP integration."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from types import SimpleNamespace

TEST_ROOT = Path(__file__).resolve().parents[1] / 'data/tests'
TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ['ONELANE_DIR'] = str(TEST_ROOT / '.onelane')
from lite.server import App, Device, Handler, Refusal, Server, build_prompt, first_paint_bytes, read_memories, read_persona


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
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, TIINY_BASE='http://localhost/v1', TIINY_KEY='test-private-key', TIINY_MODEL='echo')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = App(self.temp.name)
        # Most route tests begin after the separately tested first-run greeting.
        self.app.messages.clear()
        self.app.save_messages()
        self.addCleanup(self.app.close)

    def request(self, method, path, body=None, status=200, headers=None):
        actual, response_headers, result = wire(self.app, method, path, body, headers)
        self.assertEqual(actual, status, result)
        self.assertNotIn('test-private-key', str(result))
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
        self.request('PATCH', '/api/settings', {'talkEnabled': True}, 501)
        self.request('PATCH', '/api/settings', {'voice': {'enabled': True}}, 501)

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

    def test_models_and_explicit_future_refusals(self):
        with patch.object(self.app.device, 'request', return_value={'data': [{'id': 'echo'}]}):
            models = self.request('GET', '/api/models')
        self.assertEqual(models['device'], [{'id': 'echo', 'name': 'echo', 'running': True}])
        self.assertEqual(models['lan'], [])
        self.assertEqual(self.request('POST', '/api/model', {'action': 'use', 'id': 'another'})['live']['model'], 'echo')
        self.assertEqual(json.loads((self.app.root / 'config.json').read_text())['model'], 'another')
        for action in ('start', 'stop'):
            self.request('POST', '/api/model', {'action': action, 'id': 'echo'}, 501)
        self.request('POST', '/api/model', {'action': 'use', 'model': 'echo', 'baseUrl': 'http://elsewhere', 'apiKey': 'test-private-key'}, 501)
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
    def test_selfcheck_measures_fresh_process_and_budget(self):
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

    def test_retry_budget_and_errors_never_disclose_key(self):
        self.app.device.model = "real-model"
        self.app.device.busy_budget = 0
        error = urllib.error.HTTPError('http://localhost', 502, 'test-private-key', {}, io.BytesIO(b'test-private-key'))
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), patch('urllib.request.urlopen', side_effect=error) as opened:
            with self.assertRaises(Refusal) as caught:
                self.app.device.request('/models')
        self.assertEqual(opened.call_count, 1)
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
