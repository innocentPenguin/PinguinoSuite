// Synchra-style dashboard: /?type=dash  (source tabs bar, Activity Feed panel, Chat panel, Ctrl+K search). /?type=dash&panel=chat|activity shows one panel (for pop-out).
// Globals from index.html/chat.js: $, esc, api, q, W, msgs, conns, isBot, colourOf, badgeHtml, bodyHtml, popOut, sideToggle.
const DASH = {profs: {}, active: 'Default', builtin: [], src: 'all', paused: false, queue: [], lock: true, edit: false, ign: new Set(), user: '', menu: null, panels: ['activity', 'chat'], widths: [50, 50], fs: {activity: 14, chat: 14}, split: {on: false, dir: 'row', a: 'all', b: 'all', kind: 'source'}, viewers: {}};
try { Object.assign(DASH, JSON.parse(localStorage.getItem('multi-dash') || '{}'), {paused: false, queue: [], menu: null, edit: false, ign: new Set()}); } catch (e) { /* storage blocked */ }
const dashSave = () => {      // lock stays per browser; the layout lives on the server in the active profile
  try { localStorage.setItem('multi-dash', JSON.stringify({lock: DASH.lock})); } catch (e) { /* ignore */ }
  if (DASH.active) fetch('/api/dash', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({name: DASH.active, layout: {panels: DASH.panels, widths: DASH.widths, src: DASH.src, fs: DASH.fs, split: DASH.split}})}).catch(() => {});
};
function dApply(st) { DASH.profs = st.profiles; DASH.active = st.active; DASH.builtin = st.builtin; const l = st.profiles[st.active]; if (l) { DASH.panels = l.panels; DASH.widths = l.widths; DASH.src = l.src; DASH.fs = l.fs || DASH.fs; DASH.split = l.split || DASH.split; } }
const D_LOGO = {twitch: ['#9146ff', 'T'], youtube: ['#e62117', '▶'], kick: ['#53fc18', 'K'], discord: ['#5865f2', 'D'], tiktok: ['#111', '♪']};
const D_PILL = {follow: ['Follow', '#4ade80', '#08210f'], redeem: ['Redeem', '#8ecfe0', '#08242c'], sub: ['Sub', '#a78bfa', '#170a3a'], resub: ['Resub', '#a78bfa', '#170a3a'],
  gift: ['Gift', '#c084fc', '#220a3a'], cheer: ['Cheer', '#facc15', '#2b2200'], raid: ['Raid', '#f472b6', '#38081f'], announcement: ['Notice', '#fb923c', '#2b1200'], shoutout: ['Shoutout', '#7cb7f5', '#071b33'], ban: ['Ban', '#f87171', '#330808'], timeout: ['Timeout', '#fb923c', '#2b1200'], unban: ['Unban', '#94a3b8', '#0b1220'], mod: ['Mod', '#4ade80', '#08210f'], unmod: ['Unmod', '#94a3b8', '#0b1220']};
const D_UNIT = {raid: 'viewers', cheer: 'bits', gift: 'subs', resub: 'months', sub: 'months', redeem: 'points'};
const dIcon = p => { const [c, l] = D_LOGO[p] || ['#888', '?']; return `<span class="d-ic" style="background:${c};color:${p === 'kick' ? '#111' : '#fff'}" title="${esc(p)}">${l}</span>`; };
const dAge = ts => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? 'now' : s < 3600 ? Math.floor(s / 60) + 'm' : s < 86400 ? Math.floor(s / 3600) + 'h' : Math.floor(s / 86400) + 'd'; };
const dLink = html => html.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
const dOk = m => (DASH.src === 'all' || m.platform === DASH.src) && (!DASH.user || (m.user || '').toLowerCase() === DASH.user) && !DASH.ign.has((m.user || '').toLowerCase());
const dName = m => (m.display || m.user || '');
const dRest = m => String(m.text || '').replace(new RegExp('^' + dName(m).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*', 'i'), '').replace(/^(followed|redeemed|subscribed|resubscribed|gifted subs|cheered|is raiding)\s*/i, '');

const D_CSS = `
#dash{display:flex;flex-direction:column;height:100vh;box-sizing:border-box;padding:6px;gap:6px;background:var(--bg)}
.d-top,.d-tabs{display:flex;gap:6px;align-items:center;border:1px solid var(--line);border-radius:8px;padding:5px 8px;background:var(--panel,#1a1814)}
.d-top .grow{flex:1}.d-btn{background:transparent;border:1px solid var(--line);color:inherit;border-radius:6px;padding:3px 10px;cursor:pointer;font:inherit}.d-btn:hover{border-color:var(--accent)}.d-btn.on{background:var(--accent);color:#111}
.d-search{min-width:230px;text-align:left;color:var(--mut)}.d-search kbd{float:right;margin-left:30px;background:#ffffff18;border-radius:4px;padding:0 6px;font-size:11px}
.d-tabs{overflow-x:auto}.d-tab{display:flex;align-items:center;gap:7px;padding:3px 8px;border-radius:6px;cursor:pointer;white-space:nowrap;border:1px solid transparent}.d-tab.on{border-color:var(--accent);background:#ff8a1f18}
.d-ic{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font:800 12px 'Segoe UI',sans-serif;flex:none}
.d-dot{width:9px;height:9px;border-radius:50%;background:#777;display:inline-block}.d-dot.connected{background:#4ade80}.d-dot.connecting,.d-dot.reconnecting{background:#facc15}.d-dot.error,.d-dot.needs_auth{background:#f87171}
.d-kebab{opacity:.6;cursor:pointer;padding:0 6px;border-radius:4px}.d-kebab:hover{opacity:1;background:#ffffff18}
#d-panels{flex:1;display:flex;gap:6px;min-height:0}.d-panel{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:8px;min-width:0;background:var(--panel,#1a1814);overflow:hidden}
.d-edit .d-panel{outline:2px dashed var(--accent);outline-offset:-3px}
.d-ph{display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--line)}.d-ph b{flex:1;font-size:1.05em}.d-ph select{background:transparent;color:inherit;border:0;font:inherit;opacity:.8}
.d-ic2{cursor:pointer;opacity:.7;padding:2px 5px;border-radius:4px}.d-ic2:hover{opacity:1;background:#ffffff18}
.d-alerts{display:flex;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid var(--line)}.d-alerts b{margin-right:6px}.d-alerts .d-btn{padding:4px 12px}
.d-list{flex:1;overflow-y:auto;min-height:0}.d-row{display:flex;gap:12px;align-items:flex-start;padding:10px 12px;border-bottom:1px solid var(--line);position:relative}
.d-age{opacity:.65;min-width:2.4em;padding-top:2px}.d-main{flex:1;min-width:0;word-break:break-word}.d-pill{display:inline-block;border-radius:6px;padding:1px 9px;font-weight:700;margin:0 8px 0 10px}
.d-user{font-weight:700}.d-chip{display:inline-block;background:#ffffff1c;border-radius:6px;padding:1px 9px;margin-left:8px}.d-link{display:block;margin-top:3px}.d-link a{color:#8ab4ff}
.d-chat .d-row{padding:7px 12px;gap:6px;align-items:baseline;flex-wrap:wrap}.d-chat .d-row.notice{opacity:.6;font-size:.95em}.d-date{text-align:center;color:var(--mut);font-size:.8em;padding:6px;border-bottom:1px solid var(--line)}
.d-chat .d-row .bd{margin-right:3px}.d-chat img.emo{height:1.6em;vertical-align:middle}
.d-menu{position:fixed;z-index:80;background:var(--panel,#1a1814);border:1px solid var(--accent);border-radius:8px;padding:4px;min-width:190px;box-shadow:0 6px 20px #000a}.d-menu div{padding:6px 10px;cursor:pointer;border-radius:5px}.d-menu div:hover{background:#ff8a1f30}.d-menu hr{border:0;border-top:1px solid var(--line);margin:3px 0}
.d-box{display:flex;gap:6px;align-items:center;padding:8px 10px;border-top:1px solid var(--line)}.d-box input{flex:1;background:transparent;border:0;color:inherit;font:inherit;outline:0}.d-box select{background:transparent;color:inherit;border:1px solid var(--line);border-radius:6px;padding:3px}
.d-sr{position:fixed;inset:0;background:#000a;z-index:90;display:flex;justify-content:center;padding-top:10vh}.d-sr>div{width:min(640px,92vw);max-height:70vh;background:var(--panel,#1a1814);border:1px solid var(--accent);border-radius:10px;display:flex;flex-direction:column}
.d-sr input{padding:12px;background:transparent;border:0;border-bottom:1px solid var(--line);color:inherit;font-size:1.1em;outline:0}.d-sr .d-list{padding:4px}
.d-viewers{opacity:.85;font-size:.85em}.d-div{flex:none;width:7px;margin:0 -3px;cursor:col-resize;border-radius:4px;z-index:5}.d-div:hover,.d-div.on{background:var(--accent)}.d-unlocked .d-div{background:#ffffff20}
.d-halves{flex:1;display:flex;min-height:0}.d-halves.hcol{flex-direction:column}.d-halves>.d-list{flex:1 1 0;border:0}.d-halves.hrow>.d-list+.d-list{border-left:2px solid var(--accent)}.d-halves.hcol>.d-list+.d-list{border-top:2px solid var(--accent)}
.d-emo{position:absolute;bottom:52px;right:14px;background:var(--panel,#1a1814);border:1px solid var(--accent);border-radius:8px;padding:6px;display:grid;grid-template-columns:repeat(8,1fr);gap:2px;z-index:70}.d-emo span{cursor:pointer;padding:3px;font-size:1.3em;border-radius:4px}.d-emo span:hover{background:#ff8a1f30}`;

async function renderDash() {
  if (!DASH.loaded) { try { dApply(await fetch('/api/dash').then(r => r.json())); } catch (e) { /* defaults */ } DASH.loaded = true; }
  $('#hdr').style.display = 'none';
  if (!$('#d-css')) { const s = document.createElement('style'); s.id = 'd-css'; s.textContent = D_CSS; document.head.appendChild(s); }
  const only = q.get('panel');
  $('#body').innerHTML = `<div id="dash" class="${DASH.edit ? 'd-edit' : ''}">${only ? '' : `<div class="d-top" id="d-top"></div><div class="d-tabs" id="d-tabs"></div>`}<div id="d-panels"></div></div>`;
  if (!only) { dTop(); dTabs(); }
  dPanels(); dFill(); dViewRefresh();
  fetch('/api/viewers').then(r => r.json()).then(c => window.dashViewers(c.counts)).catch(() => {});
}
function dTop() {
  $('#d-top').innerHTML = `<button class="d-btn" data-d="profile" title="Switch the saved window layout">Profile &#9662;</button><button class="d-btn ${DASH.edit ? 'on' : ''}" data-d="edit" ${DASH.lock ? 'disabled style="opacity:.5"' : ''} title="${DASH.lock ? 'Unlock first' : 'Move or remove panels'}">Edit layout</button>
    <button class="d-btn" data-d="add">+ Add</button><button class="d-btn" data-d="lock" title="${DASH.lock ? 'Layout locked' : 'Layout unlocked'}">${DASH.lock ? '&#128274;' : '&#128275;'}</button><span class="grow"></span><span class="d-viewers" id="d-vtot" title="People watching live right now"></span>
    <button class="d-btn d-search" data-d="search">&#128269; Search <kbd>Ctrl + K</kbd></button><button class="d-btn" data-d="settings" title="Text, highlights, sounds, split chat">&#9881;</button><a class="d-btn" href="/?type=obs&widget=chat" title="OBS widgets">OBS</a><a class="d-btn" href="/" title="Setup and connections">?</a>`;
}
const dViewTxt = p => { const n = DASH.viewers[p]; return n == null ? '' : '&#128065; ' + Number(n).toLocaleString(); };
function dViewRefresh() {
  document.querySelectorAll('[data-vp]').forEach(e => { e.innerHTML = dViewTxt(e.dataset.vp); });
  const t = $('#d-vtot'); if (!t) return; const v = Object.values(DASH.viewers).filter(x => x != null);
  t.innerHTML = v.length ? '&#128065; ' + v.reduce((a, b) => a + b, 0).toLocaleString() + ' watching' : '';
}
window.dashViewers = c => { if (c) DASH.viewers = c; if (W.type === 'dash') dViewRefresh(); };
function dTabs() {
  const el = $('#d-tabs'); if (!el) return;
  el.innerHTML = `<span class="d-btn ${DASH.src === 'all' ? 'on' : ''}" data-d="src" data-p="all" title="All sources">&#9638;</span>` + conns.map(c => `<span class="d-tab ${DASH.src === c.platform ? 'on' : ''}" data-d="src" data-p="${esc(c.platform)}">${dIcon(c.platform)}<span>${esc(c.channel || c.label)}</span><span class="d-viewers" data-vp="${esc(c.platform)}">${dViewTxt(c.platform)}</span>
    <span class="d-dot ${esc(c.status)}" title="${esc(c.label)}: ${esc(c.status)} ${esc(c.detail || '')}${c.official ? '' : ' (UNOFFICIAL)'}${c.capabilities && !c.capabilities.send ? ' (read-only)' : ''}"></span><span class="d-kebab" data-d="tabmenu" data-p="${esc(c.platform)}">&#8942;</span></span>`).join('');
}
function dPanels() {
  const only = q.get('panel'), list = only ? [only] : DASH.panels;
  $('#d-panels').className = DASH.lock ? '' : 'd-unlocked';
  $('#d-panels').innerHTML = list.map((p, i) => `${i && !only ? `<div class="d-div" data-div="${i - 1}" title="Drag to resize"></div>` : ''}<div class="d-panel d-${p}" data-panel="${p}" style="flex:${only ? 1 : DASH.widths[i] || 50};font-size:${DASH.fs[p] || 14}px">
    <div class="d-ph"><b>${p === 'activity' ? 'Activity Feed' : 'Chat'}</b>${DASH.edit ? `<span class="d-ic2" data-d="left" data-p="${p}">&#9664;</span><span class="d-ic2" data-d="right" data-p="${p}">&#9654;</span><span class="d-ic2" data-d="rm" data-p="${p}">&#10005;</span>` : ''}
      <select data-d="psrc" title="Which sources this panel shows"><option value="all">All sources</option>${conns.map(c => `<option value="${esc(c.platform)}" ${DASH.src === c.platform ? 'selected' : ''}>${esc(c.label)}</option>`).join('')}</select>
      <span class="d-ic2" data-d="fsm" data-p="${p}" title="Smaller text">A&minus;</span><span class="d-ic2" data-d="fsp" data-p="${p}" title="Bigger text">A+</span>${p === 'chat' ? `<span class="d-ic2" data-d="split" title="Split this chat in halves">&#9707;</span>` : ''}
      <span class="d-ic2" data-d="settings" title="Settings">&#9881;</span>${only ? '' : `<span class="d-ic2" data-d="pop" data-p="${p}" title="Open in its own window">&#8599;</span>`}</div>
    ${p === 'activity' ? `<div class="d-alerts"><b>&#128039; Alerts</b><button class="d-btn" data-d="pause" title="Pause new rows (they queue up)">${DASH.paused ? '&#9654;' : '&#10074;&#10074;'}</button><button class="d-btn" data-d="next" title="Show the next queued row">&#9193;</button><button class="d-btn" data-d="skip" title="Skip (drop) the next queued row">&#10006;</button><button class="d-btn" data-d="all" title="Show everything queued">&#9197;</button><span class="mut" id="d-qn"></span></div>` : ''}
    ${p === 'chat' && DASH.split.on ? `<div class="d-halves ${DASH.split.dir === 'col' ? 'hcol' : 'hrow'}"><div class="d-list" id="d-l-chat-a"></div><div class="d-list" id="d-l-chat-b"></div></div>` : `<div class="d-list" id="d-l-${p}"></div>`}
    ${p === 'chat' ? `<div class="d-box"><select id="d-plat">${conns.filter(c => c.capabilities && c.capabilities.send).map(c => `<option value="${esc(c.platform)}">${esc(c.label)}</option>`).join('')}</select><input id="d-txt" maxlength="500" placeholder="Message"><span class="d-ic2" data-d="emoji" title="Emoji">&#9786;</span><span class="d-ic2" data-d="send" title="Send to the chosen platform only">&#10148;</span></div>` : ''}</div>`).join('');
}
function dRowActivity(m) {
  const pill = D_PILL[m.event] || [m.event, '#aaa', '#111'], chips = [];
  if (m.amount) chips.push(`${m.amount.toLocaleString()} ${D_UNIT[m.event] || ''}`.trim());
  const rest = dRest(m), links = (rest.match(/https?:\/\/\S+/g) || []), txt = rest.replace(/https?:\/\/\S+/g, '').trim();
  if (txt) chips.push(txt.slice(0, 80));
  if ((m.flags || []).includes('refollow')) chips.push('refollow');
  return `<div class="d-row" data-id="${esc(m.id)}"><span class="d-age" data-ts="${m.ts}">${dAge(m.ts)}</span>${dIcon(m.platform)}<div class="d-main"><span class="d-pill" style="background:${pill[1]};color:${pill[2]};margin-left:0">${esc(pill[0])}</span><span class="d-user">${esc(dName(m))}</span>${chips.map(c => `<span class="d-chip" ${c === 'refollow' ? 'style="font-size:.8em;opacity:.8"' : ''}>${esc(c)}</span>`).join('')}${links.map(l => `<span class="d-link">${dLink(esc(l))}</span>`).join('')}</div><span class="d-kebab" data-d="rowmenu" data-u="${esc((m.user || '').toLowerCase())}" data-id="${esc(m.id)}">&#8942;</span></div>`;
}
function dRowChat(m) {
  const col = colourOf(m) || (m.platform === 'twitch' ? '#a970ff' : '#ff8a1f');
  if (m.event) return `<div class="d-row notice" data-id="${esc(m.id)}">${dIcon(m.platform)}<span><b>${esc(dName(m))}</b> ${dLink(esc(dRest(m) || m.text))}</span></div>`;
  return `<div class="d-row ${isBot(m) ? 'bot' : ''}" data-id="${esc(m.id)}">${dIcon(m.platform)}<span>${badgeHtml(m)}<b style="color:${col}">${esc(dName(m))}</b>: ${dLink(bodyHtml(m))}</span></div>`;
}
function dFill() {
  const a = $('#d-l-activity'), c = $('#d-l-chat');
  if (a) { a.innerHTML = msgs.filter(m => m.event && dOk(m)).slice(-100).reverse().map(dRowActivity).join('') || '<div class="empty">No activity yet. Follows, redeems, subs, gifts, cheers and raids show here.</div>'; }
  const ca = $('#d-l-chat-a'), cb = $('#d-l-chat-b');
  if (ca && cb) {
    const all = msgs.filter(m => dOk(m)), k = DASH.split.kind;
    const fa = k === 'events' ? all.filter(m => !m.event) : all.filter(m => DASH.split.a === 'all' || m.platform === DASH.split.a);
    const fb = k === 'events' ? all.filter(m => m.event) : all.filter(m => DASH.split.b === 'all' || m.platform === DASH.split.b);
    if (k === 'flow') { cb.innerHTML = all.slice(-60).map(dRowChat).join(''); ca.innerHTML = ''; dFlow(); }
    else { ca.innerHTML = fa.slice(-150).map(dRowChat).join(''); cb.innerHTML = fb.slice(-150).map(dRowChat).join(''); ca.scrollTop = ca.scrollHeight; cb.scrollTop = cb.scrollHeight; }
  }
  if (c) { c.innerHTML = `<div class="d-date">${new Date().toLocaleDateString(undefined, {year: 'numeric', month: 'long', day: 'numeric'})}</div>` + msgs.filter(dOk).slice(-200).map(dRowChat).join(''); c.scrollTop = c.scrollHeight; }
  const n = $('#d-qn'); if (n) n.textContent = DASH.queue.length ? DASH.queue.length + ' waiting' : '';
}
function dFlow() {      // newest rows live in B; whatever no longer fits in B continues at the bottom of A
  const a = $('#d-l-chat-a'), b = $('#d-l-chat-b'); if (!a || !b) return;
  b.style.overflow = 'hidden';
  while (b.scrollHeight > b.clientHeight + 1 && b.children.length > 1) a.appendChild(b.children[0]);
  while (a.children.length > 200) a.children[0].remove();
  a.scrollTop = a.scrollHeight;
}
window.dashAdd = m => {
  if (W.type !== 'dash' || !dOk(m)) return;
  const ca = $('#d-l-chat-a'), cb = $('#d-l-chat-b');
  if (ca && cb) {
    const k = DASH.split.kind, add = (el, ok) => { if (!ok) return; const end = el.scrollTop + el.clientHeight >= el.scrollHeight - 40; el.insertAdjacentHTML('beforeend', dRowChat(m)); while (el.children.length > 250) el.children[0].remove(); if (end) el.scrollTop = el.scrollHeight; };
    if (k === 'flow') { cb.insertAdjacentHTML('beforeend', dRowChat(m)); dFlow(); }
    else if (k === 'events') add(m.event ? cb : ca, true);
    else { add(ca, DASH.split.a === 'all' || m.platform === DASH.split.a); add(cb, DASH.split.b === 'all' || m.platform === DASH.split.b); }
  }
  const c = $('#d-l-chat'), a = $('#d-l-activity');
  if (c) { const end = c.scrollTop + c.clientHeight >= c.scrollHeight - 40; c.insertAdjacentHTML('beforeend', dRowChat(m)); while (c.children.length > 300) c.children[1].remove(); if (end) c.scrollTop = c.scrollHeight; }
  if (a && m.event) { if (DASH.paused) { DASH.queue.push(m); dFill(); } else { const e = a.querySelector('.empty'); if (e) e.remove(); a.insertAdjacentHTML('afterbegin', dRowActivity(m)); } }
};
window.dashConn = () => { if (W.type === 'dash') { dTabs(); const s = $('#d-plat'); if (s) { const v = s.value; dPanels(); dFill(); } } };
setInterval(() => document.querySelectorAll('#dash .d-age').forEach(e => { e.textContent = dAge(+e.dataset.ts); }), 30000);

function dMenu(x, y, items) {
  dMenuClose(); const el = document.createElement('div'); el.className = 'd-menu'; el.id = 'd-menu';
  el.innerHTML = items.map((it, i) => it === '-' ? '<hr>' : `<div data-mi="${i}">${esc(it[0])}</div>`).join('');
  el.style.left = Math.min(x, innerWidth - 210) + 'px'; el.style.top = Math.min(y, innerHeight - 40 * items.length) + 'px';
  el.addEventListener('click', e => { const d = e.target.closest('[data-mi]'); if (d) { items[+d.dataset.mi][1](); dMenuClose(); } });
  document.body.appendChild(el);
}
const dMenuClose = () => { const e = $('#d-menu'); if (e) e.remove(); };
async function dSearch() {
  const o = document.createElement('div'); o.className = 'd-sr'; o.id = 'd-sr';
  o.innerHTML = '<div><input id="d-sq" placeholder="Search chat, users, activity..." autofocus><div class="d-list" id="d-sl"><div class="empty">Type to search</div></div></div>';
  o.addEventListener('click', e => { if (e.target === o) o.remove(); });
  document.body.appendChild(o); const inp = $('#d-sq'); inp.focus(); let t;
  inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(async () => {
    const v = inp.value.trim(); if (!v) return;
    const r = await fetch('/api/search?q=' + encodeURIComponent(v)).then(r => r.json()).catch(() => []);
    $('#d-sl').innerHTML = r.slice(0, 60).map(m => m.event ? dRowActivity(m) : dRowChat(m)).join('') || '<div class="empty">Nothing found</div>'; }, 250); });
}
document.addEventListener('keydown', e => {
  if (W.type !== 'dash') return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (!$('#d-sr')) dSearch(); }
  else if (e.key === 'Escape') { const s = $('#d-sr'); if (s) s.remove(); dMenuClose(); }
  else if (e.key === 'Enter' && e.target.id === 'd-txt') dSend();
});
async function dSend() {
  const t = $('#d-txt'), p = $('#d-plat'); if (!t || !p || !t.value.trim()) return;
  const r = await fetch('/api/send', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({platform: p.value, text: t.value.trim()})}).then(r => r.json());
  if (r.ok) t.value = ''; else { t.placeholder = r.detail || 'Could not send'; t.value = ''; }
}
document.addEventListener('click', async e => {
  if (W.type !== 'dash') return;
  if (!e.target.closest('#d-menu') && !e.target.closest('[data-d="emoji"]')) { dMenuClose(); const em = $('#d-emo'); if (em && !e.target.closest('#d-emo')) em.remove(); }
  const t = e.target.closest('[data-d]'); if (!t) return;
  const a = t.dataset.d, p = t.dataset.p, r = t.getBoundingClientRect();
  if (a === 'src') { DASH.src = p; DASH.user = ''; dashSave(); renderDash(); }
  else if (a === 'psrc') return;
  else if (a === 'tabmenu') { e.stopPropagation(); const c = conns.find(x => x.platform === p) || {};
    dMenu(r.left, r.bottom, [[`${c.label || p}: ${c.status || '?'}${c.detail ? ' - ' + c.detail : ''}`, () => {}], '-', ['Show only this source', () => { DASH.src = p; dashSave(); renderDash(); }], ['Connection settings', () => { location.href = '/'; }], ['Pop out its chat', () => popOut('dash-' + p, location.origin + '/?type=dash&panel=chat', c.label || p, {w: 520, h: 800})]]); }
  else if (a === 'rowmenu') { e.stopPropagation(); const u = t.dataset.u;
    dMenu(r.left - 150, r.bottom, [['Copy name', () => navigator.clipboard && navigator.clipboard.writeText(u)], ['Show only this person', () => { DASH.user = u; dFill(); }], ['Clear person filter', () => { DASH.user = ''; dFill(); }], ['Hide this person here', () => { DASH.ign.add(u); dFill(); }]]); }
  else if (a === 'settings') sideToggle(true, 'text');
  else if (a === 'fsm' || a === 'fsp') { DASH.fs[p] = Math.min(40, Math.max(10, (DASH.fs[p] || 14) + (a === 'fsp' ? 1 : -1))); const el = document.querySelector(`.d-panel[data-panel="${p}"]`); if (el) el.style.fontSize = DASH.fs[p] + 'px'; if (DASH.split.on) dFlow(); dashSave(); }
  else if (a === 'split') {
    const sp = DASH.split, on = o => { Object.assign(sp, o, {on: true}); dashSave(); renderDash(); };
    const plats = conns.map(c => c.platform), a1 = plats[0] || 'all', b1 = plats[1] || 'all';
    dMenu(r.left - 260, r.bottom, [[sp.on ? 'Split is ON - choose another split:' : 'Split the chat in two halves:', () => {}], '-',
      ['Side by side: newest on the right, older flows to the left', () => on({kind: 'flow', dir: 'row'})],
      ['Top and bottom: newest at the bottom, older flows up', () => on({kind: 'flow', dir: 'col'})],
      ['Side by side: one platform each', () => on({kind: 'source', dir: 'row', a: a1, b: b1})],
      ['Top and bottom: one platform each', () => on({kind: 'source', dir: 'col', a: a1, b: b1})],
      ['Chat on the left, events on the right', () => on({kind: 'events', dir: 'row'})],
      '-', ['Open the two halves as separate windows (2 monitors)', () => dSplitWindows()],
      ...(sp.on ? [['Back to one chat', () => { sp.on = false; dashSave(); renderDash(); }]] : [])]);
  }
  else if (a === 'search') dSearch();
  else if (a === 'lock') { DASH.lock = !DASH.lock; if (DASH.lock) DASH.edit = false; dashSave(); renderDash(); }
  else if (a === 'edit') { DASH.edit = !DASH.edit; renderDash(); }
  else if (a === 'add') dMenu(r.left, r.bottom, [['Activity Feed', () => { if (!DASH.panels.includes('activity')) DASH.panels.unshift('activity'); dashSave(); renderDash(); }], ['Chat', () => { if (!DASH.panels.includes('chat')) DASH.panels.push('chat'); dashSave(); renderDash(); }]]);
  else if (a === 'profile') dMenu(r.left, r.bottom, [...Object.keys(DASH.profs).map(n => [(n === DASH.active ? '✓ ' : '') + n, async () => { dApply(await fetch('/api/dash/active', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({name: n})}).then(r => r.json())); renderDash(); }]), '-',
    ['Save layout as new profile...', async () => { const n = prompt('Profile name?'); if (!n || !n.trim()) return; DASH.active = n.trim(); dashSave(); setTimeout(async () => { dApply(await fetch('/api/dash').then(r => r.json())); renderDash(); }, 300); }],
    ...(DASH.builtin.includes(DASH.active) ? [] : [['Delete profile "' + DASH.active + '"', async () => { dApply(await fetch('/api/dash/' + encodeURIComponent(DASH.active), {method: 'DELETE'}).then(r => r.json())); renderDash(); }]])]);
  else if (a === 'rm') { DASH.panels = DASH.panels.filter(x => x !== p); dashSave(); renderDash(); }
  else if (a === 'left' || a === 'right') { const i = DASH.panels.indexOf(p), j = a === 'left' ? i - 1 : i + 1; if (j >= 0 && j < DASH.panels.length) { [DASH.panels[i], DASH.panels[j]] = [DASH.panels[j], DASH.panels[i]]; dashSave(); renderDash(); } }
  else if (a === 'pop') popOut('dash-' + p, location.origin + '/?type=dash&panel=' + p, p === 'chat' ? 'Chat' : 'Activity Feed', {w: 520, h: 800});
  else if (a === 'pause') { DASH.paused = !DASH.paused; if (!DASH.paused) dFlush(DASH.queue.length); renderDash(); }
  else if (a === 'next') dFlush(1);
  else if (a === 'skip') { DASH.queue.shift(); dFill(); }
  else if (a === 'all') dFlush(DASH.queue.length);
  else if (a === 'send') dSend();
  else if (a === 'emoji') { if ($('#d-emo')) return $('#d-emo').remove(); const d = document.createElement('div'); d.id = 'd-emo'; d.className = 'd-emo'; d.innerHTML = ['😀','😂','😍','😎','😭','😡','🥳','🤔','👍','👏','🔥','🎉','💜','🐧','❤️','✨'].map(x => `<span>${x}</span>`).join(''); d.addEventListener('click', ev => { if (ev.target.tagName === 'SPAN') { $('#d-txt').value += ev.target.textContent; $('#d-txt').focus(); } }); $('.d-chat').appendChild(d); }
});
async function dSplitWindows() {
  const mode = DASH.split.kind === 'events' ? 'events' : DASH.split.kind === 'source' ? 'platform' : 'flow', plats = [DASH.split.a, DASH.split.b].filter(x => x && x !== 'all');
  const j = await fetch('/api/splits/apply', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({mode, platforms: plats, aot: false})}).then(r => r.json()).catch(() => ({}));
  if (!j.panes) return;
  ['a', 'b'].forEach(k => popOut('pane-split-' + k, location.origin + '/?type=chat&pane=split-' + k, j.panes['split-' + k].name, {w: 560, h: 520, fresh: true}));
}
// drag the divider between two panels
document.addEventListener('mousedown', e => {
  const d = e.target.closest && e.target.closest('.d-div'); if (!d || W.type !== 'dash' || DASH.lock) return;
  e.preventDefault(); const i = +d.dataset.div, ps = [...document.querySelectorAll('.d-panel')]; d.classList.add('on');
  const tot = DASH.widths[i] + DASH.widths[i + 1], x0 = ps[i].getBoundingClientRect().left, w = ps[i].getBoundingClientRect().width + ps[i + 1].getBoundingClientRect().width;
  const mv = ev => { const f = Math.min(0.9, Math.max(0.1, (ev.clientX - x0) / w)); DASH.widths[i] = Math.round(tot * f); DASH.widths[i + 1] = tot - DASH.widths[i]; ps[i].style.flex = DASH.widths[i]; ps[i + 1].style.flex = DASH.widths[i + 1]; if (DASH.split.on) dFlow(); };
  const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); d.classList.remove('on'); dashSave(); };
  document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
});
document.addEventListener('change', e => { if (W.type === 'dash' && e.target.dataset.d === 'psrc') { DASH.src = e.target.value; dashSave(); renderDash(); } });
function dFlush(n) {
  const a = $('#d-l-activity'); if (!a) return;
  DASH.queue.splice(0, n).forEach(m => a.insertAdjacentHTML('afterbegin', dRowActivity(m)));
  const k = $('#d-qn'); if (k) k.textContent = DASH.queue.length ? DASH.queue.length + ' waiting' : '';
}
