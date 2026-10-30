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
    rk: { missing: false, fail: false, posts: [], s: { active: false, limit: 5, games: [], net: 0, inProgress: 0, wins: 0, losses: 0, day: '2026-10-30', week: { wins: 5, losses: 2, net: 3 }, month: { wins: 20, losses: 9, net: 11 }, breakAfter: 3, lossStreak: 2, brk: { active: false, reason: '', afterGames: 3, lossStreak: 2, since: '' }, breaks: [], startedAt: '', endedAt: '' } },
    yt: { missing: false, fail: false, posts: [], orders: [{ id: 7, login: 'yt:UCabc123', display: 'Anna', platform: 'youtube', item: '1v1', label: '1v1 vs Peng', price: 500, status: 'pending', createdAt: 1000, place: 1 }, { id: 8, login: 'yt:UCdef456', display: 'Bo', platform: 'youtube', item: 'casual', label: 'Casual game with Peng', price: 200, status: 'pending', createdAt: 1300, place: 2 }, { id: 5, login: 'yt:UCold', display: 'Old', platform: 'youtube', item: '1v1', label: '1v1 vs Peng', price: 500, status: 'done', createdAt: 100 }] },
    intros: [{ platform: 'twitch', user_id: '1', login: 'amy', text: 'hello <b>there</b>', status: 'pending', submitted_at: 1 }, { platform: 'twitch', user_id: '2', login: 'bob', text: 'yo', status: 'pending', submitted_at: 2 }, { platform: 'twitch', user_id: '3', login: 'cy', text: 'old', status: 'approved', submitted_at: 0 }],
    tree: fx('obs_tree'), status: fx('obs_status'), live: fx('live'), act: fx('activity_limit_30'), wheel: fx('wheel_public'),
    cmds: fx('commands_profiles'), overlays: fx('overlays'), ochat: fx('overlaychat_status'),
    customs: { open: true, activity: 'competitive', mode: 'balanced', format: '3v3', queue: [{ username: 'spywobbles', display: 'spywobbles', mmr: 800 }, { username: 'pineyapplie', display: 'PineyApplie', mmr: 1700 }], match: null },
    logs: [], music: [], chat: [], seq: 0, runs: [], modCalls: [], posts: [], sse: new Set(), delayMs: opts.delayMs || 0, noEvents: !!opts.noEvents, failNext: new Set(), eventId: 0,
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
    // load-test hooks (Q): /__load?chat=N&events=M injects lines at once, /__down?ms=T answers 503 and drops the event stream for T ms
    if (p === '/__load') { for (let i = 0; i < (+u.searchParams.get('chat') || 0); i++) server.addChat('Load' + (i % 40), 'load line ' + i + ' ' + 'x'.repeat(i % 50)); for (let i = 0; i < (+u.searchParams.get('events') || 0); i++) { const e = { ts: Math.floor(Date.now() / 1000), kind: 'redeem', type: 'redeem', user: 'ev' + (i % 30), what: 'Load ' + i, detail: 'Load ' + i, amount: 1, message: '', seq: ++st.act.seq }; st.act.items.push(e); } return send(res, 200, { ok: true, chat: st.chat.length, act: st.act.items.length }); }
    if (p === '/__down') { st.downUntil = Date.now() + (+u.searchParams.get('ms') || 3000); st.sse.forEach(r => r.end()); st.sse.clear && st.sse.clear(); return send(res, 200, { ok: true }); }
    if (p === '/__mode') { st.mode = u.searchParams.get('m') || 'ok'; return send(res, 200, { ok: true, mode: st.mode }); }
    if (st.mode === 'down') { st.sse.forEach(r => r.end()); res.writeHead(503, { 'Access-Control-Allow-Origin': '*' }); return res.end('down'); }
    if (st.mode === '500') { res.writeHead(500, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }); return res.end('{"ok":false,"error":"boom"}'); }
    if (st.mode === 'bad') { res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }); return res.end('{not json <html>'); }
    if (st.mode === 'slow') await new Promise(r => setTimeout(r, 3000));
    if (st.downUntil && Date.now() < st.downUntil) { res.writeHead(503, { 'Access-Control-Allow-Origin': '*' }); return res.end('down'); }
    if (st.delayMs) await new Promise(r => setTimeout(r, st.delayMs));
    if (m === 'POST') {
      if (!process.env.MOCK_OPEN && !/^Bearer \S+/.test(req.headers.authorization || '')) return send(res, 401, { ok: false, error: 'token required' });
      const b = await body(req); st.posts.push({ p, b });
      if (st.failNext.has(p)) { st.failNext.delete(p); return send(res, 200, { ok: false, error: 'OBS refused the change' }); }
      if (p === '/api/obs/scene') { if (!st.tree.scenes.some(s => s.name === b.scene)) return send(res, 200, { ok: false, error: 'OBS has no scene called that' }); st.tree.current = st.tree.scene = b.scene; st.tree.scenes.forEach(s => s.current = s.name === b.scene); push('obs', st.tree); return send(res, 200, { ok: true }); }
      if (p === '/api/obs/item') { const it = findItem(st.tree.items, b.itemId); if (!it) return send(res, 200, { ok: false, error: 'that source is not in the scene' }); it.enabled = b.enabled != null ? !!b.enabled : !it.enabled; push('obs', st.tree); return send(res, 200, { ok: true, enabled: it.enabled }); }
      if (p === '/api/run') { st.runs.push(b.text); { const pm = /^!pm (.+)$/.exec(b.text || ''); if (pm) { if (st.pmFail) return send(res, 200, { ok: false, error: 'mods only' }); if (!st.pmNoop) st.customs.pmName = pm[1]; } } if (b.text === '!queue close') st.customs.open = false; if (b.text === '!queue open') st.customs.open = true; if (b.text === '!next') st.customs.queue.shift(); { const wm = /^!wheel (mode|size|odd|eligibility) ([a-z0-9]+)$/.exec(b.text || ''); if (wm) { st.wheel[wm[1] === 'size' ? 'teamSize' : wm[1] === 'odd' ? 'oddPolicy' : wm[1]] = wm[1] === 'size' ? +wm[2] : wm[2]; push('wheel', st.wheel); } else if (b.text === '!wheel close') { st.wheel.status = 'closed'; push('wheel', st.wheel); } } if (/^!kick /.test(b.text)) st.customs.queue = st.customs.queue.filter(q => q.username !== b.text.slice(6)); push('customs', st.customs); return send(res, 200, { ok: true }); }
      if (p === '/api/commands/profile') { const c = st.cmds.commands.find(x => x.id === b.id); if (!c) return send(res, 200, { ok: false, error: 'unknown command' }); c.enabled = b.enabled; return send(res, 200, { ok: true }); }
      if (p === '/api/ranked') { if (st.rk.missing) return send(res, 404, {}); st.rk.posts.push(b); const s = st.rk.s, snap = () => { const o = Object.assign({}, s, { visible: s.games.slice(-s.limit), inProgress: s.games.length + 1, break: Object.assign({}, s.brk, { afterGames: s.breakAfter, lossStreak: s.lossStreak }) }); delete o.brk; return o; }, refuse = e => send(res, 200, Object.assign({ ok: false, error: e }, snap())); if (st.rk.fail) return refuse('mods only'); const a = b.action; if (a === 'start') { Object.assign(s, { active: true, games: [], wins: 0, losses: 0, net: 0, startedAt: new Date(2026, 9, 30, 18, 0).toISOString(), endedAt: '' }); } else if (a === 'stop') { s.active = false; s.endedAt = new Date(2026, 9, 30, 21, 0).toISOString(); } else if (a === 'win' || a === 'loss') { if (!s.active) return refuse('not running'); s.games.push(a === 'win' ? 'W' : 'L'); s[a === 'win' ? 'wins' : 'losses']++; s.net += a === 'win' ? 1 : -1; s.week.net += a === 'win' ? 1 : -1; s.week[a === 'win' ? 'wins' : 'losses']++; if (!s.brk.active) { const n = s.games.length, tail = (s.games.join('').match(/L*$/) || [''])[0].length; const why = s.breakAfter && n % s.breakAfter === 0 ? n + ' games' : s.lossStreak && tail >= s.lossStreak ? s.lossStreak + ' losses in a row' : ''; if (why) { s.brk = { active: true, reason: why, since: new Date(2026, 9, 30, 19, 5).toISOString() }; s.breaks.push({ at: s.brk.since, reason: why, afterGames: s.breakAfter }); } } } else if (a === 'undo') { const g = s.games.pop(); if (g) { s[g === 'W' ? 'wins' : 'losses']--; s.net += g === 'W' ? -1 : 1; s.week.net += g === 'W' ? -1 : 1; s.week[g === 'W' ? 'wins' : 'losses']--; } } else if (a === 'reset') Object.assign(s, { games: [], wins: 0, losses: 0, net: 0 }); else if (a === 'limit') { if (!(b.value >= 1 && b.value <= 20)) return refuse('limit 1-20'); s.limit = b.value; } else if (a === 'break') { if (!s.active) return refuse('not running'); if (!s.brk.active) { s.brk = { active: true, reason: 'manual', since: new Date(2026, 9, 30, 19, 30).toISOString() }; s.breaks.push({ at: s.brk.since, reason: 'manual', afterGames: s.breakAfter }); } } else if (a === 'resume') s.brk = Object.assign({}, s.brk, { active: false }); else if (a === 'breakafter' || a === 'lossstreak') { if (!(b.value >= 0 && b.value <= 20)) return refuse('0-20'); s[a === 'breakafter' ? 'breakAfter' : 'lossStreak'] = b.value; } else return refuse('unknown action'); return send(res, 200, Object.assign({ ok: true }, snap())); }
    if (p === '/api/ytorders') { if (st.yt.missing) return send(res, 404, {}); st.yt.posts.push(b); const o = st.yt.orders.find(x => String(x.id) === String(b.id)); if (st.yt.fail) return send(res, 200, { ok: false, error: 'mods only' }); if (!o) return send(res, 200, { ok: false, error: 'no such order' }); if (o.status !== 'pending') return send(res, 200, { ok: false, error: 'already ' + o.status }); o.status = b.action === 'cancel' ? 'cancelled' : 'done'; return send(res, 200, { ok: true, order: o, pending: st.yt.orders.filter(x => x.status === 'pending').length }); }
      if (p === '/api/customs/mod') {
        const a = b.action, v = b.value; let ran = null;
        if (a === 'pm') { if (st.pmFail) return send(res, 200, { ok: false, error: 'mods only' }); if (/^[!/]/.test(String(v)) || String(v).length > 20) return send(res, 200, { ok: false, error: 'bad pm name' }); st.pms = (st.pms || []).concat([b]); if (!st.pmNoop) st.customs.pmName = String(v); return send(res, 200, { ok: true, pmName: st.customs.pmName || '' }); }
        if (a === 'plan' || a === 'shuffle' || a === 'undoshuffle') { st.planCalls = st.planCalls || []; st.planCalls.push({ a, v }); const c = st.customs, fail = e => send(res, 200, { ok: false, error: e, customs: c });
          if (st.planFail) return fail('mods only');
          if (a === 'plan') { const n = Number(v); if (!Number.isInteger(n) || n < 0 || n > 50) return fail('plan 0-50'); c.plannedMatches = n; }
          else if (a === 'shuffle') { st.bs = c.queue.slice(); c.queue = c.queue.slice().reverse(); c.canUndoShuffle = true; }
          else { if (!c.canUndoShuffle) return fail('nothing to undo'); c.queue = st.bs || c.queue; c.canUndoShuffle = false; }
          return send(res, 200, { ok: true, customs: c }); }
        if (a === 'queue') { st.customs.open = v === 'open' ? true : v === 'close' ? false : st.customs.open; if (v === 'clear') st.customs.queue = []; ran = '!queue ' + v; }
        else if (a === 'next') { st.customs.queue.shift(); ran = '!next'; }
        else if (a === 'kick') { st.customs.queue = st.customs.queue.filter(q => q.username !== v); ran = '!kick ' + v; }
        else if (['mode', 'format', 'casual', 'koth'].includes(a)) { st.customs[a === 'casual' ? 'casualStyle' : a] = v; ran = '!' + a + ' ' + v; }
        else ran = '!' + a;
        st.modCalls.push({ a, v }); push('customs', st.customs); return send(res, 200, { ok: true, ran, customs: st.customs });
      }
      if (p === '/api/intros' && req.method === 'POST') { st.introCalls = st.introCalls || []; st.introCalls.push(b); const it = st.intros.find(x => String(x.user_id) === String(b.user_id) && x.platform === (b.platform || 'twitch')); if (!['approve', 'reject'].includes(b.action)) return send(res, 200, { ok: false, error: 'action must be submit, remove, approve, reject or settings' }); if (!it) return send(res, 200, { ok: false, error: 'no such intro' }); if (it.status !== 'pending') return send(res, 200, { ok: false, error: 'that intro is not waiting for approval' }); it.status = b.action === 'approve' ? 'approved' : 'rejected'; return send(res, 200, { ok: true, intro: it }); }
      if (p === '/api/scene-layouts' && req.method === 'POST') { if (b.action === 'setgame') { if (b.profile !== '*' && !/^[hv]$/.test(b.profile || '')) return send(res, 200, { ok: false, error: 'profile must be h or v' }); st.currentGame = String(b.game || '').slice(0, 40); st.gameCalls = (st.gameCalls || 0) + 1; return send(res, 200, { ok: true, currentGame: st.currentGame }); } return send(res, 200, { ok: false, error: 'unsupported in mock' }); }
      if (p === '/api/customs/teams') { st.customs.teams = st.customs.teams || { orange: { name: 'Orange', color: '#ff7a00' }, blue: { name: 'Blue', color: '#1e8fff' } }; for (const k of ['orange', 'blue']) if (b[k]) Object.assign(st.customs.teams[k], { name: b[k].name || st.customs.teams[k].name, color: b[k].color || st.customs.teams[k].color }); push('customs', st.customs); return send(res, 200, { ok: true, teams: st.customs.teams }); }
      if (p === '/api/recap/test') { (st.rcalls = st.rcalls || []).push(b); return send(res, 200, { ok: true, text: 'Recap text', clip: { title: 'Clutch', url: 'https://clips.twitch.tv/x', views: 12 }, posted: !!b.post, duplicate: false }); }
      if (p === '/api/raid/prep') { (st.rcalls = st.rcalls || []).push(b); if (st.raidMode === 'dup') return send(res, 200, { ok: true, fired: false, duplicate: true }); if (st.raidMode === 'err') return send(res, 200, { ok: false, error: 'chat is offline' }); if (st.raidMode === 'slow') return setTimeout(() => send(res, 200, { ok: true, fired: true, duplicate: false }), 150); return send(res, 200, { ok: true, fired: true, duplicate: false }); }
      if (p === '/api/channel/update') { st.chan = Object.assign(st.chan || {}, b); return send(res, 200, { ok: true, game: b.game, title: b.title }); }
      if (p === '/api/stream/info') { st.sinfo = b; return send(res, 200, { ok: true, results: Object.fromEntries((b.platforms || []).map(k => [k, { ok: k !== 'kick', error: k === 'kick' ? 'Kick API not available' : undefined }])) }); }
      if (p === '/api/stream/schedule') { st.sched = b; return send(res, 200, { ok: true, broadcastId: 'bc1', url: 'https://youtube.com/watch?v=bc1' }); }
      if (p === '/api/wheel/queue-add') { st.we = st.we || []; const add = (b.users || []).filter(x => !st.we.includes(x)); st.we.push(...add); (st.wcalls = st.wcalls || []).push({ p, b }); return send(res, 200, { ok: true, added: add, skipped: [] }); }
      if (p === '/api/wheel/remove') { st.we = (st.we || []).filter(x => !(b.users || []).includes(x)); (st.wcalls = st.wcalls || []).push({ p, b }); return send(res, 200, { ok: true, removed: b.users || [] }); }
      if (p === '/api/wheel/cancel') { (st.wcalls = st.wcalls || []).push({ p, b }); return send(res, 200, { ok: true }); }
      if (p === '/api/customs/queue-add') { (st.wcalls = st.wcalls || []).push({ p, b }); (b.users || []).forEach(u => st.customs.queue.push({ username: u, display: u })); return send(res, 200, { ok: true, added: b.users || [] }); }
      if (p.startsWith('/api/wheel/')) return send(res, 200, { ok: true, wheel: { status: 'open', round: 3, teamSize: 3, entrants: [], signedUp: 0, public: st.wheel } });
      if (p === '/api/customs/sim-say') { st.say = st.say || []; st.say.push(b); return send(res, 200, { ok: true, spoke: !!b.speak, sent: 1, blocked: 0, lines: ['x'] }); }
      if (p === '/api/control') { st.ctl = st.ctl || []; st.ctl.push(b); if (b.action === 'volume') st.mvol = b.value; return send(res, 200, { ok: true }); }
      if (p === '/api/preset') { st.presets = st.presets || []; st.presets.push(b); if (st.presetFail) return send(res, st.presetFail, { ok: false, error: 'no such preset' }); if (b.name === 'songify') st.songify = true; else if (b.name === 'takeback') st.songify = false; else return send(res, 200, { ok: false, error: 'unknown preset ' + b.name }); return send(res, 200, { ok: true, settings: {} }); }
      if (p === '/api/mod-action') { st.music.push(b.action); return send(res, 200, { ok: true, code: 'ok', title: 'Birds & the Bees', artist: 'Baby Keem' }); }
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
    if (p === '/api/modaudit') return send(res, 200, { ok: true, entries: [{ id: 'h-2', at: 1700000100, who: 'modsam', role: 'mod', action: 'timeout', target: 'troll', before: '', after: '600s', page: 'host', src: 'host' }, { id: 'h-1', at: 1700000000, who: 'viewerx', role: 'viewer', action: 'intro submitted', target: 'twitch:1', before: '', after: 'hello', page: 'host', src: 'host' }], more: false });
    if (p === '/api/streaks') return send(res, 200, { ok: true, people: 7, board: [12, 9, 7, 5, 4, 3, 1].map((n, i) => ({ login: 'u' + i, name: 'User' + i, best: n, current: Math.max(0, n - 2) })) });
    if (p === '/api/shoutouts') return send(res, 200, { ok: true, current: 'kira', pending: [{ user: 'bo', by: 'modsam', queuedSecAgo: 5 }], recent: [{ user: 'ann', minAgo: 7 }] });
    if (p === '/api/intros') { const stt = u.searchParams.get('status'); return send(res, 200, { ok: true, settings: {}, pending: st.intros.filter(x => x.status === 'pending').length, intros: st.intros.filter(x => !stt || x.status === stt) }); }
    if (p === '/api/prestream') return send(res, 200, { ok: true, module: 'prestream', status: 'fail', ts: 1, items: [{ id: 'a', label: 'Chat connected', status: 'pass', detail: '' }, { id: 'b', label: 'Mic', status: 'warn', detail: 'quiet' }, { id: 'c', label: 'OBS WebSocket', status: 'fail', detail: 'not reachable' }] });
    if (p === '/api/scene-health') return send(res, 200, { ok: false, problems: ['main: layout has no visible widget'], profiles: {} });
    if (p === '/api/recap/preview') return send(res, 200, { ok: true, text: 'Recap text', line: 'Recap', clip: { title: 'Clutch', url: 'https://clips.twitch.tv/x', views: 12 }, window: { start: 1, end: 2 } });
    if (p === '/api/channel/info') return send(res, 200, { ok: true, title: 'Customs with viewers', game: 'Rocket League', tags: ['English', 'Customs'] });
    if (p === '/api/stream/info') return send(res, 200, { ok: true, platforms: { youtube: { connected: true, canSchedule: true, title: 'Customs with viewers', description: 'Join the queue!', tags: ['rl'] }, kick: { connected: false }, tiktok: { manual: true } } });
    if (p === '/api/wheel/public') return send(res, 200, st.wheel);
    if (p === '/api/ranked') return st.rk.missing ? send(res, 404, {}) : send(res, 200, Object.assign({ ok: true }, st.rk.s, { visible: st.rk.s.games.slice(-st.rk.s.limit), inProgress: st.rk.s.games.length + 1, break: Object.assign({}, st.rk.s.brk, { afterGames: st.rk.s.breakAfter, lossStreak: st.rk.s.lossStreak }) }));
    if (p === '/api/ytorders') { if (st.yt.missing) return send(res, 404, {}); const all = u.searchParams.get('status') === 'all', list = st.yt.orders.filter(x => all || x.status === 'pending'); return send(res, 200, { ok: true, pending: list.filter(x => x.status === 'pending').length, orders: list, items: [{ key: '1v1', label: '1v1 vs Peng', price: 500 }, { key: 'casual', label: 'Casual game with Peng', price: 200 }] }); }
    if (p === '/api/customs/state') return opts.noCustoms ? send(res, 404, {}) : send(res, 200, st.customs);
    if (p === '/api/chat/recent') { if (opts.noChat) return send(res, 404, {}); const since = +u.searchParams.get('since') || 0; return send(res, 200, { ok: true, seq: st.seq, messages: st.chat.filter(c => c.seq > since) }); }
    if (p === '/api/wheel/state') return send(res, 200, { ok: true, status: 'open', round: 3, teamSize: 3, entrants: (st.we || []).map(login => ({ login })), signedUp: 0, public: st.wheel });
    if (p === '/api/commands/profiles') return send(res, 200, st.cmds);
    if (p === '/api/eventlog') { if (opts.noLogs) return send(res, 404, {}); const k = u.searchParams.get('kind'), since = +u.searchParams.get('since') || 0; const ev = st.logs.filter(l => l.kind === k && l.ts > since); return send(res, 200, { ok: true, kind: k, count: ev.length, more: false, latest: ev.length ? ev[ev.length - 1].ts : since, events: ev }); }
    if (p === '/api/state') return send(res, 200, { playback: { is_playing: true, progress_ms: 60000, track: { id: 't1', name: 'Birds & the Bees', artists: ['Baby Keem'], album: 'The Melodic Blue', art: 'https://i.scdn.co/image/x', duration_ms: 180000 }, device: { id: 'd1', name: 'PC', volume: st.mvol != null ? st.mvol : 40 } }, now_item: { requester: 'spywobbles' }, songify: !!st.songify, ...(st.rl ? st.rl : {}), ...(st.sc ? { selfcheck: st.sc } : {}) });
    if (p === '/api/devices') return send(res, 200, { devices: [{ id: 'd1', name: 'PC', is_active: true, supports_volume: true, type: 'Computer', volume_percent: 40 }, { id: 'd2', name: 'Phone', is_active: false, supports_volume: true, type: 'Smartphone', volume_percent: 70 }] });
    if (p === '/api/now') return send(res, 200, { title: 'Birds & the Bees', artist: 'Baby Keem', requestedBy: 'spywobbles' });
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
