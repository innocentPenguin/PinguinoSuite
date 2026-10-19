// Chat: the combined chat page/window (all platforms, badges, emotes, colours, search, pins, quick mod actions, reply)
// and the stream-safe popout. Uses globals from index.html ($, esc, api, W, msgs, conns, cards, hhmm, WID, TIERS, pass).
let BOTS = new Set(), MYNAMES = new Set(), MUTED = new Set(), PINS = [];
const isBot = m => !!(m.is_bot || m.is_self || BOTS.has((m.user || '').toLowerCase()));
fetch('/api/setup').then(r => r.json()).then(s => {
  BOTS = new Set((s.settings.bot_accounts || []).map(x => x.toLowerCase()));
  MYNAMES = new Set((s.settings.my_names || []).map(x => x.toLowerCase()));
}).catch(() => {});
fetch('/api/rules').then(r => r.json()).then(r => { MUTED = new Set(((r.rules || {}).muted || []).map(x => x.toLowerCase())); }).catch(() => {});
fetch('/api/pins').then(r => r.json()).then(r => { PINS = r.pins || []; }).catch(() => {});

const CF = (() => {
  const k = 'multi-chat-' + (typeof WID !== 'undefined' && WID ? WID : 'page');
  let f = {off: [], bots: 'dim', prio: false, strip: true, q: false};
  try { f = Object.assign(f, JSON.parse(localStorage.getItem(k) || '{}')); } catch (e) { /* storage may be blocked */ }
  f.save = () => { try { localStorage.setItem(k, JSON.stringify({off: f.off, bots: f.bots, prio: f.prio, strip: f.strip, q: f.q})); } catch (e) { /* ignore */ } };
  return f;
})();
let chatTarget = null, searchTerm = '', searchSeq = 0;

// --- rendering helpers ---------------------------------------------------------------
const BADGES = {broadcaster: ['HOST', '#e0455b'], moderator: ['MOD', '#2fa84f'], vip: ['VIP', '#d94fa0'], subscriber: ['SUB', '#b36b00'],
  founder: ['SUB', '#b36b00'], partner: ['✓', '#b36b00'], staff: ['STAFF', '#999'], 'sub-gifter': ['GIFT', '#b36b00'], 'bits': ['BITS', '#b58900']};
const badgeHtml = m => (m.badges || []).filter(b => BADGES[b]).slice(0, 4).map(b => `<span class="bd" style="background:${BADGES[b][1]}" title="${esc(b)}">${BADGES[b][0]}</span>`).join('');
const emoteUrl = id => `https://static-cdn.jtvnimg.com/emoticons/v2/${encodeURIComponent(id)}/default/dark/1.0`;
function bodyHtml(m) {
  const map = {}; (m.emotes || []).forEach(e => { if (e.text) map[e.text] = e.id; });
  const parts = String(m.text || '').split(/(\s+)/).map(tok => map[tok] ? `<img class="emo" alt="${esc(tok)}" title="${esc(tok)}" src="${emoteUrl(map[tok])}" onerror="this.replaceWith(document.createTextNode(this.alt))">` : esc(tok)).join('');
  return parts;
}
const mentionsMe = m => { const t = (m.text || '').toLowerCase(); return !isBot(m) && [...MYNAMES].some(n => t.includes(n)); };
const colourOf = m => /^#[0-9a-fA-F]{6}$/.test(m.color || '') ? m.color : '';
const canMod = m => m.platform === 'twitch' && !isBot(m) && (conns.find(c => c.platform === 'twitch') || {capabilities: {}}).capabilities;

const MSGC = new Map();
const foreignText = t => { const l = [...String(t)].filter(c => /\p{L}/u.test(c)); return l.length >= 4 && l.filter(c => c.charCodeAt(0) > 127).length / l.length > 0.3; };
const msgById = id => MSGC.get(id) || msgs.find(m => m.id === id) || null;
const isQuestionForMe = m => (m.reasons || []).some(r => ['question', 'mention', 'reply_to_me'].includes(r.rule)) || (/\?/.test(m.text || '') && mentionsMe(m)) || m.event === 'cheer';
function chatVisible(m) {
  if (CF.off.includes(m.platform) || !pass(m)) return false;
  if (CF.bots === 'hide' && isBot(m)) return false;
  if (CF.q && !isBot(m) && !isQuestionForMe(m)) return false;
  if (CF.prio && !isBot(m) && !(TIERS[m.tier || 'none'] >= TIERS.medium)) return false;
  return true;
}
function chatMsg(m, opts = {}) {
  const bot = isBot(m), mine = m.is_self, men = mentionsMe(m), caps = canMod(m) || {};
  const mod = (m.badges || []).includes('moderator') || (m.badges || []).includes('broadcaster');
  const reasons = (m.reasons || []).map(r => `${r.rule} ${r.points > 0 ? '+' : ''}${r.points}`).join(', ');
  const rep = m.reply_to_user ? `<span class="rep">&#8618; ${esc(m.reply_to_user)}</span>` : '';
  const flag = bot ? '<span class="bt">bot</span>' : (m.first_time ? '<span class="bt first">first</span>' : '');
  const col = colourOf(m);
  if (m.id && !opts.plain) { MSGC.set(m.id, m); if (MSGC.size > 1500) MSGC.delete(MSGC.keys().next().value); }
  const assistBtns = opts.plain || !m.id || m.event || bot ? '' : `<button data-suggest="${esc(m.id)}" title="Suggest replies (you approve, nothing is sent by itself)">&#128161;</button>
    ${foreignText(m.text) ? `<button data-translate="${esc(m.id)}" title="Translate to English">&#127760;</button>` : ''}<button data-mark="${esc(m.id)}" title="Mark to answer (adds a priority card)">&#9733;</button>
    <button data-mute="${esc(m.user)}" title="Mute this viewer in the ranking (local)">&#128263;</button>`;
  const tools = opts.plain || !m.id ? '' : `<span class="tools">${assistBtns}${bot ? '' : `<button data-reply="${esc(m.id)}" title="Reply (goes to ${esc(m.platform)} only)">&#8617;</button>`}
    <button data-pin="${esc(m.id)}" title="Pin to the top">&#128204;</button>
    ${caps.mod_timeout ? `<button data-mod="timeout" data-id="${esc(m.id)}" title="Timeout 10 min">&#9201;</button><button data-mod="ban" data-id="${esc(m.id)}" title="Ban">&#9940;</button>` : ''}
    ${caps.mod_delete ? `<button data-mod="delete" data-id="${esc(m.id)}" title="Delete this message">&#128465;</button>` : ''}</span>`;
  return `<div class="msg tier-${m.tier} ${styleClasses(m)}${bot ? ' bot' : ''}${CF.bots === 'dim' ? '' : ' nodim'}${mine ? ' self' : ''}${mod ? ' modmsg' : ''}" data-mid="${esc(m.id)}" title="${esc(reasons ? 'score ' + m.score + ': ' + reasons : '')}">
    <span class="t">${hhmm(m.ts)}</span>${markerHtml(m.platform)}${badgeHtml(m)}<span class="u" ${col ? `style="color:${col}"` : ''} ${opts.plain || !m.user_id ? '' : `data-chatter="${esc(m.platform)}|${esc(m.user_id)}|${esc(m.id)}" title="Who is this?"`}>${esc(m.display || m.user)}</span>${flag}${eventLabel(m)}${rep}${bodyHtml(m)}${tools}</div>`;
}
function chatAdd(m) {
  if (searchTerm) return;
  const f = $('#cfeed'); if (!f || !chatVisible(m)) return;
  const atEnd = f.scrollTop + f.clientHeight >= f.scrollHeight - 40;
  f.insertAdjacentHTML('beforeend', chatMsg(m));
  while (f.children.length > 500) f.firstChild.remove();
  if (W.scroll !== 'manual' && atEnd) f.scrollTop = f.scrollHeight;
}
function chatFeed() {
  const f = $('#cfeed'); if (!f) return;
  f.innerHTML = msgs.filter(chatVisible).slice(-300).map(m => chatMsg(m)).join('') || '<div class="empty">No messages yet. When a connected platform gets chat, it shows up here.</div>';
  f.scrollTop = f.scrollHeight;
}
function chatPins() {
  const s = $('#cpins'); if (!s) return;
  s.innerHTML = PINS.map(p => `<div class="pin">&#128204; <span class="pf">${esc(p.platform)}</span><b ${/^#/.test(p.color || '') ? `style="color:${esc(p.color)}"` : ''}>${esc(p.display)}</b> ${esc(p.text)}
    <button class="lnk" data-unpin="${esc(p.id)}">unpin</button></div>`).join('');
}
function chatStrip() {
  const s = $('#cstrip'); if (!s) return;
  const pf = PANE && PANE.filter || {}, open = (cards.open || []).filter(c => !CF.off.includes(c.platform) && pf.kind !== 'events' && (!(pf.platforms || []).length || pf.platforms.includes(c.platform))).slice(0, 3);
  if (!CF.strip) { s.innerHTML = `<button class="lnk" data-cf="strip">Show ${(cards.open || []).length} message(s) that need a reply</button>`; return; }
  s.innerHTML = (open.length ? open.map(c => `<div class="cc ${c.tier === 'high' ? 'high' : ''}"><div class="ch"><span class="pf">${esc(c.platform)}</span><b>${esc(c.display)}</b>
      <span class="mut" title="${esc((c.reasons || []).map(r => r.rule + ' ' + r.points).join(', '))}">score ${c.score}</span></div>
      <div>${esc(c.text)}</div><div class="act"><button class="p" data-ca="answer" data-id="${esc(c.id)}">Answered</button><button data-ca="reply" data-id="${esc(c.id)}">Reply</button>
      <button data-ca="snooze" data-id="${esc(c.id)}">Snooze</button><button data-ca="dismiss" data-id="${esc(c.id)}">Dismiss</button></div></div>`).join('')
    : '<div class="mut cnone">Nothing needs a reply right now.</div>') +
    ((cards.open || []).length > 3 ? `<div class="mut cnone">+${cards.open.length - 3} more in the Needs-an-answer window</div>` : '') +
    '<button class="lnk" data-cf="strip">Hide</button>';
}
function chatCompose() {
  const sendable = conns.filter(c => c.capabilities && c.capabilities.send && c.status === 'connected');
  const box = $('#ccomp'); if (!box) return;
  if (!sendable.length) { box.innerHTML = '<div class="mut cnone">Replying is off: no connected platform can send yet. Set one up in the Multi launcher.</div>'; return; }
  const cur = ($('#cplat') || {}).value;
  box.innerHTML = `${chatTarget ? `<div class="ctgt">Replying to <b>${esc(chatTarget.display || chatTarget.user)}</b>: ${esc((chatTarget.text || '').slice(0, 50))} <button class="lnk" data-cf="clr">cancel</button></div>` : ''}
    <div class="tpls">${TPLS.map((t, i) => `<button class="chip2" data-tpl="${i}" title="${esc(t)}">${esc(t.length > 26 ? t.slice(0, 25) + '...' : t)}</button>`).join('')}<button class="lnk" data-assist="tpls">edit</button></div>
    <div class="row"><select id="cplat" title="A message goes to this ONE platform only">${sendable.map(c => `<option value="${esc(c.platform)}">${esc(c.label)}</option>`).join('')}</select>
    <input id="ctxt" maxlength="500" placeholder="Type a reply - goes to the platform on the left only" style="flex:1"><button class="p" id="cgo">Send</button></div><div id="cres" class="mut"></div>`;
  if (chatTarget && sendable.some(c => c.platform === chatTarget.platform)) $('#cplat').value = chatTarget.platform;
  else if (cur) $('#cplat').value = cur;
  $('#cgo').onclick = chatSend; $('#ctxt').onkeydown = e => { if (e.key === 'Enter') chatSend(); };
}
async function chatSend() {
  const text = $('#ctxt').value.trim(); if (!text) return;
  const body = {platform: $('#cplat').value, text};
  if (chatTarget && chatTarget.platform === body.platform) { body.reply_to = chatTarget.message_id || chatTarget.id; if (chatTarget.state) body.card_id = chatTarget.id; }
  const r = await fetch('/api/send', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)}).then(r => r.json());
  if (r.ok) { chatTarget = null; chatCompose(); $('#cres').textContent = 'Sent'; if ($('#ctxt')) $('#ctxt').focus(); api('/api/cards').then(c => { cards = c; chatStrip(); }); }
  else $('#cres').textContent = r.detail || 'Could not send';
}
function chatBar() {
  const plats = conns.map(c => `<button class="chip2 ${CF.off.includes(c.platform) ? 'off' : ''}" data-cf="plat" data-p="${esc(c.platform)}" title="${esc(c.label)}: ${esc(c.status)}. Click to show or hide.">
    <span class="dot ${c.status}"></span> ${esc(c.label.replace(' (unofficial)', ''))}</button>`).join('');
  const botLbl = {dim: 'Bot replies: dimmed', show: 'Bot replies: normal', hide: 'Bot replies: hidden'}[CF.bots];
  const keep = $('#csearch') ? $('#csearch').value : searchTerm;
  $('#cbar').innerHTML = `<span class="szbox" title="Chat text size"><button class="chip2" data-lk-step="-1" title="Smaller text">A-</button><b id="lk-sz" class="lksz">${lookGet('size')}</b><button class="chip2" data-lk-step="1" title="Bigger text">A+</button>
    <button class="chip2 ${GEAR ? 'on' : ''}" data-cf="gear" title="Text, spacing, background and logos for this chat">&#9881; Text &amp; look</button></span>${plats}<input id="csearch" type="search" placeholder="Search chat..." value="${esc(keep)}" style="width:140px">
    <button class="chip2" data-cf="bots" title="Cycle how replies from bots (and you) are shown">${botLbl}</button>
    <button class="chip2 ${CF.q ? 'on' : ''}" data-cf="q" title="Only messages that look like a question for you or mention you">Questions for me</button>
    <button class="chip2 ${CF.prio ? 'on' : ''}" data-cf="prio" title="Only show messages worth answering (plus bot replies)">Priority only</button>
    <a class="chip2" href="/?type=style" target="_self" title="Fonts, colours, backgrounds and highlights">Look</a>
    ${PANE ? `<span class="chip2" title="This window shows: ${esc(PANE.name || 'a part of the chat')}">${esc(PANE.name || 'pane')}</span>` : `<button class="chip2" data-cf="popout" title="Open this chat in its own window - drag it to any monitor">Pop out</button>`}
    <a class="chip2" href="/" target="_self" title="Setup, layouts, smart features">Setup</a>`;
  $('#csearch').oninput = e => chatSearch(e.target.value);
}

// --- quick look controls on the chat page itself: live, saved, no need to open the editor ------------------------
let GEAR = false, lookTimer = null;
const lookGet = k => (PANE && PANE.look && PANE.look[k] != null) ? PANE.look[k] : (CS ? CS.base[k] : '');
function lookSet(k, v) {
  if (!CS) return;
  if (PANE) PANE.look = Object.assign({}, PANE.look, {[k]: v}); else CS.base[k] = v;
  applyStyle();
  clearTimeout(lookTimer);
  lookTimer = setTimeout(() => { if (PANE) api('/api/panes/' + PID, {b: {look: PANE.look}}); else api('/api/chatstyle', {b: {style: CS}}); }, 350);
  const z = $('#lk-sz'); if (z) z.textContent = lookGet('size');
}
function gearHtml() {
  const g = lookGet, sl = (k, lab, lo, hi, step, unit = '') => `<label class="cf">${lab} <input type="range" data-lk="${k}" min="${lo}" max="${hi}" step="${step}" value="${g(k)}"><b>${g(k)}${unit}</b></label>`;
  const sel = (k, lab, opts) => `<label class="cf">${lab} <select data-lk="${k}">${opts.map(([v, t]) => `<option value="${v}" ${String(g(k)) === String(v) ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
  const tog = (k, lab) => `<label class="cf"><input type="checkbox" data-lk="${k}" data-bool="1" ${g(k) ? 'checked' : ''}> ${lab}</label>`;
  return `<div class="ahd"><b>Text &amp; look ${PANE ? '(this window only)' : '(all chat windows)'}</b><button class="lnk" data-cf="gear">close</button></div><div class="rg">
    ${sl('size', 'Text size', 9, 48, 1, 'px')}
    ${sel('family', 'Font', FAMILIES.map(f => [f, f]))}
    ${sl('line', 'Line spacing', 1, 2.2, 0.05)}${sl('spacing', 'Space between messages', 0, 20, 1, 'px')}
    <span class="cf">Density <button class="chip2" data-lk-dens="tight">Tight</button><button class="chip2" data-lk-dens="normal">Normal</button><button class="chip2" data-lk-dens="roomy">Roomy</button></span>
    <label class="cf">Background <input type="color" data-lk="bg" value="${g('bg')}"></label>${sl('bgA', 'Background strength', 0, 100, 1, '%')}
    <label class="cf">Text colour <input type="color" data-lk="text" value="${g('text')}"></label>
    ${sel('marker', 'Platform logos', [['text', 'Word'], ['logo', 'Logo'], ['both', 'Logo and word'], ['none', 'Nothing']])}
    ${tog('timestamps', 'Times')}${tog('badges', 'Badges')}${tog('platformTag', 'Platform marker')}
    ${PANE ? `<button class="chip2" data-lk-reset="1" title="Make this window follow the main look again">Follow main look</button>` : ''}
    <a class="chip2" href="/?type=style">All look options...</a></div>`;
}
function chatGear() { const el = $('#cgearp'); if (!el) return; el.hidden = !GEAR; if (GEAR) el.innerHTML = gearHtml(); }
document.addEventListener('input', e => {
  const t = e.target, k = t.dataset && t.dataset.lk; if (!k || !$('#cgearp') || !$('#cgearp').contains(t)) return;
  const v = t.dataset.bool ? t.checked : t.type === 'range' ? parseFloat(t.value) : t.value;
  lookSet(k, v); const b = t.parentElement.querySelector('b'); if (b && t.type === 'range') b.textContent = t.value + b.textContent.replace(/[-0-9.]/g, '');
});
document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const d = b.dataset;
  if (d.lkStep) { lookSet('size', Math.max(9, Math.min(48, +lookGet('size') + (+d.lkStep) * (+lookGet('size') >= 20 ? 2 : 1)))); if (GEAR) chatGear(); }
  else if (d.lkDens) { const x = {tight: [1, 1.2], normal: [4, 1.35], roomy: [9, 1.5]}[d.lkDens]; lookSet('spacing', x[0]); lookSet('line', x[1]); chatGear(); }
  else if (d.lkReset && PANE) { PANE.look = {}; applyStyle(); api('/api/panes/' + PID, {b: {look: {}}}); chatGear(); }
  else if (d.cf === 'gear') { GEAR = !GEAR; chatBar(); chatGear(); }
});
async function chatSearch(term) {
  searchTerm = term.trim(); const seq = ++searchSeq;
  if (!searchTerm) { chatFeed(); return; }
  const rows = await api('/api/search?q=' + encodeURIComponent(searchTerm));
  if (seq !== searchSeq) return;
  const f = $('#cfeed'); f.innerHTML = `<div class="empty">${rows.length} result(s) for "${esc(searchTerm)}" - clear the box to go back to live chat</div>` +
    rows.slice().reverse().filter(m => !CF.off.includes(m.platform)).map(m => chatMsg(m)).join('');
  f.scrollTop = 0;
}
function chatNotice(text) {
  const f = $('#cfeed'); if (!f) return;
  f.insertAdjacentHTML('beforeend', `<div class="notice msg e-modaction">${esc(text)}</div>`); f.scrollTop = f.scrollHeight;
}
function renderChat() {
  $('#body').innerHTML = `<div id="cbar" class="cbar"></div><div id="cgearp" class="cassist" hidden></div><div id="cpins"></div><div id="cstrip" class="cstrip"></div><div id="cfeed" class="cfeed"></div><div id="cassist" class="cassist" hidden></div><div id="ccomp" class="ccomp"></div>`;
  chatBar(); chatPins(); chatStrip(); chatFeed(); chatCompose();
}

// --- stream-safe popout: OBS browser source / dock -------------------------------------
// /popout?platforms=twitch,youtube&size=22&bots=show&max=14   Public chat only: no cards, notes, composer, scores or muted users.
function popVisible(m) {
  const p = new URLSearchParams(location.search), pl = (p.get('platforms') || '').split(',').filter(Boolean);
  if (pl.length && !pl.includes(m.platform)) return false;
  if (p.get('bots') !== 'show' && isBot(m)) return false;
  if (MUTED.has((m.user || '').toLowerCase()) || m.raw_type === 'dev') return false;
  return true;
}
const popMsg = m => { const col = colourOf(m); return `<div class="pm msg ${styleClasses(m)}">${badgeHtml(m)}<b class="u" ${col ? `style="color:${col}"` : ''}>${esc(m.display || m.user)}</b>${eventLabel(m)}${bodyHtml(m)}</div>`; };
function renderPopout() {
  const p = new URLSearchParams(location.search), max = Math.min(parseInt(p.get('max')) || 30, 100);
  document.body.classList.add('popout'); document.documentElement.style.setProperty('--fs', (parseInt(p.get('size')) || 20) + 'px');
  $('#hdr').style.display = 'none';
  $('#body').innerHTML = '<div id="pfeed" class="pfeed"></div>';
  const f = $('#pfeed');
  const draw = () => { f.innerHTML = msgs.filter(popVisible).slice(-max).map(popMsg).join(''); };
  draw(); window.popAdd = m => { if (!popVisible(m)) return; f.insertAdjacentHTML('beforeend', popMsg(m)); while (f.children.length > max) f.firstChild.remove(); };
}

document.addEventListener('click', async e => {
  if (W.type !== 'chat') return;
  const b = e.target.closest('button'); if (!b) return;
  const d = b.dataset;
  if (d.reply) { chatTarget = msgs.find(m => m.id === d.reply) || null; chatCompose(); if ($('#ctxt')) $('#ctxt').focus(); return; }
  if (d.pin || d.unpin) { const r = await api('/api/pins', {b: {message_id: d.pin || d.unpin, pin: !!d.pin}}); PINS = r.pins || []; chatPins(); return; }
  if (d.mod) {
    const m = msgs.find(x => x.id === d.id); if (!m) return;
    const label = {timeout: 'Timeout 10 minutes', ban: 'BAN permanently', delete: 'Delete this message'}[d.mod];
    if (!confirm(`${label}: ${m.display || m.user} on ${m.platform}?\n"${(m.text || '').slice(0, 80)}"`)) return;
    const r = await fetch('/api/mod/' + d.mod, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({message_id: d.id, seconds: 600})}).then(r => r.json());
    chatNotice(r.ok ? `${d.mod} done: ${m.display || m.user}` : `${d.mod} failed: ${r.detail || 'error'}`); return;
  }
  if (d.ca) {
    const c = (cards.open || []).find(x => x.id === d.id);
    if (d.ca === 'reply') { chatTarget = c || null; chatCompose(); if ($('#ctxt')) $('#ctxt').focus(); return; }
    await api('/api/cards/' + encodeURIComponent(d.id) + '/' + d.ca, {b: {seconds: 300}});
    cards = await api('/api/cards'); chatStrip(); return;
  }
  const k = d.cf; if (!k) return;
  if (k === 'plat') { const p = d.p; CF.off = CF.off.includes(p) ? CF.off.filter(x => x !== p) : CF.off.concat(p); chatBar(); chatFeed(); chatStrip(); }
  else if (k === 'bots') { CF.bots = {dim: 'show', show: 'hide', hide: 'dim'}[CF.bots]; chatBar(); chatFeed(); }
  else if (k === 'prio') { CF.prio = !CF.prio; chatBar(); chatFeed(); }
  else if (k === 'q') { CF.q = !CF.q; chatBar(); chatFeed(); }
  else if (k === 'strip') { CF.strip = !CF.strip; chatStrip(); }
  else if (k === 'popout') { const r = await popOut('chat-main', location.origin + '/?type=chat', 'Chat', {w: 520, h: 900}); if (r === 'blocked') chatNotice('The browser blocked the pop-up - allow pop-ups for this page.'); }
  else if (k === 'clr') { chatTarget = null; chatCompose(); }
  CF.save();
});

// ---------------------------------------------------------------- assisted chat
let TPLS = [];
fetch('/api/templates').then(r => r.json()).then(r => { TPLS = r.templates || []; if (W.type === 'chat') chatCompose(); }).catch(() => {});
const rel = ts => { const s = Date.now() / 1000 - ts; return s < 90 ? 'just now' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago'; };
function assistOpen(html) { const p = $('#cassist'); if (!p) return; p.hidden = false; p.innerHTML = `<div class="ahd"><b>Assist</b><button class="lnk" data-assist="close">close</button></div>${html}`; }
async function postJson(path, body) {
  const r = await fetch(path, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body || {})});
  const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.status); return j;
}
async function assistChatter(platform, uid, mid) {
  assistOpen('<div class="mut">Loading...</div>');
  try {
    const c = await (await fetch(`/api/chatter/${encodeURIComponent(platform)}/${encodeURIComponent(uid)}`)).json();
    if (c.detail) throw new Error(c.detail);
    const caps = (conns.find(x => x.platform === 'twitch') || {capabilities: {}}).capabilities;
    assistOpen(`<div class="chcard"><div><b ${/^#/.test(c.color) ? `style="color:${esc(c.color)}"` : ''}>${esc(c.display)}</b> <span class="pf pf-${esc(platform)}">${esc(platform)}</span>
      ${c.badges.map(b => `<span class="bt">${esc(b)}</span>`).join('')}${c.muted ? '<span class="bt">muted</span>' : ''}</div>
      <div class="mut">First seen ${rel(c.first_seen)} &middot; last ${rel(c.last_seen)} &middot; ${c.messages} message(s) &middot; you answered ${c.cards.answered}, missed ${c.cards.missed}</div>
      <div class="chrec">${c.recent.map(r => `<div>${esc(r.text)}</div>`).join('')}</div>
      <label>Private note <textarea id="cnote" maxlength="500" rows="2" placeholder="e.g. likes Elden Ring, birthday in May">${esc(c.note)}</textarea></label>
      <div class="act"><button class="p" data-assist="savenote" data-user="${esc(c.user)}">Save note</button>
        ${mid ? `<button data-suggest="${esc(mid)}">Suggest replies</button>` : ''}
        <button data-mute="${esc(c.user)}" data-muted="${c.muted ? '0' : '1'}">${c.muted ? 'Unmute' : 'Mute'} in ranking</button>
        ${platform === 'twitch' && caps.mod_timeout && mid ? `<button data-mod="timeout" data-id="${esc(mid)}">Timeout 10 min</button><button data-mod="ban" data-id="${esc(mid)}">Ban</button>` : ''}</div></div>`);
  } catch (e) { assistOpen(`<div class="mut">No history for this chatter yet (${esc(e.message)}).</div>`); }
}
async function assistSuggest(mid) {
  const m = msgById(mid); if (!m) return;
  assistOpen(`<div class="mut">Drafting replies to <b>${esc(m.display || m.user)}</b>: ${esc((m.text || '').slice(0, 80))}</div><div class="mut">Thinking...</div>`);
  try {
    const r = await postJson('/api/assist/suggest', {message_id: mid});
    assistOpen(`<div class="mut">Replies to <b>${esc(m.display || m.user)}</b>: ${esc((m.text || '').slice(0, 80))}</div>
      ${r.replies.map((t, i) => `<div class="sug"><span>${esc(t)}</span><span class="act"><button data-assist="use" data-i="${i}" data-id="${esc(mid)}">Use</button><button class="p" data-assist="send" data-i="${i}" data-id="${esc(mid)}">Send</button></span></div>`).join('')}
      <small class="mut">${r.source === 'ai' ? 'Drafted by AI. Nothing is sent until you click Send.' : 'Quick-reply templates (' + esc(r.why || 'no AI') + '). Add an AI key in setup for smarter drafts.'}</small>`);
    window.__sug = r.replies;
  } catch (e) { assistOpen(`<div class="mut">Could not draft replies: ${esc(e.message)}</div>`); }
}
async function assistTranslate(mid) {
  const m = msgById(mid); if (!m) return;
  assistOpen(`<div class="mut">Translating...</div>`);
  try {
    const r = await postJson('/api/assist/translate', {message_id: mid});
    assistOpen(`<div class="mut">${esc(m.display || m.user)} wrote:</div><div>${esc(m.text)}</div>
      <div class="mut" style="margin-top:6px">${r.source === 'ai' ? 'English:' : 'Translation unavailable (' + esc(r.why || 'no AI key') + ').'}</div><div><b>${esc(r.text || '')}</b></div>`);
  } catch (e) { assistOpen(`<div class="mut">Could not translate: ${esc(e.message)}</div>`); }
}
document.addEventListener('click', async e => {
  if (W.type !== 'chat') return;
  const u = e.target.closest('[data-chatter]');
  if (u) { const [pl, uid, mid] = u.dataset.chatter.split('|'); assistChatter(pl, uid, mid); return; }
  const b = e.target.closest('button'); if (!b) return;
  const d = b.dataset;
  try {
    if (d.suggest) { assistSuggest(d.suggest); return; }
    if (d.translate) { assistTranslate(d.translate); return; }
    if (d.mark) { await postJson('/api/cards/manual', {message_id: d.mark}); cards = await api('/api/cards'); chatStrip(); chatNotice('Marked to answer: it is now a priority card.'); return; }
    if (d.mute) { await postJson('/api/viewers/' + encodeURIComponent(d.mute) + '/mute', {muted: d.muted !== '0'}); chatNotice((d.muted === '0' ? 'Unmuted ' : 'Muted ') + d.mute + ' in the ranking.'); return; }
    if (d.tpl !== undefined) { const t = (TPLS[+d.tpl] || '').replace('{name}', chatTarget ? (chatTarget.display || chatTarget.user) : '').replace(/\s+/g, ' ').trim(); const i = $('#ctxt'); if (i) { i.value = (i.value ? i.value + ' ' : '') + t; i.focus(); } return; }
    const a = d.assist; if (!a) return;
    if (a === 'close') { $('#cassist').hidden = true; }
    else if (a === 'savenote') { await postJson('/api/viewers/' + encodeURIComponent(d.user) + '/note', {note: $('#cnote').value}); b.textContent = 'Saved'; }
    else if (a === 'use' || a === 'send') {
      const m = msgById(d.id), text = (window.__sug || [])[+d.i]; if (!m || !text) return;
      if (a === 'use') { chatTarget = m; chatCompose(); const i = $('#ctxt'); if (i) { i.value = text; i.focus(); } return; }
      await postJson('/api/send', {platform: m.platform, text, reply_to: m.id, card_id: 'c:' + m.id});
      cards = await api('/api/cards'); chatStrip(); b.textContent = 'Sent'; b.disabled = true;
    }
    else if (a === 'tpls') {
      assistOpen(`<label>Quick replies, one per line. {name} becomes the chatter's name.<textarea id="ctpls" rows="6">${esc(TPLS.join('\n'))}</textarea></label><div class="act"><button class="p" data-assist="savetpls">Save</button></div>`);
    }
    else if (a === 'savetpls') { const r = await postJson('/api/templates', {templates: $('#ctpls').value.split('\n')}); TPLS = r.templates; chatCompose(); $('#cassist').hidden = true; }
  } catch (err) { assistOpen(`<div class="mut">That did not work: ${esc(err.message)}</div>`); }
});
