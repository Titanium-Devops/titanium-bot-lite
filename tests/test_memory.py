"""The second memory writer and the recall that chooses, against a fake device."""
import json
from datetime import date, timedelta
from unittest.mock import patch

from lite.server import (MEMORY_BUDGET, build_prompt, is_memorable, read_memories, render_memory,
                         select_relevant, split_fact)
from tests.test_agent_tools import stream_response
from tests.test_server import AppCase


def reply_stream(text):
    return stream_response([{'choices': [{'delta': {'content': text}}]},
                            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}])


class ExtractionTests(AppCase):
    def setUp(self):
        super().setUp()
        # Anything but the echo model, which reverses text and cannot extract a fact.
        self.app.device.model = self.app.device.resolved_model = 'offline-model'

    def turn(self, text, reply='Noted.', extracted='NONE'):
        answers = [reply_stream(reply), reply_stream(extracted)]
        with patch('urllib.request.urlopen', side_effect=answers) as opened:
            self.app.send(dict(agentId='titan', text=text))
            self.wait_idle()
        return opened

    def facts(self):
        return sorted(m['name'] for m in read_memories(self.app.root))

    def test_second_call_writes_profile_and_log_and_removes_the_superseded_fact(self):
        self.app.update_state(dict(target='profile', action='write', fact='The owner lives in Austin.'))
        seen = {}
        def watch(request, **kwargs):
            if b'You keep the long-term memory' in (request.data or b''):
                # The reply is already saved before the device is asked anything else.
                seen['transcript'] = json.loads((self.app.root / 'transcripts/main.json').read_text(encoding='utf-8'))
                return reply_stream('\n'.join((
                    'profile: The owner lives in Dallas.',
                    'log: The owner joined Titanium Computing in September 2026.',
                    'note: The owner prefers the window seat.',
                    'remove: The owner lives in Austin.')))
            return reply_stream('Congratulations on the move.')
        with patch('urllib.request.urlopen', side_effect=watch):
            self.app.send(dict(agentId='titan', text='I moved to Dallas last week and joined Titanium Computing.'))
            self.wait_idle()
        self.assertEqual(seen['transcript'][-1]['text'], 'Congratulations on the move.')
        self.assertEqual(seen['transcript'][-1]['type'], 'text')
        profile = (self.app.root / 'memory/profile.md').read_text(encoding='utf-8')
        self.assertIn('The owner lives in Dallas.', profile)
        self.assertNotIn('Austin', profile)
        log = next((self.app.root / 'memory/log').glob('*.md')).read_text(encoding='utf-8')
        self.assertIn('The owner joined Titanium Computing in September 2026.', log)
        self.assertIn('[note] The owner prefers the window seat.', log)
        self.assertEqual(self.facts(), ['The owner joined Titanium Computing in September 2026.',
                                        'The owner lives in Dallas.',
                                        '[note] The owner prefers the window seat.'])

    def test_none_writes_nothing_and_unparsed_prose_is_ignored(self):
        self.turn('Please summarise the plan for the week ahead.', extracted='NONE')
        self.assertEqual(self.facts(), [])
        self.turn('Please summarise the plan for the month ahead.',
                  extracted='Sure, here is what I would keep in mind for later.')
        self.assertEqual(self.facts(), [])

    def test_over_long_fact_is_refused_rather_than_sliced(self):
        single = 'The owner ' + 'runs a very long unbroken clause ' * 20 + 'with no sentence end'
        self.assertGreater(len(single), 500)
        self.turn('Tell me everything about the workshop I described yesterday.',
                  extracted='profile: ' + single)
        self.assertEqual(self.facts(), [])
        self.assertIn('extracted sentence refused at', (self.app.root / 'lite.log').read_text(encoding='utf-8'))

    def test_long_fact_splits_at_a_sentence_boundary_and_keeps_every_word(self):
        first = 'The owner runs Titanium Computing with Richard. ' * 8
        second = 'The workshop is in the garage behind the house. ' * 4
        self.turn('Here is the whole story of the workshop and the business, in detail.',
                  extracted='log: ' + first + second)
        saved = self.facts()
        self.assertEqual(len(saved), 2)
        for fact in saved:
            self.assertLessEqual(len(fact), 500)
        self.assertEqual(' '.join(sorted(saved, key=len, reverse=True)), (first + second).strip())

    def test_unmemorable_exchange_costs_no_second_inference(self):
        for trivial in ('thanks', 'ok', 'Cool!', 'yes'):
            with self.subTest(trivial=trivial):
                self.assertFalse(is_memorable(trivial))
                opened = self.turn(trivial, reply='Any time.')
                self.assertEqual(opened.call_count, 1)
        self.assertTrue(is_memorable('Who is Richard?'))
        self.assertTrue(is_memorable('I keep the workshop keys in the blue tin by the door.'))
        self.assertEqual(self.turn('Who is Richard?').call_count, 2)

    def test_echo_model_and_failed_turns_run_no_extraction(self):
        self.app.device.model = 'echo'
        self.app.send(dict(agentId='titan', text='Remember that the workshop key is in the blue tin.'))
        self.wait_idle()
        self.assertEqual(self.app.messages[-1]['type'], 'text')
        self.assertEqual(self.facts(), [])
        self.app.device.model = self.app.device.resolved_model = 'offline-model'
        with patch('urllib.request.urlopen', side_effect=ValueError('the device dropped the stream')) as opened:
            self.app.send(dict(agentId='titan', text='Remember that the workshop key is in the blue tin.'))
            self.wait_idle()
        self.assertEqual(self.app.messages[-1]['type'], 'turn-failed')
        self.assertEqual(opened.call_count, 1)

    def test_failed_extraction_is_a_log_line_not_a_failed_turn(self):
        answers = [reply_stream('Saved.'), ValueError('the device dropped the stream')]
        with patch('urllib.request.urlopen', side_effect=answers):
            self.app.send(dict(agentId='titan', text='I keep the workshop keys in the blue tin by the door.'))
            self.wait_idle()
        self.assertEqual(self.app.messages[-1]['type'], 'text')
        self.assertEqual(self.app.messages[-1]['text'], 'Saved.')
        self.assertIn('memory extraction failed', (self.app.root / 'lite.log').read_text(encoding='utf-8'))


class RecallTests(AppCase):
    def fill_log(self, count=45, text='fact-{:02}', start=date(2026, 1, 1)):
        for path in (self.app.root / 'memory/log').glob('*.md'):
            path.unlink()
        (self.app.root / 'memory/log/2026-01.md').write_text(
            '\n'.join(f'- ({start + timedelta(days=i)}) {text.format(i)}' for i in range(count)), encoding='utf-8')

    def test_ranker_prefers_an_overlapping_fact_over_a_newer_one(self):
        self.fill_log()
        (self.app.root / 'memory/log/2025-11.md').write_text(
            '- (2025-11-02) Biscuit the dog eats the salmon food and nothing else.\n', encoding='utf-8')
        quiet = build_prompt(self.app.root)
        self.assertNotIn('Biscuit', quiet)
        self.assertIn('fact-44', quiet)
        asked = build_prompt(self.app.root, 'What does Biscuit eat in the morning?')
        self.assertIn('Biscuit the dog eats the salmon food', asked)
        self.assertNotIn('fact-05', asked)
        self.assertIn('fact-44', asked)
        self.assertEqual(select_relevant('Tell me about the dog', read_memories(self.app.root)), [])

    def test_budget_line_names_the_remaining_count_and_holds_four_thousand_characters(self):
        self.fill_log(count=30, text='Workshop note {:02}. ' + 'The bench is against the north wall. ' * 10)
        rendered = render_memory(self.app.root)
        shown = [line for line in rendered.splitlines() if line.startswith('- (')]
        self.assertLess(len(rendered), MEMORY_BUDGET + 400)
        self.assertGreater(len(shown), 5)
        self.assertIn(f'{30 - len(shown)} more facts are saved on disk', rendered)
        self.assertIn('memory/log/', rendered)
        self.assertIn('the owner can open any of them in Files', rendered)
        self.fill_log(count=2)
        small = render_memory(self.app.root)
        self.assertIn('Every saved fact is above.', small)
        self.assertNotIn('more facts are saved on disk', small)

    def test_render_is_frozen_per_conversation_and_rebuilt_when_memory_changed(self):
        self.fill_log(count=6)
        state = {}
        first = build_prompt(self.app.root, 'Tell me about fact-03', 'Titan', state)
        second = build_prompt(self.app.root, 'Something else entirely', 'Titan', state)
        self.assertEqual(render_memory(self.app.root, 'anything', state),
                         render_memory(self.app.root, 'anything else', state))
        self.assertEqual(first.split('Saved memories:')[1], second.split('Saved memories:')[1])
        self.app.update_state(dict(target='profile', action='write', fact='The owner likes tea.'))
        self.assertIn('The owner likes tea.', build_prompt(self.app.root, 'unrelated', 'Titan', state))

    def test_split_fact_refuses_what_cannot_be_broken(self):
        self.assertEqual(split_fact('Short enough.'), (['Short enough.'], []))
        kept, refused = split_fact('a' * 40 + '. ' + 'b' * 80, cap=60)
        self.assertEqual(kept, ['a' * 40 + '.'])
        self.assertEqual(refused, ['b' * 80])
        self.assertEqual(split_fact('c' * 90, cap=60), ([], ['c' * 90]))
