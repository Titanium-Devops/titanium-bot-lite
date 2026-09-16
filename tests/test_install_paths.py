"""The two ways in: the farm archive and the pip package. No network in either test."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import tomllib
import unittest

import lite

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / 'scripts/release.py'))['build_release']
IDENT = 'titanium-tiiny-bot'


def find_farm():
    """The farm is a separate project, so its tests run only where a checkout is present."""
    import os
    candidates = [os.environ.get('FARM_REPO'), ROOT.parent / 'tiinyapp-farm']
    for candidate in candidates:
        if candidate and (Path(candidate) / 'farm' / 'farm.py').is_file():
            return Path(candidate)
    return None


def catalog_manifest(version, archive):
    """The fields farm.validate_manifest consumes, matching the published manifest."""
    return {
        'id': IDENT, 'name': 'Titanium Tiiny Bot', 'version': version,
        'pitch': 'A local assistant with chat, files, memories and voice.',
        'description': 'Runs beside your Tiiny on Mac or Linux.',
        'entry': {'python': 'lite', 'args': ['--port', '7788']},
        'requires': {'python': '3.11', 'ports': [7788],
                     'device': {'models': ['chat', 'tts'], 'npuUnits': 57}},
        'permissions': ['microphone', 'files', 'network', 'device'],
        'health': '/api/health', 'selfcheck': True,
        'release': {'url': archive.name,
                    'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                    'size': archive.stat().st_size},
    }


@unittest.skipIf(find_farm() is None, 'no tiinyapp-farm checkout; set FARM_REPO to run this')
class FarmInstallTests(unittest.TestCase):
    """README tells an owner that farm update preserves data. This is that sentence, measured."""

    @classmethod
    def setUpClass(cls):
        repo = find_farm()
        sys.path.insert(0, str(repo))
        cls.addClassCleanup(sys.path.remove, str(repo))
        from farm import farm
        cls.farm_module = farm

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='lite-farm-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home'
        self.catalog = Path(temporary.name) / 'catalog'
        self.catalog.mkdir(parents=True)
        with contextlib.redirect_stdout(io.StringIO()):
            built, _ = BUILD(ROOT)
        self.archive = self.catalog / built.name
        shutil.copyfile(built, self.archive)
        self.version = (ROOT / 'lite/VERSION').read_text(encoding='utf-8').strip()
        major, minor, patch = self.version.split('.')
        self.next_version = f'{major}.{minor}.{int(patch) + 1}'
        self.write_catalog(self.version)
        # home is also config_home, so no real ~/.tiinyapps file is read or written.
        self.client = self.farm_module.Farm(home=self.home, catalog=str(self.catalog))

    def write_catalog(self, version):
        (self.catalog / (IDENT + '.json')).write_text(
            json.dumps(catalog_manifest(version, self.archive), indent=2), encoding='utf-8')

    def run_quietly(self, call, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            call(*args, **kwargs)
        return output.getvalue()

    def test_update_keeps_the_owners_data_and_moves_the_version(self):
        self.run_quietly(self.client.install, IDENT, yes=True)
        app = self.home / IDENT
        self.assertEqual((app / 'current').read_text(encoding='utf-8').strip(), self.version)
        self.assertTrue((app / self.version / 'lite' / '__main__.py').is_file())

        # Whatever the owner has said to Titan lives here, beside the installed version.
        keys = app / 'data' / 'keys.json'
        keys.parent.mkdir(exist_ok=True)
        keys.write_text('{"key": "the owner key"}', encoding='utf-8')
        (app / 'data' / 'transcripts').mkdir()
        (app / 'data' / 'transcripts' / 'titan.jsonl').write_text('{"text": "hello"}\n', encoding='utf-8')

        self.write_catalog(self.next_version)
        self.run_quietly(self.client.install, IDENT, yes=True, update=True)

        self.assertEqual((app / 'current').read_text(encoding='utf-8').strip(), self.next_version)
        self.assertEqual(keys.read_text(encoding='utf-8'), '{"key": "the owner key"}')
        self.assertEqual((app / 'data' / 'transcripts' / 'titan.jsonl').read_text(encoding='utf-8'), '{"text": "hello"}\n')
        self.assertTrue((app / self.next_version / 'lite' / 'VERSION').is_file())

    def test_update_refuses_to_go_backwards(self):
        self.run_quietly(self.client.install, IDENT, yes=True)
        self.write_catalog('0.0.1')
        self.assertIn('up to date', self.run_quietly(self.client.install, IDENT, yes=True, update=True))
        self.assertEqual((self.home / IDENT / 'current').read_text(encoding='utf-8').strip(), self.version)

    def test_the_published_archive_is_what_the_installer_accepts(self):
        # The checksum and size in the manifest are the ones release.py produces, and the
        # installer refuses a mismatch rather than running unverified bytes.
        manifest = catalog_manifest(self.version, self.archive)
        self.assertEqual(len(manifest['release']['sha256']), 64)
        broken = dict(manifest['release'], sha256='0' * 64)
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaisesRegex(self.farm_module.FarmError, 'Checksum mismatch'):
                self.client.download(broken, Path(scratch) / 'release.tar')


class PipPackageTests(unittest.TestCase):
    """SPEC.md step 6 promises pip install titanium-bot-lite. These are its terms."""

    @classmethod
    def setUpClass(cls):
        cls.pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))

    def test_one_version_source_and_a_console_script_that_cannot_collide(self):
        project = self.pyproject['project']
        self.assertEqual(project['name'], 'titanium-bot-lite')
        self.assertIn('version', project['dynamic'])
        self.assertEqual(self.pyproject['tool']['setuptools']['dynamic']['version'],
                         {'file': 'lite/VERSION'})
        self.assertEqual(project['requires-python'], '>=3.11')
        self.assertEqual(project['dependencies'], [])
        scripts = project['scripts']
        self.assertEqual(scripts, {'titanbot-lite': 'lite.server:main'})
        # The official Tiiny CLI and the unrelated tiiny-sdk package both install "tiiny".
        for name in scripts:
            self.assertFalse(name == 'tiiny' or name.startswith('tiiny-'), name)

    def test_the_wheel_carries_the_console_and_none_of_the_excluded_trees(self):
        try:
            from setuptools import build_meta
        except ImportError:  # pragma: no cover - setuptools ships with every supported Python
            self.skipTest('setuptools is not importable')
        import zipfile
        with tempfile.TemporaryDirectory(prefix='lite-wheel-') as scratch:
            source = Path(scratch) / 'source'
            source.mkdir()
            for name in ('lite', 'brand'):
                shutil.copytree(ROOT / name, source / name,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'data'))
            for name in ('README.md', 'LICENSE', 'pyproject.toml', 'MANIFEST.in'):
                shutil.copyfile(ROOT / name, source / name)
            output = Path(scratch) / 'dist'
            output.mkdir()
            cwd = Path.cwd()
            try:
                import os
                os.chdir(source)
                with contextlib.redirect_stdout(io.StringIO()):
                    wheel = build_meta.build_wheel(str(output))
            finally:
                os.chdir(cwd)
            names = zipfile.ZipFile(output / wheel).namelist()
        self.assertIn('lite/VERSION', names)
        self.assertIn('lite/tools.json', names)
        self.assertIn('lite/console/console.html', names)
        self.assertIn('lite/console/styles.css', names)
        self.assertIn('lite/seeds/persona.md', names)
        self.assertIn('lite/console/brand/tiiny-logo.svg', names)
        self.assertTrue(wheel.startswith(f'titanium_bot_lite-{lite.__version__}-'), wheel)
        for name in names:
            self.assertFalse(set(Path(name).parts) & {'vendor', 'tests', '__pycache__'}, name)
            self.assertFalse(name.endswith(('.pyc', '.pyo')), name)
            self.assertFalse(name.startswith('lite/data/'), name)

    def test_the_readme_documents_one_install_section(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertEqual(readme.count('\n## Install Titan\n'), 1)
        for heading in ('## Install with farm', '## Run it in ten minutes'):
            self.assertNotIn(heading, readme)
        # The hedge the audit named: no install path may be documented as not yet published.
        self.assertNotIn('Once the farm release is published', readme)
        self.assertIn('pip install titanium-bot-lite', readme)
        self.assertIn('farm install titanium-tiiny-bot', readme)


if __name__ == '__main__':
    unittest.main()
