"""First-run setup and owner-controlled persona contracts, without a GUI."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os

from lite.server import App, PERSONA, build_prompt, read_skills


class SeedTests(unittest.TestCase):
    def test_first_run_greeting_seeds_and_owner_edits_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {'TIINY_MODEL': 'echo', 'TIINY_KEY': '', 'ONELANE_DIR': str(root / '.lane'),
                                       'TIINY_BASE': 'http://192.0.2.10/v1'}):
                app = App(root)
                try:
                    self.assertEqual((root / 'persona.md').read_text(encoding='utf-8'), PERSONA)
                    self.assertEqual(len(app.messages), 1)
                    self.assertIn('What should I call you?', app.messages[0]['text'])
                    self.assertIn('your assistant', app.messages[0]['text'])
                    skills = read_skills(root)
                    self.assertEqual({s['name'] for s in skills}, {'handbook-never-ask', 'handbook-plain-words', 'handbook-what-i-can-do', 'onboarding'})
                    for skill in skills:
                        self.assertEqual(skill['id'], skill['name'])
                        self.assertNotIn('save_onboarding_answer', skill['body'])
                        self.assertNotIn('finish_onboarding', skill['body'])
                    self.assertIn('BEFORE', PERSONA)
                    self.assertIn('I never ask anybody to type a password', PERSONA)
                    app.patch_settings({'persona': 'Owner edited this persona.'})
                    (root / 'skills/onboarding/SKILL.md').write_text('owner custom skill', encoding='utf-8')
                    self.assertIn('Owner edited this persona.', build_prompt(root))
                    transcript = app.messages.copy()
                finally:
                    app.close()
                app = App(root)
                try:
                    self.assertEqual(app.messages, transcript)
                    self.assertEqual(app.get_settings()['persona'], 'Owner edited this persona.')
                    self.assertEqual((root / 'skills/onboarding/SKILL.md').read_text(encoding='utf-8'), 'owner custom skill')
                finally:
                    app.close()

    def test_source_contract_for_shared_sprite_and_separate_roster_status(self):
        console = Path(__file__).resolve().parents[1] / 'lite/console'
        source = (console / 'app.js').read_text(encoding='utf-8')
        self.assertIn('window.TitanCrew?.stillFor(0, mood)', source)
        self.assertIn('class="worker-name"', source)
        self.assertIn('class="worker-status"', source)
        self.assertIn('Personality', (console / 'settings.js').read_text(encoding='utf-8'))
