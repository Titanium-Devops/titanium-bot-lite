"""The optional second form in SPEC.md step 6: Titan as a TiinyOS custom MCP connector.

Everything here runs against the real handler over the wire. What it cannot prove is the
last step, importing the connector into TiinyOS, because that needs the device key and
real firmware; docs/REPORT.md says so in the same words.
"""
import json
from pathlib import Path
import unittest

from lite import mcp
from tests.test_server import AppCase, wire


def rpc(app, message, status=200):
    actual, headers, payload = wire(app, 'POST', '/mcp', message)
    assert actual == status, (actual, payload)
    return payload


class DescriptorTests(AppCase):
    def test_the_address_a_person_pastes_into_tiinyos(self):
        facts = self.request('GET', '/api/mcp')
        self.assertEqual(facts['url'], 'http://localhost/mcp')
        self.assertEqual(facts['transport'], 'http')
        # docs/tiiny-platform.md section 8: the connector runs on the computer, not the device.
        self.assertEqual(facts['runEnvironment'], 'Computer')
        self.assertIs(facts['enabled'], True)
        self.assertEqual(facts['tools'], ['titan_memories', 'titan_skills', 'titan_skill'])

    def test_switching_it_off_closes_the_door_and_says_so(self):
        self.app.config['mcp'] = False
        self.assertIs(self.request('GET', '/api/mcp')['enabled'], False)
        self.request('POST', '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, status=404)


class ProtocolTests(AppCase):
    def test_initialize_lists_the_three_read_only_tools(self):
        answer = rpc(self.app, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                'params': {'protocolVersion': mcp.PROTOCOL}})
        self.assertEqual(answer['result']['protocolVersion'], mcp.PROTOCOL)
        self.assertEqual(answer['result']['serverInfo']['name'], 'titanium-tiiny-bot')
        self.assertEqual(answer['result']['capabilities'], {'tools': {'listChanged': False}})
        listed = rpc(self.app, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})['result']['tools']
        self.assertEqual([tool['name'] for tool in listed],
                         ['titan_memories', 'titan_skills', 'titan_skill'])
        for tool in listed:
            self.assertEqual(tool['inputSchema']['type'], 'object')
            self.assertTrue(tool['description'])

    def test_a_notification_is_accepted_without_an_answer(self):
        status, _, payload = wire(self.app, 'POST', '/mcp',
                                  {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(status, 202)
        self.assertEqual(payload, b'')

    def test_the_device_chat_reads_the_seeded_skills(self):
        answer = rpc(self.app, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                'params': {'name': 'titan_skills', 'arguments': {}}})
        text = answer['result']['content'][0]['text']
        self.assertIs(answer['result']['isError'], False)
        for seeded in ('handbook-what-i-can-do', 'handbook-plain-words', 'onboarding'):
            self.assertIn(seeded, text)
        full = rpc(self.app, {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                              'params': {'name': 'titan_skill',
                                         'arguments': {'id': 'handbook-plain-words'}}})
        self.assertIn('# Plain words', full['result']['content'][0]['text'])
        missing = rpc(self.app, {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
                                 'params': {'name': 'titan_skill', 'arguments': {'id': 'nothing'}}})
        self.assertIs(missing['result']['isError'], True)

    def test_memories_come_back_and_can_be_filtered(self):
        (self.app.root / 'memory').mkdir(exist_ok=True)
        (self.app.root / 'memory' / 'profile.md').write_text(
            '- (2026-09-13) The owner drinks tea\n- (2026-09-13) The owner lives in Texas\n', encoding='utf-8')
        everything = rpc(self.app, {'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call',
                                    'params': {'name': 'titan_memories', 'arguments': {}}})
        self.assertIn('drinks tea', everything['result']['content'][0]['text'])
        self.assertIn('lives in Texas', everything['result']['content'][0]['text'])
        filtered = rpc(self.app, {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                  'params': {'name': 'titan_memories', 'arguments': {'search': 'tea'}}})
        self.assertIn('drinks tea', filtered['result']['content'][0]['text'])
        self.assertNotIn('lives in Texas', filtered['result']['content'][0]['text'])

    def test_nothing_this_connector_offers_can_change_a_file(self):
        before = sorted((path.relative_to(self.app.root), path.stat().st_mtime_ns)
                        for path in self.app.root.rglob('*') if path.is_file())
        for name, arguments in (('titan_memories', {}), ('titan_skills', {}),
                                ('titan_skill', {'id': 'onboarding'})):
            rpc(self.app, {'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                           'params': {'name': name, 'arguments': arguments}})
        after = sorted((path.relative_to(self.app.root), path.stat().st_mtime_ns)
                       for path in self.app.root.rglob('*') if path.is_file())
        self.assertEqual(before, after)
        source = Path(mcp.__file__).read_text(encoding='utf-8')
        for writer in ('write_text', 'write_bytes', 'unlink', 'mkdir', 'atomic_write', 'app.send'):
            self.assertNotIn(writer, source)

    def test_a_bad_message_gets_a_json_rpc_error_rather_than_a_crash(self):
        self.assertEqual(rpc(self.app, {'id': 1, 'method': 'ping'})['error']['code'], -32600)
        self.assertEqual(rpc(self.app, {'jsonrpc': '2.0', 'id': 1, 'method': 'resources/list'})['error']['code'], -32601)
        self.assertEqual(rpc(self.app, {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                        'params': {}})['error']['code'], -32602)
        self.request('GET', '/mcp', status=405)

    def test_a_browser_on_another_site_cannot_read_the_memories(self):
        # The same cross-origin rule every writing route uses, applied to the connector.
        self.request('POST', '/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                     status=403, headers={'Origin': 'http://evil.example'})


class ConfigTests(AppCase):
    def test_the_switch_is_a_real_config_field(self):
        from lite.server import DEFAULTS
        self.assertIs(DEFAULTS['mcp'], True)
        saved = json.loads((self.app.root / 'config.json').read_text(encoding='utf-8'))
        self.assertIs(saved['mcp'], True)


if __name__ == '__main__':
    unittest.main()
