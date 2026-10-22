// Master View harness: node Tests/master/run.mjs   (no app, no real Host, no OBS; uses the recorded fixtures + mock-host.mjs on a scratch port)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { startMock } from './mock-host.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const C = createRequire(import.meta.url)(path.join(here, '..', '..', 'App', 'src', 'master', 'master-core.js'));
const fx = n => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', n + '.json'), 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
let pass = 0, fail = 0; const failures = [];
async function t(name, fn) { try { await fn(); pass++; console.log('  ok   ' + name); } catch (e) { fail++; failures.push(name); console.log('  FAIL ' + name + '\n       ' + (e && e.message || e)); } }

/* minimal fake DOM, just what reconcile() touches */
class N { constructor(n) { this.n = n; this.kids = []; this.parentNode = null; this.ups = 0; }
  get firstChild() { return this.kids[0] || null; } get nextSibling() { const p = this.parentNode; return p ? p.kids[p.kids.indexOf(this) + 1] || null : null; }
  insertBefore(el, ref) { if (el.parentNode) el.parentNode.kids.splice(el.parentNode.kids.indexOf(el), 1); el.parentNode = this; const i = ref ? this.kids.indexOf(ref) : this.kids.length; this.kids.splice(i < 0 ? this.kids.length : i, 0, el); this.moves = (this.moves || 0) + 1; return el; }
  removeChild(el) { this.kids.splice(this.kids.indexOf(el), 1); el.parentNode = null; } }
const mk = rows => { const p = new N('root'); let created = 0, updated = 0; const render = list => C.reconcile(p, list, r => r.k, r => { created++; return new N(r.k); }, (el, r) => { updated++; el.txt = r.v; });
  return { p, render, stats: () => ({ created, updated }), keys: () => p.kids.map(k => k._k) }; };

console.log('core: scenes');
await t('scene rows: loose scenes first, folders with counts, current highlighted', () => {
  const tree = fx('obs_tree'); const rows = C.buildSceneRows(tree.scenes, { current: 'Rocket' });
  assert.equal(rows.length, 18); assert.equal(rows[0].name, 'Rocket'); assert.equal(rows.filter(r => r.current).length, 1);
});
const folderScenes = [{ name: 'Games / Rocket League', folder: 'Games', label: 'Rocket League', current: false }, { name: 'Games / Minecraft', folder: 'Games', label: 'Minecraft', current: true }, { name: 'Intro', folder: '', label: 'Intro', current: false }, { name: '[RL] Main', folder: '[RL]', label: 'Main', current: false }];
await t('folders nest, collapse hides children, search expands them', () => {
  let r = C.buildSceneRows(folderScenes, {}); assert.deepEqual(r.map(x => x.key), ['s:Intro', 'f:Games', 's:Games / Rocket League', 's:Games / Minecraft', 'f:[RL]', 's:[RL] Main']);
  assert.equal(r[1].hasCurrent, true); assert.equal(r[2].indent, 1);
  r = C.buildSceneRows(folderScenes, { collapsed: new Set(['Games']) }); assert.deepEqual(r.map(x => x.key), ['s:Intro', 'f:Games', 'f:[RL]', 's:[RL] Main']);
  r = C.buildSceneRows(folderScenes, { collapsed: new Set(['Games']), query: 'mine' }); assert.deepEqual(r.map(x => x.key), ['f:Games', 's:Games / Minecraft']);
  r = C.buildSceneRows(folderScenes, { query: 'games' }); assert.equal(r.filter(x => x.type === 'scene').length, 2);   // matching the folder name keeps its scenes
});
await t('optimistic current scene overrides the server flag', () => { const r = C.buildSceneRows(folderScenes, { current: 'Intro' }); assert.equal(r.filter(x => x.current).map(x => x.name).join(), 'Intro'); });

console.log('core: sources');
const items = fx('obs_tree').items;
await t('item rows keep OBS order (top first) and eye state', () => { const r = C.buildItemRows(items, {}); assert.equal(r.length, items.length); assert.equal(r[0].name, 'Players'); assert.equal(r.find(x => x.id === 135).enabled, true); assert.equal(r.find(x => x.id === 141).enabled, false); });
const grouped = [{ id: 1, name: 'Cam group', kind: 'group', enabled: false, children: [{ id: 2, name: 'Cam', kind: 'dshow_input', enabled: true }, { id: 3, name: 'Frame', kind: 'image_source', enabled: true }] }, { id: 4, name: 'Chat', kind: 'browser_source', enabled: true }];
await t('groups nest with depth, children of a hidden group are dimmed, collapse works', () => {
  let r = C.buildItemRows(grouped, {}); assert.deepEqual(r.map(x => [x.id, x.depth, x.dimmed]), [[1, 0, false], [2, 1, true], [3, 1, true], [4, 0, false]]); assert.equal(r[0].type, 'group');
  r = C.buildItemRows(grouped, { collapsed: new Set([1]) }); assert.deepEqual(r.map(x => x.id), [1, 4]); assert.equal(r[0].collapsed, true);
});
await t('search keeps the group of a matching child, drops the rest', () => { const r = C.buildItemRows(grouped, { query: 'frame' }); assert.deepEqual(r.map(x => x.id), [1, 3]); });
await t('optimistic override flips the row at once, and dims the children when a group is hidden', () => {
  const r = C.buildItemRows(grouped, { override: id => (id === 1 ? true : id === 4 ? false : undefined) }); assert.equal(r[0].enabled, true); assert.equal(r[1].dimmed, false); assert.equal(r.find(x => x.id === 4).enabled, false);
});
await t('findItem/flatIds walk groups', () => { assert.equal(C.findItem(grouped, 3).name, 'Frame'); assert.deepEqual(C.flatIds(grouped), [1, 2, 3, 4]); assert.equal(C.findItem(grouped, 99), null); });

console.log('core: store + optimistic');
await t('store only notifies changed keys; deep-equal patch is silent', () => {
  const s = C.createStore({ a: { x: 1 }, b: 1 }); let calls = []; s.subscribe(ch => calls.push(ch.join()));
  assert.deepEqual(s.set({ a: { x: 1 }, b: 1 }), []); assert.deepEqual(s.set({ a: { x: 2 }, b: 1 }), ['a']); s.set({ b: 2 }); assert.deepEqual(calls, ['a', 'b']);
});
await t('optimistic: settles on agreement, keeps on disagreement, expires after ttl', () => {
  let now = 1000; const o = C.createOptimistic(500, () => now); o.set('k', true); o.settle('k', false); assert.equal(o.has('k'), true); now += 400; assert.deepEqual(o.expire(), []); o.settle('k', true); assert.equal(o.has('k'), false);
  o.set('z', 'Scene'); now += 600; assert.deepEqual(o.expire(), ['z']); assert.equal(o.size(), 0);
});

console.log('core: customs commands');
await t('customs actions map to the same chat commands as the website', () => {
  const e = C.customsText; assert.equal(e('queue-open'), '!queue open'); assert.equal(e('queue-clear'), '!queue clear'); assert.equal(e('next', ''), '!next'); assert.equal(e('next', 'orange'), '!next orange');
  assert.equal(e('match', 'fill'), '!match fill'); assert.equal(e('finish', 'blue'), '!finish blue'); assert.equal(e('format', '3v3'), '!format 3v3'); assert.equal(e('koth', 'on'), '!koth on'); assert.equal(e('kick', '@Spy_Wobbles'), '!kick Spy_Wobbles');
});
await t('customs actions reject anything off the allow-list (no chat injection)', () => {
  const e = C.customsText; assert.equal(e('match', 'explode'), null); assert.equal(e('win', 'red'), null); assert.equal(e('kick', 'a b'), null); assert.equal(e('kick', 'x\n!ban all'), null); assert.equal(e('kick', ''), null); assert.equal(e('format', '17v17'), null); assert.equal(e('rm -rf', ''), null);
});

console.log('core: SSE parser');
await t('parses id/event/data, joins data lines, ignores comments, survives CRLF and split chunks', () => {
  const got = []; const p = C.createSseParser(m => got.push(m));
  p('retry: 1000\n\n: hb\n\nid: 5\nevent: obs\nda'); p('ta: {"a":1}\r\n\r\nevent: chat\ndata: line1\ndata: line2\n\n');
  assert.deepEqual(got[0], { id: '5', event: 'obs', data: { a: 1 } }); assert.equal(got.length, 2); assert.equal(got[1].data, 'line1\nline2');
});

console.log('core: DOM reconcile (diffed updates, no re-render)');
await t('unchanged rows are not touched; one changed row = one update; order changes move nodes only', () => {
  const m = mk(); const rows = [{ k: 'a', v: 1 }, { k: 'b', v: 2 }, { k: 'c', v: 3 }];
  m.render(rows); assert.deepEqual(m.stats(), { created: 3, updated: 3 }); m.render(rows.map(r => ({ ...r }))); assert.deepEqual(m.stats(), { created: 3, updated: 3 });
  m.render([{ k: 'a', v: 1 }, { k: 'b', v: 9 }, { k: 'c', v: 3 }]); assert.deepEqual(m.stats(), { created: 3, updated: 4 });
  const nodeB = m.p.kids[1]; m.render([{ k: 'b', v: 9 }, { k: 'a', v: 1 }, { k: 'c', v: 3 }]); assert.equal(m.p.kids[0], nodeB); assert.deepEqual(m.keys(), ['b', 'a', 'c']); assert.equal(m.stats().created, 3);
  m.render([{ k: 'c', v: 3 }]); assert.deepEqual(m.keys(), ['c']);
});
await t('reconcile handles 500 rows with a single toggle in well under a frame', () => {
  const m = mk(); const rows = Array.from({ length: 500 }, (_, i) => ({ k: 'r' + i, v: 0 })); m.render(rows);
  const t0 = process.hrtime.bigint(); for (let i = 0; i < 100; i++) { rows[250] = { k: 'r250', v: i + 1 }; m.render(rows); } const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 100;
  assert.ok(ms < 2, 'avg ' + ms.toFixed(2) + ' ms per render');
});

console.log('core: feed');
await t('mergeFeed dedupes by key, caps length; activityLine reads the real fixture kinds', () => {
  const l = []; assert.equal(C.mergeFeed(l, [{ k: 1 }, { k: 2 }], x => x.k, 3), true); assert.equal(C.mergeFeed(l, [{ k: 2 }], x => x.k, 3), false); C.mergeFeed(l, [{ k: 3 }, { k: 4 }], x => x.k, 3); assert.deepEqual(l.map(x => x.k), [2, 3, 4]);
  const lines = fx('activity_limit_30').items.map(C.activityLine); assert.ok(lines.every(s => typeof s === 'string' && s.length > 3)); assert.ok(lines.some(s => /raided out to/.test(s)));
});

console.log('transport: Host client against the mock');
const mock = await startMock(0); const port = mock.address().port, base = 'http://127.0.0.1:' + port; const st = mock.st;
const api = C.createApi({ base, fetch, getToken: () => 'tok', timeoutMs: 800 });
await t('GET parses the recorded tree; POST without a token is refused like the real Host', async () => {
  const r = await api.get('/api/obs/tree'); assert.ok(r.ok); assert.equal(r.json.connected, true); assert.equal(r.json.scenes.length, 18);
  const bad = await C.createApi({ base, fetch, getToken: () => '' }).post('/api/obs/scene', { scene: 'Rocket' }); assert.equal(bad.ok, false); assert.equal(bad.status, 401);
});
await t('POST scene / item change state; unknown scene is a clean error', async () => {
  assert.ok((await api.post('/api/obs/scene', { scene: 'Minecraft' })).ok); assert.equal((await api.get('/api/obs/tree')).json.current, 'Minecraft');
  const r = await api.post('/api/obs/item', { scene: 'Minecraft', itemId: 141, enabled: true }); assert.ok(r.ok); assert.equal(r.json.enabled, true);
  const bad = await api.post('/api/obs/scene', { scene: 'Nope' }); assert.equal(bad.ok, false); assert.match(bad.error, /no scene/);
});
await t('Host down -> status 0 "not reachable"; slow Host -> timeout', async () => {
  const dead = await C.createApi({ base: 'http://127.0.0.1:1', fetch, timeoutMs: 500 }).get('/api/status'); assert.equal(dead.status, 0); assert.match(dead.error, /not reachable/);
  st.delayMs = 1200; const slow = await api.get('/api/status'); st.delayMs = 0; assert.equal(slow.error, 'timeout');
});
await t('local round trip is fast (median of 40 GETs under 25 ms)', async () => {
  const xs = []; for (let i = 0; i < 40; i++) xs.push((await api.get('/api/obs/status')).ms); xs.sort((a, b) => a - b); const med = xs[20]; console.log('       median ' + med + ' ms, p95 ' + xs[37] + ' ms'); assert.ok(med < 25);
});

console.log('transport: poller');
await t('poller never overlaps requests, kick() runs now, stop() stops', async () => {
  let inflight = 0, maxIn = 0, runs = 0;
  const p = C.createPoller({ interval: 20, run: async () => { inflight++; maxIn = Math.max(maxIn, inflight); runs++; await sleep(60); inflight--; } });
  p.start(); await sleep(250); assert.equal(maxIn, 1); const r0 = runs; p.stop(); await sleep(150); assert.ok(runs <= r0 + 1);
  let n = 0; const q = C.createPoller({ interval: 5000, run: async () => { n++; } }); q.start(); await sleep(30); assert.equal(n, 1); q.kick(); await sleep(30); assert.equal(n, 2); q.stop();
  let on = false, m = 0; const g = C.createPoller({ interval: 10, run: async () => { m++; }, shouldRun: () => on }); g.start(); await sleep(60); assert.equal(m, 0); on = true; await sleep(60); assert.ok(m > 0); g.stop();
});

console.log('transport: SSE (live push)');
await t('events: snapshot on connect, then pushes arrive within a few ms of the Host change', async () => {
  const got = []; const ev = C.createEvents({ url: base + '/api/events', fetch, onMessage: m => got.push({ ...m, at: Date.now() }), sleep: ms => sleep(Math.min(ms, 50)) });
  ev.start(); await sleep(150); assert.equal(ev.isConnected(), true); assert.equal(got[0].event, 'snapshot'); assert.equal(got[0].data.obs.current, 'Minecraft');
  const t0 = Date.now(); await api.post('/api/obs/scene', { scene: 'Chatless' }); await sleep(60); const o = got.find(m => m.event === 'obs' && m.data.current === 'Chatless'); assert.ok(o, 'obs event'); console.log('       POST -> push seen after ' + (o.at - t0) + ' ms');
  mock.addChat('SpyWobbles', 'push test'); await sleep(40); assert.equal(got.find(m => m.event === 'chat').data.text, 'push test');
  ev.stop();
});
await t('events: reconnects after the stream drops and resumes with Last-Event-ID', async () => {
  const got = []; const states = []; const seenIds = []; const rf = (u, o) => { seenIds.push(o.headers['Last-Event-ID']); return fetch(u, o); };
  const ev = C.createEvents({ url: base + '/api/events', fetch: rf, onMessage: m => got.push(m), onState: s => states.push(s), sleep: ms => sleep(20) });
  ev.start(); await sleep(120); mock.st.sse.forEach(r => r.end()); await sleep(200);
  assert.deepEqual(states.slice(0, 3), [true, false, true]); assert.equal(seenIds[0], undefined); assert.ok(seenIds[1] != null); ev.stop();
});
await t('events: an old Host without /api/events backs off and reports offline (polling stays in charge)', async () => {
  const m2 = await startMock(0, { noEvents: true }); const states = []; let tries = 0;
  const ev = C.createEvents({ url: 'http://127.0.0.1:' + m2.address().port + '/api/events', fetch: (u, o) => { tries++; return fetch(u, o); }, onState: s => states.push(s), sleep: ms => sleep(30) });
  ev.start(); await sleep(200); ev.stop(); assert.equal(ev.isConnected(), false); assert.deepEqual(states, []); assert.ok(tries >= 2); m2.close();
});

console.log('end to end: optimistic click against a failing Host');
await t('optimistic scene change rolls back when the Host refuses, and the error text is usable', async () => {
  const opt = C.createOptimistic(2500); opt.set('scene', 'Rocket'); st.failNext.add('/api/obs/scene'); const r = await api.post('/api/obs/scene', { scene: 'Rocket' });
  if (!r.ok) opt.drop('scene'); assert.equal(opt.has('scene'), false); assert.equal(r.error, 'OBS refused the change');
});
await t('customs: activity / pick / streamer map like the website and reject junk', () => {
  assert.equal(C.customsText('activity', 'rl koth'), '!activity rl koth'); assert.equal(C.customsText('activity', 'end'), '!activity end'); assert.equal(C.customsText('activity', 'rl; !ban x'), null);
  assert.equal(C.customsText('pick', 'auto'), '!pick auto'); assert.equal(C.customsText('pick', 'a b'), '!pick a b'); assert.equal(C.customsText('pick', 'a b c d e'), null); assert.equal(C.customsText('streamer', 'out'), '!streamer out'); assert.equal(C.customsText('streamer', 'x'), null);
});
await t('logs: end-of-game removals fold into one "6 players" row, teams stay one line, filters split the logs', () => {
  const rm = ['a', 'b', 'c', 'd', 'e', 'f'].map((u, i) => ({ k: 'r' + i, t: 'p', ts: 10 + i, type: 'removed', user: u, group: 'm7' }));
  const items = [{ k: 't', t: 'p', ts: 5, type: 'teams', matchId: 7, blue: ['x', 'y', 'z'], orange: ['a', 'b', 'c'] }, ...rm, { k: 'j', t: 'p', ts: 20, type: 'join', user: 'n' }, { k: 'o', t: 'b', ts: 21, type: 'overlay', file: 'goal.html', action: 'changed', by: 'ivan' }, { k: 'c1', t: 'c', ts: 22, user: 'q', text: 'hi' }];
  const open = new Set(), rows = C.logRows(items, 'players', '', open);
  assert.deepEqual(rows.map(r => r.kind), ['teams', 'group', 'line']); assert.equal(rows[1].label, '6 players'); assert.equal(rows[0].blue.join(), 'x,y,z');
  open.add(rows[1].key); assert.equal(C.logRows(items, 'players', '', open).length, 3 + 6);
  assert.equal(C.logRows(items, 'backend', '', open)[0].text, 'goal.html changed by ivan'); assert.equal(C.logRows(items, 'chat', '', open).length, 1); assert.equal(C.logRows(items, 'all', 'ivan', open).length, 1);
  assert.equal(C.logRows(rm.slice(0, 1), 'all', '', open)[0].kind, 'line');
});
await t('logs: Players log derived from customs changes (join, leave, match start teams, end-of-game removals)', () => {
  const q = u => ({ username: u }), A = { queue: [q('a'), q('b')], match: null }, B = { queue: [q('a'), q('b'), q('c')], match: null };
  assert.deepEqual(C.diffCustoms(A, B, 1).map(x => x.type + ':' + x.user), ['join:c']); assert.deepEqual(C.diffCustoms(B, A, 1).map(x => x.type + ':' + x.user), ['leave:c']);
  const M = { queue: [q('c')], match: { id: 3, players: [{ username: 'a' }, { username: 'b' }], blue: ['a'], orange: ['b'] } };
  const started = C.diffCustoms(B, M, 2); assert.deepEqual(started.map(x => x.type), ['teams']); assert.equal(started[0].blue[0], 'a');
  const over = C.diffCustoms(M, { queue: [q('c')], match: null }, 3); assert.deepEqual(over.map(x => x.type + ':' + x.group), ['removed:m3', 'removed:m3']);
  assert.deepEqual(C.diffCustoms(null, A), []);
});
await t('logs: 02 eventlog events normalise (ms -> s, teams detail, groups, error level)', () => {
  const tm = C.normLog({ id: 5, ts: 1792592000000, kind: 'players', type: 'teams', group: 'match-7', detail: { id: 7, blue: ['a', 'b'], orange: ['c'] } });
  assert.equal(tm.t, 'p'); assert.equal(tm.ts, 1792592000); assert.equal(tm.blue.join(), 'a,b'); assert.equal(tm.matchId, 7);
  const mc = [1, 2, 3].map(i => C.normLog({ id: 10 + i, ts: 1792592100000 + i, kind: 'players', type: 'match_clear', user: 'u' + i, group: 'end-7', text: 'u' + i + ' cleared' }));
  const rows = C.logRows([tm, ...mc], 'players', '', new Set()); assert.deepEqual(rows.map(r => r.kind), ['teams', 'group']); assert.equal(rows[1].label, '3 players');
  assert.equal(C.normLog({ id: 1, ts: 1, kind: 'backend', type: 'obs', text: 'x', detail: { level: 'error' } }).level, 'error');
});
await t('customs/mod and chat/recent answer in the Host b9fad8f shapes', async () => {
  const r = await api.post('/api/customs/mod', { action: 'queue', value: 'close' }); assert.equal(r.json.ran, '!queue close'); assert.equal(r.json.customs.open, false);
  mock.addChat('X', 'hi'); const c = await api.get('/api/chat/recent?since=0'); assert.ok(Array.isArray(c.json.messages) && c.json.messages.at(-1).ts > 1e11);
});
await t('customs: a !next goes out exactly once through /api/run', async () => {
  st.posts.length = 0; const text = C.customsText('next', ''); await api.post('/api/run', { text, user: 'broadcaster' }); assert.deepEqual(st.posts.map(p => p.b.text), ['!next']); assert.equal(st.runs.at(-1), '!next');
});

await t('player: state, devices and control round trip', async () => {
  const s = await api.get('/api/state'); assert.equal(s.json.playback.track.album, 'The Melodic Blue');
  const d = await api.get('/api/devices'); assert.equal(d.json.devices.length, 2);
  await api.post('/api/control', { action: 'volume', value: 25 }); await api.post('/api/control', { action: 'transfer', value: 'd2' });
  assert.deepEqual(st.ctl.map(c => c.action), ['volume', 'transfer']); assert.equal((await api.get('/api/state')).json.playback.device.volume, 25);
});

await t('customs: strike, move, in, out commands and drop maths', async () => {
  assert.equal(C.customsText('strike', 'bob perma'), '!strike @bob perma'); assert.equal(C.customsText('unstrike', '@bob'), '!unstrike @bob');
  assert.equal(C.customsText('move', 'bob 3'), '!move bob 3'); assert.equal(C.customsText('move', 'bob 0'), null);
  assert.equal(C.customsText('in', 'bob orange'), '!in bob orange'); assert.equal(C.customsText('in', 'bob green'), null); assert.equal(C.customsText('out', 'bob'), '!out bob');
  assert.equal(C.customsText('strike', 'bob; !queue clear'), null);
  assert.deepEqual(C.strikeMarks({ temp: 1, perma: 1 }, 3), ['perma', 'temp', 'none']); assert.deepEqual(C.strikeMarks({ strikes: 2, halfStrike: 1, permaStrikes: 1 }, 3), ['perma', 'temp', 'temp', 'half']);
  assert.equal(C.dropPos(0, 2, true), 3); assert.equal(C.dropPos(2, 0, false), 1); assert.equal(C.dropPos(0, 1, false), 1); assert.equal(C.dropPos(-1, 1, true), 3);
});

await t('activity defaults: one table, ordered Host steps', () => {
  assert.deepEqual(C.activityPlan('koth', { koth: false, format: '2v2', mode: 'balanced' }), [['koth', 'on']]);
  assert.deepEqual(C.activityPlan('competitive', { koth: true, format: '1v1', mode: 'random' }), [['koth', 'off'], ['format', '2v2'], ['mode', 'balanced']]);
  assert.deepEqual(C.activityPlan('competitive', { koth: false, format: '2v2', mode: 'balanced' }), []);
  assert.deepEqual(C.activityPlan('casual', { koth: true, format: '1v1' }), [['koth', 'off']]); assert.deepEqual(C.activityPlan('nope', {}), []);
});

await t('wheel: Tourney maps to !wheel open only; queue-add / remove / cancel / queue-add round trip', async () => {
  assert.equal(C.customsText('wheel', 'open'), '!wheel open'); assert.equal(C.customsText('wheel', 'x; !queue clear'), null);
  const a = await api.post('/api/wheel/queue-add', { users: ['ann', 'bob'] }); assert.deepEqual(a.json.added, ['ann', 'bob']);
  assert.deepEqual((await api.get('/api/wheel/state')).json.entrants.map(e => e.login), ['ann', 'bob']);
  await api.post('/api/wheel/remove', { users: ['ann'] }); assert.deepEqual((await api.get('/api/wheel/state')).json.entrants.map(e => e.login), ['bob']);
  assert.equal((await api.post('/api/wheel/cancel')).json.ok, true); assert.equal((await api.post('/api/customs/queue-add', { users: ['ann'] })).json.ok, true);
});

await t('teams: name/colour validation, sizes up to 16, tags and the TikTok block', () => {
  assert.equal(C.teamName('  Pingus '), 'Pingus'); assert.equal(C.teamName('!kick'), null); assert.equal(C.teamName('x'.repeat(21)), null); assert.equal(C.teamName(''), null);
  assert.equal(C.teamColor('#FF7A00'), '#ff7a00'); assert.equal(C.teamColor('orange'), null); assert.equal(C.teamColor('#ff7a0'), null);
  assert.equal(C.customsText('format', '5v5'), '!format 5v5'); assert.equal(C.customsText('format', '16v16'), '!format 16v16'); assert.equal(C.customsText('format', '2v3'), null); assert.equal(C.customsText('format', '17v17'), null); assert.equal(C.customsText('format', '3v3; !x'), null);
  assert.equal(C.fmtSize('10v10'), 10); assert.equal(C.fmtSize('3v3'), 3); assert.equal(C.fmtSize(null), 2);
  assert.deepEqual(C.parseTags('#rl, customs ,RL,, fun'), ['rl', 'customs', 'fun']); assert.deepEqual(C.twitchTags(['rocket league', 'a-b!']), ['rocketleague', 'ab']);
  assert.equal(C.copyBlock({ title: 'T', description: 'D', tags: 'rocket league, fun' }), ['T', 'D', '#rocketleague #fun'].join('|').replace(/\|/g, String.fromCharCode(10, 10)));
});

await t('teams + stream info round trips on the mock', async () => {
  const r = await api.post('/api/customs/teams', { orange: { name: 'Pingus', color: '#ffb347' } }); assert.equal(r.json.teams.orange.name, 'Pingus'); assert.equal((await api.get('/api/customs/state')).json.teams.blue.name, 'Blue');
  assert.equal((await api.get('/api/channel/info')).json.game, 'Rocket League');
  const u = await api.post('/api/stream/info', { title: 'x', platforms: ['youtube', 'kick'] }); assert.equal(u.json.results.youtube.ok, true); assert.equal(u.json.results.kick.ok, false);
  assert.equal((await api.post('/api/stream/schedule', { platform: 'youtube', title: 'x', startsAt: '2030-01-01T00:00:00Z' })).json.broadcastId, 'bc1');
});

mock.closeAllConnections && mock.closeAllConnections(); mock.close();
console.log('\n' + (fail ? 'FAILED ' + fail + ' of ' + (pass + fail) + ': ' + failures.join('; ') : 'PASS ' + pass + ' tests'));
process.exit(fail ? 1 : 0);
