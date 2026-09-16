"""Deterministic clock, queue and HTTP checks. No browser or device required."""
import contextlib
from datetime import datetime
import io
import json
import threading
import time
import unittest
from unittest.mock import patch

from lite import __version__
from lite.cron import Cron
from lite.routines import Scheduler
from lite.server import Refusal, lite_is_running
from tests.test_server import AppCase
from tests.test_agent_tools import tool_call


class CronTests(unittest.TestCase):
    def test_twenty_expressions_and_times(self):
        cases = [
            ('* * * * *', '2026-09-11 09:15', True),
            ('15 9 * * *', '2026-09-11 09:15', True),
            ('15 9 * * *', '2026-09-11 09:16', False),
            ('*/15 * * * *', '2026-09-11 10:45', True),
            ('*/15 * * * *', '2026-09-11 10:46', False),
            ('0 */3 * * *', '2026-09-11 12:00', True),
            ('0 */3 * * *', '2026-09-11 13:00', False),
            ('0 9-17 * * 1-5', '2026-09-11 17:00', True),
            ('0 9-17 * * 1-5', '2026-09-12 09:00', False),
            ('5,20,35 8,10 * * *', '2026-09-11 10:20', True),
            ('5,20,35 8,10 * * *', '2026-09-11 11:20', False),
            ('10-20/5 * * * *', '2026-09-11 10:15', True),
            ('10-20/5 * * * *', '2026-09-11 10:16', False),
            ('0 0 29 2 *', '2028-02-29 00:00', True),
            ('0 0 29 2 *', '2028-02-28 00:00', False),
            ('0 0 * * 0', '2026-09-13 00:00', True),
            ('0 0 * * 7', '2026-09-13 00:00', True),
            ('0 0 1 * 5', '2026-09-11 00:00', True),
            ('0 0 1 * 5', '2026-10-01 00:00', True),
            ('0 0 * 1,6-9 *', '2026-10-01 00:00', False),
        ]
        for expression, wall, expected in cases:
            with self.subTest(expression=expression, wall=wall):
                self.assertEqual(Cron(expression).matches(datetime.fromisoformat(wall)), expected)

    def test_next_run_calendar_and_strict_boundary(self):
        stamp = datetime(2026, 9, 11, 9, 15).timestamp()
        self.assertEqual(Cron('*/15 * * * *').next_after(stamp), stamp + 900)
        self.assertEqual(datetime.fromtimestamp(Cron('0 0 29 2 *').next_after(stamp)), datetime(2028, 2, 29))
        self.assertIsNone(Cron('0 0 31 2 *').next_after(stamp))
        for expression in ('weekly', '* * * *', '60 * * * *', '*/0 * * * *', '1-0 * * * *', '1,,2 * * * *'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                Cron(expression)


class RoutineTests(AppCase):
    def create(self, enabled=True):
        self.app.update_state(dict(target='routine', action='create', name='Morning notes', prompt='Review notes', schedule='* * * * *', enabled=True))
        path = list((self.app.root / 'routines').glob('*/routine.json'))[-1]
        ident = path.parent.name
        self.assertFalse(json.loads(path.read_text(encoding='utf-8'))['enabled'])
        if enabled:
            self.app.update_state(dict(target='routine', action='enable', id=ident))
        return ident, path

    def due(self, ident):
        signature, _ = self.app.scheduler.next_runs[ident]
        due = int(time.time() // 60) * 60
        self.app.scheduler.next_runs[ident] = (signature, due)
        return due

    def test_due_once_transcript_and_tool_loop(self):
        ident, path = self.create()
        calls = []
        def chat(messages, emit, **options):
            calls.append(messages.copy())
            if len(calls) == 1:
                return {'total_tokens': 1, '_message': {'tool_calls': [tool_call('Write', {'path': 'routine.txt', 'content': 'scheduled'})]}}
            emit('Notes reviewed')
            return {'total_tokens': 1, '_message': {'content': 'Notes reviewed'}}
        due = self.due(ident)
        with patch.object(self.app.device, 'chat', side_effect=chat):
            self.app.scheduler.tick(due + 1)
            self.app.scheduler.tick(due + 2)
            self.wait_idle()
        runs = json.loads((path.parent / 'runs.json').read_text(encoding='utf-8'))
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['status'], 'ok')
        self.assertGreaterEqual(runs[0]['finishedAt'], runs[0]['startedAt'])
        transcript = self.request('GET', '/api/transcript?agentId=routine-' + ident)['messages']
        self.assertEqual(transcript[0]['conversationName'], 'Morning notes')
        self.assertEqual(transcript[-1]['text'], 'Notes reviewed')
        self.assertTrue(any('toolCallId' in m for m in transcript))
        self.assertEqual(self.app.messages, [])
        self.assertEqual((self.app.root / 'files/routine.txt').read_text(encoding='utf-8'), 'scheduled')

    def test_disabled_never_runs_and_missed_run_is_skipped(self):
        ident, path = self.create(False)
        self.app.scheduler.tick(time.time() + 120)
        self.wait_idle()
        self.assertEqual(json.loads((path.parent / 'runs.json').read_text(encoding='utf-8')), [])
        self.app.update_state(dict(target='routine', action='resume', id=ident))
        due = self.due(ident)
        self.app.scheduler.tick(due + 120)
        self.wait_idle()
        self.assertEqual(json.loads((path.parent / 'runs.json').read_text(encoding='utf-8')), [])
        # Restart disregards the stored last run, even if it was days ago.
        item = json.loads(path.read_text(encoding='utf-8'))
        item['lastRunAt'] = 1
        path.write_text(json.dumps(item), encoding='utf-8')
        fresh = Scheduler(self.app)
        self.assertGreater(fresh.next_runs[ident][1], time.time())

    def test_pause_enable_delete_console_routes(self):
        ident, path = self.create(False)
        for verb, expected in [('enable', True), ('pause', False), ('enable', True), ('disable', False)]:
            result = self.request('POST', '/api/library', dict(kind='routine', verb=verb, id=ident))
            self.assertEqual(result['library']['routines'][0]['enabled'], expected)
            self.assertEqual(result['library']['routines'][0]['nextRunAt'] is not None, expected)
        self.request('POST', '/api/library', dict(kind='routine', verb='delete', id=ident))
        self.assertFalse(path.exists())
        self.assertFalse((path.parent / 'runs.json').exists())

    def test_error_history_and_worker_survives(self):
        ident, path = self.create()
        due = self.due(ident)
        with patch.object(self.app.device, 'chat', side_effect=Refusal('Device unavailable')):
            self.app.scheduler.tick(due + 1)
            self.wait_idle()
        run = json.loads((path.parent / 'runs.json').read_text(encoding='utf-8'))[0]
        self.assertEqual((run['status'], run['detail']), ('error', 'Device unavailable'))
        self.app.send(dict(agentId='titan', text='hello'))
        self.wait_idle()
        self.assertEqual(self.app.messages[-1]['text'], 'olleh')

    def test_pause_queued_routine_and_no_overlapping_turns(self):
        ident, path = self.create()
        entered, release = threading.Event(), threading.Event()
        def chat(messages, emit, **options):
            entered.set()
            release.wait(2)
            emit('finished')
            return {'total_tokens': 0}
        with patch.object(self.app.device, 'chat', side_effect=chat) as mock:
            self.app.send(dict(agentId='titan', text='busy'))
            self.assertTrue(entered.wait(1))
            due = self.due(ident)
            self.app.scheduler.tick(due + 1)
            self.assertEqual(mock.call_count, 1)
            self.app.update_state(dict(target='routine', action='pause', id=ident))
            release.set()
            self.wait_idle()
            self.assertEqual(mock.call_count, 1)
        self.assertEqual(json.loads((path.parent / 'runs.json').read_text(encoding='utf-8')), [])

    def test_health_identity_and_probe(self):
        payload = self.request('GET', '/api/health')
        self.assertEqual(payload, dict(app='titanium-bot-lite', version=__version__))
        for value, expected in [(payload, True), ({'version': __version__}, False), (dict(payload, version='wrong'), False)]:
            def response(*args, **kwargs):
                obj = io.BytesIO(json.dumps(value).encode())
                obj.status = 200
                return obj
            with patch('urllib.request.OpenerDirector.open', side_effect=response):
                self.assertEqual(lite_is_running(8123), expected)

    def test_history_cap_started_status_and_device_lane(self):
        ident, path = self.create()
        runs_path = path.parent / 'runs.json'
        runs_path.write_text(json.dumps([dict(id=str(i), status='ok') for i in range(20)]), encoding='utf-8')
        def response(*args, **kwargs):
            running = json.loads(runs_path.read_text(encoding='utf-8'))
            self.assertEqual(len(running), 20)
            self.assertEqual(running[-1]['status'], 'running')
            self.assertIsNone(running[-1]['finishedAt'])
            obj = io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Scheduled answer'}}], 'usage': {'total_tokens': 2}}).encode())
            obj.headers = {'Content-Type': 'application/json'}
            return obj
        self.app.device.model = self.app.device.resolved_model = 'offline-model'
        with patch.object(self.app.device.lane, 'hold', side_effect=lambda **kw: contextlib.nullcontext()) as lane, patch('urllib.request.urlopen', side_effect=response):
            self.app.scheduler.tick(self.due(ident) + 1)
            self.wait_idle()
        lane.assert_called_once()
        runs = json.loads(runs_path.read_text(encoding='utf-8'))
        self.assertEqual(len(runs), 20)
        self.assertEqual(runs[0]['id'], '1')
        self.assertEqual(runs[-1]['status'], 'ok')

    def test_creation_notice_and_same_turn_enable_refusal(self):
        calls = []
        def chat(messages, emit, **options):
            calls.append(1)
            if len(calls) == 1:
                return {'_message': {'tool_calls': [tool_call('update_state', dict(target='routine', action='create', name='Draft', prompt='hi', schedule='* * * * *', enabled=True))]}}
            if len(calls) == 2:
                ident = self.app.library()['routines'][0]['id']
                return {'_message': {'tool_calls': [tool_call('update_state', dict(target='routine', action='resume', id=ident), 'call-2')]}}
            self.assertIn('owner must enable', messages[-1]['content'])
            emit('Saved.')
            return {'_message': {'content': 'Saved.'}}
        with patch.object(self.app.device, 'chat', side_effect=chat):
            self.app.send(dict(agentId='titan', text='Save a routine'))
            self.wait_idle()
        self.assertFalse(self.app.library()['routines'][0]['enabled'])
        self.assertIn('switched off until you enable', self.app.messages[-1]['text'])

    def test_bad_routine_does_not_stop_scheduler(self):
        ident, _ = self.create()
        broken = self.app.root / 'routines/broken'
        broken.mkdir()
        (broken / 'routine.json').write_text('{', encoding='utf-8')
        self.app.scheduler.tick(self.due(ident) + 1)
        self.wait_idle()
        self.assertEqual(len(self.app.library()['routines']), 1)
        self.assertTrue(self.app.worker.is_alive())
