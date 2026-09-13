"""Device speech turns and a short-lived, private WAV cache."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def pick_models(rows):
    valid = [r for r in rows if isinstance(r, dict) and isinstance(r.get('id'), str) and r['id']]
    asr = next((r['id'] for r in valid if r.get('type') == 'Speech-to-Text' or
                isinstance(r.get('capabilities'), list) and 'asr' in r['capabilities']), None)
    tts = next((r['id'] for r in valid if r.get('type') == 'Text-to-Speech'), None)
    return asr, tts


class Voice:
    def __init__(self, app):
        self.app = app
        self.folder = app.root / 'voice'
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.lock = threading.Lock()
        self.loaded = None
        self.tts_model = None
        self.last_used = 0
        self.busy = False
        self.thread = threading.Thread(target=self._maintain, name='Voice expiry', daemon=True)
        self.thread.start()

    def settings(self):
        asr, tts = pick_models(self.app.device.request('/models').get('data', []))
        tts = tts or self.tts_model
        mode = self.app.settings['voice'].get('mode', 'off')
        return dict(enabled=mode != 'off', mode=mode, asrModel=asr, ttsModel=tts)

    def request(self, path, data, content_type='application/json', lifecycle=False):
        from .server import Refusal
        device = self.app.device
        headers = {'Authorization': 'Bearer ' + device.key, 'Content-Type': content_type}
        url = device.base + path
        if lifecycle:
            # Model start and stop are management routes, so they hang off the
            # device root rather than the /v1 model base.
            parsed = urllib.parse.urlsplit(device.base)
            url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))
            # On 1.0 firmware every service shares port 80 and nginx picks one out
            # of the Host header, so name the one we want. On older firmware the
            # gateway has a port of its own and the header means nothing there, so
            # sending it pointed these calls at the wrong service. It also used to
            # be sent with the vhost default base, which resolved to the TiinyOS
            # proxy and answered 502.
            if parsed.port in (None, 80):
                headers['Host'] = 'p8800.api.tiiny'
        try:
            with device.lane.hold(why='Titan voice', wait=90):
                with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as response:
                    raw = response.read()
                    if 'json' in response.headers.get('Content-Type', ''):
                        value = json.loads(raw)
                        if value.get('error') or value.get('code', 0) not in (0, 200):
                            raise Refusal('The device could not finish the speech request.', 503)
                    return raw
        except (urllib.error.URLError, OSError, TimeoutError):
            raise Refusal('The device could not finish the speech request. Please try again.', 503) from None

    def lifecycle(self, model, action):
        return self.request('/api/v1/models/' + urllib.parse.quote(model, safe='') + '/' + action,
                            b'{}', lifecycle=True)

    def expire(self, now=None):
        now = time.time() if now is None else now
        for path in self.folder.glob('*.wav'):
            if path.is_symlink() or now - path.stat().st_mtime >= 3600:
                path.unlink(missing_ok=True)
        with self.lock:
            if self.loaded and not self.busy and now - self.last_used >= 300:
                self.lifecycle(self.loaded, 'stop')
                self.loaded = None

    def close(self):
        with self.lock:
            if self.loaded and not self.busy:
                try:
                    self.lifecycle(self.loaded, 'stop')
                    self.loaded = None
                except Exception:
                    self.app.device.log.exception('Voice model release failed')

    def _maintain(self):
        while not self.app.stopping.wait(1):
            try:
                self.expire()
            except Exception:
                self.app.device.log.exception('Voice maintenance failed')

    def audio(self, name):
        from .server import Refusal
        if not re.fullmatch(r'[a-f0-9]{32}\.wav', name):
            raise Refusal('That recording was not found.', 404)
        path = self.folder / name
        if path.is_symlink() or not path.is_file():
            raise Refusal('That recording was not found.', 404)
        if time.time() - path.stat().st_mtime >= 3600:
            path.unlink(missing_ok=True)
            raise Refusal('That recording has expired.', 404)
        return path.read_bytes()

    def turn(self, audio):
        from .server import Refusal
        with self.app.lock, self.lock:
            if self.busy:
                raise Refusal('Wait for Titan to finish speaking.', 409)
            self.busy = True
        try:
            settings = self.settings()
            if not settings['enabled']:
                raise Refusal('Voice is switched off in Settings.', 409)
            asr, tts = settings['asrModel'], settings['ttsModel']
            if not asr:
                raise Refusal('Load a speech model on the device first', 503)
            if not tts:
                raise Refusal('Load a text-to-speech model on the device first', 503)
            boundary = uuid.uuid4().hex
            raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{asr}\r\n'
                   f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="recording{audio["suffix"]}"\r\n'
                   f'Content-Type: {audio["mime"]}\r\n\r\n').encode() + audio['data'] + f'\r\n--{boundary}--\r\n'.encode()
            heard = json.loads(self.request('/audio/transcriptions', raw, 'multipart/form-data; boundary=' + boundary)).get('text', '')
            if not isinstance(heard, str) or not heard.strip():
                raise Refusal('I could not hear any words. Please try again.')
            done = threading.Event()
            result = {}
            with self.app.lock:
                sent = self.app.send(dict(agentId='titan', text=heard), spoken=True)['message']
                self.app.voice_waiters[sent['id']] = (done, result)
            while not done.wait(.2):
                if self.app.stopping.is_set():
                    raise Refusal('The server is stopping.', 503)
            if result.get('type') != 'text':
                raise Refusal(result.get('text', 'Titan could not finish this reply.'), 503)
            said = result['text']
            with self.lock:
                if self.loaded != tts:
                    if self.loaded:
                        self.lifecycle(self.loaded, 'stop')
                        self.loaded = None
                    self.lifecycle(tts, 'start')
                    self.loaded = tts
                    self.tts_model = tts
            wav = self.request('/audio/speech', json.dumps(dict(model=tts, input=said)).encode())
            if not (wav.startswith(b'RIFF') and wav[8:12] == b'WAVE'):
                raise Refusal('The device did not return a WAV recording.', 502)
            name = uuid.uuid4().hex + '.wav'
            path = self.folder / name
            with path.open('xb') as output:
                output.write(wav)
            path.chmod(0o600)
            return dict(heard=heard.strip(), said=said, audio='/api/voice/say/' + name)
        finally:
            with self.lock:
                self.last_used = time.time()
                self.busy = False
            if self.app.stopping.is_set():
                self.close()
