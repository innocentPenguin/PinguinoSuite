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

  /* ---------- state ---------- */
  const cached = ls.get('cache', {});
  const S = C.createStore({
    tree: cached.tree || { connected: false, current: '', scene: '', scenes: [], folders: [], items: [] }, treeStale: !!cached.tree,
    obsStatus: null, live: null, host: null, hostUp: null, customs: cached.customs || null, customsOk: null, wheel: null,
    customsMod: null, cmds: [], overlays: null, ovErr: null, ochat: null, link: { sse: false, ms: null }, tick: 0,
  });
  const opt = C.createOptimistic(2500);
  const ui = {
    view: null, query: '', tab: ls.get('tab', 'customs'), pane: 'scenes',
    folders: new Set(ls.get('folders', [])), groups: new Set(ls.get('groups', [])), kb: { scenes: null, sources: null },
    itemsBy: {}, tookControl: false, logCat: ls.get('logcat') || 'all', logSeq: 0, logsOk: null, openGroups: new Set(), prevCustoms: null, feed: [], chat: [], chatSeq: 0, actSeq: 0, chatOk: null, sent: new Map(), renaming: null, ochatLog: [],
  };
  const saveCache = () => ls.set('cache', { tree: S.get('tree'), customs: S.get('customs') });

  /* ---------- toasts, arming, command sending ---------- */
  function toast(msg, bad) { const t = h('div', 'toast' + (bad ? ' bad' : ''), msg); $('#toasts').append(t); setTimeout(() => t.remove(), bad ? 5000 : 2200); }
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
  async function sendCustom(action, value, btn) {
    const text = C.customsText(action, value); if (!text) { toast('Not allowed: ' + action, true); return; }
    const now = Date.now(), last = ui.sent.get(text) || 0;
    if (now - last < 1200) { toast('Already sent ' + text); return; }
    ui.sent.set(text, now); flash(btn); if (!ui.tookControl) { ui.tookControl = true; schedule('customs'); } await tokenReady;
    let r = null;
    if (HOSTMOD.has(action.startsWith('queue-') ? 'queue' : action) && S.get('customsMod') !== false) {
      r = await api.post('/api/customs/mod', action.startsWith('queue-') ? { action: 'queue', value: action.slice(6) } : { action, value: value || '' });
      if (r.status === 404) { S.set({ customsMod: false }); r = null; }
    }
    if (!r) r = await api.post('/api/run', { text, user: 'broadcaster' });
    if (r.ok) { toast('Sent ' + text); if (r.json && r.json.customs) S.set({ customs: r.json.customs, customsOk: true }); else pollers.customs.kick(); }
    else { ui.sent.delete(text); toast(text + ': ' + r.error, true); }
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
      <div class="ctl free" id="cu-ctl"><span id="cu-who">In control: …</span><span class="sp"></span><span class="faint" id="cu-badge"></span></div>
      <div id="cu-note" class="note" hidden></div>
      <div class="cgrid">
        ${sec('c-act', 'Activity', `<div class="btns">${[['Competitive', 'competitive'], ['Casual', 'casual'], ['KOTH', 'koth'], ['Viewers', 'viewers']].map(([l, v]) => b(l, 'activity', 'rl ' + v, 'rd warn', 'activity:' + v)).join('')}${b('End activity', 'activity', 'end', 'rd warn')}</div>`, ' <span class="faint" id="cu-act"></span>')}
        ${sec('c-q', 'Queue', `<div class="btns">${b('Open', 'queue-open', null, 'g', 'queue:open')}${b('Close', 'queue-close', null, 'rd', 'queue:close')}${b('Clear', 'queue-clear', null, 'og warn', 'queue:clear')}</div><ul class="qlist" id="cu-queue"></ul>`, ' <span class="faint" id="cu-qn"></span>')}
        ${sec('c-m', 'Match', `<div class="btns">${b('Fill', 'match', 'fill', 'g')}${b('Move all → Queue', 'match', 'queue')}${b('Clear match', 'match', 'clear', 'rd warn')}${b('Orange wins', 'finish', 'orange', 'or', 'win:orange')}${b('Blue wins', 'finish', 'blue', 'bl', 'win:blue')}</div><div class="teams" id="cu-teams"></div>`, ' <span class="faint" id="cu-match"></span>')}
        ${sec('c-n', 'Next match', `<div class="btns">${b('▶ Everyone out', 'next', '', 'pri')}${b('Orange stays', 'next', 'orange', 'or')}${b('Blue stays', 'next', 'blue', 'bl')}</div>`)}
        ${sec('c-t', 'Teams', `${seg('mode', [['Balanced', 'balanced'], ['Random', 'random'], ['Manual', 'picks']])}<div class="btns" style="margin-top:6px">${b('Reroll', 'reroll')}${b('Balance', 'balance')}</div><div class="row" id="cu-manual" style="margin-top:6px" hidden><input type="text" id="cu-pick" placeholder="who goes Blue" autocomplete="off" spellcheck="false" style="flex:1;min-width:0"><button class="sm bl" id="cu-pickgo">Set Blue</button>${b('Auto', 'pick', 'auto')}</div>`)}
        ${sec('c-s', 'Settings', `<div class="lbl">Team size</div>${seg('format', ['1v1', '2v2', '3v3', '4v4'].map(x => [x, x]))}<div class="lbl">Game mode</div>${seg('gamemode', [['Standard', 'standard'], ['Dropshot', 'dropshot'], ['Rumble', 'rumble']])}`)}
        ${sec('c-k', 'KOTH', `${seg('koth', [['Off', 'off'], ['On', 'on']])}<div class="faint sm" style="margin-top:4px">On: winners stay, challengers come in.</div>`)}
        ${sec('c-p', 'Players', `<div class="row"><input type="text" id="cu-kick" placeholder="Kick by name" style="flex:1;min-width:0" autocomplete="off" spellcheck="false"><button class="sm rd" id="cu-kickgo">Kick</button></div><div class="btns" style="margin-top:6px"><span class="faint sm" style="align-self:center">Streamer</span>${b('In', 'streamer', 'in', 'g')}${b('Out', 'streamer', 'out')}</div>`)}
        ${sec('c-w', 'Wheel', `<div class="btns"><button class="sm pri" data-wh="spin">Spin</button><button class="sm" data-wh="new">New round</button><button class="sm rd warn" data-wh="reset">Reset</button></div><div class="kv" style="margin-top:6px" id="wh-kv"></div>`, ' <span class="faint" id="wh-badge"></span>')}
      </div>`;
  }
  const holderName = c => { const x = c && c.controlHolder; return !x ? '' : typeof x === 'string' ? x : (x.name || x.display || x.user || x.id || ''); };
  function renderCustoms() {
    const c = S.get('customs'), ok = S.get('customsOk'), note = $('#cu-note');
    const msg = ok === false ? (c ? 'Customs state is stale (the Host stopped answering it).' : 'The Host has no /api/customs/state yet. Buttons still work (they run the same chat commands the website sends); the live queue appears once the Host has it.') : '';
    note.hidden = !msg; note.textContent = msg;
    const holder = holderName(c), mine = ui.tookControl && !holder;
    $('#cu-ctl').className = 'ctl ' + (holder ? 'other' : mine ? 'mine' : 'free');
    $('#cu-who').textContent = holder ? '🎮 In control: ' + holder : mine ? '🎮 In control: you (app)' : '🎮 In control: nobody · any click takes it';
    const q = (c && Array.isArray(c.queue)) ? c.queue : [];
    $('#cu-badge').textContent = c ? (c.open === true ? 'queue open' : c.open === false ? 'queue closed' : '') + (c.format ? ' · ' + c.format : '') + (c.gameMode && c.gameMode !== 'standard' ? ' · ' + c.gameMode : '') : '';
    $('#cu-act').textContent = c && c.activity && c.activity !== 'none' ? '· ' + c.activity : '';
    $('#cu-qn').textContent = c ? '· ' + q.length + ' waiting' : '';
    C.reconcile($('#cu-queue'), q.map((p, i) => ({ u: p.username || p.user || p.name || '?', d: p.display || p.username || p.name || '?', n: i + 1, m: p.mmr })), r => r.u, () => { const li = h('li'); li.append(h('span', 'num'), h('span', 't'), h('button', 'x ghost sm', '✕')); li.lastChild.title = 'Kick'; return li; },
      (li, r) => { li.dataset.u = r.u; li.children[0].textContent = r.n; li.children[1].textContent = r.d + (r.m ? ' · ' + r.m : ''); });
    const m = c && c.match, live = !!(m && m.status !== 'finished');
    $('#cu-match').textContent = m ? '· ' + (m.status || 'on') + (m.id != null ? ' #' + m.id : '') : '· none';
    const tv = JSON.stringify([m && m.orange, m && m.blue]), tb = $('#cu-teams');
    if (tb._s !== tv) { tb._s = tv; tb.textContent = ''; for (const [k, lbl] of [['orange', 'Orange'], ['blue', 'Blue']]) { const col = h('div', 'tm ' + k); col.append(h('b', '', lbl)); const names = (m && m[k]) || []; names.forEach(n => col.append(h('span', 'ell', n))); if (!names.length) col.append(h('span', 'faint', '–')); tb.append(col); } }
    const cur = { mode: c && c.mode, format: c && c.format, gamemode: c && (c.gameMode || c.gamemode), koth: c ? (c.koth ? 'on' : 'off') : null, activity: c && c.activity, queue: c ? (c.open ? 'open' : 'close') : null };
    for (const bt of $$('#tab-customs [data-st]')) {
      const [k, v] = bt.dataset.st.split(':'), on = cur[k] === v;
      if (k === 'win') bt.disabled = !live;
      else if (k === 'activity') bt.classList.toggle('is-live', on);
      else if (k === 'queue') bt.classList.toggle('q-on', on);
      else { bt.classList.toggle('cur', on); bt.disabled = on; }
    }
    $('#cu-manual').hidden = !(c && c.mode === 'picks');
    const w = S.get('wheel');
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
        d.className = 'feeditem ' + (x.kind === 'sub' ? 'sub ' : '') + 'k-' + (x.t || (x.kind === 'group' ? 'p' : '')) + (x.t === 'e' ? ' ev' : ''); d.dataset.k = x.key;
        d.children[0].textContent = fmtT(x.ts); const t = d.children[1]; t.textContent = '';
        if (x.kind === 'group') { const a = h('a', 'grp', x.label); a.title = x.names; a.dataset.g = x.key; t.append(a, document.createTextNode(' ' + x.text + (x.open ? '' : ' (click to show)'))); }
        else if (x.kind === 'teams') { t.append(h('span', 'who', x.text + ': '), h('span', 'tb', 'Blue: ' + (x.blue.join(', ') || '–')), document.createTextNode('  '), h('span', 'to', 'Orange: ' + (x.orange.join(', ') || '–'))); }
        else if (x.t === 'c') t.append(h('span', 'who', x.user), document.createTextNode(': ' + x.text));
        else t.append(h('span', x.t === 'e' ? 'who' : 'lg lg-' + (x.type || 'x'), x.text));
      });
    if (stick) box.scrollTop = box.scrollHeight;
    const n = [];
    if (ui.chatOk === false) n.push('Live chat needs the Host chat feed.');
    if (ui.logsOk === false && (ui.logCat === 'backend' || ui.logCat === 'all')) n.push('Backend log (bot + overlay actions) needs the Host /api/logs: not connected yet. Players log is built here from queue changes (no history before this window opened).');
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
  // Host logs ({seq, ts, cat: players|backend, type, ...}); chat lines come from /api/chat/recent so cat chat is skipped here
  function addLogs(list) {
    const T = { players: 'p', backend: 'b' };
    const add = (list || []).filter(x => T[x.cat]).map(x => Object.assign({}, x, { k: 'L' + x.seq, t: T[x.cat], ts: x.ts > 1e11 ? x.ts / 1000 : x.ts }));
    if ((list || []).length) ui.logSeq = Math.max(ui.logSeq, ...list.map(x => x.seq || 0));
    if (C.mergeFeed(ui.feed, add, x => x.k, 800)) { ui.feed.sort((a, b) => a.ts - b.ts); schedule('feed'); }
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
  const R = { scenes: renderScenes, sources: renderSources, bar: renderBar, customs: renderCustoms, feed: renderFeed, cmds: renderCmds, overlays: renderOverlays };
  S.subscribe(ch => {
    if (ch.includes('tree')) schedule('scenes', 'sources', 'bar');
    if (ch.some(k => ['obsStatus', 'live', 'host', 'hostUp', 'link'].includes(k))) schedule('bar');
    if (ch.includes('customs') || ch.includes('wheel') || ch.includes('customsOk')) schedule('customs');
    if (ch.includes('customs')) { const nx = S.get('customs'); if (ui.logsOk !== true) { const add = C.diffCustoms(ui.prevCustoms, nx); if (add.length && C.mergeFeed(ui.feed, add, x => x.k, 800)) { ui.feed.sort((a, b2) => a.ts - b2.ts); schedule('feed'); } } ui.prevCustoms = nx; }
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
      const r = await api.get('/api/logs?cat=all&since=' + ui.logSeq + '&limit=500');
      if (r.status === 404) { if (ui.logsOk !== false) { ui.logsOk = false; schedule('feed'); } return; }
      if (r.ok) { if (ui.logsOk !== true) { ui.logsOk = true; schedule('feed'); } addLogs(r.json.items); }
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
      if (m.event === 'snapshot' && d) { d.obs && applyTree(d.obs); d.obsstatus && S.set({ obsStatus: d.obsstatus }); d.live && S.set({ live: d.live }); d.customs && S.set({ customs: d.customs, customsOk: true }); d.wheel && S.set({ wheel: normWheel(d.wheel) }); d.chat && addChat(d.chat); d.logs && (ui.logsOk = true, addLogs(d.logs)); d.activity && addActivity(d.activity); }
      else if (m.event === 'obs') applyTree(d); else if (m.event === 'obsstatus') S.set({ obsStatus: d }); else if (m.event === 'live') S.set({ live: d });
      else if (m.event === 'customs') S.set({ customs: d, customsOk: true }); else if (m.event === 'wheel') S.set({ wheel: normWheel(d) });
      else if (m.event === 'chat') { ui.chatOk = true; addChat([d]); } else if (m.event === 'activity') addActivity([d]); else if (m.event === 'log') { ui.logsOk = true; addLogs([d]); }
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
    if (b && b.dataset.cu) { if (b.disabled) return; if (b.classList.contains('warn') && !armed(b)) return; sendCustom(b.dataset.cu, b.dataset.v, b); }
    else if (b && b.dataset.wh) { if (b.classList.contains('warn') && !armed(b)) return; flash(b); ui.tookControl = true; tokenReady.then(() => api.post('/api/wheel/' + b.dataset.wh)).then(r => { if (r.ok) { toast('Wheel: ' + b.dataset.wh); r.json && r.json.wheel ? S.set({ wheel: normWheel(r.json.wheel) }) : pollers.wheel.kick(); } else toast('Wheel: ' + r.error, true); }); }
    else if (b && b.id === 'cu-pickgo') { const v = $('#cu-pick').value.trim().replace(/\s+/g, ' '); C.customsText('pick', v) ? (sendCustom('pick', v, b), $('#cu-pick').value = '') : toast('Type 1 to 4 Twitch names first', true); }
    else if (b && b.id === 'cu-kickgo') { C.customsText('kick', $('#cu-kick').value) ? (sendCustom('kick', $('#cu-kick').value, b), $('#cu-kick').value = '') : toast('Type a Twitch name first', true); }
  });
  $('#tab-customs').addEventListener('change', e => { const k = e.target.dataset.cuset; if (!k || !e.target.value) return; sendCustom(k, e.target.value, e.target); });
  $('#tab-customs').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.target.id === 'cu-kick' || e.target.id === 'cu-pick')) $(e.target.id === 'cu-kick' ? '#cu-kickgo' : '#cu-pickgo').click(); });
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
