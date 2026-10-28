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
    win: v => (['blue', 'grey', 'orange'].includes(v) ? '!win ' + v : null),
    finish: v => (['blue', 'grey', 'orange'].includes(v) ? '!finish ' + v : null),
    koth: v => (['on', 'off'].includes(v) ? '!koth ' + v : null),
    mode: v => (['balanced', 'random', 'picks'].includes(v) ? '!mode ' + v : null),
    format: v => (/^([1-9]|1[0-6])v\1$/.test(v) ? '!format ' + v : null),   // customs 2v2-4v4, Fortnite viewers any size 1-16 (Host must accept NvN)
    gamemode: v => (['standard', 'dropshot', 'rumble'].includes(v) ? '!gamemode ' + v : null),
    casual: v => (['group', 'teams'].includes(v) ? '!casual ' + v : null),
    activity: v => (/^(?:(?:rl|fn) )?(?:competitive|casual|koth|viewers|boxfights|zonewars|fnviewers|end)$/.test(v) ? '!activity ' + v : null),
    pick: v => (v === 'auto' || /^[A-Za-z0-9_]{1,25}( [A-Za-z0-9_]{1,25}){0,3}$/.test(v) ? '!pick ' + v : null),
    streamer: v => (['in', 'out'].includes(v) ? '!streamer ' + v : null),
    strike: v => { const m = /^@?([A-Za-z0-9_]{2,25})( perma)?$/.exec(String(v || '').trim()); return m ? '!strike @' + m[1] + (m[2] ? ' perma' : '') : null; },
    unstrike: v => { const m = /^@?([A-Za-z0-9_]{2,25})( perma)?$/.exec(String(v || '').trim()); return m ? '!unstrike @' + m[1] + (m[2] ? ' perma' : '') : null; },
    move: v => { const m = /^@?([A-Za-z0-9_]{2,25}) (\d{1,3})$/.exec(String(v || '').trim()); return m && +m[2] >= 1 ? '!move ' + m[1] + ' ' + m[2] : null; },
    in: v => { const m = /^@?([A-Za-z0-9_]{2,25}) (blue|grey|orange)$/.exec(String(v || '').trim()); return m ? '!in ' + m[1] + ' ' + m[2] : null; },
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
  // Overlay-layout game for an activity (Host layouts are tagged with Twitch category names; '' = none). Sent as POST /api/scene-layouts {action:'setgame',profile:'*',game}.
  const UI_SCALES = [90, 100, 115, 130];
  const normScale = v => { const n = Math.round(Number(v)); return UI_SCALES.includes(n) ? n : 100; };   // anything else (old or hand-edited storage) falls back to 100
  const gameOf = (sub, game) => (sub === 'end' ? '' : game === 'fn' || /^(boxfights|zonewars|fnviewers)$/.test(sub) ? 'Fortnite' : 'Rocket League');   // game: 'fn'/'rl' prefix of '!activity fn koth'
  // Recap card: {text|line, clip:{title,url,views}} from the Host -> what the header card and the Stream tab show. clip.url only https.
  function recapView(j) {
    j = j || {}; const c = j.clip && typeof j.clip === 'object' ? j.clip : null, url = c && String(c.url || '').startsWith('https://') ? String(c.url) : '';
    return { text: String(j.text || j.line || '').trim(), clipTitle: c ? String(c.title || '') : '', clipUrl: url, views: c && c.views != null ? +c.views : null, hasClip: !!url };
  }
  // Team size from a format like "3v3" (2 when unknown). Works for 10v10 too.
  const fmtSize = f => { const m = /^(\d{1,2})v\d{1,2}$/.exec(String(f || '')); return m ? +m[1] || 2 : 2; };
  // Team name + colour (customs only; the emoji team lines are for tourneys). Colour = #rrggbb.
  const TEAM_DEFAULTS = { orange: { name: 'Orange', color: '#ff7a00' }, blue: { name: 'Grey', color: '#9aa0a6' } };   // the second team is Grey now; a Host that still says Blue keeps showing Blue (its name and colour win)
  /* The second team's state key is 'blue' (old) or 'grey' (new); the UI side key stays 'blue'. teamEntry reads the team from /api/customs/state, teamWord is the word the Host commands take. */
  const teamEntry = (c, side) => { const t = c && c.teams; return t ? (t[side] || (side === 'blue' ? t.grey : null) || null) : null; };
  const teamWord = (c, side) => (side === 'blue' && c && c.teams && c.teams.grey && !c.teams.blue ? 'grey' : side);
  const teamPlayers = (m, side) => { if (!m) return []; const p = side === 'blue' ? (m.blueP || m.greyP) : m[side + 'P']; if (Array.isArray(p) && p.length) return p; const l = side === 'blue' ? (m.blue || m.grey) : m[side]; return Array.isArray(l) ? l : []; };
  const TEAM_PRESETS = [['Penguin orange', '#ff7a00'], ['Amber', '#ffb347'], ['Ember', '#ff4d00'], ['Gold', '#ffc833'], ['Cream', '#f3e3c3'], ['Red', '#e74c3c'], ['Pink', '#ff5fa2'], ['Purple', '#9b59b6'],
    ['Blue', '#1e8fff'], ['Sky', '#5aaeff'], ['Teal', '#1abc9c'], ['Green', '#2ecc71'], ['Lime', '#a4e000'], ['White', '#ffffff'], ['Grey', '#9aa0a6']];
  function teamName(v) { const s = String(v == null ? '' : v).replace(/[\u0000-\u001f]/g, '').trim(); return s && s.length <= 20 && !/^[!\/.]/.test(s) ? s : null; }
  function teamColor(v) { const s = String(v == null ? '' : v).trim().toLowerCase(); return /^#[0-9a-f]{6}$/.test(s) ? s : null; }
  // Stream info: Twitch tags (max 10, 25 chars, letters/digits/spaces only) and a hashtag line for TikTok
  function parseTags(v) { const seen = new Set(), out = []; for (const t of String(v || '').split(/[,\n]+/)) { const s = t.replace(/^#+/, '').trim(); if (s && !seen.has(s.toLowerCase())) { seen.add(s.toLowerCase()); out.push(s); } } return out; }
  const twitchTags = tags => tags.map(t => t.replace(/[^A-Za-z0-9 ]/g, '').replace(/\s+/g, '')).filter(Boolean).map(t => t.slice(0, 25)).slice(0, 10);
  function copyBlock(si) { const tags = parseTags(si.tags).map(t => '#' + t.replace(/\s+/g, '')); return [si.title, si.description, tags.join(' ')].filter(x => x && String(x).trim()).join('\n\n'); }
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

  // Wheel admin = the chat command "!wheel ..." (the site has no wheel admin page; the Host runs it through POST /api/run as the broadcaster).
  // Spin / New round / Reset keep their own Host routes (/api/wheel/spin|new|reset); remove and queue-add use /api/wheel/remove and /queue-add.
  const WHEEL_OPT = { mode: ['random', 'balanced'], size: ['1', '2', '3', '4'], odd: ['waitlist', 'trio', 'partial', 'hold', 'mod'], eligibility: ['all', 'subs'] };
  const WHEEL_PLAIN = ['open', 'close', 'draw', 'undo', 'announce', 'end'];
  function wheelCmd(sub, val) {
    sub = String(sub || ''); val = String(val == null ? '' : val).trim().replace(/^@/, '');
    if (WHEEL_PLAIN.includes(sub)) return '!wheel ' + sub;
    if (WHEEL_OPT[sub]) return WHEEL_OPT[sub].includes(val) ? '!wheel ' + sub + ' ' + val : null;
    if (sub === 'remove') return /^[A-Za-z0-9_]{2,25}$/.test(val) ? '!wheel remove ' + val : null;
    if (sub === 'mmr') { const m = /^([A-Za-z0-9_]{2,25})[ :]+([0-9]{1,5})$/.exec(val); return m && +m[2] <= 20000 ? '!wheel mmr ' + m[1] + ' ' + (+m[2]) : null; }
    return null;
  }
  // what the segmented buttons highlight: the Host's value (GET /api/wheel/public) unless a just-clicked overlay is still fresh
  function wheelView(w, ov, now) {
    w = w || {}; ov = ov || {}; now = now || Date.now();
    const pick = (k, hostV) => { const o = ov[k]; let v = o && o.until > now ? o.v : hostV; v = v == null ? null : String(v).toLowerCase(); return v && WHEEL_OPT[k].includes(v) ? v : null; };
    return { mode: pick('mode', w.mode), size: pick('size', w.teamSize), odd: pick('odd', w.oddPolicy), eligibility: pick('eligibility', w.eligibility),
      status: w.status || null, entrants: w.entrantCount != null ? w.entrantCount : (w.names || []).length, teams: (w.teams || []).length, waitlist: (w.waitlist || []).length };
  }
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
    const base = o.base, f = o.fetch, onResult = o.onResult || (() => {}), tok = o.getToken || (() => ''), timeout = o.timeoutMs || 5000, inflight = new Map();
    // Plain words for the statuses a write can come back with (toasts show r.error): never a silent success.
    const why = (st, j) => st === 401 ? 'Not signed in to the Host (token rejected). Reopen the app' : st === 403 ? 'Refused by the Host (not allowed)' : st === 429 ? 'Host says slow down (rate limited). Try again in a moment' : st === 503 ? 'Host is busy or starting (503)' : j && (j.error || j.code) ? String(j.error || j.code) : 'HTTP ' + st;
    async function call(method, path, body, extra) { const r = await call0(method, path, body, extra); try { onResult(r); } catch (e) { /* observer only */ } return r; }
    async function call0(method, path, body, extra) {
      const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      const timer = ctl ? setTimeout(() => ctl.abort(), (extra && extra.timeoutMs) || timeout) : null;
      const headers = {};
      if (method !== 'GET') { headers['Content-Type'] = 'application/json'; const t = tok(); if (t) headers.Authorization = 'Bearer ' + t; }
      const t0 = Date.now();
      try {
        const r = await f(base + path, { method, headers, body: body == null ? undefined : JSON.stringify(body), cache: 'no-store', signal: ctl && ctl.signal });
        let j = null, junk = false; try { const tx = typeof r.text === 'function' ? await r.text() : JSON.stringify(await r.json()); if (tx.trim()) { try { j = JSON.parse(tx); } catch (e) { junk = r.ok; } } } catch (e) { /* empty body */ }   // a 200 that is not JSON (proxy page, half a reply) is a failure, not data
        return { ok: r.ok && !junk && !(j && j.ok === false), status: r.status, json: j, ms: Date.now() - t0, junk, error: !r.ok ? why(r.status, j) : junk ? 'unreadable reply' : (j && j.ok === false ? (j.error || 'refused') : '') };
      } catch (e) {
        return { ok: false, status: 0, json: null, ms: Date.now() - t0, error: e && e.name === 'AbortError' ? 'timeout' : 'Host not reachable' };
      } finally { if (timer) clearTimeout(timer); }
    }
    // An identical POST (same path + body) while one is still in flight shares its answer: a double-click or key repeat sends once.
    function post(p, b, x) {
      const key = p + ' ' + JSON.stringify(b || {}); if (inflight.has(key)) return inflight.get(key);
      const pr = call('POST', p, b || {}, x).finally(() => inflight.delete(key)); inflight.set(key, pr); return pr;
    }
    return { get: (p, x) => call('GET', p, null, x), post, base };
  }

  /* ---------- source health: Host / Spotify / Multi each count consecutive failures; pollers back off (x2 up to 30 s) while their source fails and recover on the first success ---------- */
  function createHealth(o) {
    const max = (o && o.maxMs) || 30000, DOWN = 2, fails = {}, subs = [];
    const note = (n, st) => subs.forEach(cb => { try { cb(n, st); } catch (e) { /* a listener must not break the poll */ } });
    return {
      ok(n) { const was = fails[n] || 0; fails[n] = 0; if (was >= DOWN) note(n, 'up'); },
      fail(n) { const f = fails[n] = (fails[n] || 0) + 1; if (f === DOWN) note(n, 'down'); },
      fails: n => fails[n] || 0, down: n => (fails[n] || 0) >= DOWN,
      delay: (n, base) => Math.min(Math.max(max, base), base * Math.pow(2, Math.min(fails[n] || 0, 8))),
      onChange: cb => subs.push(cb),
    };
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
          const h = { Accept: 'text/event-stream' };   // no Last-Event-ID: the Host ignores it and the Host CORS list does not allow it, so sending it blocked every reconnect
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
  const LOG_CATS = { all: null, chat: 'c', events: 'e', players: 'p', backend: 'b', mods: 'm' };
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
    const list = items.filter(x => (want ? x.t === want : x.t !== 'm') && (!needle || ((x.user || '') + ' ' + logText(x)).toLowerCase().includes(needle))).slice(-(cap || 400));
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
  // Host /api/modaudit entry {id, at(unix s), who, role, action, target, before, after} -> feed item (category Mods; not shown under All)
  const modText = e => { const w = e.who || '?', r = e.role && e.role !== 'mod' ? ' (' + e.role + ')' : '', t = e.target ? ' ' + e.target : '', ch = e.before || e.after ? ' [' + (e.before || '–') + ' → ' + (e.after || '–') + ']' : ''; return w + r + ': ' + (e.action || 'action') + t + ch; };
  const normMod = e => ({ k: 'M' + e.id, t: 'm', ts: +e.at || 0, type: 'mod', user: e.who || '', text: modText(e) });
  // Status strip for the Feed tab from the Host's /api/shoutouts, /api/intros?status=pending and /api/scene-health answers (any may be null = not available)
  function headsView(sh, intro, health, streaks) {
    const out = [];
    if (sh && sh.ok !== false) { const cur = sh.current, pend = (sh.pending || []).length, last = (sh.recent || [])[0]; out.push({ k: 'shout', warn: false, text: 'Shoutout: ' + (cur ? 'now ' + cur : 'idle') + (pend ? ' · ' + pend + ' queued' : '') + (last ? ' · last ' + last.user + ' ' + (last.minAgo < 1 ? 'just now' : last.minAgo + ' min ago') : '') }); }
    if (intro && intro.ok !== false && typeof intro.pending === 'number') out.push({ k: 'intro', warn: intro.pending > 0, text: 'Intros waiting: ' + intro.pending });
    if (streaks && streaks.ok !== false && (streaks.board || []).length) { const t = streaks.board[0]; out.push({ k: 'streaks', warn: false, text: 'Streaks: ' + (t.name || t.login || '?') + ' ' + (+t.best || 0) }); }
    if (health && health.ok === false && Array.isArray(health.problems) && health.problems.length) out.push({ k: 'scenes', warn: true, text: 'Scenes: ' + health.problems.length + ' problem' + (health.problems.length > 1 ? 's' : ''), tip: health.problems.map(p => p + ' -> ' + healthHint(p)).join('\n') });
    return out;
  }
  // Host /api/streaks {board:[{login,name,best,current,...}]} (already sorted best first) -> top n rows for the card
  const streakRows = (j, n) => ((j && j.board) || []).slice(0, n || 5).map((u, i) => ({ k: String(u.login || u.name || i), n: i + 1, name: u.name || u.login || '?', best: +u.best || 0, current: +u.current || 0 }));
  // Host /api/prestream {status, items:[{id,label,status:pass|warn|fail,detail}]} -> header label + the items that are not fine, worst first
  function prestreamView(j) {
    if (!j || j.ok === false || !Array.isArray(j.items)) return { state: '', label: 'Pre-stream', items: [] };
    const rank = { fail: 0, warn: 1 }, bad = j.items.filter(i => i.status === 'fail' || i.status === 'warn').sort((a, b) => rank[a.status] - rank[b.status]);
    const f = bad.filter(i => i.status === 'fail').length, w = bad.length - f;
    return { state: f ? 'bad' : w ? 'warn' : 'ok', label: f || w ? 'Pre-stream: ' + [f && f + ' fail', w && w + ' warn'].filter(Boolean).join(', ') : 'Pre-stream ok', items: bad.map(i => ({ id: i.id, status: i.status, text: i.label + (i.detail ? ' (' + i.detail + ')' : '') })) };
  }
  // plain-words fix for a /api/scene-health problem line
  function healthHint(p) {
    p = String(p || '');
    if (/has no visible widget/.test(p)) return 'Open that layout in the website scene editor and switch at least one widget on, or pick another layout.';
    const m = p.match(/nothing listens on port (\d+)/);
    if (m) return 'Start the module that serves port ' + m[1] + (m[1] === '8766' ? ' (PinguinoMulti: alerts)' : '') + ', or hide that widget in the layout.';
    if (/layout unreadable/.test(p)) return 'The layout file is broken: restore it from the layout history or re-save the layout.';
    return 'Check the layout in the website scene editor.';
  }
  // seconds since the Host last answered, only when it is stale enough to matter (and not already reported offline)
  const staleSecs = (now, last, limit) => (last && now - last > (limit || 10000) ? Math.round((now - last) / 1000) : 0);
  // pending viewer intros for the approve/reject list: rows still waiting, minus the ones just decided here (optimistic), oldest first as the Host sends them
  const introKey = i => (i.platform || 'twitch') + ':' + (i.user_id != null ? i.user_id : i.login);
  const introRows = (intro, gone) => ((intro && intro.intros) || []).filter(i => i && i.status === 'pending' && !(gone && gone.has(introKey(i)))).map(i => ({ k: introKey(i), platform: i.platform || 'twitch', user_id: String(i.user_id != null ? i.user_id : ''), login: i.login || '?', text: String(i.text || '') }));
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

  /* Songify hand-off button: the Spotify module's /api/state reports songify:true/false; when it does not, the last successful action is shown and marked as such */
  function songifyView(st, last) {
    const known = !!st && typeof st.songify === 'boolean', ok = !!last && last.ok === true && (last.name === 'songify' || last.name === 'takeback');
    const on = known ? st.songify : ok ? last.name === 'songify' : null;
    return { known, on, name: on ? 'takeback' : 'songify', label: on ? 'Take back' : 'Hand off to Songify', armLabel: on ? 'Sure? Take the music back' : 'Sure? Hand the music to Songify',
      text: on == null ? 'State unknown (the player is not answering)' : (on ? 'Songify has the music' : 'The bot runs the music') + (known ? '' : ' (last action, not confirmed)') };
  }
  /* Spotify rate limit chip: the module's /api/state reports rate_limited:true plus rate_limited_until (epoch s) and rate_limited_until_hhmm; anything else (false, missing, an old module) shows nothing */
  function rateLimitView(st) {
    if (!st || st.rate_limited !== true) return { limited: false, until: '', text: '' };
    let t = typeof st.rate_limited_until_hhmm === 'string' ? st.rate_limited_until_hhmm.trim() : '';
    if (!t && Number.isFinite(Number(st.rate_limited_until)) && Number(st.rate_limited_until) > 0) { const d = new Date(Number(st.rate_limited_until) * 1000); t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
    return { limited: true, until: t, text: t ? 'Spotify rate limited until ' + t : 'Spotify rate limited' };
  }
  /* Spotify self-check chip: /api/state.selfcheck = {ok, checks:[{id,label,ok,reason}], api_calls_hour, api_call_budget}; shown only when ok === false (missing or old module = nothing) */
  function selfcheckView(st) {
    const sc = st && st.selfcheck; if (!sc || typeof sc !== 'object' || sc.ok !== false) return { bad: false, text: '', title: '' };
    const failed = (Array.isArray(sc.checks) ? sc.checks : []).filter(x => x && x.ok === false), name = x => String(x.label || x.id || 'check');
    const lines = failed.map(x => name(x) + (x.reason ? ': ' + x.reason : ''));
    const used = Number(sc.api_calls_hour), budget = Number(sc.api_call_budget);
    if (used > 0 && budget > 0 && used / budget > 0.8) lines.push('API calls this hour: ' + used + ' of ' + budget);
    return { bad: true, text: 'Spotify: ' + (failed.length ? failed.map(name).join(', ') : 'self-check failing'), title: lines.join(String.fromCharCode(10)) };
  }
  /* Platform display names. A person is a string key ("yt:UC…", "tt:name", "tw:login", a plain Twitch login) or an object from the Host. Returns {key, name, platform:'twitch'|'youtube'|'tiktok', tag:'T'|'YT'|'TT', epic}.
     Name order: display > displayName/display_name > handle/login > name > (directory entry for the same key) > the key with its prefix stripped. A raw "yt:UC…" / "tt:…" is never returned as a name. key stays the Host key for commands. */
  const PLAT_TAG = { twitch: 'T', youtube: 'YT', tiktok: 'TT', kick: 'KK', facebook: 'FB' };
  function platOf(s) { const v = String(s == null ? '' : s).toLowerCase().trim(); return /^(tw|twitch)$/.test(v) ? 'twitch' : /^(yt|youtube)$/.test(v) ? 'youtube' : /^(tt|tiktok)$/.test(v) ? 'tiktok' : /^(kk|kick)$/.test(v) ? 'kick' : /^(fb|facebook)$/.test(v) ? 'facebook' : ''; }
  const KEYPRE = /^(tw|twitch|yt|youtube|tt|tiktok|kk|kick|fb|facebook)[:]/i, YTID = /^UC[A-Za-z0-9_-]{20,}$/;
  function personInfo(x, dir) {
    const o = x && typeof x === 'object' ? x : null, s = f => (o && typeof o[f] === 'string' ? o[f].trim() : '');
    const key = String(o ? (s('key') || s('username') || s('user') || s('id') || s('login') || s('name') || s('display')) : (x == null ? '' : x)).trim();
    const dk = dir && typeof dir.get === 'function' ? dir.get(key.toLowerCase()) : null, d = dk && dk !== o ? dk : null;
    const pre = KEYPRE.exec(key), stripped = key.replace(KEYPRE, '');
    const hostShape = !!s('name') && !!s('display') && s('name') !== s('display');   // Host queue rows: name = viewer display name, display = Epic name
    let name = hostShape ? s('name') : (s('display') || s('displayName') || s('display_name') || s('handle') || s('login') || s('name') || (d ? (d.name || '') : ''));
    if (KEYPRE.test(name)) name = name.replace(KEYPRE, '');
    if (!name || name === key && pre) name = stripped;
    let platform = platOf(s('platform')) || platOf(s('source')) || platOf(s('provider')) || (pre ? platOf(pre[1]) : '') || (d ? d.platform : '') || (YTID.test(stripped) || /^@/.test(name) ? 'youtube' : 'twitch');
    if (YTID.test(name)) name = 'YouTube viewer …' + name.slice(-4);
    if (!name) name = '?';
    return { key: d && d.key && !o ? d.key : key, name, platform, tag: PLAT_TAG[platform], epic: s('epic') || s('epicName') || s('epic_name') || (hostShape && s('display') !== key ? s('display') : '') || (d ? d.epic : '') };
  }
  function personDir(lists) {
    const m = new Map();
    for (const l of lists) for (const x of Array.isArray(l) ? l : []) { if (!x || typeof x !== 'object') continue; const i = personInfo(x); if (!i.key) continue; m.set(i.key.toLowerCase(), i); for (const alt of [x.display, x.name, i.name, i.epic]) if (typeof alt === 'string' && alt && !m.has(alt.toLowerCase())) m.set(alt.toLowerCase(), i); }
    return m;
  }
  /* Text for toasts and confirm lines: any "yt:UC…" / "tt:name" / "tw:login" key inside it becomes the person's display name */
  function cleanKeys(text, dir) { return String(text == null ? '' : text).replace(/\b(?:tw|twitch|yt|youtube|tt|tiktok|kk|kick|fb|facebook):[^\s,;()]+/gi, m => personInfo(m, dir).name); }
  function personText(x, dir) { const i = personInfo(x, dir); return i.name + (i.epic ? ' (' + i.epic + ')' : ''); }
  /* Raid prep: POST /api/raid/prep {target, now:false} -> {ok, fired, duplicate}. The target is required (it is stored for !leftbehind); a Twitch login: letters, digits, underscore, 1-25 */
  function raidTarget(s) {
    const t = String(s == null ? '' : s).trim().replace(/^@/, '');
    if (!t) return { ok: false, target: '', error: 'Type the raid target first' };
    if (!/^[A-Za-z0-9_]{1,25}$/.test(t)) return { ok: false, target: t, error: 'Raid target: a Twitch name (letters, numbers, underscore, up to 25)' };
    return { ok: true, target: t.toLowerCase(), error: '' };
  }
  function raidPrepView(r, target, errText) {
    const j = r && r.json && typeof r.json === 'object' ? r.json : {};
    if (!r || !r.ok || j.ok === false) return { kind: 'bad', text: errText || (j.error ? 'Raid prep: ' + j.error : 'Raid prep failed') };
    if (j.duplicate) return { kind: 'warn', text: 'Already fired for this raid (3 min window)' };
    if (j.fired) return { kind: 'good', text: 'Raid line sent for ' + target };
    return { kind: 'bad', text: 'Raid prep: the Host answered but fired nothing' + (j.reason ? ' (' + j.reason + ')' : '') };
  }
  /* Private match name (Customs panel): POST /api/customs/mod {action:'pm', value:name} -> {ok, pmName}. One token, 1-20 characters, no leading ! or /. */
  function pmName(v) {
    const s = String(v == null ? '' : v).trim();
    if (!s) return { ok: false, name: '', error: 'Type the private match name first' };
    if (/s/.test(s)) return { ok: false, name: s, error: 'Private match name: one word, no spaces' };
    if (s.length > 20) return { ok: false, name: s, error: 'Private match name: 20 characters at most' };
    if (/^[!/]/.test(s) || /[ -]/.test(s)) return { ok: false, name: s, error: 'Private match name cannot start with ! or /' };
    return { ok: true, name: s, error: '' };
  }
  /* what the panel shows: a just-set name wins for 12 s, then the Host's pmName; '' means the Host reports none, null means this Host does not report it at all */
  function pmView(c, ov, now) {
    const has = !!c && typeof c.pmName === 'string', cur = has ? c.pmName.trim() : null, live = ov && ov.until > (now == null ? Date.now() : now);
    const pending = !!live && cur !== ov.name;
    return { known: has, cur, shown: live ? ov.name : cur, pending, text: live ? ov.name : has ? (cur || '(not set)') : '(the Host does not report it yet)' };
  }
  function pmResult(r, name, errText) {
    const j = r && r.json && typeof r.json === 'object' ? r.json : {};
    if (!r || !r.ok || j.ok === false) return { kind: 'bad', text: errText || (j.error ? 'PM name: ' + j.error : 'PM name was not set') };
    return { kind: 'good', text: 'Private match name set: ' + (typeof j.pmName === 'string' && j.pmName ? j.pmName : name) };
  }
  /* One raid prep request at a time; the same target is not sent again for 10 s after a send that the Host accepted or that is still unknown; a failed send frees it */
  function createRaidGuard(clock) {
    const now = clock || Date.now; let busy = false, last = null;
    return {
      begin(target) { if (busy) return { ok: false, why: 'Raid prep is already being sent' }; if (last && last.target === target && now() - last.at < 10000) return { ok: false, why: 'Raid prep for ' + target + ' was just sent' }; busy = true; last = { target, at: now() }; return { ok: true, why: '' }; },
      end(failed) { busy = false; if (failed) last = null; },
      get busy() { return busy; },
    };
  }
  return { pmName, pmView, pmResult, teamEntry, teamWord, teamPlayers, createRaidGuard, raidTarget, raidPrepView, cleanKeys, personInfo, personDir, personText, PLAT_TAG, selfcheckView, rateLimitView, wheelCmd, wheelView, WHEEL_OPT, songifyView, prestreamView, healthHint, staleSecs, createHealth, streakRows, introKey, introRows, modText, normMod, headsView, UI_SCALES, normScale, createStore, createOptimistic, buildSceneRows, buildItemRows, findItem, flatIds, customsText, CUSTOMS, fmtSize, TEAM_DEFAULTS, TEAM_PRESETS, teamName, teamColor, parseTags, twitchTags, copyBlock, ACTIVITY_DEFAULTS, activityPlan, gameOf, recapView, normStrike, strikeMarks, dropPos, createSseParser, createApi, createPoller, createEvents, reconcile, mergeFeed, normLog, logRows, logText, diffCustoms, activityLine, sig };
});
