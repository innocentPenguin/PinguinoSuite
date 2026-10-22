/* Master View page (UI). Talks straight to the Host on 127.0.0.1:8770: no website, no core hop. Logic lives in master-core.js (tested in Tests/master). */
(() => {
  'use strict';
  const C = MasterCore;
  const HOST = (new URLSearchParams(location.search).get('host')) || 'http://127.0.0.1:8770';
  const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const ls = { get(k, d) { try { const v = localStorage.getItem('mv.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem('mv.' + k, JSON.stringify(v)); } catch (e) { /* storage may be blocked */ } } };
  if (/popout=1/.test(location.search)) document.body.classList.add('pop');

  /* ---------- token + api ---------- */
  let token = '';
  const tokenReady = (async () => {
    try {
      const T = window.__TAURI__ || (window.parent && window.parent !== window && window.parent.__TAURI__);
      if (T && T.core) token = (await T.core.invoke('core_config')).token || '';
      else { const m = document.querySelector('meta[name="pinguino-token"]'); token = m ? m.content : ''; }
    } catch (e) { /* GETs work without it; writes will say so */ }
  })();
  const api = C.createApi({ base: HOST, fetch: (u, o) => fetch(u, o), getToken: () => token, timeoutMs: 4000 });

  /* ---------- Spotify strip (the Spotify module, 127.0.0.1:8771) ---------- */
  const MUSIC = (new URLSearchParams(location.search).get('music')) || 'http://127.0.0.1:8771';
  const mapi = C.createApi({ base: MUSIC, fetch: (u, o) => fetch(u, o), getToken: () => token, timeoutMs: 4000 });

  /* ---------- state ---------- */
  const cached = ls.get('cache', {});
  const S = C.createStore({
    tree: cached.tree || { connected: false, current: '', scene: '', scenes: [], folders: [], items: [] }, treeStale: !!cached.tree,
    obsStatus: null, live: null, host: null, hostUp: null, customs: cached.customs || null, customsOk: null, wheel: null,
    now: null, nowOk: null, customsMod: null, cmds: [], overlays: null, ovErr: null, ochat: null, link: { sse: false, ms: null }, tick: 0,
  });
  const opt = C.createOptimistic(2500);
  const ui = {
    wq: ls.get('wq') || null, ov: {}, simChat: ls.get('simchat') !== '0', strikeOv: {}, pop: null, drag: null, view: null, query: '', sim: false, simState: null, sel: {}, tab: ls.get('tab', 'customs'), pane: 'scenes',
    folders: new Set(ls.get('folders', [])), groups: new Set(ls.get('groups', [])), kb: { scenes: null, sources: null },
    itemsBy: {}, tookControl: false, logCat: ls.get('logcat') || 'all', logTs: {}, logsOk: null, openGroups: new Set(), prevCustoms: null, feed: [], chat: [], chatSeq: 0, actSeq: 0, chatOk: null, sent: new Map(), renaming: null, ochatLog: [],
  };
  const saveCache = () => ls.set('cache', { tree: S.get('tree'), customs: S.get('customs') });

  /* ---------- toasts, arming, command sending ---------- */
  function toast(msg, bad) {
    const old = [...$('#toasts').children].find(x => x.dataset.m === msg);
    if (old) { clearTimeout(old._t); old._t = setTimeout(() => old.remove(), bad ? 5000 : 2200); return; }
    const t = h('div', 'toast' + (bad ? ' bad' : ''), msg); t.dataset.m = msg; $('#toasts').append(t); t._t = setTimeout(() => t.remove(), bad ? 5000 : 2200);
  }
  function flash(btn) { if (!btn) return; btn.classList.add('flash'); setTimeout(() => btn.classList.remove('flash'), 220); }
  function armed(btn) {   // second click within 2.5 s confirms; returns true when this click is the confirming one
    if (btn._armT) { clearTimeout(btn._armT); btn._armT = null; btn.classList.remove('arm'); btn.textContent = btn._lbl; return true; }
    btn._lbl = btn.textContent; btn.textContent = 'Sure?'; btn.classList.add('arm');
    btn._armT = setTimeout(() => { btn._armT = null; btn.classList.remove('arm'); btn.textContent = btn._lbl; }, 2500); return false;
  }
  async function sendCmd(text, btn) {
    const now = Date.now(), last = ui.sent.get(text) || 0;
    if (now - last < 1200) { toast('Already sent ' + text); return; }   // never send the same line twice in a burst
    ui.sent.set(text, now); flash(btn);
    await tokenReady;
    const r = await api.post('/api/run', { text, user: 'broadcaster' });
    if (r.ok) { logLocal('bot', 'You ran ' + text); toast('Sent ' + text); pollers.customs.kick(); pollers.wheel.kick(); } else { ui.sent.delete(text); toast(text + ': ' + r.error, true); }
  }

  /* customs button -> POST /api/customs/mod {action,value} (answers with the new state); old Host (404) or gamemode -> /api/run chat command */
  const HOSTMOD = new Set(['queue', 'next', 'match', 'win', 'finish', 'balance', 'reroll', 'kick', 'mode', 'format', 'koth', 'casual']);
  /* ---------- player simulator: a local fake customs state, nothing leaves the app ---------- */
  const SIMNAMES = ['spywobbles', 'salman201223', 'SkyRLTN', 'LvLMarshmello', 'pineyapplie', 'gonkilluagg', 'yoohoo15', 'FrostByte', 'NovaKick', 'AeroLily', 'TurboToast', 'WaffleRL', 'DemoDan', 'BumpBoi', 'CeilingCat', 'FlipReset'];
  const simFresh = () => ({ waiting: true, open: true, queue: [], match: null, mode: 'balanced', format: '2v2', gameMode: 'standard', koth: false, activity: 'competitive', streamer: 'in', wheel: { status: 'none', entrants: [], round: 0, teamSize: 2, teams: [] }, _n: 0, _id: 0 });
  function simAdd(st, n) { for (let i = 0; i < n; i++) { const k = st._n++, nm = SIMNAMES[k % SIMNAMES.length] + (k >= SIMNAMES.length ? Math.floor(k / SIMNAMES.length) : ''); st.queue.push({ username: nm.toLowerCase(), display: nm, mmr: 600 + Math.floor(Math.random() * 900) }); } }
  // Chat events for POST /api/customs/sim-say (02): collected while the sim runs, spoken in order afterwards
  function simEv(st, event, extra) {
    const body = Object.assign({ event, queue: st.queue.map(p => p.display) }, extra || {}), m = st.match;
    if (m && /^(match_start|result|koth)/.test(event)) { const mmr = {}; (m._p || []).forEach(p => { mmr[p.display] = p.mmr; }); body.match = { id: m.id, orange: m.orange.slice(), blue: m.blue.slice(), mmr }; }
    (st._ev = st._ev || []).push(body);
  }
  async function simSay(evs) {
    if (!ui.simChat || !evs.length) return; await tokenReady;
    for (const e of evs) {
      const r = await api.post('/api/customs/sim-say', Object.assign({ speak: true }, e));
      if (r.status === 404) { if (!ui.saySeen) { ui.saySeen = 1; toast('Simulator chat needs the Host /api/customs/sim-say (not there yet)', true); } return; }
      if (!r.ok || !r.json || r.json.ok === false) toast('Chat: ' + ((r.json && r.json.error) || r.error || 'HTTP ' + r.status), true);
      else if (r.json.blocked) toast('Chat blocked by the 30 s duplicate guard: ' + e.event, true);
      else if (r.json.spoke === false) toast('Chat is switched off on the Host (sim_say.json)');
    }
  }
  const simSize = st => +String(st.format || '2v2')[0] || 2;
  function simSplit(st, ps) {
    const a = ps.slice(); if (st.mode === 'random') a.sort(() => Math.random() - .5); else a.sort((x, y) => y.mmr - x.mmr);
    const o = [], bl = []; a.forEach((p, i) => (st.mode === 'random' ? i % 2 : [0, 1, 1, 0][i % 4]) ? bl.push(p) : o.push(p)); return [o, bl];
  }
  function simFill(st) {
    const m0 = st.match;
    if (m0 && m0.status !== 'finished') {   // running game: top up only the empty slots, from the front of the queue (the bot's !match fill)
      const empty = simSize(st) * 2 - m0.orange.length - m0.blue.length; if (empty <= 0) return 'The match is already full';
      const add = st.queue.splice(0, empty); if (!add.length) return 'Nobody is waiting in the queue';
      add.forEach(p => { const toBlue = m0.blue.length < m0.orange.length; (toBlue ? m0.blue : m0.orange).push(p.display); m0._p.push(p); }); simEv(st, 'match_start'); return 'Filled ' + add.length + ' empty slot' + (add.length === 1 ? '' : 's');
    }
    const n = simSize(st) * 2; if (st.queue.length < 2) return 'Need at least 2 players in the queue';
    const ps = st.queue.splice(0, n), [o, bl] = simSplit(st, ps);
    st.match = { id: ++st._id, status: 'live', orange: o.map(p => p.display), blue: bl.map(p => p.display), _p: ps }; simEv(st, 'match_start'); return '';
  }
  function simApply(action, value) {
    const st = ui.simState, v = value || ''; let msg = '';
    const r0 = simApply0(st, action, v); let out = r0;
    if (action === 'sim' && !ui.simState.match && ui.simState.waiting && ui.simState.queue.length >= simSize(ui.simState) * 2) { simFill(ui.simState); ui.simState.waiting = false; out = (r0 ? r0 + '; ' : '') + 'enough players, game started'; }
    simSay((ui.simState._ev || []).splice(0)); return out;
  }
  function simApply0(st, action, v) {
    let msg = '';
    const nameOf = x => String(x).toLowerCase();
    if (action === 'sim') { if (v === 'add' || v === 'add4' || v === 'add8') { const n0 = st.queue.length; simAdd(st, v === 'add' ? 1 : v === 'add4' ? 4 : 8); st.queue.slice(n0).forEach((p, i) => simEv(st, 'join', { player: p.display, pos: n0 + i + 1 })); } else if (v === 'rm') { const p = st.queue.pop(); if (p) simEv(st, 'leave', { player: p.display }); } else if (v === 'reset') ui.simState = simFresh(); else if (v === 'streamer') { } }
    else if (action === 'activity') {   // choosing an activity sets its defaults (table in master-core); leaving KOTH restores the old team size
      const a = v.split(' ').pop(), d = C.ACTIVITY_DEFAULTS[a] || {}; st.activity = a === 'end' ? 'none' : a;
      if (d.koth != null) { if (d.koth && !st.koth) st._prevFmt = st.format; if (!d.koth && st.koth && !d.format && st._prevFmt) { st.format = st._prevFmt; st._prevFmt = ''; } st.koth = d.koth; }
      if (d.format) st.format = d.format; if (d.mode) st.mode = d.mode;
    }
    else if (action === 'streamer') {   // the streamer is a player: he waits at the back like anyone, and leaves queue and match when he sits out
      const isS = p => p.streamer; st.streamer = v;
      if (v === 'in') { if (!st.queue.some(isS) && !(st.match && st.match._p.some(isS))) { st.queue.push({ username: 'streamer', display: 'Streamer', mmr: 1500, streamer: true }); simEv(st, 'join', { player: 'Streamer', pos: st.queue.length }); msg = 'Streamer is in the queue'; } }
      else { const had = st.queue.some(isS) || (st.match && st.match._p.some(isS)); st.queue = st.queue.filter(p => !isS(p)); if (st.match) { st.match._p = st.match._p.filter(p => !isS(p)); st.match.orange = st.match.orange.filter(n => n !== 'Streamer'); st.match.blue = st.match.blue.filter(n => n !== 'Streamer'); } if (had) { simEv(st, 'leave', { player: 'Streamer' }); msg = 'Streamer sits out'; } }
    }
    else if (action === 'wheel') { st.wheel.status = 'open'; msg = 'Wheel sign-ups open'; }
    else if (action === 'queue-open') { st.open = true; simEv(st, 'queue_open'); } else if (action === 'queue-close') { st.open = false; simEv(st, 'queue_close'); } else if (action === 'queue-clear') { st.queue = []; simEv(st, 'queue_clear'); }
    else if (action === 'match') { if (v === 'fill') msg = simFill(st); else if (v === 'queue' || v === 'clear') { if (st.match && v === 'queue') st.queue.unshift(...st.match._p); st.match = null; } }
    else if (action === 'finish') {
      const m = st.match; if (!m) return 'No match is running';
      const win = v === 'orange' ? 'orange' : 'blue', lose = win === 'orange' ? 'blue' : 'orange', ps = m._p;
      simEv(st, 'result', { winner: win, mode: st.koth ? 'koth' : st.activity === 'competitive' ? 'points' : 'casual', pointsWin: 3, pointsLoss: 1 });
      if (st.koth) {   // winners stay, losers go to the back, challengers come in
        const stay = ps.filter(p => m[win].includes(p.display)), out = ps.filter(p => m[lose].includes(p.display));
        st.queue.push(...out); const ch = st.queue.splice(0, simSize(st));
        const orange = win === 'orange' ? stay : ch, blue = win === 'orange' ? ch : stay;
        if (ch.length < simSize(st)) simEv(st, 'koth_wait', { winner: win, need: simSize(st), have: ch.length }); else simEv(st, 'koth_stays', { winner: win });
        st.match = { id: ++st._id, status: 'live', orange: orange.map(p => p.display), blue: blue.map(p => p.display), _p: stay.concat(ch) }; simEv(st, 'match_start'); msg = win + ' stays';
      } else { st.queue.push(...ps); st.match = null; msg = win + ' won'; if (st.queue.length >= simSize(st) * 2) { simFill(st); msg += ', next game started'; } else { st.waiting = true; msg += ', waiting for ' + (simSize(st) * 2 - st.queue.length) + ' more player(s)'; } }
    }
    else if (action === 'reroll' || action === 'balance') { if (st.match) { const [o, bl] = simSplit(Object.assign({}, st, { mode: action === 'reroll' ? 'random' : 'balanced' }), st.match._p); st.match.orange = o.map(p => p.display); st.match.blue = bl.map(p => p.display); } }
    else if (action === 'mode') st.mode = v; else if (action === 'format') st.format = v; else if (action === 'gamemode') st.gameMode = v;
    else if (action === 'koth') { st.koth = v === 'on'; if (st.koth) { st.format = '1v1'; if (!st.match) { if (st.queue.length >= 2) simFill(st); else st.waiting = true; } msg = 'KOTH on: 1v1, winners stay'; } }
    else if (action === 'kick') { const k = nameOf(v); const who = st.queue.find(p => nameOf(p.username) === k || nameOf(p.display) === k); if (who) simEv(st, 'kick', { player: who.display, inLobby: !!(st.match && st.match._p.some(p => p === who)) }); st.queue = st.queue.filter(p => nameOf(p.username) !== k && nameOf(p.display) !== k); if (st.match) { st.match._p = st.match._p.filter(p => nameOf(p.display) !== k); st.match.orange = st.match.orange.filter(n => nameOf(n) !== k); st.match.blue = st.match.blue.filter(n => nameOf(n) !== k); } }
    else if (action === 'strike' || action === 'unstrike') {
      const [u, f] = v.split(' '), k = nameOf(u); st.strikes = st.strikes || {}; const s = st.strikes[k] = st.strikes[k] || { temp: 0, half: 0, perma: 0 }, key = f === 'perma' ? 'perma' : 'temp';
      s[key] = Math.max(0, s[key] + (action === 'strike' ? 1 : -1)); msg = k + (action === 'strike' ? ' got a ' : ' lost a ') + (key === 'perma' ? 'permanent ' : '') + 'strike';
    }
    else if (action === 'move') { const [u, p] = v.split(' '), k = nameOf(u), i = st.queue.findIndex(x => nameOf(x.username) === k); if (i < 0) msg = k + ' is not waiting'; else { const [x] = st.queue.splice(i, 1); st.queue.splice(Math.max(0, Math.min(+p - 1, st.queue.length)), 0, x); } }
    else if (action === 'in') {
      const [u, team] = v.split(' '), k = nameOf(u), m = st.match, other = team === 'orange' ? 'blue' : 'orange';
      if (!m) msg = 'No game is running'; else if (m[team].length >= simSize(st)) msg = team + ' has no empty slot. Drag someone out first';
      else { const oi = m[other].findIndex(n => nameOf(n) === k); if (oi >= 0) m[team].push(m[other].splice(oi, 1)[0]); else { const qi = st.queue.findIndex(x => nameOf(x.username) === k); if (qi < 0) msg = k + ' is not waiting'; else { const x = st.queue.splice(qi, 1)[0]; m._p.push(x); m[team].push(x.display); } } }
    }
    else if (action === 'out') {
      const k = nameOf(v), m = st.match; if (m) { const pi = m._p.findIndex(x => nameOf(x.display) === k); if (pi >= 0) { st.queue.unshift(m._p.splice(pi, 1)[0]); m.orange = m.orange.filter(n => nameOf(n) !== k); m.blue = m.blue.filter(n => nameOf(n) !== k); } }
    }
    else msg = '(not simulated: ' + action + ')';
    schedule('customs'); return msg;
  }
  function setOv(o) { const until = Date.now() + 5000; for (const k in o) if (o[k] != null) ui.ov[k] = { v: o[k], until }; schedule('customs'); setTimeout(() => schedule('customs'), 5100); }
  async function sendCustom(action, value, btn, raw) {
    if (action === 'activity' && !ui.sim && !raw) {   // the Host's !activity does not set KOTH/team size/mode: send those too (defaults in master-core)
      const sub = String(value || '').split(' ').pop(), c = S.get('customs') || {}, d = C.ACTIVITY_DEFAULTS[sub] || {};
      const steps = C.activityPlan(sub, { koth: !!c.koth, format: c.format, mode: c.mode });
      setOv({ activity: sub === 'end' ? 'none' : sub, koth: d.koth == null ? null : d.koth ? 'on' : 'off', format: d.format, mode: d.mode });
      const ok = await sendCustom(action, value, btn, true); if (ok) for (const [a, v2] of steps) await sendCustom(a, v2, null, true); return ok;
    }
    if (ui.sim) { flash(btn); const m = simApply(action, value); if (m) toast(m); return !/no empty slot|not waiting|No game/.test(m || ''); }
    const text = C.customsText(action, value); if (!text) { toast('Not allowed: ' + action, true); return false; }
    const now = Date.now(), last = ui.sent.get(text) || 0;
    if (now - last < 1200) { toast('Already sent ' + text); return false; }
    ui.sent.set(text, now); flash(btn); if (!ui.tookControl) { ui.tookControl = true; schedule('customs'); } await tokenReady;
    let r = null;
    if (HOSTMOD.has(action.startsWith('queue-') ? 'queue' : action) && S.get('customsMod') !== false) {
      r = await api.post('/api/customs/mod', action.startsWith('queue-') ? { action: 'queue', value: action.slice(6) } : { action, value: value || '' });
      if (r.status === 404) { S.set({ customsMod: false }); r = null; }
    }
    if (!r) r = await api.post('/api/run', { text, user: 'broadcaster' });
    if (r.ok) { toast('Sent ' + text); if (r.json && r.json.customs) S.set({ customs: r.json.customs, customsOk: true }); else pollers.customs.kick(); }
    else { ui.sent.delete(text); toast(text + ': ' + r.error, true); }
    return r.ok;
  }

  // Docked player (bottom right). Data: /api/state (+ /api/now fallback); Stream volume/device = the Spotify Connect device.
  const pl = { volAt: 0, devs: null, mini: ls.get('plmini') === '1', flip: null };
  function plView() {
    const st = S.get('mstate'), n = S.get('now') || {}, p = (st && st.playback) || null, t = (p && p.track) || null;
    const req = (st && st.now_item && st.now_item.requester) || n.requestedBy || '';
    return { title: t ? t.name : n.title, artist: t ? (t.artists || []).join(', ') : n.artist, album: t ? t.album : '', art: t ? t.art : '',
      playing: p ? !!p.is_playing : null, prog: p ? p.progress_ms : 0, dur: t ? t.duration_ms : 0, vol: p && p.device ? p.device.volume : null, dev: p && p.device ? p.device.name : '', req };
  }
  function renderMusic() {
    const ok = S.get('nowOk'), box = $('#player'), v = plView();
    box.hidden = ok === null; box.classList.toggle('mini', pl.mini); box.classList.toggle('off', ok === false);
    $('#pl-title').textContent = ok === false ? 'Spotify module not reachable' : v.title || 'Nothing playing';
    $('#pl-artist').textContent = v.artist || ''; $('#pl-album').textContent = v.album || '';
    $('#pl-req').textContent = v.req ? 'req ' + v.req : '';
    const art = $('#pl-art'), cur = art.querySelector('img');
    if (v.art && (!cur || cur.dataset.u !== v.art)) { const im = h('img'); im.dataset.u = v.art; im.alt = ''; im.onerror = () => im.remove(); im.src = v.art; art.prepend(im); if (cur) cur.remove(); }
    else if (!v.art && cur) cur.remove();
    const playing = pl.flip && Date.now() < pl.flip.until ? pl.flip.v : v.playing;
    $('#pl-play').textContent = playing ? '⏸' : '▶';
    $('#pl-prog').style.width = v.dur ? Math.min(100, v.prog / v.dur * 100) + '%' : '0';
    const vs = $('#pl-vst');
    if (v.vol != null && document.activeElement !== vs && Date.now() - pl.volAt > 2000) { vs.value = v.vol; $('#pl-vn').textContent = v.vol + '%'; }
    $('#pl-dst').title = v.dev ? 'Playing on ' + v.dev : 'Pick the Spotify device that plays';
    $$('#player button[data-mu], #player [data-pl], #pl-vol').forEach(b => { b.disabled = ok === false; });
    vs.disabled = ok === false;
  }
  async function musicAction(action, btn) {
    flash(btn); const n = plView(); await tokenReady;
    const r = await mapi.post('/api/mod-action', { action });
    if (r.ok && r.json && r.json.ok !== false) { toast(({ like: 'Liked', skip: 'Skipped', previous: 'Back', ban_song: 'Song banned', ban_artist: 'Artist banned' })[action] + ((r.json.title || n.title) ? ': ' + (r.json.title || n.title) : '')); pollers.music.kick(); }
    else toast(action + ': ' + ((r.json && (r.json.error || r.json.code)) || r.error), true);
  }
  async function playerCtl(action, value, btn) {
    if (btn) flash(btn); await tokenReady;
    const r = await mapi.post('/api/control', value === undefined ? { action } : { action, value });
    if (r.ok && !(r.json && r.json.ok === false)) pollers.music.kick();
    else toast(action + ': ' + ((r.json && (r.json.error || r.json.code)) || r.error || 'HTTP ' + r.status), true);
    return r;
  }
  function plToggle(btn) {
    const v = plView(), want = !(pl.flip && Date.now() < pl.flip.until ? pl.flip.v : v.playing);
    pl.flip = { v: want, until: Date.now() + 1500 }; renderMusic();
    playerCtl(want ? 'resume' : 'pause', undefined, btn).then(r => { if (!r.ok) { pl.flip = null; renderMusic(); } });
  }
  let volTimer = 0;
  function plVolume() {
    const val = +$('#pl-vst').value; pl.volAt = Date.now(); $('#pl-vn').textContent = val + '%';
    clearTimeout(volTimer); volTimer = setTimeout(() => playerCtl('volume', val), 150);
  }
  async function plDevices() {
    const box = $('#pl-devs'); if (!box.hidden) { box.hidden = true; return; }
    box.hidden = false; box.replaceChildren(h('span', 'faint sm', 'Loading devices…'));
    const r = await mapi.get('/api/devices'), cur = (plView().dev);
    if (!r.ok) { box.replaceChildren(h('span', 'faint sm', 'Could not load devices: ' + (r.error || 'HTTP ' + r.status))); return; }
    const list = (r.json && r.json.devices) || [];
    if (!list.length) { box.replaceChildren(h('span', 'faint sm', 'No Spotify devices found. Open Spotify on this PC.')); return; }
    box.replaceChildren(...list.map(d => { const b = h('button', 'sm' + (d.is_active || d.name === cur ? ' g' : ''), (d.is_active ? '● ' : '') + d.name); b.dataset.dev = d.id; b.title = d.type + (d.volume_percent != null ? ' · ' + d.volume_percent + '%' : ''); return b; }));
  }

  /* ---------- status bar ---------- */
  function pill(id, cls, label) { const e = $('#' + id); if (!e) return; e.className = 'pill ' + cls; e.lastChild.textContent = label; }
  function renderBar() {
    const live = S.get('live'), os = S.get('obsStatus'), ho = S.get('host'), tree = S.get('tree'), up = S.get('hostUp'), link = S.get('link');
    pill('p-live', live ? (live.live ? 'live' : '') : '', live ? (live.live ? 'LIVE' : 'Offline') : '…');
    const obsOn = os ? os.connected : tree.connected;
    pill('p-obs', obsOn ? 'ok' : 'bad', obsOn ? 'OBS' : 'OBS off');
    pill('p-rec', os && os.recording ? 'live' : '', os && os.recording ? 'Recording' : 'Not recording');
    const rb = os && os.replayBuffer; pill('p-rb', rb && rb.active ? 'ok' : (os && os.replayBufferEnabled ? 'warn' : ''), rb && rb.active ? 'Replay on' : 'Replay off');
    pill('p-chat', ho ? (ho.chatConnected && ho.eventSubConnected ? 'ok' : 'warn') : '', ho ? (ho.chatConnected ? 'Chat' : 'Chat off') + (ho.eventSubConnected ? '' : ' · no events') : 'Chat');
    pill('p-link', up === false ? 'bad' : (link.sse ? 'acc' : 'ok'), up === false ? 'Host offline' : (link.sse ? '⚡ push' : 'poll') + (link.ms != null ? ' ' + link.ms + ' ms' : ''));
    const off = $('#offline'); let msg = '';
    if (up === false) msg = 'The Host is not answering on ' + HOST.replace('http://', '') + '. Showing the last known state; controls are paused until it is back.';
    else if (!tree.connected) msg = 'OBS is not connected to the Host. Scenes below are the last ones seen (greyed); start OBS or check the websocket settings.';
    off.hidden = !msg; off.textContent = msg;
    $('#pane-scenes').style.opacity = tree.connected && up !== false ? '' : '.6';
    $('#pane-sources').style.opacity = tree.connected && up !== false ? '' : '.6';
  }

  /* ---------- scenes + sources ---------- */
  let rowsScenes = [], rowsSources = [];
  const effCurrent = () => (opt.has('scene') ? opt.get('scene') : S.get('tree').current);
  const viewScene = () => ui.view || effCurrent();
  const itemKey = id => 'i:' + viewScene() + ':' + id;

  function mkSceneRow() { const d = h('div', 'r'); d.setAttribute('role', 'option'); d.append(h('span', 'tw'), h('span', 't')); return d; }
  function updSceneRow(el, r) {
    el.className = 'r ' + (r.type === 'folder' ? 'folder' : 'scene') + (r.current || r.hasCurrent ? ' cur' : '') + (r.type === 'scene' && r.view ? ' view' : '') + (r.kb ? ' kb' : '');
    el.style.paddingLeft = 6 + (r.indent || 0) * 16 + 'px';
    el.dataset.a = r.type; el.dataset.n = r.name; el.title = r.type === 'scene' ? r.name : r.name + ' (folder)';
    el.firstChild.textContent = r.type === 'folder' ? (r.collapsed ? '▸' : '▾') : '';
    el.lastChild.textContent = r.label;
    if (r.type === 'folder') { el.lastChild.textContent = r.label; el.lastChild.dataset.n = r.count; }
    el.setAttribute('aria-selected', r.current ? 'true' : 'false');
  }
  function renderScenes() {
    const tree = S.get('tree'), cur = effCurrent(), vs = viewScene();
    const rows = C.buildSceneRows(tree.scenes, { query: ui.query, collapsed: ui.folders, current: cur });
    rows.forEach(r => { r.kb = ui.pane === 'scenes' && ui.kb.scenes === r.key; r.view = r.type === 'scene' && r.name === vs && vs !== cur; });
    rowsScenes = rows;
    C.reconcile($('#scenes'), rows, r => r.key, mkSceneRow, updSceneRow);
    $('#scene-count').textContent = tree.scenes.length ? tree.scenes.length + ' scenes' : '';
  }
  function mkItemRow() { const d = h('div', 'r'); d.setAttribute('role', 'option'); d.append(h('span', 'tw'), h('span', 'eye'), h('span', 't'), h('span', 'k')); return d; }
  function updItemRow(el, r) {
    el.className = 'r ' + r.type + (r.enabled ? ' on' : '') + (r.dimmed ? ' dim' : '') + (r.kb ? ' kb' : '') + (r.pend ? ' pend' : '');
    el.style.paddingLeft = 6 + r.depth * 16 + 'px';
    el.dataset.a = r.type; el.dataset.id = r.id; el.title = r.name + (r.kind ? ' · ' + r.kind : '');
    const [tw, eye, t, k] = el.children;
    tw.textContent = r.type === 'group' ? (r.collapsed ? '▸' : '▾') : ''; eye.textContent = r.enabled ? '◉' : '○'; t.textContent = r.name;
    k.textContent = r.type === 'group' ? r.count + ' items' : shortKind(r.kind);
  }
  const shortKind = k => String(k || '').replace(/_source$/, '').replace(/^OBS_SOURCE_TYPE_/, '').replace(/_/g, ' ').toLowerCase();
  function renderSources() {
    const tree = S.get('tree'), vs = viewScene();
    const items = tree.scene === vs ? tree.items : (ui.itemsBy[vs] || []);   // last seen items of that scene, so a switch never flashes an empty list
    const rows = C.buildItemRows(items, { query: ui.query, collapsed: ui.groups, override: id => (opt.has(itemKey(id)) ? opt.get(itemKey(id)) : undefined) });
    rows.forEach(r => { r.kb = ui.pane === 'sources' && ui.kb.sources === r.key; r.pend = opt.has(itemKey(r.id)); });
    rowsSources = rows;
    C.reconcile($('#sources'), rows, r => r.key, mkItemRow, updItemRow);
    $('#src-scene').textContent = vs ? '· ' + vs + (ui.view && ui.view !== tree.current ? ' (viewing)' : '') : '';
    $('#src-follow').style.visibility = ui.view ? '' : 'hidden';
  }

  async function goScene(name, onlyView) {
    if (!name) return;
    if (onlyView) { ui.view = name; renderSources(); renderScenes(); pollers.tree.kick(); return; }
    ui.view = null; opt.set('scene', name); renderScenes(); renderSources();     // instant: the click is visible before the Host answers
    pollers.tree.kick();    // fetch the new scene's sources in parallel with the switch
    await tokenReady;
    const r = await api.post('/api/obs/scene', { scene: name });
    if (!r.ok) { opt.drop('scene'); renderScenes(); renderSources(); toast('Scene: ' + r.error, true); } else setTimeout(() => pollers.tree.kick(), 60);
  }
  async function toggleItem(id) {
    const tree = S.get('tree'), vs = viewScene(), items = tree.scene === vs ? tree.items : (ui.itemsBy[vs] || []);
    const it = C.findItem(items, id); if (!it) return;
    const k = itemKey(id), now = opt.has(k) ? opt.get(k) : !!it.enabled, want = !now;
    opt.set(k, want); renderSources();
    await tokenReady;
    const r = await api.post('/api/obs/item', { scene: vs, itemId: id, enabled: want });
    if (!r.ok) { opt.drop(k); renderSources(); toast(it.name + ': ' + r.error, true); } else setTimeout(() => pollers.tree.kick(), 60);
  }

  function applyTree(t, fromCache) {
    if (!t || typeof t !== 'object') return;
    if (t.connected === false && S.get('tree').scenes.length) { S.set({ tree: Object.assign({}, S.get('tree'), { connected: false }), treeStale: true }); return; }   // keep the last scenes while OBS is away
    if (t.scene) ui.itemsBy[t.scene] = t.items || [];
    S.set({ tree: t, treeStale: false });
    if (opt.has('scene')) opt.settle('scene', t.current);
    (function settle(list) { for (const it of list || []) { opt.settle('i:' + t.scene + ':' + it.id, !!it.enabled); if (Array.isArray(it.children)) settle(it.children); } })(t.items);
  }

  /* ---------- customs / wheel ---------- */
  /* Customs panel: categories like the website's Master View (Activity, Queue, Match, Next match, Teams, Settings, KOTH, Players, Wheel), colour coded
     green = open/positive, red = close/destructive, orange/blue = team results, in the app's compact sizing. Every click takes control (the Host runs it as the broadcaster). */
  function mkCustomsSkeleton() {
    const b = (label, a, v, cls, st, tip) => `<button class="sm ${cls || ''}" data-cu="${a}"${v != null ? ` data-v="${v}"` : ''}${st ? ` data-st="${st}"` : ''}${tip ? ` title="${tip}"` : ''}>${label}</button>`;
    const sec = (cls, title, body, sub) => `<section class="cs ${cls}"><h4>${title}${sub || ''}</h4>${body}</section>`;
    const seg = (key, items) => `<div class="seg">${items.map(([l, v]) => b(l, key, v, '', key + ':' + v)).join('')}</div>`;
    $('#tab-customs').innerHTML = `
      <div class="ctl free" id="cu-ctl"><span id="cu-who">In control: …</span><span class="sp"></span><span class="faint" id="cu-badge"></span><button class="sm" id="cu-sim" title="Play with fake players: nothing is sent to the Host">🧪 Simulator</button></div>
      <div id="cu-note" class="note" hidden></div>
      <div class="cgrid">
        ${sec('c-act', 'Activity', `<div class="btns">${[['Competitive', 'competitive'], ['Casual', 'casual'], ['KOTH', 'koth'], ['Viewers', 'viewers']].map(([l, v]) => b(l, 'activity', 'rl ' + v, 'rd warn', 'activity:' + v)).join('')}${b('End activity', 'activity', 'end', 'rd warn')}</div>`, ' <span class="faint" id="cu-act"></span>')}
        <section class="cs c-ask" id="cu-ask" hidden><b id="cu-ask-t"></b><div class="faint sm" id="cu-ask-s"></div><div class="btns" style="margin-top:6px"><button class="sm rd" data-ask="remove" title="Cancel the game and take everyone out of the queue">Remove them</button><button class="sm pri" data-ask="back" title="Cancel the game; players go back to the front of the queue in their old order, ahead of anyone who joined later">Put back in queue</button><button class="sm" data-ask="keep" title="Change it and leave everyone as they are">Leave as is</button><button class="sm ghost" data-ask="cancel" title="Do not change anything">✕</button></div></section>
        <section class="cs c-st"><div class="row"><span class="faint sm">Streamer</span><div class="seg" style="flex:1">${b('In', 'streamer', 'in', '', 'streamer:in')}${b('Out', 'streamer', 'out', '', 'streamer:out')}</div></div></section>
        ${sec('c-q', 'Queue', `<div class="btns">${b('Open', 'queue-open', null, 'g', 'queue:open')}${b('Close', 'queue-close', null, 'rd', 'queue:close')}${b('Clear', 'queue-clear', null, 'og warn', 'queue:clear')}</div><ul class="qlist" id="cu-queue"></ul>`, ' <span class="faint" id="cu-qn"></span>')}
        ${sec('c-m', 'Match', `<div class="btns">${b('Fill', 'match', 'fill', 'g')}${b('Move all → Queue', 'match', 'queue')}${b('Clear match', 'match', 'clear', 'rd warn')}${b('Orange wins', 'finish', 'orange', 'or', 'win:orange')}${b('Blue wins', 'finish', 'blue', 'bl', 'win:blue')}</div><div class="teams" id="cu-teams"></div>`, ' <span class="faint" id="cu-match"></span>')}
        ${sec('c-t', 'Teams', `${seg('mode', [['Balanced', 'balanced'], ['Random', 'random'], ['Manual', 'picks']])}<div class="btns" style="margin-top:6px">${b('Reroll', 'reroll')}${b('Balance', 'balance')}</div><div class="row" id="cu-manual" style="margin-top:6px" hidden><input type="text" id="cu-pick" placeholder="who goes Blue" autocomplete="off" spellcheck="false" style="flex:1;min-width:0"><button class="sm bl" id="cu-pickgo">Set Blue</button>${b('Auto', 'pick', 'auto')}</div>`)}
        ${sec('c-s', 'Settings', `<div class="lbl">Team size</div>${seg('format', ['1v1', '2v2', '3v3', '4v4'].map(x => [x, x]))}<div class="lbl">Game mode</div>${seg('gamemode', [['Standard', 'standard'], ['Dropshot', 'dropshot'], ['Rumble', 'rumble']])}`)}
        ${sec('c-k', 'KOTH', `${seg('koth', [['Off', 'off'], ['On', 'on']])}<div class="faint sm" style="margin-top:4px">On: winners stay, challengers come in.</div>`)}
        ${sec('c-p', 'Players', `<div class="row"><input type="text" id="cu-kick" placeholder="Kick by name" style="flex:1;min-width:0" autocomplete="off" spellcheck="false"><button class="sm rd" id="cu-kickgo">Kick</button></div>`)}
        ${sec('c-sim', 'Player simulator', `<div class="btns">${b('+ Player', 'sim', 'add')}${b('+ 4', 'sim', 'add4')}${b('+ 8', 'sim', 'add8')}${b('Remove one', 'sim', 'rm')}${b('Reset sim', 'sim', 'reset', 'rd')}</div><div class="row" style="margin-top:6px"><button class="sm" id="cu-simchat" title="Speak the simulator's events in the real Twitch chat (Chatty), so you can judge the wording">Chat: ON</button><span class="faint sm" id="cu-simnote"></span></div>`)}
        ${sec('c-w', 'Wheel', `<div class="btns"><button class="sm pri" data-wh="spin">Spin</button><button class="sm" data-wh="new">New round</button><button class="sm rd warn" data-wh="reset">Reset</button></div><div class="btns" style="margin-top:6px"><button class="sm" id="wh-q" data-wq="queue">Queue</button><button class="sm" id="wh-t" data-wq="tourney" title="Open the wheel for tournament sign-ups (!wheel open)">Tourney</button></div><div class="kv" style="margin-top:6px" id="wh-kv"></div>`, ' <span class="faint" id="wh-badge"></span>')}
      </div>`;
  }
  const curCustoms = () => (ui.sim ? ui.simState : S.get('customs'));
  const strikesFor = u => { const c = curCustoms(), k = String(u).toLowerCase(), x = c && c.strikes && c.strikes[k]; return C.normStrike(x || ui.strikeOv[k]); };
  const strikesKnown = u => { const c = curCustoms(); return !!(c && c.strikes && c.strikes[String(u).toLowerCase()]); };
  function strikeBtn() { const b = h('button', 'sbtn'); return b; }
  function fillStrike(b, u) {
    const s = strikesFor(u), c = curCustoms(), sig = JSON.stringify([s, u, strikesKnown(u), c && c.strikeLimit]); if (b._s === sig) return; b._s = sig;
    b.dataset.su = u; b.textContent = ''; C.strikeMarks(s, c && c.strikeLimit).forEach(k => b.append(h('i', 'k-' + k, k === 'half' ? '½' : 'I')));
    b.title = (s.perma ? s.perma + ' permanent, ' : '') + (s.temp ? s.temp + ' temporary' : '') + (s.half ? ' + a half' : '') || 'No strikes';
    if (!s.perma && !s.temp && !s.half) b.title = strikesKnown(u) ? 'No strikes. Click to add or remove' : 'Click to add or remove a strike';
    else b.title += '. Click to add or remove';
  }
  function playerRow(u, label, from) {
    const d = h('div', 'pr'); d.draggable = true; d.dataset.u = u; d.dataset.from = from;
    const sb = strikeBtn(), x = h('button', 'x ghost sm', '✕'); x.title = 'Remove from the game (back out, then off the queue)';
    d.append(h('span', 't ell', label), sb, x); fillStrike(sb, u); return d;
  }
  function renderPop() {
    const pop = $('#strikepop'), u = ui.pop, btn = u && $$('#tab-customs .sbtn').find(b => b.dataset.su === u);
    if (!btn) { ui.pop = null; pop.hidden = true; return; }
    const s = strikesFor(u); pop.hidden = false; pop.dataset.u = u; pop.querySelector('.pu').textContent = u;
    pop.querySelector('[data-sa="rm"]').disabled = strikesKnown(u) && !s.temp && !s.half && !s.perma;
    const r = btn.getBoundingClientRect(); pop.style.left = Math.max(4, Math.min(innerWidth - pop.offsetWidth - 4, r.left - 20)) + 'px'; pop.style.top = Math.max(4, Math.min(innerHeight - pop.offsetHeight - 4, r.bottom + 4)) + 'px';
  }
  async function doStrike(u, kind) {
    const s = strikesFor(u), perma = kind === 'perma' || (kind === 'rm' && !s.temp && !s.half && s.perma > 0), suffix = perma ? ' perma' : '';
    const ok = await sendCustom(kind === 'rm' ? 'unstrike' : 'strike', u + suffix);
    if (ok && !ui.sim && !strikesKnown(u)) {   // the Host does not send strike counts yet: keep a local tally so the chip still moves
      const k = u.toLowerCase(), o = ui.strikeOv[k] = C.normStrike(ui.strikeOv[k]), key = perma ? 'perma' : 'temp'; o[key] = Math.max(0, o[key] + (kind === 'rm' ? -1 : 1));
    }
    schedule('customs');
  }
  async function dropTo(t) {
    const d = ui.drag; if (!d) return; const c = curCustoms() || {}, q = (c.queue || []).map(p => String(p.username || p.user || p.name || '').toLowerCase());
    if (t.kind === 'queue') {
      if (d.from === 'queue') { const fi = q.indexOf(d.u), pos = C.dropPos(fi, t.idx, t.after); if (fi >= 0 && pos - 1 !== fi) sendCustom('move', d.u + ' ' + pos); }
      else { const pos = C.dropPos(-1, t.idx, t.after); if (await sendCustom('out', d.u) && pos > 1) sendCustom('move', d.u + ' ' + pos); }
    } else {
      if (d.from === t.team) return; const m = c.match, size = +String(c.format || '2v2')[0] || 2;
      if (!m || m.status === 'finished') { toast('No game is running', true); return; }
      if ((m[t.team] || []).length >= size) { toast(t.team + ' is full: drag someone out first', true); return; }
      sendCustom('in', d.u + ' ' + t.team);
    }
  }
  /* ---------- wheel: Queue / Undo, Cancel, Tourney ---------- */
  const queueNames = () => ((curCustoms() && curCustoms().queue) || []).map(p => String(p.username || p.user || p.name || '').toLowerCase()).filter(Boolean);
  const simWheel = () => ui.simState.wheel;
  async function wheelEntrants() {
    if (ui.sim) return simWheel().entrants.slice();
    const r = await api.get('/api/wheel/state'); return r.ok ? (r.json.entrants || []).map(x => String(x && x.login || x && x.name || x).toLowerCase()) : null;
  }
  function wheelErr(r, what, need) { if (r.status === 404) toast(what + ' needs the Host ' + need + ' (asked 02, not there yet)', true); else toast(what + ': ' + ((r.json && (r.json.error || r.json.code)) || r.error || 'HTTP ' + r.status), true); }
  function setWq(v) { ui.wq = v; ls.set('wq', v); schedule('customs'); }
  async function wheelQueue() {
    const q = queueNames(); if (!q.length) { toast('The queue is empty', true); return; }
    const cur = await wheelEntrants(); if (cur === null) { toast('Could not read the wheel', true); return; }
    const add = q.filter(u => !cur.includes(u)); if (!add.length) { toast('Everyone in the queue is already on the wheel'); return; }
    if (ui.sim) { simWheel().entrants.push(...add); if (simWheel().status === 'none') simWheel().status = 'open'; setWq({ added: add, at: Date.now() }); toast(add.length + ' added to the wheel'); return; }
    await tokenReady; ui.tookControl = true;
    const r = await api.post('/api/wheel/queue-add', { users: add });
    if (!r.ok || (r.json && r.json.ok === false)) { wheelErr(r, 'Queue → wheel', '/api/wheel/queue-add'); return; }
    const added = ((r.json && r.json.added) || add).map(x => String(x).toLowerCase()); setWq({ added, at: Date.now() });
    toast(added.length + ' added to the wheel' + (r.json && r.json.skipped && r.json.skipped.length ? ', ' + r.json.skipped.length + ' skipped' : '')); pollers.wheel.kick();
  }
  async function wheelUndo() {   // take back what Queue added, but only people still on the wheel; they return to the queue in their old order
    const wq = ui.wq; if (!wq) return;
    const cur = await wheelEntrants(); if (cur === null) { toast('Could not read the wheel', true); return; }
    const stay = wq.added.filter(u => cur.includes(u)), inQ = new Set(queueNames()), back = stay.filter(u => !inQ.has(u));
    if (ui.sim) { const W = simWheel(); W.entrants = W.entrants.filter(u => !stay.includes(u)); back.forEach(u => { const p = (ui.simState.match && ui.simState.match._p || []).find(x => x.username === u) || { username: u, display: u, mmr: 1000 }; ui.simState.queue.push(p); }); setWq(null); toast('Undone: ' + stay.length + ' off the wheel, ' + back.length + ' back in the queue'); return; }
    await tokenReady; ui.tookControl = true;
    if (stay.length) { const r = await api.post('/api/wheel/remove', { users: stay }); if (!r.ok || (r.json && r.json.ok === false)) { wheelErr(r, 'Undo', '/api/wheel/remove'); return; } }
    if (back.length) { const r = await api.post('/api/customs/queue-add', { users: back }); if (!r.ok || (r.json && r.json.ok === false)) { wheelErr(r, 'Undo (back to the queue)', '/api/customs/queue-add'); return; } }
    setWq(null); toast('Undone: ' + stay.length + ' off the wheel, ' + back.length + ' back in the queue'); pollers.wheel.kick(); pollers.customs.kick();
  }
  /* ---------- changing the activity (or the sim streamer) while people wait or play: ask what happens to them ---------- */
  const playersNow = () => {
    const c = curCustoms() || {}, m = c.match, live = !!(m && m.status !== 'finished');
    return { q: (c.queue || []).length, g: live ? (ui.sim ? (m._p || []).length : (m.orange || []).length + (m.blue || []).length) : 0, live };
  };
  function wantsAsk(action, value) {
    if (action === 'activity') { const sub = String(value || '').split(' ').pop(), c = curCustoms() || {}; if ((sub === 'end' ? 'none' : sub) === c.activity) return false; }
    else if (!(ui.sim && action === 'streamer')) return false;
    const n = playersNow(); return n.q + n.g > 0;
  }
  function renderAsk() {
    const box = $('#cu-ask'), a = ui.ask; box.hidden = !a; if (!a) return;
    const n = playersNow(), tot = n.q + n.g, what = a.action === 'activity' ? 'Switching to ' + (a.value.split(' ').pop()) : 'Streamer ' + a.value;
    $('#cu-ask-t').textContent = what + '. What about the ' + tot + ' player' + (tot === 1 ? '' : 's') + '?';
    $('#cu-ask-s').textContent = (n.g ? n.g + ' in the running game (it is cancelled)' : '') + (n.g && n.q ? ' · ' : '') + (n.q ? n.q + ' waiting' : '');
  }
  async function askDo(choice) {
    const a = ui.ask; if (!a) return; ui.ask = null; renderAsk();
    if (choice === 'cancel') return;
    const n = playersNow();
    if (choice === 'remove') { if (n.live) await sendCustom('match', 'clear', null, true); if (playersNow().q) await sendCustom('queue-clear', null, null, true); }
    else if (choice === 'back') { if (n.live) await sendCustom('match', 'queue', null, true); }   // game players return ahead of everyone who joined later (the bot's !match queue / the sim do exactly that)
    await sendCustom(a.action, a.value, null);
  }
  const holderName = c => { const x = c && c.controlHolder; return !x ? '' : typeof x === 'string' ? x : (x.name || x.display || x.user || x.id || ''); };
  function renderCustoms() {
    const c = ui.sim ? ui.simState : S.get('customs'), ok = ui.sim ? true : S.get('customsOk'), note = $('#cu-note');
    { const sc = $('#cu-simchat'); sc.textContent = 'Chat: ' + (ui.simChat ? 'ON' : 'OFF'); sc.classList.toggle('g', ui.simChat); $('#cu-simnote').textContent = ui.simChat ? 'Fake players, but the lines go to REAL chat' : 'Nothing is sent to the Host or chat'; }
    $('#cu-sim').classList.toggle('cur', !!ui.sim); $('.c-sim').hidden = !ui.sim;
    const msg = ok === false ? (c ? 'Customs state is stale (the Host stopped answering it).' : 'The Host has no /api/customs/state yet. Buttons still work (they run the same chat commands the website sends); the live queue appears once the Host has it.') : '';
    note.hidden = !msg; note.textContent = msg;
    const holder = ui.sim ? '' : holderName(c), mine = ui.tookControl && !holder;
    $('#cu-ctl').className = 'ctl ' + (ui.sim ? 'mine' : holder ? 'other' : mine ? 'mine' : 'free');
    $('#cu-who').textContent = ui.sim ? '🧪 Simulator: fake players, nothing is sent' : holder ? '🎮 In control: ' + holder : mine ? '🎮 In control: you (app)' : '🎮 In control: nobody · any click takes it';
    const q = (c && Array.isArray(c.queue)) ? c.queue : [];
    $('#cu-badge').textContent = c ? (c.open === true ? 'queue open' : c.open === false ? 'queue closed' : '') + (c.format ? ' · ' + c.format : '') + (c.gameMode && c.gameMode !== 'standard' ? ' · ' + c.gameMode : '') : '';
    $('#cu-act').textContent = c && c.activity && c.activity !== 'none' ? '· ' + c.activity : '';
    $('#cu-qn').textContent = c ? '· ' + q.length + ' waiting' : '';
    const seats = (+String((c && c.format) || '2v2')[0] || 2) * 2, isStr = p => !!(p.streamer || p.isStreamer || String(p.username || p.user || '').toLowerCase() === 'innocentpenguin');
    const strIn = q.some(isStr) || !!(c && c.match && c.match.status !== 'finished' && (ui.sim ? (c.match._p || []).some(isStr) : (c.streamer === 'in'))), gold = Math.max(1, seats - (strIn ? 1 : 0));
    let ng = 0; const kinds = q.map(p => { if (isStr(p)) return 's'; ng++; return ng <= gold ? 'n' : ng <= gold + 2 ? 'b' : ''; });
    C.reconcile($('#cu-queue'), q.map((p, i) => ({ k: kinds[i], u: String(p.username || p.user || p.name || '?').toLowerCase(), d: p.display || p.username || p.name || '?', n: i + 1, m: p.mmr, sk: JSON.stringify([strikesFor(String(p.username || p.user || p.name || '?')), strikesKnown(String(p.username || p.user || p.name || '?')), c.strikeLimit]) })), r => r.u, () => { const li = h('li'); li.draggable = true; li.dataset.from = 'queue'; li.append(h('span', 'num'), h('span', 't'), h('span', 'mmr'), h('span', 'qtag'), strikeBtn(), h('button', 'x ghost sm', '✕')); li.lastChild.title = 'Kick'; return li; },
      (li, r) => { li.dataset.u = r.u; li.className = r.k === 'n' ? 'next-up' : r.k === 'b' ? 'backup' : r.k === 's' ? 'is-streamer' : ''; li.children[0].textContent = '#' + r.n; li.children[1].textContent = r.d; li.children[2].textContent = r.m || ''; li.children[3].textContent = r.k === 'n' ? 'NEXT' : r.k === 'b' ? 'BACKUP' : r.k === 's' ? 'STREAMER' : ''; fillStrike(li.children[4], r.u); });
    const m = c && c.match, live = !!(m && m.status !== 'finished');
    $('#cu-match').textContent = m ? '· ' + (m.status || 'on') + (m.id != null ? ' #' + m.id : '') : '· none';
    const tv = JSON.stringify([m && m.orange, m && m.blue, [...(m && m.orange || []), ...(m && m.blue || [])].map(n => [strikesFor(n), strikesKnown(n)]), c && c.strikeLimit]), tb = $('#cu-teams');
    if (tb._s !== tv) { tb._s = tv; tb.textContent = ''; for (const [k, lbl] of [['orange', 'Orange'], ['blue', 'Blue']]) { const col = h('div', 'tm ' + k); col.dataset.team = k; col.append(h('b', '', lbl)); const names = (m && m[k]) || []; names.forEach(n => col.append(playerRow(String(n).toLowerCase(), n, k))); if (!names.length) col.append(h('span', 'faint', '–')); tb.append(col); } }
    renderPop(); renderAsk();
    const cur = { mode: c && c.mode, format: c && c.format, gamemode: c && (c.gameMode || c.gamemode), koth: c ? (c.koth ? 'on' : 'off') : null, activity: c && c.activity, queue: c ? (c.open ? 'open' : 'close') : null };
    cur.streamer = (ui.sim ? c && c.streamer : null) || (c && c.streamer);
    for (const k in cur) if (cur[k] == null && ui.sel[k] != null) cur[k] = ui.sel[k];
    for (const k in ui.ov) if (ui.ov[k].until > Date.now()) cur[k] = ui.ov[k].v;   // just-clicked values win until the Host state catches up   // Host offline: show what was last clicked
    for (const bt of $$('#tab-customs [data-st]')) {
      const [k, v] = bt.dataset.st.split(':'), on = cur[k] === v;
      if (k === 'win') bt.disabled = !live;
      else if (k === 'activity') bt.classList.toggle('is-live', on);
      else if (k === 'queue') bt.classList.toggle('q-on', on);
      else { bt.classList.toggle('cur', on); bt.disabled = on; }
    }
    const fb = $('#tab-customs [data-cu="match"][data-v="fill"]'); if (fb) {   // no game: Start; a running game: Fill empty slots (greyed when full or nobody waits)
      const empty = live ? (+String((c && c.format) || '2v2')[0] || 2) * 2 - (m.orange || []).length - (m.blue || []).length : 0;
      fb.textContent = !live ? '▶ Start' : 'Fill empty slots' + (empty > 0 ? ' (' + empty + ')' : ''); fb.disabled = live && (empty <= 0 || !q.length);
      fb.title = live ? 'Bring the next players from the queue into every empty slot of this game' : 'Start a game from the queue';
    }
    $('#cu-manual').hidden = !(c && c.mode === 'picks');
    const W0 = ui.sim && ui.simState.wheel, w = ui.sim ? { status: W0.status, entrantCount: W0.entrants.length, names: W0.entrants, mode: 'random', teamSize: W0.teamSize, teams: W0.teams, waitlist: [] } : S.get('wheel');
    { const wq = $('#wh-q'); wq.textContent = ui.wq ? 'Undo' : 'Queue'; wq.classList.toggle('cur', !!ui.wq); wq.disabled = !ui.wq && !queueNames().length; wq.title = ui.wq ? 'Take back what Queue added: they leave the wheel and, if they are still on it, return to the queue in their old order' : 'Copy everyone in the customs queue onto the wheel'; $('#wh-t').classList.toggle('cur', !!w && w.status === 'open'); }
    $('#wh-badge').textContent = w ? '· ' + (w.status || '?') : '';
    const kv = [['Entrants', w ? (w.entrantCount ?? (w.names || []).length) : '–'], ['Mode', w ? [w.label || w.mode, w.teamSize ? w.teamSize + 'v' + w.teamSize : ''].filter(Boolean).join(' · ') : '–'], ['Teams', w ? (w.teams || []).length : '–'], ['Waitlist', w ? (w.waitlist || []).length : '–']];
    const box = $('#wh-kv'), sigv = C.sig(kv); if (box._s !== sigv) { box._s = sigv; box.textContent = ''; kv.forEach(([a, b2]) => box.append(h('b', '', a), h('span', '', String(b2)))); }
  }

  const normWheel = w => (w && w.public && typeof w.public === 'object' ? Object.assign({}, w.public, { status: w.status || w.public.status, round: w.round, teamSize: w.teamSize || w.public.teamSize }) : w);

  /* ---------- feed ---------- */
  function mkFeed() {
    $('#tab-feed').innerHTML = '<div class="row sm" style="margin-bottom:6px;gap:4px" id="feed-chips">' + [['all', 'All'], ['chat', 'Chat'], ['players', 'Players'], ['backend', 'Backend'], ['events', 'Events']].map(([k, l]) => `<button class="sm chip" data-lc="${k}">${l}</button>`).join('') + '</div><div class="faint sm" id="feed-note" style="margin-bottom:6px"></div><div id="feedlist"></div>';
  }
  const fmtT = ts => new Date(ts * 1000).toTimeString().slice(0, 5);
  function renderFeed() {
    $$('#feed-chips .chip').forEach(c => c.classList.toggle('on', c.dataset.lc === ui.logCat));
    const rows = C.logRows(ui.feed, ui.logCat, ui.query, ui.openGroups, 300).map(r => Object.assign(r, { sg: r.kind + '|' + (r.open ? 1 : 0) + '|' + r.text + '|' + (r.label || '') + '|' + (r.blue || []) + '|' + (r.orange || []) }));
    const box = $('#tab-feed'), stick = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    C.reconcile($('#feedlist'), rows, x => x.key, () => { const d = h('div', 'feeditem'); d.append(h('span', 'ts'), h('span', 't')); return d; },
      (d, x) => {
        d.className = 'feeditem ' + (x.lvl === 'error' ? 'lvl-error ' : '') + (x.kind === 'sub' ? 'sub ' : '') + 'k-' + (x.t || (x.kind === 'group' ? 'p' : '')) + (x.t === 'e' ? ' ev' : ''); d.dataset.k = x.key;
        d.children[0].textContent = fmtT(x.ts); const t = d.children[1]; t.textContent = '';
        if (x.kind === 'group') { const a = h('a', 'grp', x.label); a.title = x.names; a.dataset.g = x.key; t.append(a, document.createTextNode(' ' + x.text + (x.open ? '' : ' (click to show)'))); }
        else if (x.kind === 'teams') { t.append(h('span', 'who', x.text + ': '), h('span', 'tb', 'Blue: ' + (x.blue.join(', ') || '–')), document.createTextNode('  '), h('span', 'to', 'Orange: ' + (x.orange.join(', ') || '–'))); }
        else if (x.t === 'c') t.append(h('span', 'who', x.user), document.createTextNode(': ' + x.text));
        else t.append(h('span', x.t === 'e' ? 'who' : 'lg lg-' + (x.lvl === 'error' ? 'error' : (x.type || 'x')), x.text));
      });
    if (stick) box.scrollTop = box.scrollHeight;
    const n = [];
    if (ui.chatOk === false) n.push('Live chat needs the Host chat feed.');
    if (ui.logsOk === false && (ui.logCat === 'backend' || ui.logCat === 'all')) n.push('Backend log (bot + overlay actions) needs the Host /api/eventlog: not connected yet. Players log is built here from queue changes (no history before this window opened).');
    if (ui.logsOk === true && !rows.length) n.push('Nothing in this log yet.');
    $('#feed-note').textContent = n.join(' ');
  }
  function addActivity(list) {
    const add = (list || []).map(a => ({ k: 'a' + a.seq, t: 'e', ts: a.ts, user: a.user || '', type: a.kind, text: C.activityLine(a) }));
    if ((list || []).length) ui.actSeq = Math.max(ui.actSeq, ...list.map(a => a.seq || 0));
    if (C.mergeFeed(ui.feed, add, x => x.k, 800)) { ui.feed.sort((a, b) => a.ts - b.ts); schedule('feed'); }
  }
  function addChat(list) {
    const add = (list || []).map(m => ({ k: 'c' + (m.seq != null ? m.seq : m.ts + m.user), t: 'c', ts: m.ts ? (m.ts > 1e11 ? m.ts / 1000 : m.ts) : Date.now() / 1000, user: m.display || m.user || '?', text: m.text || '' }));
    if ((list || []).length) ui.chatSeq = Math.max(ui.chatSeq, ...list.map(m => m.seq || 0));
    if (C.mergeFeed(ui.feed, add, x => x.k, 800)) { ui.feed.sort((a, b) => a.ts - b.ts); schedule('feed'); }
  }
  // Host logs: 02's /api/eventlog events (players + backend; chat comes from /api/chat/recent)
  function addLogs(list) {
    const add = (list || []).filter(e => e.kind === 'players' || e.kind === 'backend').map(C.normLog);
    (list || []).forEach(e => { if (e.ts > (ui.logTs[e.kind] || 0)) ui.logTs[e.kind] = e.ts; });
    if (C.mergeFeed(ui.feed, add, x => x.k, 1500)) { ui.feed.sort((a, b) => a.ts - b.ts); schedule('feed'); }
  }
  // my own actions are backend log lines too, until the Host logs them itself
  function logLocal(type, text) { if (ui.logsOk === true) return; const ts = Date.now() / 1000; C.mergeFeed(ui.feed, [{ k: 'ap:' + ts + type, t: 'b', ts, type, text, src: 'app' }], x => x.k, 800); schedule('feed'); }

  /* ---------- commands + overlays tabs ---------- */
  function mkCmds() { $('#tab-cmds').innerHTML = '<div class="row sm faint" style="margin-bottom:6px"><span>Toggle a chat command on/off for everyone. The search box at the bottom filters this list.</span></div><div id="cmdlist"></div>'; }
  function renderCmds() {
    const q = ui.query.toLowerCase(), all = S.get('cmds') || [];
    const rows = all.filter(c => !c.archived && (!q || (c.name + ' ' + (c.aliases || []).join(' ') + ' ' + (c.description || '') + ' ' + (c.category || '')).toLowerCase().includes(q))).slice(0, 250)
      .map(c => ({ id: c.id, name: c.name, d: (c.permission || '') + (c.uses ? ' · ' + c.uses + ' uses' : ''), on: opt.has('c:' + c.id) ? opt.get('c:' + c.id) : c.enabled !== false, p: opt.has('c:' + c.id) }));
    C.reconcile($('#cmdlist'), rows, r => r.id, () => { const d = h('div', 'cmd'); d.append(h('span', 't'), h('span', 'd'), h('span', 'sw')); return d; },
      (d, r) => { d.dataset.id = r.id; d.children[0].textContent = r.name; d.children[1].textContent = r.d; d.children[2].className = 'sw' + (r.on ? ' on' : ''); d.style.opacity = r.p ? '.7' : ''; });
  }
  async function toggleCmd(id) {
    const c = (S.get('cmds') || []).find(x => x.id === id); if (!c) return;
    const k = 'c:' + id, want = !(opt.has(k) ? opt.get(k) : c.enabled !== false); opt.set(k, want); renderCmds(); await tokenReady;
    const r = await api.post('/api/commands/profile', { id, enabled: want, by: 'master-view' });
    if (!r.ok) { opt.drop(k); renderCmds(); toast(id + ': ' + r.error, true); } else { c.enabled = want; setTimeout(() => { opt.drop(k); pollers.cmds.kick(); }, 400); }
  }
  function mkOverlays() {
    $('#tab-overlays').innerHTML = `<div class="sec"><h4>Files <span class="faint" id="ov-n"></span></h4><div id="ov-note" class="note" hidden></div><div id="ovlist"></div></div>
      <div class="sec"><h4>Overlay chat <span class="faint" id="oc-st"></span></h4><div class="msgs" id="oc-msgs"></div>
      <div class="chatbox"><textarea id="oc-text" placeholder="Ask for an overlay change, e.g. “make the goal bar orange”" rows="2"></textarea><div class="row"><span class="faint sm" id="oc-hint">Ctrl+Enter sends</span><span class="sp"></span><button class="pri sm" id="oc-send">Send</button></div></div></div>`;
  }
  const fsize = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n > 1024 ? Math.round(n / 1024) + ' KB' : n + ' B';
  function renderOverlays() {
    const o = S.get('overlays'), q = ui.query.toLowerCase();
    const files = ((o && o.files) || []).filter(f => !q || f.path.toLowerCase().includes(q)).map(f => ({ path: f.path, size: f.size, url: f.url, text: f.text, ren: ui.renaming === f.path }));
    $('#ov-n').textContent = o ? '· ' + (o.files || []).length : '';
    const oe = S.get('ovErr'), on = $('#ov-note'); on.hidden = !(oe || !o || !(o.files || []).length); on.textContent = oe ? 'Overlay files are not connected yet: ' + oe + '. The Host serves them from /api/overlays.' : !o ? 'Loading overlay files from the Host…' : 'No overlay files in the Host overlays folder yet.';
    if (ui.renaming) return;
    C.reconcile($('#ovlist'), files, r => r.path, () => { const d = h('div', 'of'); d.append(h('span', 't'), h('span', 'd')); for (const [a, l] of [['open', 'Open'], ['copy', 'Copy URL'], ['ren', 'Rename'], ['del', 'Delete']]) { const b = h('button', 'sm ghost' + (a === 'del' ? ' warn' : ''), l); b.dataset.ov = a; d.append(b); } return d; },
      (d, r) => { d.dataset.p = r.path; d.dataset.u = r.url; d.children[0].textContent = r.path; d.children[1].textContent = fsize(r.size); });
    const st = S.get('ochat'); $('#oc-st').textContent = st ? (st.enabled && st.hasKey ? '· ' + st.callsToday + '/' + st.dailyCalls + ' calls today' : '· off') : '';
    $('#oc-hint').textContent = st && !(st.enabled && st.hasKey) ? 'Overlay chat is switched off in the Host (needs overlaychat.json enabled + a Claude key in the vault).' : 'Ctrl+Enter sends';
    $('#oc-send').disabled = !!st && !(st.enabled && st.hasKey);
  }
  function renderOcMsgs() {
    C.reconcile($('#oc-msgs'), ui.ochatLog, m => m.k, () => h('div', 'msg'), (d, m) => { d.className = 'msg' + (m.me ? ' me' : ''); d.textContent = ''; d.append(document.createTextNode(m.text)); (m.proposals || []).forEach(p => { const b = h('button', 'sm', 'Apply ' + (p.path || p.id)); b.dataset.apply = p.id; b.style.display = 'block'; b.style.marginTop = '6px'; d.append(b); }); });
    $('#oc-msgs').scrollTop = 1e9;
  }
  async function askOverlay() {
    const ta = $('#oc-text'), text = ta.value.trim(); if (!text) return;
    ta.value = ''; ui.ochatLog.push({ k: 'm' + ui.ochatLog.length, me: true, text }); renderOcMsgs();
    const pend = { k: 'm' + ui.ochatLog.length, text: '…' }; ui.ochatLog.push(pend); renderOcMsgs(); await tokenReady;
    const r = await api.post('/api/overlaychat/ask', { text, user: 'master-view' }, { timeoutMs: 120000 });
    pend.text = r.ok ? (r.json.text || 'Done.') + ((r.json.files || []).length ? '\nFiles: ' + r.json.files.join(', ') : '') : 'Error: ' + r.error; pend.proposals = r.ok ? r.json.proposals : null; pend.k += 'r'; renderOcMsgs();
  }

  /* ---------- rendering scheduler (poll-driven renders coalesce to one per tick; clicks render synchronously) ---------- */
  const dirty = new Set(); let raf = 0;
  function schedule(...names) { names.forEach(n => dirty.add(n)); if (!raf) raf = setTimeout(() => { raf = 0; const d = [...dirty]; dirty.clear(); d.forEach(n => R[n] && R[n]()); }, 0); }
  const R = { scenes: renderScenes, sources: renderSources, bar: renderBar, music: renderMusic, customs: renderCustoms, feed: renderFeed, cmds: renderCmds, overlays: renderOverlays };
  S.subscribe(ch => {
    if (ch.includes('tree')) schedule('scenes', 'sources', 'bar');
    if (ch.some(k => ['obsStatus', 'live', 'host', 'hostUp', 'link'].includes(k))) schedule('bar');
    if (ch.includes('customs') || ch.includes('wheel') || ch.includes('customsOk')) schedule('customs');
    if (ch.includes('customs')) { const nx = S.get('customs'); if (ui.logsOk !== true) { const add = C.diffCustoms(ui.prevCustoms, nx); if (add.length && C.mergeFeed(ui.feed, add, x => x.k, 800)) { ui.feed.sort((a, b2) => a.ts - b2.ts); schedule('feed'); } } ui.prevCustoms = nx; }
    if (ch.includes('now') || ch.includes('nowOk')) schedule('music');
    if (ch.includes('cmds')) schedule('cmds');
    if (ch.includes('overlays') || ch.includes('ochat') || ch.includes('ovErr')) schedule('overlays');
  });

  /* ---------- pollers ---------- */
  const visible = () => !document.hidden;
  let linkMs = []; const noteMs = ms => { linkMs.push(ms); if (linkMs.length > 8) linkMs.shift(); S.set({ link: { sse: S.get('link').sse, ms: Math.round(linkMs.reduce((a, b) => a + b, 0) / linkMs.length) } }); };
  const sse = () => S.get('link').sse;
  function seen(r) { if (r.status > 0) { if (S.get('hostUp') !== true) S.set({ hostUp: true }); noteMs(r.ms); } else if (S.get('hostUp') !== false) S.set({ hostUp: false }); }
  const P = (interval, run, shouldRun) => C.createPoller({ interval, run, shouldRun: shouldRun || visible });
  const pollers = {
    tree: P(() => (sse() ? 4000 : 450), async () => { const vs = viewScene(), q = vs && vs !== S.get('tree').current ? '?scene=' + encodeURIComponent(vs) : ''; const r = await api.get('/api/obs/tree' + q); seen(r); if (r.ok) { applyTree(r.json); saveCacheSoon(); } }),
    slow: P(() => (sse() ? 6000 : 2000), async () => {
      const [a, b, c] = await Promise.all([api.get('/api/obs/status'), api.get('/api/status'), api.get('/api/live')]);
      seen(a); const p = {}; if (a.ok) p.obsStatus = a.json; if (b.ok) p.host = b.json; if (c.ok) p.live = c.json; S.set(p);
    }),
    customs: P(() => (sse() ? 4000 : 1000), async () => {
      const r = await api.get('/api/customs/state'); if (r.status === 404 || r.status === 0) { if (S.get('customsOk') !== false) S.set({ customsOk: false }); return; }
      if (r.ok) { S.set({ customs: r.json, customsOk: true }); saveCacheSoon(); }
    }),
    wheel: P(() => (sse() ? 4000 : 1500), async () => { const r = await api.get('/api/wheel/public'); if (r.ok) S.set({ wheel: normWheel(r.json) }); }),
    activity: P(() => (sse() ? 5000 : 1500), async () => { const r = await api.get('/api/activity?since=' + ui.actSeq + '&limit=60'); if (r.ok) addActivity(r.json.items); }),
    chat: P(() => (ui.chatOk === false ? 30000 : (sse() ? 4000 : 800)), async () => {
      const r = await api.get('/api/chat/recent?since=' + ui.chatSeq + '&limit=50');
      if (r.status === 404) { ui.chatOk = false; schedule('feed'); return; }
      if (r.ok) { ui.chatOk = true; addChat(Array.isArray(r.json) ? r.json : r.json.items || r.json.messages); }
    }),
    logs: P(() => (ui.logsOk === false ? 30000 : (sse() ? 5000 : 1200)), async () => {
      const got = await Promise.all(['players', 'backend'].map(k => api.get('/api/eventlog?kind=' + k + '&limit=' + (ui.logTs[k] ? 500 : 300) + (ui.logTs[k] ? '&since=' + ui.logTs[k] : ''))));
      if (got.every(r => r.status === 404)) { if (ui.logsOk !== false) { ui.logsOk = false; schedule('feed'); } return; }
      if (got.some(r => r.ok)) { if (ui.logsOk !== true) { ui.logsOk = true; schedule('feed'); } got.forEach(r => r.ok && addLogs(r.json.events)); }
    }),
    music: P(() => (document.hidden ? 8000 : 2500), async () => {
      const [a, b] = await Promise.all([mapi.get('/api/now'), mapi.get('/api/state')]);
      if (a.ok || b.ok) S.set({ now: a.ok ? a.json : S.get('now'), mstate: b.ok ? b.json : null, nowOk: true }); else S.set({ nowOk: false });
    }),
    cmds: P(5000, async () => { const r = await api.get('/api/commands/profiles'); if (r.ok) S.set({ cmds: r.json.commands || [] }); }, () => visible() && ui.tab === 'cmds'),
    overlays: P(8000, async () => { const [a, b] = await Promise.all([api.get('/api/overlays'), api.get('/api/overlaychat/status')]); const p = { ovErr: a.ok ? null : (a.error || 'HTTP ' + a.status) }; if (a.ok) p.overlays = a.json; if (b.ok) p.ochat = b.json; S.set(p); }, () => visible() && ui.tab === 'overlays'),
  };
  let cacheT = 0; function saveCacheSoon() { if (!cacheT) cacheT = setTimeout(() => { cacheT = 0; saveCache(); }, 3000); }
  setInterval(() => { if (opt.expire().length) { schedule('scenes', 'sources', 'cmds'); } }, 500);   // unconfirmed optimistic changes fall back to what the Host says

  /* ---------- live push from the Host (/api/events, see Docs/MASTER_VIEW_APP.md); polling keeps running slowly as a safety net ---------- */
  const events = C.createEvents({
    url: HOST + '/api/events', fetch: (u, o) => fetch(u, o),
    onState: on => { S.set({ link: { sse: on, ms: S.get('link').ms } }); if (!on) Object.values(pollers).forEach(p => p.kick()); },
    onMessage: m => {
      const d = m.data;
      if (m.event === 'snapshot' && d) { d.obs && applyTree(d.obs); d.obsstatus && S.set({ obsStatus: d.obsstatus }); d.live && S.set({ live: d.live }); d.customs && S.set({ customs: d.customs, customsOk: true }); d.wheel && S.set({ wheel: normWheel(d.wheel) }); d.chat && addChat(d.chat);  d.activity && addActivity(d.activity); }
      else if (m.event === 'obs') applyTree(d); else if (m.event === 'obsstatus') S.set({ obsStatus: d }); else if (m.event === 'live') S.set({ live: d });
      else if (m.event === 'customs') S.set({ customs: d, customsOk: true }); else if (m.event === 'wheel') S.set({ wheel: normWheel(d) });
      else if (m.event === 'chat') { ui.chatOk = true; addChat([d]); } else if (m.event === 'activity') addActivity([d]); else if (m.event === 'backendlog') { ui.logsOk = true; addLogs([Object.assign({ kind: 'backend' }, d)]); } else if (m.event === 'playerlog') { ui.logsOk = true; addLogs([Object.assign({ kind: 'players' }, d)]); }
    },
  });

  /* ---------- events: one delegated listener per area ---------- */
  function paneOf(el) { return el.closest('#scenes') ? 'scenes' : el.closest('#sources') ? 'sources' : null; }
  function setKb(pane, key) { ui.pane = pane; ui.kb[pane] = key; pane === 'scenes' ? renderScenes() : renderSources(); }
  $('#scenes').addEventListener('click', e => {
    const row = e.target.closest('.r'); if (!row) return; setKb('scenes', rowsScenes.find(r => r.name === row.dataset.n && r.type === row.dataset.a)?.key);
    if (row.dataset.a === 'folder') { const f = row.dataset.n; ui.folders.has(f) ? ui.folders.delete(f) : ui.folders.add(f); ls.set('folders', [...ui.folders]); renderScenes(); }
    else goScene(row.dataset.n, e.ctrlKey || e.metaKey);
  });
  $('#sources').addEventListener('click', e => {
    const row = e.target.closest('.r'); if (!row) return; const id = +row.dataset.id; setKb('sources', 'i:' + id);
    if (row.dataset.a === 'group' && e.target.closest('.tw')) { ui.groups.has(id) ? ui.groups.delete(id) : ui.groups.add(id); ls.set('groups', [...ui.groups]); renderSources(); } else toggleItem(id);
  });
  $('#sources').addEventListener('contextmenu', e => { const row = e.target.closest('.r.group'); if (row) { e.preventDefault(); const id = +row.dataset.id; ui.groups.has(id) ? ui.groups.delete(id) : ui.groups.add(id); ls.set('groups', [...ui.groups]); renderSources(); } });
  $('#scenes-fold').onclick = () => { const f = S.get('tree').folders; if (ui.folders.size) ui.folders.clear(); else f.forEach(x => ui.folders.add(x)); ls.set('folders', [...ui.folders]); renderScenes(); };
  $('#src-follow').onclick = () => { ui.view = null; renderScenes(); renderSources(); pollers.tree.kick(); };
  $('#q').addEventListener('input', e => { ui.query = e.target.value; renderScenes(); renderSources(); renderCmds(); renderOverlays(); renderFeed(); });
  $('#tab-customs').addEventListener('click', e => {
    const b = e.target.closest('button'), li = e.target.closest('.qlist li');
    if (li && b && b.classList.contains('x')) { sendCustom('kick', li.dataset.u, b); return; }
    if (b && b.dataset.ask) { askDo(b.dataset.ask); return; }
    if (b && b.dataset.wq) {
      if (b.disabled) return; flash(b);
      if (b.dataset.wq === 'queue') ui.wq ? wheelUndo() : wheelQueue(); else sendCustom('wheel', 'open', b);
      return;
    }
    if (b && b.id === 'cu-simchat') { ui.simChat = !ui.simChat; ls.set('simchat', ui.simChat ? '1' : '0'); schedule('customs'); return; }
    if (b && b.id === 'cu-sim') { ui.sim = !ui.sim; if (ui.sim && !ui.simState) { ui.simState = simFresh(); simAdd(ui.simState, 6); ui.simState.queue.push({ username: 'streamer', display: 'Streamer', mmr: 1500, streamer: true }); } schedule('customs'); return; }
    if (b && b.dataset.cu) { if (b.disabled) return; if (b.dataset.st && !ui.sim) { const [k, v] = b.dataset.st.split(':'); if (k !== 'win') { ui.sel[k] = v; schedule('customs'); } } if (b.classList.contains('warn') && !armed(b)) return; if (wantsAsk(b.dataset.cu, b.dataset.v)) { ui.ask = { action: b.dataset.cu, value: b.dataset.v }; renderAsk(); return; } sendCustom(b.dataset.cu, b.dataset.v, b); }
    else if (b && b.dataset.wh && ui.sim) { if (b.classList.contains('warn') && !armed(b)) return; const W = simWheel(), k = b.dataset.wh; if (k === 'reset') { W.entrants = []; W.teams = []; W.status = 'open'; setWq(null); } else if (k === 'new') { W.round++; W.teams = []; W.status = 'open'; } else if (W.entrants.length >= W.teamSize * 2) { W.status = 'drawing'; toast('Sim wheel: spin (draw not simulated)'); } else toast('Not enough entrants', true); schedule('customs'); }
    else if (b && b.dataset.wh) { if (b.classList.contains('warn') && !armed(b)) return; flash(b); ui.tookControl = true; tokenReady.then(() => api.post('/api/wheel/' + b.dataset.wh)).then(r => { if (r.ok) { toast('Wheel: ' + b.dataset.wh); r.json && r.json.wheel ? S.set({ wheel: normWheel(r.json.wheel) }) : pollers.wheel.kick(); } else toast('Wheel: ' + r.error, true); }); }
    else if (b && b.id === 'cu-pickgo') { const v = $('#cu-pick').value.trim().replace(/\s+/g, ' '); C.customsText('pick', v) ? (sendCustom('pick', v, b), $('#cu-pick').value = '') : toast('Type 1 to 4 Twitch names first', true); }
    else if (b && b.id === 'cu-kickgo') { C.customsText('kick', $('#cu-kick').value) ? (sendCustom('kick', $('#cu-kick').value, b), $('#cu-kick').value = '') : toast('Type a Twitch name first', true); }
  });
  $('#tab-customs').addEventListener('change', e => { const k = e.target.dataset.cuset; if (!k || !e.target.value) return; sendCustom(k, e.target.value, e.target); });
  $('#tab-customs').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.target.id === 'cu-kick' || e.target.id === 'cu-pick')) $(e.target.id === 'cu-kick' ? '#cu-kickgo' : '#cu-pickgo').click(); });
  document.body.append(Object.assign(h('div', 'strikepop'), { id: 'strikepop', hidden: true, innerHTML: '<b class="pu"></b><div class="pb"><button class="sm" data-sa="cancel" title="Cancel">✕</button><button class="sm plus" data-sa="temp" title="Add a temporary strike (wears off after a day)">+ I</button><button class="sm plus" data-sa="perma" title="Add a permanent strike (never expires)">+ I perma</button><button class="sm minus" data-sa="rm" title="Remove a strike (temporary first, then permanent)">−</button></div>' }));
  $('#tab-customs').addEventListener('click', e => {
    const sb = e.target.closest('.sbtn'); if (sb) { e.stopPropagation(); ui.pop = ui.pop === sb.dataset.su ? null : sb.dataset.su; renderPop(); return; }
    const x = e.target.closest('.pr .x'); if (x) { const u = x.closest('.pr').dataset.u; sendCustom('out', u).then(ok => ok && sendCustom('kick', u)); }
  });
  $('#strikepop').addEventListener('click', e => { const b = e.target.closest('[data-sa]'); if (!b || b.disabled) return; const u = $('#strikepop').dataset.u; if (b.dataset.sa === 'cancel') { ui.pop = null; renderPop(); return; } doStrike(u, b.dataset.sa); });
  document.addEventListener('click', e => { if (ui.pop && !e.target.closest('#strikepop, .sbtn')) { ui.pop = null; renderPop(); } });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && ui.ask) { ui.ask = null; renderAsk(); } if (e.key === 'Escape' && ui.pop) { ui.pop = null; renderPop(); } });
  const dropAt = e => {
    const li = e.target.closest('#cu-queue li'), tm = e.target.closest('.tm[data-team]'), ql = e.target.closest('#cu-queue');
    if (li) { const idx = [...li.parentNode.children].indexOf(li), r = li.getBoundingClientRect(); return { kind: 'queue', idx, after: e.clientY > r.top + r.height / 2, el: li }; }
    if (ql) return { kind: 'queue', idx: ql.children.length - 1, after: true, el: ql };
    if (tm) return { kind: 'team', team: tm.dataset.team, el: tm };
    return null;
  };
  const clearDrop = () => $$('.dropb, .dropa, .dropt, .dragging').forEach(n => n.classList.remove('dropb', 'dropa', 'dropt', 'dragging'));
  $('#tab-customs').addEventListener('dragstart', e => { const r = e.target.closest && e.target.closest('#cu-queue li, .pr'); if (!r) return; ui.drag = { u: r.dataset.u, from: r.dataset.from }; e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', r.dataset.u); } catch (_) { } r.classList.add('dragging'); });
  $('#tab-customs').addEventListener('dragend', () => { ui.drag = null; clearDrop(); });
  $('#tab-customs').addEventListener('dragover', e => { if (!ui.drag) return; const t = dropAt(e); clearDrop(); if (!t) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; t.el.classList.add(t.kind === 'team' ? 'dropt' : t.el.tagName === 'LI' ? (t.after ? 'dropa' : 'dropb') : 'dropt'); });
  $('#tab-customs').addEventListener('drop', e => { if (!ui.drag) return; const t = dropAt(e); if (!t) return; e.preventDefault(); const go = () => dropTo(t); clearDrop(); go().finally(() => { ui.drag = null; }); });
  $('#player').addEventListener('click', e => {
    const m = e.target.closest('[data-mu]'); if (m) { if (m.disabled) return; if (m.classList.contains('warn') && !armed(m)) return; musicAction(m.dataset.mu, m); return; }
    const t = e.target.closest('[data-pl]'); if (t && !t.disabled) { plToggle(t); return; }
    const d = e.target.closest('[data-dev]'); if (d) { playerCtl('transfer', d.dataset.dev, d).then(r => { if (r.ok) { toast('Playing on ' + d.textContent.replace('● ', '')); $('#pl-devs').hidden = true; } }); return; }
    if (e.target.closest('#pl-vol')) { $('#pl-menu').hidden = !$('#pl-menu').hidden; return; }
    if (e.target.closest('#pl-dst')) { plDevices(); return; }
    if (e.target.closest('#pl-min')) { pl.mini = !pl.mini; ls.set('plmini', pl.mini ? '1' : '0'); renderMusic(); }
  });
  $('#pl-vst').addEventListener('input', plVolume);
  document.addEventListener('click', e => { if (!e.target.closest('#player')) $('#pl-menu').hidden = true; });
  $('#tab-cmds').addEventListener('click', e => { const row = e.target.closest('.cmd'); if (row && e.target.closest('.sw, .t')) toggleCmd(row.dataset.id); });
  $('#tab-overlays').addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.id === 'oc-send') return askOverlay();
    if (b.dataset.apply) { await tokenReady; const r = await api.post('/api/overlaychat/apply', { id: b.dataset.apply, user: 'master-view' }); r.ok ? (toast('Applied'), b.remove(), pollers.overlays.kick()) : toast(r.error, true); return; }
    const row = b.closest('.of'); if (!row || !b.dataset.ov) return; const p = row.dataset.p, url = HOST + row.dataset.u;
    if (b.dataset.ov === 'open') { window.PGWin ? PGWin.open({ label: 'ov-' + p.replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 30), url, title: 'Overlay · ' + p, width: 960, height: 540, remember: false }).catch(x => toast(String(x.message || x), true)) : window.open(url, '_blank'); }
    else if (b.dataset.ov === 'copy') { try { await navigator.clipboard.writeText(url); toast('Copied ' + url); } catch (x) { toast(url); } }
    else if (b.dataset.ov === 'del') { if (!armed(b)) return; await tokenReady; const r = await api.post('/api/overlays/delete', { path: p }); r.ok ? (toast('Moved to the overlay trash'), pollers.overlays.kick()) : toast(r.error, true); }
    else if (b.dataset.ov === 'ren') {
      ui.renaming = p; const t = row.children[0], inp = h('input'); inp.type = 'text'; inp.value = p; inp.style.cssText = 'width:100%;padding:2px 6px'; t.replaceChildren(inp); inp.focus(); inp.select();
      const done = async ok => { const v = inp.value.trim(); ui.renaming = null; if (ok && v && v !== p) { await tokenReady; const r = await api.post('/api/overlays/rename', { from: p, to: v }); r.ok ? toast('Renamed') : toast(r.error, true); } pollers.overlays.kick(); row._s = undefined; t.textContent = p; renderOverlays(); };
      inp.onkeydown = ev => { if (ev.key === 'Enter') done(true); else if (ev.key === 'Escape') done(false); }; inp.onblur = () => ui.renaming && done(false);
    }
  });
  document.addEventListener('keydown', e => { if (e.target.id === 'oc-text' && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); askOverlay(); } });
  function setTab(t) {
    ui.tab = t; ls.set('tab', t); $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t)); $$('.tabbody').forEach(d => d.hidden = d.id !== 'tab-' + t);
    if (t === 'cmds') { pollers.cmds.kick(); renderCmds(); } if (t === 'overlays') { pollers.overlays.kick(); renderOverlays(); } if (t === 'feed') renderFeed();
  }
  $('#tabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setTab(b.dataset.tab); });
  $('#b-help').onclick = () => { $('#help').hidden = false; }; $('#help-close').onclick = () => { $('#help').hidden = true; };
  $('#help').addEventListener('click', e => { if (e.target.id === 'help') $('#help').hidden = true; });
  ['scenes', 'sources'].forEach(p => $('#' + p).addEventListener('focus', () => { ui.pane = p; p === 'scenes' ? renderScenes() : renderSources(); }));

  document.addEventListener('keydown', e => {
    const inField = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (e.key === 'Escape') { if (!$('#help').hidden) { $('#help').hidden = true; return; } if (ui.query || inField) { $('#q').value = ''; ui.query = ''; document.activeElement.blur(); renderScenes(); renderSources(); renderCmds(); renderOverlays(); renderFeed(); } return; }
    if (inField) return;
    if (e.altKey && /^[1-9]$/.test(e.key)) { const s = rowsScenes.filter(r => r.type === 'scene')[+e.key - 1]; if (s) { e.preventDefault(); goScene(s.name); } return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); return; }
    if (e.key === '?') { $('#help').hidden = !$('#help').hidden; return; }
    if (e.key === '[' || e.key === ']') { ui.pane = ui.pane === 'scenes' ? 'sources' : 'scenes'; $('#' + ui.pane).focus(); return; }
    if (e.shiftKey && !e.repeat) {
      const m = { N: ['next', ''], O: ['queue-open'], C: ['queue-close'] }[e.key.toUpperCase()];
      if (m) { e.preventDefault(); sendCustom(m[0], m[1] || '', null); return; }
      if (e.key.toUpperCase() === 'S') { e.preventDefault(); tokenReady.then(() => api.post('/api/wheel/spin')).then(r => r.ok ? toast('Wheel: spin') : toast(r.error, true)); return; }
    }
    if (/^[1-4]$/.test(e.key) && !e.shiftKey) { setTab(['customs', 'feed', 'cmds', 'overlays'][+e.key - 1]); return; }
    const pane = paneOf(document.activeElement) || ui.pane, rows = pane === 'scenes' ? rowsScenes : rowsSources;
    if (!rows.length) return;
    let i = rows.findIndex(r => r.key === ui.kb[pane]);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); i = i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1))); setKb(pane, rows[i].key); const el = $$('.r.kb', $('#' + pane))[0]; el && el.scrollIntoView({ block: 'nearest' }); return; }
    if (i < 0) return; const r = rows[i];
    if (pane === 'scenes' && e.key === 'Enter') { e.preventDefault(); if (r.type === 'folder') { ui.folders.has(r.name) ? ui.folders.delete(r.name) : ui.folders.add(r.name); ls.set('folders', [...ui.folders]); renderScenes(); } else goScene(r.name, false); }
    if (pane === 'sources' && (e.key === ' ' || e.key.toLowerCase() === 'e' || e.key === 'Enter')) { e.preventDefault(); toggleItem(r.id); }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) Object.values(pollers).forEach(p => p.kick()); });
  window.addEventListener('focus', () => Object.values(pollers).forEach(p => p.kick()));

  /* ---------- start ---------- */
  mkCustomsSkeleton(); mkFeed(); mkCmds(); mkOverlays();
  $('#feed-chips').addEventListener('click', e => { const b = e.target.closest('[data-lc]'); if (b) { ui.logCat = b.dataset.lc; ls.set('logcat', ui.logCat); renderFeed(); } });
  $('#feedlist').addEventListener('click', e => { const g = e.target.closest('a.grp'); if (g) { const k = g.dataset.g; ui.openGroups.has(k) ? ui.openGroups.delete(k) : ui.openGroups.add(k); renderFeed(); } });
  setTab(ui.tab);
  renderBar(); renderScenes(); renderSources(); renderCustoms(); renderFeed();    // first paint from the cached state, before any request returns
  tokenReady.then(() => { Object.values(pollers).forEach(p => p.start()); events.start(); });
  window.MasterView = { S, ui, opt, pollers, api, goScene, toggleItem, sendCmd, applyTree };   // for the browser console / tests
})();
