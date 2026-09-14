"""Speech HTTP contracts without a browser, GUI, or live device."""
import contextlib
import io
import json
import os
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import wave

from lite.voice import pick_models
from tests.test_server import AppCase, wire


def tiny_wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(24000)
        recording.writeframes(b'\0\0' * 24)
    return output.getvalue()


def multipart(filename='recording.webm', data=b'webm recording', name='file'):
    return (f'--speech\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + data + b'\r\n--speech--\r\n'


class ModelPickingTests(unittest.TestCase):
    def test_first_matching_type_or_capability_and_no_name_guessing(self):
        rows = [None, {}, {'id': 12, 'type': 'Speech-to-Text'},
                {'id': '', 'type': 'Text-to-Speech'}, {'id': 'whisper-asr'},
                {'id': 'capability', 'capabilities': ['asr']},
                {'id': 'typed', 'type': 'Speech-to-Text'},
                {'id': 'speaker', 'type': 'Text-to-Speech'},
                {'id': 'later', 'type': 'Text-to-Speech'}]
        self.assertEqual(pick_models(rows), ('capability', 'speaker'))
        self.assertEqual(pick_models(rows[6:]), ('typed', 'speaker'))
        self.assertEqual(pick_models([{'id': 'x', 'capabilities': 'asr'}]), (None, None))
        self.assertEqual(pick_models([]), (None, None))

    def test_a_real_tiiny_answer_picks_both_models(self):
        # Copied from GET /v1/models on a Tiiny running TiinyOS 0.1.34, 2026-09-14, with the
        # chat, speech, speaking, embedding and image models all started. The rows the earlier
        # case uses were written from the docs and no device produces them, which is why voice
        # found no speech model on real firmware until this fixture was taken.
        device = [
            {'id': 'Qwen/Qwen3-8B', 'capabilities': ['main'], 'type': 'Text Generation',
             'supports_chat': True},
            {'id': 'Qwen/Qwen3-ASR-1.7B', 'capabilities': ['audio'], 'type': 'ASR',
             'supports_chat': False},
            {'id': 'Qwen/Qwen3-Embedding-0.6B', 'capabilities': ['embedding'],
             'type': 'Text Embedding'},
            {'id': 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice', 'capabilities': ['voice'],
             'type': 'Text-to-Speech', 'supports_tts': True},
            {'id': 'Tongyi-MAI/Z-Image-Turbo', 'capabilities': ['image'], 'type': 'Text-to-Image'},
        ]
        self.assertEqual(pick_models(device),
                         ('Qwen/Qwen3-ASR-1.7B', 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'))
        # With no speech model started the device stops listing it, and voice stays off
        # rather than pointing at the chat model.
        self.assertEqual(pick_models([r for r in device if r['type'] != 'ASR'])[0], None)


class VoiceTests(AppCase):
    def setUp(self):
        super().setUp()
        self.app.device.model = 'chat-model'
        self.app.device.resolved_model = 'chat-model'
        self.app.settings['voice'].update(enabled=True, mode='push')
        self.models = [{'id': 'ears', 'type': 'Speech-to-Text'},
                       {'id': 'mouth', 'type': 'Text-to-Speech'}]
        self.heard = 'Remember I like tea'
        self.said = 'I will remember that.'
        self.wav = tiny_wav()
        self.calls = []
        self.depth = threading.local()
        self.chat_round = 0
        self.use_tool = False
        self.asr_error = None
        self.tts_error = None
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.addCleanup(self.app.close)
        self.stack.enter_context(patch.object(self.app.device.lane, 'hold', self.hold))
        self.stack.enter_context(patch('urllib.request.urlopen', self.upstream))

    @contextlib.contextmanager
    def hold(self, **kwargs):
        self.assertGreater(kwargs['wait'], 0)
        self.depth.value = getattr(self.depth, 'value', 0) + 1
        try:
            yield
        finally:
            self.depth.value -= 1

    def upstream(self, request, **kwargs):
        self.assertGreater(getattr(self.depth, 'value', 0), 0, 'Device HTTP call bypassed OneLane')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-private-key')
        path = urllib.parse.urlsplit(request.full_url).path
        self.calls.append((path, request))
        if path == '/v1/models':
            result = {'data': self.models}
        elif path == '/v1/audio/transcriptions':
            if self.asr_error:
                raise self.asr_error
            result = {'text': self.heard}
        elif path == '/v1/chat/completions':
            self.chat_round += 1
            if self.use_tool and self.chat_round == 1:
                result = {'choices': [{'message': {'content': None, 'tool_calls': [
                    {'id': 'remember-1', 'type': 'function', 'function': {'name': 'update_state',
                     'arguments': json.dumps({'target': 'profile', 'text': 'I like tea'})}}
                ]}}]}
            else:
                result = {'choices': [{'message': {'content': self.said}}], 'usage': {'total_tokens': 7}}
        elif path == '/v1/audio/speech':
            if self.tts_error:
                raise self.tts_error
            response = io.BytesIO(self.wav)
            response.headers = {'Content-Type': 'audio/wav'}
            return response
        elif path in ('/api/v1/models/mouth/start', '/api/v1/models/mouth/stop'):
            self.assertEqual(request.get_header('Host'), 'p8800.api.tiiny')
            result = {'code': 0}
        else:
            self.fail('Unexpected device request: ' + path)
        response = io.BytesIO(json.dumps(result).encode())
        response.headers = {'Content-Type': 'application/json'}
        return response

    def turn(self, body=None, status=200):
        return self.request('POST', '/api/voice/turn', multipart() if body is None else body,
                            status, {'Content-Type': 'multipart/form-data; boundary=speech'})

    def test_route_transcription_reply_private_wav_and_device_contracts(self):
        result = self.turn()
        self.assertEqual(set(result), {'heard', 'said', 'audio'})
        self.assertEqual((result['heard'], result['said']), (self.heard, self.said))
        status, headers, data = wire(self.app, 'GET', result['audio'])
        self.assertEqual((status, data), (200, self.wav))
        self.assertEqual(headers['Content-Type'], 'audio/wav')
        self.assertEqual(headers['Cache-Control'], 'private, no-store')
        cache = self.app.voice.folder / result['audio'].rsplit('/', 1)[1]
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        asr = next(req for path, req in self.calls if path.endswith('/transcriptions'))
        self.assertIn(b'name="model"\r\n\r\nears', asr.data)
        self.assertIn(b'filename="recording.webm"', asr.data)
        self.assertIn(b'Content-Type: audio/webm', asr.data)
        self.assertIn(b'webm recording', asr.data)
        tts = next(req for path, req in self.calls if path.endswith('/speech'))
        self.assertEqual(json.loads(tts.data), {'model': 'mouth', 'input': self.said})
        self.assertFalse(self.app.voice.busy)
        self.assertFalse(self.app.voice_waiters)

    def test_voice_uses_ordinary_tool_loop_and_persists_spoken_transcript(self):
        self.use_tool = True
        self.turn(multipart('recording.wav', self.wav))
        self.assertEqual(self.chat_round, 2)
        messages = self.request('GET', '/api/transcript?agentId=titan')['messages']
        self.assertEqual(messages[0]['text'], self.heard)
        self.assertTrue(messages[0]['spoken'])
        self.assertEqual(messages[-1]['text'], self.said)
        self.assertEqual(messages[1]['type'], 'system')
        self.assertIn('I like tea', (self.app.root / 'memory/profile.md').read_text())
        saved = json.loads((self.app.root / 'transcripts/main.json').read_text())
        self.assertTrue(saved[0]['spoken'])
        chats = [json.loads(req.data) for path, req in self.calls if path.endswith('/chat/completions')]
        self.assertIn('tools', chats[0])
        self.assertTrue(any(m['role'] == 'tool' for m in chats[1]['messages']))

    def test_settings_model_rows_and_missing_asr_exact_sentence(self):
        self.assertEqual(self.request('GET', '/api/voice/settings'),
                         {'enabled': True, 'mode': 'push', 'asrModel': 'ears', 'ttsModel': 'mouth'})
        self.models = [self.models[1]]
        result = self.turn(status=503)
        self.assertEqual(result['error'], 'Load a speech model on the device first')
        self.assertFalse(self.app.messages)
        self.assertFalse(self.app.voice.busy)

    def test_disabled_voice_and_missing_tts(self):
        self.app.settings['voice']['mode'] = 'off'
        self.turn(status=409)
        self.app.settings['voice']['mode'] = 'push'
        self.models = self.models[:1]
        self.assertIn('no voice model is loaded', self.turn(status=503)['error'])
        self.assertFalse(self.app.messages)

    def test_tts_loaded_once_then_stopped_at_five_idle_minutes(self):
        self.turn()
        self.turn()
        starts = [p for p, _ in self.calls if p.endswith('/start')]
        self.assertEqual(starts, ['/api/v1/models/mouth/start'])
        used = self.app.voice.last_used
        self.app.voice.expire(used + 299)
        self.assertEqual(self.app.voice.loaded, 'mouth')
        self.app.voice.busy = True
        self.app.voice.expire(used + 300)
        self.assertEqual(self.app.voice.loaded, 'mouth')
        self.app.voice.busy = False
        self.app.voice.expire(used + 300)
        self.assertIsNone(self.app.voice.loaded)
        self.app.voice.expire(used + 301)
        self.assertEqual([p for p, _ in self.calls if p.endswith('/stop')], ['/api/v1/models/mouth/stop'])
        self.turn()
        self.assertEqual(len([p for p, _ in self.calls if p.endswith('/start')]), 2)

    def test_next_session_reloads_tts_absent_from_loaded_model_rows(self):
        self.turn()
        self.app.voice.expire(self.app.voice.last_used + 300)
        self.models = self.models[:1]
        result = self.turn()
        self.assertEqual(result['said'], self.said)
        self.assertEqual(len([p for p, _ in self.calls if p.endswith('/start')]), 2)

    def test_cache_expires_on_read_and_maintenance(self):
        result = self.turn()
        path = self.app.voice.folder / result['audio'].rsplit('/', 1)[1]
        now = time.time()
        os.utime(path, (now - 3601, now - 3601))
        self.assertIn('expired', self.request('GET', result['audio'], status=404)['error'])
        self.assertFalse(path.exists())
        old = self.app.voice.folder / ('a' * 32 + '.wav')
        fresh = self.app.voice.folder / ('b' * 32 + '.wav')
        old.write_bytes(self.wav)
        fresh.write_bytes(self.wav)
        os.utime(old, (now - 3600, now - 3600))
        os.utime(fresh, (now - 3599, now - 3599))
        self.app.voice.expire(now)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_private_audio_rejects_traversal_and_symlinks(self):
        alias = self.app.voice.folder / ('a' * 32 + '.wav')
        alias.symlink_to(self.app.root / 'keys.json')
        for suffix in ('../keys.json', 'wrong.wav', alias.name, 'b' * 32 + '.wav'):
            self.request('GET', '/api/voice/say/' + suffix, status=404)
        self.app.voice.expire()
        self.assertFalse(alias.is_symlink())
        self.assertTrue((self.app.root / 'keys.json').exists())

    def test_multipart_requires_one_nonempty_supported_file(self):
        duplicate = multipart().replace(b'--speech--\r\n', b'') + multipart('second.wav')
        for raw in (multipart('recording.mp3'), multipart(data=b''), multipart(name='wrong'),
                    b'--speech--\r\n', duplicate):
            with self.subTest(raw=raw):
                self.turn(raw, status=400)
        self.request('POST', '/api/voice/turn', {}, status=400)
        self.request('POST', '/api/voice/turn', b'x', status=413,
                     headers={'Content-Length': str(10 * 1024 * 1024 + 1)})
        self.assertFalse(self.calls)
        self.assertFalse(list((self.app.root / 'files').iterdir()))

    def test_silence_transport_and_invalid_tts_fail_without_leaking_key(self):
        self.heard = '  '
        self.assertIn('hear', self.turn(status=400)['error'])
        self.assertFalse(self.app.messages)
        self.heard = 'hello'
        self.asr_error = urllib.error.URLError('test-private-key')
        self.turn(status=503)
        self.asr_error = None
        self.wav = b'not a recording'
        self.assertIn('WAV', self.turn(status=502)['error'])
        self.assertFalse(list(self.app.voice.folder.iterdir()))
        self.assertFalse(self.app.voice.busy)

    def test_voice_modes_persist_and_models_are_read_only(self):
        # Budget reads local file URLs; this test's fake handles device HTTP only.
        self.stack.enter_context(patch.object(self.app, 'budget', return_value={}))
        for mode in ('off', 'push', 'always'):
            saved = self.request('PATCH', '/api/settings', {'voice': {'mode': mode}})
            self.assertEqual(saved['voice']['enabled'], mode != 'off')
            self.assertEqual(saved['talkEnabled'], mode != 'off')
            persisted = json.loads((self.app.root / 'settings.json').read_text())
            self.assertEqual(persisted['voice']['mode'], mode)
            self.assertEqual(self.request('GET', '/api/voice/settings')['mode'], mode)
        for body in ({'voice': {'mode': 'unknown'}}, {'voice': {'asrModel': 'other'}},
                     {'voice': {'ttsModel': 'other'}}):
            self.request('PATCH', '/api/settings', body, status=400)

    def test_configuration_change_releases_idle_tts(self):
        self.turn()
        # The audio is already back and the worker may still be extracting memory
        # from the exchange. Step 7a's contract is that a configuration change is
        # not made to wait for that: the extraction keeps the endpoint it started
        # on, so nothing is swapped out from under it, and the new one takes the
        # next turn. tests/test_server.py holds the endpoint half of this.
        started = self.app.device
        self.app.save_config({'name': 'Ada'})
        self.assertIsNot(self.app.device, started)
        self.wait_idle()
        self.assertIsNone(self.app.voice.loaded)
        self.assertIsNone(self.app.voice.tts_model)
        self.assertEqual(self.app.settings['botName'], 'Ada')
        self.assertEqual([p for p, _ in self.calls if p.endswith('/stop')],
                         ['/api/v1/models/mouth/stop'])

    def test_shutdown_releases_tts(self):
        self.turn()
        self.app.close()
        self.assertIsNone(self.app.voice.loaded)
        self.assertEqual([p for p, _ in self.calls if p.endswith('/stop')],
                         ['/api/v1/models/mouth/stop'])

    def test_busy_turn_refuses_before_any_device_request(self):
        self.app.voice.busy = True
        self.turn(status=409)
        self.assertFalse(self.calls)
        self.app.voice.busy = False
