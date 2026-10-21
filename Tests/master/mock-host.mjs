// Mock PinguinoHost for the Master View tests: serves the recorded fixtures (real Host answers from 2026-10-21) with a mutable OBS state,
// an SSE stream at /api/events and a customs/chat feed, so the page and the harness never touch the real OBS. Listens on 127.0.0.1 only.
// usage: node mock-host.mjs [port]   (default 8798). POSTs need any Bearer token (like the real Host).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');
const fx = n => JSON.parse(fs.readFileSync(path.join(dir, n + '.json'), 'utf8'));

export function startMock(port = 8798, opts = {}) {
  const st = {
    tree: fx('obs_tree'), status: fx('obs_status'), live: fx('live'), act: fx('activity_limit_30'), wheel: fx('wheel_public'),
    cmds: fx('commands_profiles'), overlays: fx('overlays'), ochat: fx('overlaychat_status'),
    customs: { open: true, activity: 'competitive', mode: 'balanced', format: '3v3', queue: [{ username: 'spywobbles', display: 'spywobbles', mmr: 800 }, { username: 'pineyapplie', display: 'PineyApplie', mmr: 1700 }], match: null },
    logs: [], chat: [], seq: 0, runs: [], modCalls: [], posts: [], sse: new Set(), delayMs: opts.delayMs || 0, noEvents: !!opts.noEvents, failNext: new Set(), eventId: 0,
  };
  st.tree.items.forEach(i => { if (i.id === 140) i.children = [{ id: 1, name: 'Child A', kind: 'image_source', enabled: true }, { id: 2, name: 'Child B', kind: 'image_source', enabled: false }]; });
  const send = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Authorization, X-Pinguino-Token, Content-Type' }); res.end(JSON.stringify(obj)); };
  const push = (event, data) => { const m = `id: ${++st.eventId}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`; st.sse.forEach(r => r.write(m)); };
  st.push = push;
  const body = req => new Promise(r => { let b = ''; req.on('data', c => b += c); req.on('end', () => { try { r(JSON.parse(b || '{}')); } catch (e) { r({}); } }); });
  function findItem(list, id) { for (const i of list) { if (i.id === id) return i; if (i.children) { const f = findItem(i.children, id); if (f) return f; } } return null; }

  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://x'), p = u.pathname, m = req.method;
    if (m === 'OPTIONS') { res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Authorization, X-Pinguino-Token, Content-Type' }); return res.end(); }
    if (st.delayMs) await new Promise(r => setTimeout(r, st.delayMs));
    if (m === 'POST') {
      if (!process.env.MOCK_OPEN && !/^Bearer \S+/.test(req.headers.authorization || '')) return send(res, 401, { ok: false, error: 'token required' });
      const b = await body(req); st.posts.push({ p, b });
      if (st.failNext.has(p)) { st.failNext.delete(p); return send(res, 200, { ok: false, error: 'OBS refused the change' }); }
      if (p === '/api/obs/scene') { if (!st.tree.scenes.some(s => s.name === b.scene)) return send(res, 200, { ok: false, error: 'OBS has no scene called that' }); st.tree.current = st.tree.scene = b.scene; st.tree.scenes.forEach(s => s.current = s.name === b.scene); push('obs', st.tree); return send(res, 200, { ok: true }); }
      if (p === '/api/obs/item') { const it = findItem(st.tree.items, b.itemId); if (!it) return send(res, 200, { ok: false, error: 'that source is not in the scene' }); it.enabled = b.enabled != null ? !!b.enabled : !it.enabled; push('obs', st.tree); return send(res, 200, { ok: true, enabled: it.enabled }); }
      if (p === '/api/run') { st.runs.push(b.text); if (b.text === '!queue close') st.customs.open = false; if (b.text === '!queue open') st.customs.open = true; if (b.text === '!next') st.customs.queue.shift(); if (/^!kick /.test(b.text)) st.customs.queue = st.customs.queue.filter(q => q.username !== b.text.slice(6)); push('customs', st.customs); return send(res, 200, { ok: true }); }
      if (p === '/api/commands/profile') { const c = st.cmds.commands.find(x => x.id === b.id); if (!c) return send(res, 200, { ok: false, error: 'unknown command' }); c.enabled = b.enabled; return send(res, 200, { ok: true }); }
      if (p === '/api/customs/mod') {
        const a = b.action, v = b.value; let ran = null;
        if (a === 'queue') { st.customs.open = v === 'open' ? true : v === 'close' ? false : st.customs.open; if (v === 'clear') st.customs.queue = []; ran = '!queue ' + v; }
        else if (a === 'next') { st.customs.queue.shift(); ran = '!next'; }
        else if (a === 'kick') { st.customs.queue = st.customs.queue.filter(q => q.username !== v); ran = '!kick ' + v; }
        else if (['mode', 'format', 'casual', 'koth'].includes(a)) { st.customs[a === 'casual' ? 'casualStyle' : a] = v; ran = '!' + a + ' ' + v; }
        else ran = '!' + a;
        st.modCalls.push({ a, v }); push('customs', st.customs); return send(res, 200, { ok: true, ran, customs: st.customs });
      }
      if (p.startsWith('/api/wheel/')) return send(res, 200, { ok: true, wheel: { status: 'open', round: 3, teamSize: 3, entrants: [], signedUp: 0, public: st.wheel } });
      if (p === '/api/overlays/delete') { st.overlays.files = st.overlays.files.filter(f => f.path !== b.path); return send(res, 200, { ok: true }); }
      if (p === '/api/overlays/rename') { const f = st.overlays.files.find(x => x.path === b.from); if (f) f.path = b.to; return send(res, 200, { ok: !!f }); }
      if (p === '/api/overlaychat/ask') return send(res, 200, { ok: true, text: 'I made the goal bar orange.', proposals: [{ id: 'p1', path: 'goal.html' }], files: [] });
      if (p === '/api/overlaychat/apply') return send(res, 200, { ok: true });
      return send(res, 404, { ok: false, error: 'nope' });
    }
    if (p === '/api/events') {
      if (st.noEvents) return send(res, 404, {});
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*' });
      res.write('retry: 1000\n\n'); st.sse.add(res);
      res.write(`id: ${++st.eventId}\nevent: snapshot\ndata: ${JSON.stringify({ obs: st.tree, obsstatus: st.status, live: st.live, customs: st.customs, wheel: st.wheel, activity: st.act.items.slice(-30), chat: st.chat.slice(-50), chatSeq: st.seq })}\n\n`);
      req.on('close', () => st.sse.delete(res)); return;
    }
    if (p === '/api/obs/tree') { const t = JSON.parse(JSON.stringify(st.tree)); if (u.searchParams.get('scene') && u.searchParams.get('scene') !== t.scene) { t.scene = u.searchParams.get('scene'); t.items = [{ id: 900, name: 'Only in ' + t.scene, kind: 'image_source', enabled: true }]; } return send(res, 200, t); }
    if (p === '/api/obs/status') return send(res, 200, st.status);
    if (p === '/api/status') return send(res, 200, { ok: true, chatConnected: true, eventSubConnected: true, obsConnected: true });
    if (p === '/api/live') return send(res, 200, st.live);
    if (p === '/api/activity') { const since = +u.searchParams.get('since') || 0; return send(res, 200, { ok: true, seq: st.act.seq, items: st.act.items.filter(i => i.seq > since) }); }
    if (p === '/api/wheel/public') return send(res, 200, st.wheel);
    if (p === '/api/customs/state') return opts.noCustoms ? send(res, 404, {}) : send(res, 200, st.customs);
    if (p === '/api/chat/recent') { if (opts.noChat) return send(res, 404, {}); const since = +u.searchParams.get('since') || 0; return send(res, 200, { ok: true, seq: st.seq, messages: st.chat.filter(c => c.seq > since) }); }
    if (p === '/api/wheel/state') return send(res, 200, { ok: true, status: 'open', round: 3, teamSize: 3, entrants: [], signedUp: 0, public: st.wheel });
    if (p === '/api/commands/profiles') return send(res, 200, st.cmds);
    if (p === '/api/eventlog') { if (opts.noLogs) return send(res, 404, {}); const k = u.searchParams.get('kind'), since = +u.searchParams.get('since') || 0; const ev = st.logs.filter(l => l.kind === k && l.ts > since); return send(res, 200, { ok: true, kind: k, count: ev.length, more: false, latest: ev.length ? ev[ev.length - 1].ts : since, events: ev }); }
    if (p === '/api/overlays') return send(res, 200, st.overlays);
    if (p === '/api/overlaychat/status') return send(res, 200, { enabled: true, hasKey: true, callsToday: 1, dailyCalls: 40, pendingProposals: 0, bridge: 'off' });
    send(res, 404, { ok: false });
  });
  server.addLog = l => { const x = Object.assign({ id: st.logs.length + 1, ts: Date.now() + st.logs.length }, l); st.logs.push(x); if (x.kind === 'players') push('playerlog', x); return x; };
  server.st = st; server.addChat = (user, text) => { const c = { seq: ++st.seq, user: user.toLowerCase(), display: user, text, ts: Date.now(), badges: [], color: '#ff8a00' }; st.chat.push(c); push('chat', c); };
  return new Promise(r => server.listen(port, '127.0.0.1', () => r(server)));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const s = await startMock(+process.argv[2] || 8798);
  s.addChat('SpyWobbles', 'hello from the mock'); s.addChat('PineyApplie', 'gl hf');
  console.log('mock host on 127.0.0.1:' + s.address().port);
}
