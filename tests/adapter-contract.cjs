/* Run the actual adapter without a DOM or browser. HTTP transport is urllib. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const [base, python] = process.argv.slice(2);
const transport = `
import json, sys, urllib.request, urllib.error
item = json.load(sys.stdin)
request = urllib.request.Request(item['url'], data=item['body'].encode() if item.get('body') else None,
                                 method=item['method'], headers=item['headers'])
try:
    response = urllib.request.urlopen(request, timeout=5)
except urllib.error.HTTPError as error:
    response = error
with response:
    print(json.dumps({'status': response.status, 'body': response.read().decode()}))
`;
global.window = global;
global.fetch = async (path, options = {}) => {
  const result = spawnSync(python, ['-c', transport], {
    input: JSON.stringify({url: base + path, method: options.method || 'GET',
      headers: options.headers || {}, body: options.body}), encoding: 'utf8', timeout: 10000,
  });
  assert.equal(result.status, 0, 'urllib request failed');
  const response = JSON.parse(result.stdout);
  return {ok: response.status < 400, status: response.status,
    json: async () => JSON.parse(response.body), text: async () => response.body};
};
class Events {
  constructor(path) { assert.equal(path, '/events'); Events.current = this; }
  close() { this.closed = true; }
}
global.EventSource = Events;
vm.runInThisContext(fs.readFileSync('lite/console/lite-adapter.js', 'utf8'));
(async () => {
  const adapter = await createLiteAdapter();
  try {
    assert.equal(adapter.getSnapshot().workers[0].id, 'titan');
    let updates = 0;
    adapter.subscribe(() => updates++);
    await adapter.sendMessage('titan', 'Adapter echo');
    const deadline = Date.now() + 5000;
    while (adapter.getSnapshot().workers[0].messages.at(-1)?.type !== 'text'
           || adapter.getSnapshot().workers[0].messages.at(-1)?.authorId !== 'titan') {
      assert.ok(Date.now() < deadline, 'Echo reply timed out');
      await new Promise(resolve => setTimeout(resolve, 20));
      await adapter.refresh();
    }
    assert.equal(adapter.getSnapshot().workers[0].messages.at(-1).text, 'ohce retpadA');
    assert.equal((await adapter.getModels()).live.model, 'echo');
    assert.equal((await adapter.saveSettings({botName: 'Titan test'})).botName, 'Titan test');
    const saved = await adapter.libraryAction({kind: 'memory', verb: 'remember', text: 'Likes tea'});
    assert.ok(saved.library.memories.some(item => item.name === 'Likes tea'));
    assert.ok((await adapter.readAttachmentText('titan', 'memory/profile.md')).text.includes('Likes tea'));
    assert.equal((await adapter.loadOlderMessages('titan')).hasOlder, false);
    await assert.rejects(adapter.decideApproval('titan', 'missing', 'deny'));
    await assert.rejects(adapter.runRoutine('missing'));
    const before = updates;
    Events.current.onmessage({data: '{"channel":"changed"}'});
    await new Promise(resolve => setTimeout(resolve, 1100));
    assert.ok(updates > before, 'SSE poke must reload state');
  } finally { adapter.destroy(); }
  assert.equal(Events.current.closed, true);
  console.log('Actual adapter passed against echo HTTP server through urllib');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
