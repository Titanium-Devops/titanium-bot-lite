"""Replay the captured device transport through Lite's actual queued turn."""
import io
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from lite.server import App, Refusal, read_memories
from tests.test_agent_tools import stream_response
from tests.test_server import AppCase


class DeviceTurnTests(AppCase):
    def setUp(self):
        debug = patch.dict(os.environ, LITE_DEBUG='1', TIINY_BASE='http://192.0.2.10/v1')
        debug.start()
        self.addCleanup(debug.stop)
        super().setUp()

    def test_captured_memory_call_during_first_run_reaches_transcript(self):
        greeting = self.app.message('titan', 'I’m Titan, your assistant on this device. What should I call you?')
        self.app.messages.append(greeting)
        self.app.save_messages()
        self.app.device.model = self.app.device.resolved_model = 'deepreinforce-ai/Ornith-1.0-35B'
        first = io.BytesIO((Path(__file__).parent / 'fixtures/device-stream-tool-call.sse').read_bytes())
        first.headers = {'Content-Type': 'text/event-stream'}
        answer = 'Your dog is named Biscuit and has a folded ear.'
        second = stream_response([
            {'choices': [{'delta': {'content': answer}}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
        ])
        # The third request is the second memory writer, which runs once the answer is
        # already in the transcript. It has nothing to add here: the tool saved the fact.
        third = stream_response([{'choices': [{'delta': {'content': 'NONE'}}]}])
        started = time.monotonic()
        with patch('urllib.request.urlopen', side_effect=[first, second, third]) as opened:
            self.app.send({'agentId': 'titan', 'text': 'Remember that my dog is named Biscuit and has a folded ear. Then tell me in one sentence what you remembered.'})
            with self.app.changed:
                complete = self.app.changed.wait_for(
                    lambda: any(m['type'] == 'text' and m['text'] == answer for m in self.app.messages),
                    timeout=max(0, 1 - (time.monotonic() - started)))
            self.assertTrue(complete, self.app.messages)
            self.assertLess(time.monotonic() - started, 1)
            self.wait_idle()
        self.assertEqual([m['name'] for m in read_memories(self.app.root)],
                         ['My dog is named Biscuit and has a folded ear.'])
        transcript = json.loads((self.app.root / 'transcripts/main.json').read_text())
        self.assertEqual(transcript[-1]['text'], answer)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(opened.call_count, 3)
        bodies = [json.loads(call.args[0].data) for call in opened.call_args_list]
        self.assertEqual(bodies[0]['messages'][-2]['content'], greeting['text'])
        self.assertEqual(bodies[1]['messages'][-1]['content'], 'Remembered: My dog is named Biscuit and has a folded ear.')
        self.assertEqual(bodies[1]['messages'][-1]['tool_call_id'], 'b6lPmk5epxZJLcaGvmSH43nFQDuOZ4ux')
        self.assertEqual(bodies[2]['tool_choice'], 'none')
        self.assertEqual([m['role'] for m in bodies[2]['messages']], ['system', 'user'])
        self.assertIn('NONE', bodies[2]['messages'][0]['content'])
        self.assertIn('- My dog is named Biscuit and has a folded ear.', bodies[2]['messages'][1]['content'])
        self.assertIn('Owner: Remember that my dog', bodies[2]['messages'][1]['content'])
        self.assertIn('Assistant: ' + answer, bodies[2]['messages'][1]['content'])
        # A new acquisition after both requests proves the real lane was released.
        with self.app.device.lane.hold(why='regression verification', wait=0.1):
            pass
        log = (self.app.root / 'lite.log').read_text()
        for step in ('request sent', 'chunk kinds counted', 'stream finish reason=tool_calls',
                     'tool call assembled name=update_state', 'argument_length=',
                     'tool executed name=update_state', 'result_length=',
                     'final text started', 'final text finished', 'lane released'):
            self.assertIn(step, log)
        self.assertNotIn('test-private-key', log)
        self.assertNotIn('Biscuit', log)

    def test_memory_shorthand_preserves_validation_and_explicit_fields(self):
        for args in (
            {'text': 'a' * 501}, {'text': 123}, {'text': ''},
            {'text': 'valid', 'action': 'delete'},
            {'text': 'valid', 'fact': ''}, {'fact': 'missing action'},
        ):
            with self.subTest(args=args), self.assertRaises(Refusal):
                self.app.update_state(dict(target='memory', **args))
        self.app.update_state(dict(target='memory', text='alias', fact='canonical', action='write'))
        self.app.update_state(dict(target='memory', text='canonical', action='forget'))
        self.assertEqual(read_memories(self.app.root), [])

    def test_exception_logs_traceback_without_debug_and_worker_recovers(self):
        self.app.close()
        with patch.dict(os.environ, LITE_DEBUG='0', TIINY_BASE='http://192.0.2.10/v1'):
            self.app = App(self.temp.name)
        self.addCleanup(self.app.close)
        self.app.device.model = self.app.device.resolved_model = 'offline-model'
        with patch('urllib.request.urlopen', side_effect=ValueError('broken test-private-key stream')):
            self.app.send(dict(agentId='titan', text='hello'))
            self.wait_idle()
        self.assertEqual(self.app.messages[-1]['type'], 'turn-failed')
        log = (self.app.root / 'lite.log').read_text()
        self.assertIn('Traceback (most recent call last)', log)
        self.assertIn('ValueError: broken [redacted] stream', log)
        self.assertIn('turn exception', log)
        self.assertNotIn('test-private-key', log)
        self.assertNotIn('request sent', log)
        final = stream_response([{'choices': [{'delta': {'content': 'Recovered.'}}]}])
        with patch('urllib.request.urlopen', return_value=final):
            self.app.send(dict(agentId='titan', text='try again'))
            self.wait_idle()
        self.assertEqual(self.app.messages[-1]['text'], 'Recovered.')
        self.assertEqual(self.app.messages[-1]['type'], 'text')

    def test_tool_refusal_logs_traceback_and_reaches_final_answer(self):
        from tests.test_agent_tools import tool_call
        first = stream_response([{'choices': [{'delta': {'tool_calls': [
            dict(index=0, **tool_call('update_state', {'target': 'memory', 'text': 123}))
        ]}}]}])
        final = stream_response([{'choices': [{'delta': {'content': 'Please give me a text fact.'}}]}])
        self.app.device.model = self.app.device.resolved_model = 'offline-model'
        with patch('urllib.request.urlopen', side_effect=[first, final]):
            self.app.send(dict(agentId='titan', text='remember'))
            self.wait_idle()
        log = (self.app.root / 'lite.log').read_text()
        self.assertIn('tool refused name=update_state', log)
        self.assertIn('Traceback (most recent call last)', log)
        self.assertEqual(self.app.messages[-1]['text'], 'Please give me a text fact.')
