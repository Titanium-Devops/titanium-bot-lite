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
        source = (CONSOLE / 'app.js').read_text()
        original = (VENDOR / 'app.js').read_text()
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
        resources = json.loads((CONSOLE / 'door-resources.json').read_text())
        self.assertLess(first_paint_bytes(), 250_000)
        markup = (CONSOLE / 'index.html').read_text()
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
        markup = (CONSOLE / 'console.html').read_text()
        for identity in ('room-title', 'room-subtitle', 'participant-cluster',
                         'worker-stack', 'context-card', 'transcript'):
            with self.subTest(identity=identity):
                self.assertRegex(markup, rf'id="{identity}"[^>]*></')
        self.assertTrue(markup.startswith('<div id="boot-cover"'))
        boot = (CONSOLE / 'boot-cover.js').read_text()
        self.assertIn('CEILING_MS = 8000', boot)
        self.assertIn('function shouldLiftCover(state)', boot)
        self.assertIn('window.setTimeout(settle, CEILING_MS)', boot)
        self.assertIn('whenDefined("titan-mascot")', boot)

    def test_phone_source_contracts(self):
        markup = (CONSOLE / 'console.html').read_text()
        css = (CONSOLE / 'styles.css').read_text()
        app = (CONSOLE / 'app.js').read_text()
        self.assertIn('viewport-fit=cover', (CONSOLE / 'index.html').read_text())
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

    def test_only_three_plates_and_one_character_ship(self):
        plates = list((CONSOLE / 'assets' / 'backgrounds').glob('*.webp'))
        self.assertEqual(len(plates), 6)
        self.assertEqual(len([p for p in plates if '.thumb.' not in p.name]), 3)
        for path in (CONSOLE / 'assets' / 'characters').iterdir():
            self.assertTrue(path.name.startswith('titan-'))
        self.assertIn('Titan Nebula', (CONSOLE / 'bg-boot.js').read_text())
        loader = (CONSOLE / 'door.js').read_text()
        self.assertLess(loader.index("script('bg-boot.js')"), loader.index("'styles.css'"))

    def test_dropped_modules_are_absent(self):
        for name in ('gateway-adapter.js', 'adapter.js', 'marketplace-bots.js', 'marketplace',
                     'screen-tile.js', 'cloud-browser.js', 'code-tasks.js', 'gap-badge.js',
                     'push-settings.js', 'account-menu.js', 'bot-setup.js', 'components.html'):
            with self.subTest(name=name):
                self.assertFalse((CONSOLE / name).exists())

    @unittest.skipUnless(shutil.which('node'), 'Node is optional; needed for JavaScript syntax checks')
    def test_all_javascript_parses_without_browser(self):
        for path in CONSOLE.rglob('*.js'):
            with self.subTest(file=path.name):
                result = subprocess.run([shutil.which('node'), '--check', str(path)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
