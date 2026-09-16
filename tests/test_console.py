"""Console source contracts without launching a browser or a GUI."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from lite.server import first_paint_bytes

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'lite' / 'console'
VENDOR = ROOT / 'vendor' / 'machine-room'


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.items = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


class ConsoleContractTests(unittest.TestCase):
    def test_tiiny_watermark_once_per_page_with_inline_sizes(self):
        for page, sizes in (
            ('console.html', {'width': '40vw', 'max-width': '520px',
                              'min-width': '220px', 'height': 'auto'}),
            ('index.html', {'width': '24vw', 'height': 'auto'}),
        ):
            with self.subTest(page=page):
                marks = [(tag, attrs) for tag, attrs in
                         Elements((CONSOLE / page).read_text(encoding='utf-8')).items
                         if 'tiiny-watermark' in attrs.get('class', '').split()]
                self.assertEqual(len(marks), 1)
                tag, attrs = marks[0]
                self.assertEqual(tag, 'img')
                self.assertEqual(attrs['src'], 'brand/tiiny-logo.svg')
                self.assertEqual(attrs['alt'], '')
                self.assertEqual(attrs['aria-hidden'], 'true')
                declarations = dict(part.strip().split(':', 1) for part in
                                    attrs['style'].split(';') if part.strip())
                self.assertEqual({key.strip(): value.strip() for key, value in
                                  declarations.items()}, sizes)

    def test_unchanged_ports_match_vendor(self):
        for name in ('tokens.css', 'motion.css', 'backgrounds.css', 'mascots.css',
                     'boot.css', 'settings.css', 'files-viewer.css', 'voice-call.css',
                     'mascots.js', 'voice-call-avatar.js'):
            with self.subTest(file=name):
                self.assertEqual((CONSOLE / name).read_bytes(), (VENDOR / name).read_bytes())

    def test_mascot_kit_and_sprites_match_brand_assets(self):
        for name in ('titan-mascot.js', 'characters/titan-curious.png',
                     'characters/titan-calm.png', 'characters/titan-excited.png'):
            with self.subTest(asset=name):
                self.assertEqual((CONSOLE / 'assets' / name).read_bytes(),
                                 (ROOT / 'assets' / 'console' / name).read_bytes())

    def test_named_renderer_ports_preserve_code_chips(self):
        source = (CONSOLE / 'app.js').read_text(encoding='utf-8')
        original = (VENDOR / 'app.js').read_text(encoding='utf-8')
        for start, end in (('  function inlineMarkup(', '  function paragraphMarkup('),
                           ('  function foldRepeatedRows(', '  function messageMarkup(')):
            with self.subTest(function=start):
                self.assertEqual(source[source.index(start):source.index(end)].strip(),
                                 original[original.index(start):original.index(end)].strip())
        self.assertIn('document.execCommand("copy")', source)
        self.assertIn('message.spoken', source)
        self.assertNotIn('__gapBadge', source)
        self.assertNotIn('withFoldedReportRows', source)
        self.assertNotIn('evidenceChipMarkup', source)

    def test_door_is_small_and_defers_console(self):
        resources = json.loads((CONSOLE / 'door-resources.json').read_text(encoding='utf-8'))
        self.assertLess(first_paint_bytes(), 250_000)
        markup = (CONSOLE / 'index.html').read_text(encoding='utf-8')
        nodes = Elements(markup).items
        referenced = {attrs['src'] for _, attrs in nodes if 'src' in attrs}
        referenced.update(attrs['href'] for tag, attrs in nodes if tag == 'link')
        self.assertEqual(set(resources), referenced | {'index.html'})
        self.assertNotIn('app.js', referenced)
        self.assertNotIn('assets/titan-mascot.js', referenced)
        self.assertIn('Brought to you by Titanium Bot', markup)
        self.assertIn('https://titanium.bot', markup)
        self.assertIn('brand/ti-mark.svg', markup)

    def test_empty_conversation_shell_and_boot_ceiling(self):
        markup = (CONSOLE / 'console.html').read_text(encoding='utf-8')
        for identity in ('room-title', 'room-subtitle', 'participant-cluster',
                         'worker-stack', 'context-card', 'transcript'):
            with self.subTest(identity=identity):
                self.assertRegex(markup, rf'id="{identity}"[^>]*></')
        self.assertTrue(markup.startswith('<div id="boot-cover"'))
        boot = (CONSOLE / 'boot-cover.js').read_text(encoding='utf-8')
        self.assertIn('CEILING_MS = 8000', boot)
        self.assertIn('function shouldLiftCover(state)', boot)
        self.assertIn('window.setTimeout(settle, CEILING_MS)', boot)
        self.assertIn('whenDefined("titan-mascot")', boot)

    def test_phone_source_contracts(self):
        markup = (CONSOLE / 'console.html').read_text(encoding='utf-8')
        css = (CONSOLE / 'styles.css').read_text(encoding='utf-8')
        app = (CONSOLE / 'app.js').read_text(encoding='utf-8')
        self.assertIn('viewport-fit=cover', (CONSOLE / 'index.html').read_text(encoding='utf-8'))
        self.assertLess(markup.index('id="drawer-scrim"'), markup.index('</main>'))
        self.assertIn('data-talk-button', markup)
        self.assertIn('COMPOSER_MAX_LINES = 8', app)
        self.assertIn('KEYBOARD_COMPOSER_LINES = 3', app)
        self.assertIn('if (jumpNewest.hidden === !wanted) return;', app)
        self.assertIn('if (event.isComposing || event.keyCode === 229) return;', app)
        for inset in ('--sat', '--sab', '--sal', '--sar'):
            self.assertIn(inset, css)
        self.assertNotIn('id="composer-aside"', markup)
        self.assertNotIn('id="workspace-list"', markup)

    def test_the_forty_four_pixel_floor_holds_at_every_width(self):
        css = (CONSOLE / 'styles.css').read_text(encoding='utf-8')
        block = css[css.index('/* Lite: the 44 by 44 floor'):]
        floor = block[block.index('*/') + 2:]
        self.assertIn('composer textarea is left alone', block)
        # Outside a media query, so a desktop mouse gets the same targets a finger does.
        self.assertNotIn('@media', floor)
        for control in ('.icon-button', '.dialog-close', '.composer-plus', '.voice-talk', '.send-button'):
            self.assertIn(control, floor)
        self.assertIn('min-width: 44px;', floor)
        self.assertIn('min-height: 44px;', floor)
        # The composer textarea is the named exception: docs/console-pieces.md section 2 keeps
        # its box free of padding and border so scrollHeight is the text's height, and the
        # eight-line cap reads that. A floor on this box makes the cap wrong.
        self.assertNotIn('#message-input', floor)
        self.assertNotIn('textarea', floor)

    def test_only_three_plates_and_one_character_ship(self):
        plates = list((CONSOLE / 'assets' / 'backgrounds').glob('*.webp'))
        self.assertEqual(len(plates), 6)
        self.assertEqual(len([p for p in plates if '.thumb.' not in p.name]), 3)
        for path in (CONSOLE / 'assets' / 'characters').iterdir():
            self.assertTrue(path.name.startswith('titan-'))
        self.assertIn('Titan Nebula', (CONSOLE / 'bg-boot.js').read_text(encoding='utf-8'))
        loader = (CONSOLE / 'door.js').read_text(encoding='utf-8')
        self.assertLess(loader.index("script('bg-boot.js')"), loader.index("'styles.css'"))

    def test_talking_is_loaded_and_app_does_not_stand_in_front_of_it(self):
        loader = (CONSOLE / 'door.js').read_text(encoding='utf-8')
        for name in ('voice.js', 'voice-call-avatar.js'):
            with self.subTest(file=name):
                self.assertIn(f"'{name}'", loader)
                self.assertLess(loader.index(f"'{name}'"), loader.index("'app.js'"))
        app = (CONSOLE / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn('Voice is not connected yet', app)
        self.assertNotIn("getElementById('voice-talk').addEventListener", app)

    def test_every_file_row_reaches_the_one_viewer(self):
        app = (CONSOLE / 'app.js').read_text(encoding='utf-8')
        self.assertIn("closest?.('[data-attachment-open]')", app)
        self.assertIn('viewer.open({path:row.dataset.attachmentOpen', app)
        # The kind comes off the path, so a skill filed under its frontmatter name still opens as
        # the markdown in its SKILL.md rather than as a download.
        self.assertIn('const kind = kindFor(path);', (CONSOLE / 'files-viewer.js').read_text(encoding='utf-8'))

    def test_general_offers_a_microphone_when_the_browser_can_name_one(self):
        settings = (CONSOLE / 'settings.js').read_text(encoding='utf-8')
        # Drawn only when voice.js says the browser can enumerate, which is the surface's own rule:
        # a fact the machine could not answer omits its row instead of showing an empty control.
        self.assertIn('global.__voice?.supportsMicChoice?row(\'Microphone\'', settings)
        self.assertIn('data-setting="micDeviceId"', settings)
        self.assertIn('async function fillMicrophones(host,ticket)', settings)
        self.assertIn("d.kind==='audioinput'&&d.deviceId&&d.deviceId!=='default'", settings)
        # The choice has to reach the module that opens the stream, not only the settings file.
        self.assertIn("global.__voice?.setMicDeviceId?.(", settings)

    def test_model_page_starts_stops_and_asks_for_a_key_in_one_masked_box(self):
        settings = (CONSOLE / 'settings.js').read_text(encoding='utf-8')
        # A press on a device model reaches route 7 with that model's id.
        self.assertIn("modelButton(entry.running?'stop':'start'", settings)
        self.assertIn('data-model-id="${esc(entry.id)}"', settings)
        # The credential box is masked, starts empty and is never written into.
        self.assertIn('<input type="password" data-endpoint-key', settings)
        self.assertIn("autocomplete=\"off\" value=\"\"", settings)
        self.assertNotIn('apiKey:facts', settings)
        self.assertNotIn('facts.apiKey', settings)
        # Only a typed key is sent, so an empty box keeps the one already saved.
        self.assertIn('if(key)body.apiKey=key;', settings)
        # The way back to the device, and what the device is doing now.
        self.assertIn("body={action:'use',source:'device'}", settings)
        self.assertIn('data-live-source', settings)
        self.assertNotIn('not available yet', settings)

    def test_dropped_modules_are_absent(self):
        for name in ('gateway-adapter.js', 'adapter.js', 'marketplace-bots.js', 'marketplace',
                     'screen-tile.js', 'cloud-browser.js', 'code-tasks.js', 'gap-badge.js',
                     'push-settings.js', 'account-menu.js', 'bot-setup.js', 'components.html'):
            with self.subTest(name=name):
                self.assertFalse((CONSOLE / name).exists())

    @unittest.skipUnless(shutil.which('node'), 'Node is optional; needed for JavaScript syntax checks')
    def test_voice_transport_without_browser(self):
        result = subprocess.run([shutil.which('node'), 'tests/voice-contract.cjs'],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is optional; needed for JavaScript syntax checks')
    def test_all_javascript_parses_without_browser(self):
        for path in CONSOLE.rglob('*.js'):
            with self.subTest(file=path.name):
                result = subprocess.run([shutil.which('node'), '--check', str(path)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
