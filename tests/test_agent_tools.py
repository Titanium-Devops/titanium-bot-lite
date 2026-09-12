"""Offline Step 3 tool-loop, sandbox, memory and skill regressions."""
import contextlib
import copy
import io
import json
import socket
from datetime import date, timedelta
from email.message import Message
from unittest.mock import Mock, patch

from lite.agent_tools import CAP, fetch_url
from lite.server import Refusal, TOOLS, build_prompt, read_memories
from tests.test_server import AppCase


def tool_call(name='Read', args=None, ident='call-1'):
    return dict(id=ident, type='function', function=dict(name=name, arguments=json.dumps(args or {'path': 'note.txt'})))


def stream_response(events):
    response = io.BytesIO(b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events) + b'data: [DONE]\n\n')
    response.headers = {'Content-Type': 'text/event-stream'}
    return response


class AgentToolTests(AppCase):
    def loop(self, chat):
        reply = self.app.message('titan', '', 'working')
        self.app.messages.append(reply)
        messages = [dict(role='user', content='Please help')]
        tokens = []
        with patch.object(self.app.device, 'chat', side_effect=chat):
            usage = self.app.tool_loop(messages, tokens.append, reply)
        return messages, tokens, usage

    def test_fake_device_tool_then_final_and_receipt(self):
        calls = []
        def chat(messages, emit, **options):
            calls.append(copy.deepcopy(messages))
            if len(calls) == 1:
                return {'total_tokens': 2, '_message': {'content': None, 'tool_calls': [tool_call('Write', {'path': 'note.txt', 'content': 'hello'})]}}
            emit('Saved it.')
            return {'total_tokens': 3, '_message': {'content': 'Saved it.'}}
        messages, tokens, usage = self.loop(chat)
        self.assertEqual(tokens, ['Saved it.'])
        self.assertEqual(usage['total_tokens'], 5)
        self.assertEqual((self.app.root / 'files/note.txt').read_text(), 'hello')
        self.assertEqual([m['role'] for m in messages], ['user', 'assistant', 'tool'])
        self.assertEqual(calls[1][-1]['tool_call_id'], 'call-1')
        receipt = next(m for m in self.app.messages if m.get('toolCallId') == 'call-1')
        self.assertEqual(receipt['type'], 'system')
        self.assertIn('Wrote', receipt['detail'])

    def test_actual_device_assembles_fragmented_tool_and_streams_final(self):
        first = stream_response([
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call-', 'function': {'name': 'Wr', 'arguments': '{"path":'}}]}}]},
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': '1', 'function': {'name': 'ite', 'arguments': '"note.txt","content":"hello"}'}}]}}]},
            {'choices': [], 'usage': {'total_tokens': 4}},
        ])
        second = stream_response([
            {'choices': [{'delta': {'content': 'All '}}]},
            {'choices': [{'delta': {'content': 'done.'}}]},
            {'choices': [], 'usage': {'total_tokens': 6}},
        ])
        self.app.device.model = self.app.device.resolved_model = 'offline-model'
        reply = self.app.message('titan', '', 'working')
        self.app.messages.append(reply)
        messages, tokens = [{'role': 'user', 'content': 'Save hello'}], []
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()), patch('urllib.request.urlopen', side_effect=[first, second]) as request:
            usage = self.app.tool_loop(messages, tokens.append, reply)
        self.assertEqual(tokens, ['All ', 'done.'])
        self.assertEqual(usage['total_tokens'], 10)
        bodies = [json.loads(call.args[0].data) for call in request.call_args_list]
        self.assertEqual(bodies[0]['tools'], TOOLS)
        self.assertFalse(bodies[0]['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(bodies[1]['messages'][-1]['role'], 'tool')
        self.assertEqual(bodies[1]['messages'][-1]['tool_call_id'], 'call-1')
        self.assertEqual((self.app.root / 'files/note.txt').read_text(), 'hello')

    def test_six_tool_rounds_then_final_with_tools_disabled(self):
        options_seen = []
        def chat(messages, emit, **options):
            options_seen.append(options)
            if len(options_seen) <= 6:
                return {'_message': {'tool_calls': [tool_call('Write', {'path': 'note.txt', 'content': 'hello'})]}}
            emit('Finished')
            return {'_message': {'content': 'Finished'}}
        self.loop(chat)
        self.assertEqual(len(options_seen), 7)
        self.assertTrue(all(not opts.get('allow_tools') is False for opts in options_seen[:6]))
        self.assertIs(options_seen[-1]['allow_tools'], False)
        self.assertEqual(sum('toolCallId' in m for m in self.app.messages), 6)

    def test_seventh_tool_round_is_refused_before_execution(self):
        def chat(messages, emit, **options):
            return {'_message': {'tool_calls': [tool_call('Write', {'path': 'note.txt', 'content': 'hello'})]}}
        with patch.object(self.app, 'run_tool', return_value='done') as execute:
            with self.assertRaisesRegex(Refusal, 'six-round'):
                self.loop(chat)
        self.assertEqual(execute.call_count, 6)

    def test_two_empty_replies_enable_thinking_once(self):
        options_seen = []
        def chat(messages, emit, **options):
            options_seen.append(options)
            return {'_message': {'content': ''}}
        with self.assertRaisesRegex(Refusal, 'no text'):
            self.loop(chat)
        self.assertEqual(options_seen, [{}, {}, {'thinking': True}])

    def test_read_write_roundtrip_and_sandbox(self):
        self.app.run_tool('Write', {'path': 'files/sub/note.txt', 'content': 'one\ntwo\nthree'})
        self.assertEqual(self.app.run_tool('Read', {'path': 'sub/note.txt', 'offset': 1, 'limit': 1}), 'two')
        for path in ('../persona.md', '/tmp/outside.txt', 'files/../../outside.txt'):
            for tool in ('Read', 'Write'):
                with self.subTest(path=path, tool=tool), self.assertRaises(Refusal):
                    self.app.run_tool(tool, {'path': path, 'content': 'overwrite'})
        (self.app.root / 'files/link').symlink_to(self.app.root / 'persona.md')
        (self.app.root / 'files/directory').symlink_to(self.app.root / 'memory', target_is_directory=True)
        for path in ('link', 'directory/profile.md'):
            for tool in ('Read', 'Write'):
                with self.subTest(path=path, tool=tool), self.assertRaises(Refusal):
                    self.app.run_tool(tool, {'path': path, 'content': 'overwrite'})

    def test_memory_cap_dedup_profile_and_latest_40(self):
        self.app.run_tool('update_state', {'target': 'memory', 'action': 'write', 'fact': 'a' * 500})
        with self.assertRaisesRegex(Refusal, '500'):
            self.app.run_tool('update_state', {'target': 'memory', 'action': 'write', 'fact': 'b' * 501})
        self.app.run_tool('update_state', {'target': 'memory', 'action': 'write', 'fact': 'A' * 500})
        self.assertEqual(len(read_memories(self.app.root)), 1)
        self.app.run_tool('update_state', {'target': 'profile', 'action': 'write', 'fact': 'The owner likes tea.'})
        for path in (self.app.root / 'memory/log').glob('*.md'):
            path.unlink()
        log = self.app.root / 'memory/log/2026-01.md'
        log.write_text('\n'.join(f'- ({date(2026, 1, 1) + timedelta(days=i)}) fact-{i:02}' for i in range(45)))
        prompt = build_prompt(self.app.root)
        self.assertIn('The owner likes tea.', prompt)
        for i in range(45):
            (self.assertNotIn if i < 5 else self.assertIn)(f'fact-{i:02}', prompt)
        self.assertIn('5 more facts', prompt)

    def test_catalog_and_run_skill_and_disabled_refusal(self):
        path = self.app.root / 'skills/test-skill/SKILL.md'
        path.parent.mkdir()
        path.write_text('---\nname: Test skill\ndescription: A deterministic helper\n---\nOnly the body belongs here.')
        prompt = build_prompt(self.app.root)
        self.assertIn('Test skill: A deterministic helper (skills/test-skill/SKILL.md)', prompt)
        self.assertNotIn('Only the body belongs here.', prompt)
        self.assertEqual(self.app.run_tool('run_skill', {'name': 'Test skill'}), 'Only the body belongs here.')
        (path.parent / 'disabled').touch()
        self.assertIn('Test skill', build_prompt(self.app.root))
        with self.assertRaisesRegex(Refusal, 'unavailable'):
            self.app.run_tool('run_skill', {'name': 'Test skill'})

    def test_fetch_rejects_private_addresses_before_connecting(self):
        for address in ('127.0.0.1', '10.1.2.3', '169.254.169.254', '::1'):
            with self.subTest(address=address), patch('lite.agent_tools.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 80))]), patch('lite.agent_tools.socket.socket') as connect:
                with self.assertRaisesRegex(Refusal, 'non-public'):
                    fetch_url('http://example.test/data')
                connect.assert_not_called()

    def test_fetch_text_and_byte_cap(self):
        headers = Message()
        headers['Content-Type'] = 'text/plain; charset=utf-8'
        for content in (b'hello', b'x' * (CAP + 1)):
            response = Mock(status=200, headers=headers)
            response.isclosed.return_value = False
            response.read1.side_effect = io.BytesIO(content).read
            connection = Mock()
            connection.getresponse.return_value = response
            with patch('lite.agent_tools.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))]), patch('lite.agent_tools.socket.socket'), patch('lite.agent_tools.http.client.HTTPConnection', return_value=connection):
                if len(content) > CAP:
                    with self.assertRaisesRegex(Refusal, '200 KB'):
                        fetch_url('http://example.test/data')
                else:
                    self.assertIn('hello', fetch_url('http://example.test/data'))
                connection.close.assert_called_once()

    def test_thinking_retry_recovers_after_tool_round(self):
        options_seen = []
        def chat(messages, emit, **options):
            options_seen.append(options)
            if len(options_seen) == 1:
                return {'_message': {'tool_calls': [tool_call('Write', {'path': 'note.txt', 'content': 'hello'})]}}
            if len(options_seen) < 4:
                return {'_message': {'content': ''}}
            emit('Recovered')
            return {'_message': {'content': 'Recovered'}}
        messages, tokens, _ = self.loop(chat)
        self.assertEqual(options_seen, [{}, {}, {}, {'thinking': True}])
        self.assertEqual(tokens, ['Recovered'])
        self.assertEqual(messages[-1]['role'], 'tool')
        self.assertEqual(sum('toolCallId' in m for m in self.app.messages), 1)

    def test_invalid_arguments_and_long_memory_return_refusal_to_model(self):
        malformed = tool_call(ident='malformed')
        malformed['function']['arguments'] = '{broken json'
        long_fact = tool_call('update_state', {'target': 'memory', 'action': 'write', 'fact': 'x' * 501}, 'long-fact')
        requests = []
        def chat(messages, emit, **options):
            requests.append(copy.deepcopy(messages))
            if len(requests) == 1:
                return {'_message': {'tool_calls': [malformed, long_fact]}}
            emit('Please shorten the fact.')
            return {'_message': {'content': 'Please shorten the fact.'}}
        messages, _, _ = self.loop(chat)
        results = [m for m in requests[1] if m['role'] == 'tool']
        self.assertEqual([m['tool_call_id'] for m in results], ['malformed', 'long-fact'])
        self.assertTrue(all(m['content'].startswith('Refused:') for m in results))
        self.assertIn('500 characters', results[1]['content'])
        receipts = [m for m in self.app.messages if 'toolCallId' in m]
        self.assertEqual([m['detail'] for m in receipts], [m['content'] for m in results])
        self.assertTrue(all('refused' in m['text'] for m in receipts))
        self.assertEqual(read_memories(self.app.root), [])

    def test_routine_storage_lifecycle(self):
        base = dict(target='routine', action='create', name='Morning', prompt='Review notes')
        root = self.app.root / 'routines'
        for schedule in ('61 * * * *', '0 25 * * *', 'when mail arrives', '* * * *', '*/0 * * * *'):
            with self.subTest(schedule=schedule), self.assertRaises(Refusal):
                self.app.run_tool('update_state', dict(base, schedule=schedule))
            self.assertEqual(list(root.iterdir()), [])
        self.app.run_tool('update_state', dict(base, schedule='0 9 * * 1-5'))
        path, = root.glob('*/routine.json')
        routine = json.loads(path.read_text())
        self.assertFalse(routine['enabled'])
        self.assertEqual(routine['schedule'], '0 9 * * 1-5')
        self.assertEqual(json.loads((path.parent / 'runs.json').read_text()), [])
        ident = path.parent.name
        for args in (dict(action='resume'), dict(action='update', enabled=True)):
            self.app.run_tool('update_state', dict(target='routine', id=ident, **args))
            self.assertTrue(json.loads(path.read_text())['enabled'])
        self.app.update_state(dict(target='routine', action='pause', id=ident))
        original = path.read_text()
        with self.assertRaises(Refusal):
            self.app.run_tool('update_state', dict(target='routine', action='update', id=ident, schedule='bad cron'))
        self.assertEqual(path.read_text(), original)
        self.app.run_tool('update_state', dict(target='routine', action='update', id=ident, schedule='30 10 * * *', name='Later'))
        updated = json.loads(path.read_text())
        self.assertEqual(updated['name'], 'Later')
        self.assertEqual(updated['schedule'], '30 10 * * *')
        self.assertFalse(updated['enabled'])
        self.app.run_tool('update_state', dict(target='routine', action='pause', id=ident))
        self.assertFalse(json.loads(path.read_text())['enabled'])
        self.app.run_tool('update_state', dict(target='routine', action='delete', id=ident))
        self.assertFalse(path.exists())
        self.assertFalse((path.parent / 'runs.json').exists())

    def test_fetch_redirect_and_nontext_refusal_with_ip_pinning(self):
        address = ('93.184.216.34', 8080)
        for status, mime, refusal in ((302, 'text/html', 'Redirects'), (200, 'image/png', 'Only text')):
            headers = Message()
            headers['Content-Type'] = mime
            response = Mock(status=status, headers=headers)
            connection = Mock()
            connection.getresponse.return_value = response
            with self.subTest(status=status, mime=mime), patch('lite.agent_tools.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', address)]) as resolve, patch('lite.agent_tools.socket.socket') as transport, patch('lite.agent_tools.http.client.HTTPConnection', return_value=connection):
                with self.assertRaisesRegex(Refusal, refusal):
                    fetch_url('http://example.test:8080/data?part=1')
                resolve.assert_called_once_with('example.test', 8080, type=socket.SOCK_STREAM)
                transport.return_value.connect.assert_called_once_with(address)
                self.assertEqual(connection.request.call_args.args, ('GET', '/data?part=1'))
                response.read1.assert_not_called()
                connection.close.assert_called_once()
