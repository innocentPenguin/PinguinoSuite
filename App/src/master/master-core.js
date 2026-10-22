/* Master View core: pure logic + transport, no DOM except reconcile(). UMD so a node harness can import it (Tests/master/run.mjs).
   Docs/MASTER_VIEW_APP.md describes the architecture. Nothing here touches the website. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MasterCore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ---------- small helpers ---------- */
  const lc = s => String(s == null ? '' : s).toLowerCase();
  const sig = v => JSON.stringify(v);

  /* ---------- store: set(patch) only notifies keys whose value really changed ---------- */
  function createStore(initial) {
    let state = Object.assign({}, initial), sigs = {}, subs = [];
    for (const k in state) sigs[k] = sig(state[k]);
    return {
      get: k => (k === undefined ? state : state[k]),
      set(patch) {
        const changed = [];
        for (const k in patch) { const s = sig(patch[k]); if (s !== sigs[k]) { sigs[k] = s; state[k] = patch[k]; changed.push(k); } }
        if (changed.length) subs.slice().forEach(f => f(changed, state));
        return changed;
      },
      subscribe(f) { subs.push(f); return () => { subs = subs.filter(x => x !== f); }; },
    };
  }

  /* ---------- optimistic overrides: apply at once, drop on confirm / failure / expiry ---------- */
  function createOptimistic(ttlMs, now) {
    now = now || Date.now;
    const m = new Map();
    return {
      set(key, value) { m.set(key, { value, until: now() + ttlMs }); },
      has: key => m.has(key),
      get(key) { const e = m.get(key); return e ? e.value : undefined; },
      drop(key) { m.delete(key); },
      /* the server answered with its own value: if it agrees the override is done; if it still disagrees keep it until ttl */
      settle(key, serverValue) { const e = m.get(key); if (e && e.value === serverValue) m.delete(key); },
      /* returns the keys whose override timed out (= the server never confirmed: the UI shows the server value again) */
      expire() { const out = []; const t = now(); for (const [k, e] of m) if (e.until <= t) { m.delete(k); out.push(k); } return out; },
      size: () => m.size,
    };
  }

  /* ---------- OBS tree -> rows ---------- */
  function matches(q, ...parts) { return !q || parts.some(p => lc(p).includes(q)); }

  /* scenes: [{name,folder,label,current}] -> flat rows [{type:'folder'|'scene', key, ...}] */
  function buildSceneRows(scenes, opts) {
    opts = opts || {};
    const q = lc(opts.query).trim(), collapsed = opts.collapsed || new Set(), cur = opts.current;
    const byFolder = new Map(), order = [];
    for (const s of scenes || []) {
      const f = s.folder || '';
      if (!byFolder.has(f)) { byFolder.set(f, []); order.push(f); }
      byFolder.get(f).push(s);
    }
    const rows = [];
    const sceneRow = (s, indent) => ({ type: 'scene', key: 's:' + s.name, name: s.name, label: s.label || s.name, current: cur != null ? s.name === cur : !!s.current, indent, folder: s.folder || '' });
    const loose = (byFolder.get('') || []);
    for (const s of loose) if (matches(q, s.name, s.label)) rows.push(sceneRow(s, 0));
    for (const f of order) {
      if (f === '') continue;
      const list = byFolder.get(f).filter(s => matches(q, s.name, s.label, f));
      if (!list.length) continue;
      const isCollapsed = !q && collapsed.has(f);
      rows.push({ type: 'folder', key: 'f:' + f, name: f, label: f, count: list.length, collapsed: isCollapsed, hasCurrent: list.some(s => (cur != null ? s.name === cur : s.current)) });
      if (!isCollapsed) for (const s of list) rows.push(sceneRow(s, 1));
    }
    return rows;
  }

  /* items: [{id,name,kind,enabled,children?}] -> rows with depth; groups can collapse; a search keeps matches and their group */
  function buildItemRows(items, opts) {
    opts = opts || {};
    const q = lc(opts.query).trim(), collapsed = opts.collapsed || new Set(), over = opts.override || (() => undefined);
    const rows = [];
    (function walk(list, depth, off) {
      for (const it of list || []) {
        const isGroup = Array.isArray(it.children);
        const en = over(it.id) !== undefined ? over(it.id) : !!it.enabled;
        if (q && !matches(q, it.name, it.kind) && !(isGroup && subtreeMatches(it.children, q))) continue;
        const col = isGroup && !q && collapsed.has(it.id);
        rows.push({ type: isGroup ? 'group' : 'item', key: 'i:' + it.id, id: it.id, name: it.name, kind: it.kind || '', enabled: en, depth, dimmed: !!off, collapsed: col, count: isGroup ? it.children.length : 0 });
        if (isGroup && !col) walk(it.children, depth + 1, off || !en);
      }
    })(items, 0, false);
    return rows;
  }
  function subtreeMatches(list, q) { return (list || []).some(i => matches(q, i.name, i.kind) || (Array.isArray(i.children) && subtreeMatches(i.children, q))); }

  function findItem(items, id) {
    for (const it of items || []) { if (it.id === id) return it; const f = Array.isArray(it.children) && findItem(it.children, id); if (f) return f; }
    return null;
  }
  function flatIds(items, out) { out = out || []; for (const it of items || []) { out.push(it.id); if (Array.isArray(it.children)) flatIds(it.children, out); } return out; }

  /* ---------- chat commands behind the customs buttons (same list the website allows, see worker MOD_ACTIONS) ---------- */
  const CUSTOMS = {
    'queue-open': () => '!queue open', 'queue-close': () => '!queue close', 'queue-clear': () => '!queue clear',
    balance: () => '!balance', reroll: () => '!reroll',
    next: v => '!next' + (v ? ' ' + v : ''),
    match: v => (['clear', 'fill', 'queue'].includes(v) ? '!match ' + v : null),
    win: v => (['blue', 'orange'].includes(v) ? '!win ' + v : null),
    finish: v => (['blue', 'orange'].includes(v) ? '!finish ' + v : null),
    koth: v => (['on', 'off'].includes(v) ? '!koth ' + v : null),
    mode: v => (['balanced', 'random', 'picks'].includes(v) ? '!mode ' + v : null),
    format: v => (['1v1', '2v2', '3v3', '4v4'].includes(v) ? '!format ' + v : null),
    gamemode: v => (['standard', 'dropshot', 'rumble'].includes(v) ? '!gamemode ' + v : null),
    casual: v => (['group', 'teams'].includes(v) ? '!casual ' + v : null),
    activity: v => (/^(?:(?:rl|fn) )?(?:competitive|casual|koth|viewers|boxfights|zonewars|fnviewers|end)$/.test(v) ? '!activity ' + v : null),
    pick: v => (v === 'auto' || /^[A-Za-z0-9_]{1,25}( [A-Za-z0-9_]{1,25}){0,3}$/.test(v) ? '!pick ' + v : null),
    streamer: v => (['in', 'out'].includes(v) ? '!streamer ' + v : null),
    strike: v => { const m = /^@?([A-Za-z0-9_]{2,25})( perma)?$/.exec(String(v || '').trim()); return m ? '!strike @' + m[1] + (m[2] ? ' perma' : '') : null; },
    unstrike: v => { const m = /^@?([A-Za-z0-9_]{2,25})( perma)?$/.exec(String(v || '').trim()); return m ? '!unstrike @' + m[1] + (m[2] ? ' perma' : '') : null; },
    move: v => { const m = /^@?([A-Za-z0-9_]{2,25}) (\d{1,3})$/.exec(String(v || '').trim()); return m && +m[2] >= 1 ? '!move ' + m[1] + ' ' + m[2] : null; },
    in: v => { const m = /^@?([A-Za-z0-9_]{2,25}) (blue|orange)$/.exec(String(v || '').trim()); return m ? '!in ' + m[1] + ' ' + m[2] : null; },
    out: v => { const m = /^@?([A-Za-z0-9_]{2,25})$/.exec(String(v || '').trim()); return m ? '!out ' + m[1] : null; },
    wheel: v => (v === 'open' ? '!wheel open' : null),
    kick: v => { v = String(v || '').trim().replace(/^@/, ''); return /^[A-Za-z0-9_]{2,25}$/.test(v) ? '!kick ' + v : null; },
  };
  // What choosing an activity sets (one table, used by the buttons, the simulator and the Host sequence). koth/format/mode: undefined = leave alone.
  // The bot's !activity does not touch these; !koth on makes 1v1 (remembers the old size) and !koth off restores it.
  const ACTIVITY_DEFAULTS = {
    competitive: { koth: false, format: '2v2', mode: 'balanced' }, koth: { koth: true, format: '1v1' }, casual: { koth: false }, viewers: { koth: false },
    boxfights: { koth: false }, zonewars: { koth: false }, fnviewers: { koth: false }, end: { koth: false },
  };
  // Extra Host commands to send AFTER `!activity <sub>` so the Host ends up in the activity's defaults. cur = {koth:bool, format, mode}.
  function activityPlan(sub, cur) {
    const d = ACTIVITY_DEFAULTS[sub]; if (!d) return []; cur = cur || {}; const steps = []; let fmt = cur.format;
    if (d.koth != null && d.koth !== !!cur.koth) { steps.push(['koth', d.koth ? 'on' : 'off']); fmt = d.koth ? '1v1' : null; }   // null: the Host restores the old size, so ask for ours
    if (d.format && d.format !== fmt) steps.push(['format', d.format]);
    if (d.mode && d.mode !== cur.mode) steps.push(['mode', d.mode]);
    return steps;
  }
  // Strike model (bot): temp strikes (wear off after a day), HALF strike (two halves = one temp), PERMA strikes (never expire); limit = !tune strikes (3).
  function normStrike(x) {
    if (typeof x === 'number') return { temp: x, half: 0, perma: 0 };
    x = x || {}; const n = v => Math.max(0, +v || 0);
    return { temp: n(x.temp != null ? x.temp : x.strikes), half: n(x.half != null ? x.half : x.halfStrike), perma: n(x.perma != null ? x.perma : x.permaStrikes) };
  }
  // marks in order: perma (red), temp (yellow), half (yellow, dim), then unused slots (gray) up to the limit
  function strikeMarks(s, limit) {
    s = normStrike(s); const out = [];
    for (let i = 0; i < s.perma; i++) out.push('perma'); for (let i = 0; i < s.temp; i++) out.push('temp'); if (s.half) out.push('half');
    while (out.length < (limit || 3)) out.push('none'); return out;
  }
  // final 1-based queue position when a row is dropped before/after row `target` (fromIdx = -1 when the player is not in the queue yet)
  function dropPos(fromIdx, target, after) { let j = target + (after ? 1 : 0); if (fromIdx >= 0 && fromIdx < j) j--; return Math.max(0, j) + 1; }
  function customsText(action, value) { const f = CUSTOMS[action]; return f ? f(value == null ? '' : String(value)) : null; }

  /* ---------- SSE parsing (fetch stream or EventSource text): feed chunks, get {id,event,data} messages ---------- */
  function createSseParser(onMsg) {
    let buf = '';
    return chunk => {
      buf += chunk.replace(/\r\n?/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        let ev = 'message', id = null; const data = [];
        for (const line of block.split('\n')) {
          if (!line || line[0] === ':') continue;
          const c = line.indexOf(':'); const f = c < 0 ? line : line.slice(0, c); let v = c < 0 ? '' : line.slice(c + 1); if (v[0] === ' ') v = v.slice(1);
          if (f === 'event') ev = v; else if (f === 'data') data.push(v); else if (f === 'id') id = v;
        }
        if (data.length || ev !== 'message') { let d = data.join('\n'); try { d = JSON.parse(d); } catch (e) { /* keep text */ } onMsg({ id, event: ev, data: d }); }
      }
    };
  }

  /* ---------- Host client ---------- */
  function createApi(o) {
    const base = o.base, f = o.fetch, tok = o.getToken || (() => ''), timeout = o.timeoutMs || 5000;
    async function call(method, path, body, extra) {
      const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      const timer = ctl ? setTimeout(() => ctl.abort(), (extra && extra.timeoutMs) || timeout) : null;
      const headers = {};
      if (method !== 'GET') { headers['Content-Type'] = 'application/json'; const t = tok(); if (t) headers.Authorization = 'Bearer ' + t; }
      const t0 = Date.now();
      try {
        const r = await f(base + path, { method, headers, body: body == null ? undefined : JSON.stringify(body), cache: 'no-store', signal: ctl && ctl.signal });
        let j = null; try { j = await r.json(); } catch (e) { /* empty body */ }
        return { ok: r.ok && !(j && j.ok === false), status: r.status, json: j, ms: Date.now() - t0, error: !r.ok ? 'HTTP ' + r.status : (j && j.ok === false ? (j.error || 'refused') : '') };
      } catch (e) {
        return { ok: false, status: 0, json: null, ms: Date.now() - t0, error: e && e.name === 'AbortError' ? 'timeout' : 'Host not reachable' };
      } finally { if (timer) clearTimeout(timer); }
    }
    return { get: (p, x) => call('GET', p, null, x), post: (p, b, x) => call('POST', p, b || {}, x), base };
  }

  /* ---------- poller: self-scheduling, one request in flight, kick() for "now", pausable, interval can change ---------- */
  function createPoller(o) {
    const st = o.setTimeout || setTimeout, ct = o.clearTimeout || clearTimeout;
    let timer = null, running = false, busy = false, stopped = true, interval = o.interval;
    async function tick() {
      timer = null; if (stopped) return;
      if (busy) return;
      if (o.shouldRun && !o.shouldRun()) { schedule(); return; }
      busy = true;
      try { await o.run(); } catch (e) { /* run() reports its own errors */ }
      busy = false;
      if (!stopped) schedule();
    }
    function schedule() { if (timer || stopped) return; timer = st(tick, typeof interval === 'function' ? interval() : interval); }
    return {
      start() { if (!stopped) return; stopped = false; timer = st(tick, 0); },
      stop() { stopped = true; if (timer) { ct(timer); timer = null; } },
      kick() { if (stopped) return; if (timer) { ct(timer); timer = null; } if (!busy) timer = st(tick, 0); },
      setInterval(v) { interval = v; },
      isBusy: () => busy,
    };
  }

  /* ---------- live events (SSE over fetch so the Authorization header and abort work); falls back silently ---------- */
  function createEvents(o) {
    let ctl = null, closed = false, lastId = null, failures = 0, connected = false;
    const sleep = o.sleep || (ms => new Promise(r => setTimeout(r, ms)));
    async function loop() {
      while (!closed) {
        try {
          ctl = new AbortController();
          const h = { Accept: 'text/event-stream' }; if (lastId != null) h['Last-Event-ID'] = lastId;
          const r = await o.fetch(o.url, { headers: h, cache: 'no-store', signal: ctl.signal });
          if (!r.ok || !r.body) throw new Error('HTTP ' + r.status);
          failures = 0; connected = true; o.onState && o.onState(true);
          const parse = createSseParser(m => { if (m.id != null) lastId = m.id; o.onMessage(m); });
          const rd = r.body.getReader(), dec = new TextDecoder();
          for (;;) { const { done, value } = await rd.read(); if (done) break; parse(dec.decode(value, { stream: true })); }
        } catch (e) { if (closed) return; }
        if (connected) { connected = false; o.onState && o.onState(false); }
        failures++;
        await sleep(Math.min(30000, 500 * Math.pow(2, Math.min(failures, 6))));   // 1s, 2s, 4s ... 30s; an old Host without /api/events just costs one request per 30 s
      }
    }
    return { start() { closed = false; loop(); }, stop() { closed = true; if (ctl) ctl.abort(); }, isConnected: () => connected };
  }

  /* ---------- keyed DOM reconcile: reuse nodes, move only what moved, patch only what changed ---------- */
  function reconcile(parent, rows, keyOf, create, update) {
    const old = new Map();
    for (let n = parent.firstChild; n; n = n.nextSibling) if (n._k !== undefined) old.set(n._k, n);
    let ref = parent.firstChild;
    const seen = new Set();
    for (const row of rows) {
      const k = keyOf(row); seen.add(k);
      let el = old.get(k);
      if (!el) { el = create(row); el._k = k; el._s = undefined; }
      const s = sig(row);
      if (el._s !== s) { update(el, row); el._s = s; }
      if (el === ref) ref = ref.nextSibling;
      else parent.insertBefore(el, ref);
    }
    for (const [k, el] of old) if (!seen.has(k)) parent.removeChild(el);
  }

  /* ---------- feeds (chat / activity): merge by seq, keep newest N ---------- */
  function mergeFeed(list, incoming, keyOf, cap) {
    const have = new Set(list.map(keyOf)); let changed = false;
    for (const it of incoming || []) { const k = keyOf(it); if (!have.has(k)) { have.add(k); list.push(it); changed = true; } }
    if (list.length > cap) { list.splice(0, list.length - cap); changed = true; }
    return changed;
  }

  /* ---------- logs: Chat / Players / Backend (+ Twitch events) ---------- */
  // item: {k, t:'c'|'e'|'p'|'b', ts(sec), type, user, text, group, matchId, blue[], orange[], by, reason}
  const LOG_CATS = { all: null, chat: 'c', events: 'e', players: 'p', backend: 'b' };
  function logText(x) {
    if (x.text) return x.text;
    const u = x.user || '?', by = x.by ? ' by ' + x.by : '', why = x.reason ? ' (' + x.reason + ')' : '';
    switch (x.type) {
      case 'join': return u + ' joined the queue';
      case 'leave': return u + ' left the queue';
      case 'kick': return u + ' was kicked' + by + why;
      case 'queue_clear': return 'Queue cleared' + by;
      case 'queue_open': return 'Queue opened' + by;
      case 'queue_close': return 'Queue closed' + by;
      case 'game_end': return 'Game ended' + (x.matchId != null ? ' (#' + x.matchId + ')' : '');
      case 'match_clear': return u + ' left the match';
      case 'strike_removed': return u + ' strike removed' + by;
      case 'strike_expired': return u + ' strike expired';
      case 'wheel_join': return u + ' joined the wheel';
      case 'wheel_leave': return u + ' left the wheel';
      case 'strike': return u + ' got a strike' + by + why;
      case 'removed': return u + ' was removed' + by + why;
      case 'overlay': return (x.file || 'overlay') + ' ' + (x.action || 'changed') + by;
      default: return (x.type || 'log') + (x.user ? ': ' + x.user : '');
    }
  }
  // Turns the merged item list into display rows: filters by category + search, and folds runs of same-group removals ("6 players", click to open).
  function logRows(items, cat, q, open, cap) {
    const want = LOG_CATS[cat || 'all'], needle = (q || '').toLowerCase(), out = [];
    const list = items.filter(x => (!want || x.t === want) && (!needle || ((x.user || '') + ' ' + logText(x)).toLowerCase().includes(needle))).slice(-(cap || 400));
    for (let i = 0; i < list.length; i++) {
      const x = list[i];
      if (x.group && x.t === 'p' && (x.type === 'leave' || x.type === 'removed' || x.type === 'match_clear')) {
        let j = i; while (j + 1 < list.length && list[j + 1].group === x.group && list[j + 1].type === x.type) j++;
        const run = list.slice(i, j + 1);
        if (run.length > 1) {
          const key = 'g:' + x.group + ':' + x.type, isOpen = !!(open && open.has(key));
          out.push({ key, kind: 'group', ts: run[0].ts, n: run.length, label: run.length + ' players', open: isOpen, text: x.type === 'leave' ? 'left' : x.type === 'removed' ? 'removed' : 'cleared after the game', names: run.map(r => r.user).join(', ') });
          if (isOpen) run.forEach(r => out.push({ key: r.k, kind: 'sub', ts: r.ts, text: logText(r), t: r.t }));
          i = j; continue;
        }
      }
      out.push({ key: x.k, kind: x.type === 'teams' ? 'teams' : 'line', t: x.t, lvl: x.level || '', ts: x.ts, user: x.user || '', type: x.type || '', text: x.type === 'teams' ? ('Match' + (x.matchId != null ? ' #' + x.matchId : '') + ' teams') : logText(x), blue: x.blue || [], orange: x.orange || [] });
    }
    return out;
  }
  // 02's /api/eventlog event {id, ts(ms), kind, type, user, text, group, detail} -> feed item
  function normLog(e) {
    const d = e.detail || {}, T = { players: 'p', backend: 'b', chat: 'c' };
    return { k: 'E' + e.id, t: T[e.kind] || 'b', ts: e.ts > 1e11 ? e.ts / 1000 : e.ts, type: e.type, user: e.user || '', text: e.type === 'teams' ? '' : (e.text || ''), group: e.group || '', level: d.level || '', matchId: d.id, blue: d.blue || [], orange: d.orange || [], by: d.by, reason: d.reason };
  }
  // Client-side Players log from customs state changes (used only while the Host has no /api/logs).
  function diffCustoms(prev, next, now) {
    if (!prev || !next || next.ok === false) return [];
    const ts = now || Date.now() / 1000, out = [], names = s => (s && s.queue || []).map(p => p.username || p.user || p.name).filter(Boolean);
    const pq = new Set(names(prev)), nq = new Set(names(next)), inMatch = new Set(((next.match && next.match.players) || []).map(p => p.username)), pm = prev.match, nm = next.match;
    const ended = pm && (!nm || nm.id !== pm.id);
    const gone = [...pq].filter(u => !nq.has(u) && !inMatch.has(u)), inPrevMatch = new Set(((pm && pm.players) || []).map(p => p.username));
    for (const u of nq) if (!pq.has(u) && !inPrevMatch.has(u)) out.push({ k: 'cl:' + ts + ':j:' + u, t: 'p', ts, type: 'join', user: u, src: 'app' });
    for (const u of gone) out.push({ k: 'cl:' + ts + ':l:' + u, t: 'p', ts, type: 'leave', user: u, src: 'app' });
    if (ended) {
      const stay = new Set([...nq, ...inMatch]), rem = [...inPrevMatch].filter(u => !stay.has(u));
      rem.forEach(u => out.push({ k: 'cl:' + ts + ':r:' + u, t: 'p', ts, type: 'removed', user: u, group: 'm' + pm.id, src: 'app' }));
    }
    if (nm && (!pm || nm.id !== pm.id)) out.push({ k: 'cl:t:' + nm.id, t: 'p', ts, type: 'teams', matchId: nm.id, blue: nm.blue || [], orange: nm.orange || [], src: 'app' });
    return out;
  }

  function fmtAgo(sec) { sec = Math.max(0, Math.round(sec)); if (sec < 60) return sec + 's'; if (sec < 3600) return Math.floor(sec / 60) + 'm'; return Math.floor(sec / 3600) + 'h ' + Math.floor(sec % 3600 / 60) + 'm'; }
  function activityLine(a) {
    const who = a.user || '?', n = a.amount, w = a.what && a.what !== String(n) ? a.what : '';
    switch (a.kind) {
      case 'follow': return who + ' followed';
      case 'sub': case 'resub': return who + ' ' + (a.kind === 'resub' ? 'resubbed' : 'subscribed') + (a.tier ? ' T' + a.tier : '');
      case 'gift': return who + ' gifted ' + (w || n + ' sub(s)');
      case 'cheer': return who + ' cheered ' + (n || '') + ' bits';
      case 'raid': return who + ' raided with ' + n;
      case 'raid_out': return 'raided out to ' + (a.target || who) + (n ? ' (' + n + ')' : '');
      case 'redeem': return who + ' redeemed ' + (w || a.detail || '');
      default: return (a.kind || 'event') + ': ' + who + (w ? ' ' + w : '');
    }
  }

  return { createStore, createOptimistic, buildSceneRows, buildItemRows, findItem, flatIds, customsText, CUSTOMS, ACTIVITY_DEFAULTS, activityPlan, normStrike, strikeMarks, dropPos, createSseParser, createApi, createPoller, createEvents, reconcile, mergeFeed, normLog, logRows, logText, diffCustoms, fmtAgo, activityLine, sig };
});
