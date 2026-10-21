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
    kick: v => { v = String(v || '').trim().replace(/^@/, ''); return /^[A-Za-z0-9_]{2,25}$/.test(v) ? '!kick ' + v : null; },
  };
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

  return { createStore, createOptimistic, buildSceneRows, buildItemRows, findItem, flatIds, customsText, CUSTOMS, createSseParser, createApi, createPoller, createEvents, reconcile, mergeFeed, fmtAgo, activityLine, sig };
});
