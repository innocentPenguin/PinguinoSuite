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
  let f = {off: [], bots: 'dim', prio: false, strip: true};
  try { f = Object.assign(f, JSON.parse(localStorage.getItem(k) || '{}')); } catch (e) { /* storage may be blocked */ }
  f.save = () => { try { localStorage.setItem(k, JSON.stringify({off: f.off, bots: f.bots, prio: f.prio, strip: f.strip})); } catch (e) { /* ignore */ } };
  return f;
})();
let chatTarget = null, searchTerm = '', searchSeq = 0;

// --- rendering helpers ---------------------------------------------------------------
const BADGES = {broadcaster: ['HOST', '#e0455b'], moderator: ['MOD', '#2fa84f'], vip: ['VIP', '#d94fa0'], subscriber: ['SUB', '#8a5cf6'],
  founder: ['SUB', '#8a5cf6'], partner: ['✓', '#8a5cf6'], staff: ['STAFF', '#999'], 'sub-gifter': ['GIFT', '#8a5cf6'], 'bits': ['BITS', '#b58900']};
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

function chatVisible(m) {
  if (CF.off.includes(m.platform) || !pass(m)) return false;
  if (CF.bots === 'hide' && isBot(m)) return false;
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
  const tools = opts.plain || !m.id ? '' : `<span class="tools">${bot ? '' : `<button data-reply="${esc(m.id)}" title="Reply (goes to ${esc(m.platform)} only)">&#8617;</button>`}
    <button data-pin="${esc(m.id)}" title="Pin to the top">&#128204;</button>
    ${caps.mod_timeout ? `<button data-mod="timeout" data-id="${esc(m.id)}" title="Timeout 10 min">&#9201;</button><button data-mod="ban" data-id="${esc(m.id)}" title="Ban">&#9940;</button>` : ''}
    ${caps.mod_delete ? `<button data-mod="delete" data-id="${esc(m.id)}" title="Delete this message">&#128465;</button>` : ''}</span>`;
  return `<div class="msg tier-${m.tier}${bot ? ' bot' : ''}${CF.bots === 'dim' ? '' : ' nodim'}${mine ? ' self' : ''}${men ? ' mention' : ''}${mod ? ' modmsg' : ''}" data-mid="${esc(m.id)}" title="${esc(reasons ? 'score ' + m.score + ': ' + reasons : '')}">
    <span class="t">${hhmm(m.ts)}</span><span class="pf">${esc(m.platform)}</span>${badgeHtml(m)}<span class="u" ${col ? `style="color:${col}"` : ''}>${esc(m.display || m.user)}</span>${flag}${rep}${bodyHtml(m)}${tools}</div>`;
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
  const open = (cards.open || []).filter(c => !CF.off.includes(c.platform)).slice(0, 3);
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
  $('#cbar').innerHTML = `${plats}<input id="csearch" type="search" placeholder="Search chat..." value="${esc(keep)}" style="width:140px">
    <button class="chip2" data-cf="bots" title="Cycle how replies from bots (and you) are shown">${botLbl}</button>
    <button class="chip2 ${CF.prio ? 'on' : ''}" data-cf="prio" title="Only show messages worth answering (plus bot replies)">Priority only</button>
    <a class="chip2" href="/" target="_self" title="Setup, layouts, smart features">Setup</a>`;
  $('#csearch').oninput = e => chatSearch(e.target.value);
}
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
  f.insertAdjacentHTML('beforeend', `<div class="notice">${esc(text)}</div>`); f.scrollTop = f.scrollHeight;
}
function renderChat() {
  $('#body').innerHTML = `<div id="cbar" class="cbar"></div><div id="cpins"></div><div id="cstrip" class="cstrip"></div><div id="cfeed" class="cfeed"></div><div id="ccomp" class="ccomp"></div>`;
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
const popMsg = m => { const col = colourOf(m); return `<div class="pm">${badgeHtml(m)}<b ${col ? `style="color:${col}"` : ''}>${esc(m.display || m.user)}</b>${bodyHtml(m)}</div>`; };
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
  else if (k === 'strip') { CF.strip = !CF.strip; chatStrip(); }
  else if (k === 'clr') { chatTarget = null; chatCompose(); }
  CF.save();
});
