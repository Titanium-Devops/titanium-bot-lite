/* Same-origin transport for the twelve lite routes. No credentials enter snapshots. */
(function (global) {
  'use strict';
  async function ask(path, method = 'GET', body) {
    const options = { method, headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(30000) };
    if (body instanceof FormData) options.body = body;
    else if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    const response = await fetch(path, options);
    const answer = await response.json();
    if (!response.ok) throw new Error(answer.error || `Request failed (${response.status})`);
    return answer;
  }
  global.createLiteAdapter = async function () {
    let state = await ask('/api/state');
    const listeners = new Set();
    let timer = null, reading = false, dirty = false, destroyed = false;
    const older = new Map();
    const emit = (type = 'state:changed', detail = {}) => {
      for (const listener of listeners) listener({ type, detail, snapshot: state });
    };
    const mergeOlder = (next) => {
      for (const worker of next.workers) {
        const cached = older.get(worker.id);
        const past = cached?.messages || [];
        if (cached) worker.hasOlder = cached.hasOlder;
        const currentIds = new Set(worker.messages.map(m => m.id));
        worker.messages = [...past.filter(m => !currentIds.has(m.id)), ...worker.messages];
      }
      return next;
    };
    async function refresh() {
      if (destroyed) return;
      if (reading) { dirty = true; return; }
      reading = true;
      try { state = mergeOlder(await ask('/api/state')); emit(); }
      catch (error) { emit('connection:error', { message: error.message }); }
      finally { reading = false; if (dirty) { dirty = false; schedule(); } }
    }
    // Fixed window: a continuous token stream never resets and starves the timer.
    function schedule() {
      if (destroyed || timer !== null) return;
      timer = setTimeout(() => { timer = null; refresh(); }, 900);
    }
    const events = new EventSource('/events');
    events.onmessage = schedule;
    events.onopen = schedule;
    events.onerror = () => emit('connection:error', { message: 'Reconnecting to your device…' });
    async function mutate(path, method, body) { const result = await ask(path, method, body); await refresh(); return result; }
    const agent = (context) => typeof context === 'string' ? context : context?.id || state.activeContext.id;
    const fileUrl = path => '/api/file?path=' + encodeURIComponent(path);
    const adapter = {
      getSnapshot: () => state,
      subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
      destroy() { destroyed = true; clearTimeout(timer); events.close(); listeners.clear(); },
      refresh,
      selectContext(context) { if (agent(context) !== state.activeContext.id) throw new Error('This console has one conversation.'); },
      async sendMessage(context, text, files = []) {
        let body = { agentId: agent(context), text };
        if (files.length) { body = new FormData(); body.append('agentId', agent(context)); body.append('text', text); for (const file of files) body.append('file', file, file.name); }
        return mutate('/api/send', 'POST', body);
      },
      async loadOlderMessages(context) {
        const id = agent(context), worker = state.workers.find(w => w.id === id);
        const query = new URLSearchParams({ agentId: id, before: worker.messages[0]?.id || '', limit: '100' });
        const page = await ask('/api/transcript?' + query);
        const ids = new Set(worker.messages.map(m => m.id));
        worker.messages = [...page.messages.filter(m => !ids.has(m.id)), ...worker.messages];
        worker.hasOlder = page.hasOlder;
        older.set(id, { messages: worker.messages.slice(), hasOlder: page.hasOlder });
        emit('transcript:older');
        return page;
      },
      decideApproval(context, entryId, decision) {
        decision = ({ approved: 'approve', denied: 'deny', 'allow-once': 'approve' })[decision] || decision;
        return mutate('/api/decide', 'POST', { agentId: agent(context), entryId, decision });
      },
      getModels: () => ask('/api/models'),
      setModel(body) { return mutate('/api/model', 'POST', typeof body === 'string' ? { action: 'use', id: body } : body); },
      getSettings: () => ask('/api/settings'),
      saveSettings: body => mutate('/api/settings', 'PATCH', body),
      getLibrary: () => ask('/api/library'),
      libraryAction: body => mutate('/api/library', 'POST', body),
      runRoutine: id => mutate('/api/library', 'POST', { kind: 'routine', verb: 'run', id }),
      setSkillEnabled: (id, enabled) => mutate('/api/library', 'POST', { kind: 'skill', verb: enabled ? 'enable' : 'disable', id }),
      fileUrl,
      async readAttachmentText(agentId, path) {
        const response = await fetch(fileUrl(path));
        if (!response.ok) throw new Error('This file could not be read.');
        return { text: await response.text() };
      },
      async readAttachmentImage(path) { return { url: fileUrl(path), dataUrl: fileUrl(path) }; },
    };
    return adapter;
  };
})(window);
