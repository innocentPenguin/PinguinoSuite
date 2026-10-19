// Combined chat window: every platform in one feed, bot replies visible, priority cards on top, one reply box at the bottom.
// Uses globals from index.html ($, esc, api, W, msgs, conns, cards, hhmm, WID, TIERS).
let BOTS = new Set(), MYNAMES = new Set();
const isBot = m => !!(m.is_bot || m.is_self || BOTS.has((m.user || '').toLowerCase()));
fetch('/api/setup').then(r => r.json()).then(s => {
  BOTS = new Set((s.settings.bot_accounts || []).map(x => x.toLowerCase()));
  MYNAMES = new Set((s.settings.my_names || []).map(x => x.toLowerCase()));
}).catch(() => {});

const CF = (() => {
  const k = 'multi-chat-' + (typeof WID !== 'undefined' ? WID : 'x');
  let f = {off: [], bots: 'dim', prio: false, strip: true};
  try { f = Object.assign(f, JSON.parse(localStorage.getItem(k) || '{}')); } catch (e) { /* storage may be blocked */ }
  f.save = () => { try { localStorage.setItem(k, JSON.stringify({off: f.off, bots: f.bots, prio: f.prio, strip: f.strip})); } catch (e) { /* ignore */ } };
  return f;
})();
let chatTarget = null;

function chatVisible(m) {
  if (CF.off.includes(m.platform) || !pass(m)) return false;
  if (CF.bots === 'hide' && isBot(m)) return false;
  if (CF.prio && !isBot(m) && !(TIERS[m.tier || 'none'] >= TIERS.medium)) return false;
  return true;
}
function chatMsg(m) {
  const bot = isBot(m), mine = m.is_self;
  const reasons = (m.reasons || []).map(r => `${r.rule} ${r.points > 0 ? '+' : ''}${r.points}`).join(', ');
  const rep = m.reply_to_user ? `<span class="rep">&#8618; ${esc(m.reply_to_user)}</span>` : '';
  const flag = bot ? '<span class="bt">bot</span>' : (m.first_time ? '<span class="bt first">first</span>' : '');
  return `<div class="msg tier-${m.tier}${bot ? ' bot' : ''}${CF.bots === 'dim' ? '' : ' nodim'}${mine ? ' self' : ''}" data-mid="${esc(m.id)}" title="${esc(reasons ? 'score ' + m.score + ': ' + reasons : '')}">
    <span class="t">${hhmm(m.ts)}</span><span class="pf">${esc(m.platform)}</span><span class="u">${esc(m.display || m.user)}</span>${flag}${rep}${esc(m.text)}
    ${bot || !m.id ? '' : `<button class="rb" data-reply="${esc(m.id)}" title="Reply to this message (goes to ${esc(m.platform)} only)">&#8617;</button>`}</div>`;
}
function chatAdd(m) {
  const f = $('#cfeed'); if (!f || !chatVisible(m)) return;
  const atEnd = f.scrollTop + f.clientHeight >= f.scrollHeight - 40;
  f.insertAdjacentHTML('beforeend', chatMsg(m));
  while (f.children.length > 500) f.firstChild.remove();
  if (W.scroll !== 'manual' && atEnd) f.scrollTop = f.scrollHeight;
}
function chatFeed() {
  const f = $('#cfeed'); if (!f) return;
  f.innerHTML = msgs.filter(chatVisible).slice(-300).map(chatMsg).join('') || '<div class="empty">No messages yet. When a connected platform gets chat, it shows up here.</div>';
  f.scrollTop = f.scrollHeight;
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
  $('#cbar').innerHTML = `${plats}<span class="grow"></span>
    <button class="chip2" data-cf="bots" title="Cycle how replies from bots (and you) are shown">${botLbl}</button>
    <button class="chip2 ${CF.prio ? 'on' : ''}" data-cf="prio" title="Only show messages worth answering (plus bot replies)">Priority only</button>`;
}
function renderChat() {
  $('#body').innerHTML = `<div id="cbar" class="cbar"></div><div id="cstrip" class="cstrip"></div><div id="cfeed" class="cfeed"></div><div id="ccomp" class="ccomp"></div>`;
  chatBar(); chatStrip(); chatFeed(); chatCompose();
}
document.addEventListener('click', async e => {
  if (W.type !== 'chat') return;
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.reply) { chatTarget = msgs.find(m => m.id === b.dataset.reply) || null; chatCompose(); if ($('#ctxt')) $('#ctxt').focus(); return; }
  if (b.dataset.ca) {
    const c = (cards.open || []).find(x => x.id === b.dataset.id);
    if (b.dataset.ca === 'reply') { chatTarget = c || null; chatCompose(); if ($('#ctxt')) $('#ctxt').focus(); return; }
    await api('/api/cards/' + encodeURIComponent(b.dataset.id) + '/' + b.dataset.ca, {b: {seconds: 300}});
    cards = await api('/api/cards'); chatStrip(); return;
  }
  const k = b.dataset.cf; if (!k) return;
  if (k === 'plat') { const p = b.dataset.p; CF.off = CF.off.includes(p) ? CF.off.filter(x => x !== p) : CF.off.concat(p); chatBar(); chatFeed(); chatStrip(); }
  else if (k === 'bots') { CF.bots = {dim: 'show', show: 'hide', hide: 'dim'}[CF.bots]; chatBar(); chatFeed(); }
  else if (k === 'prio') { CF.prio = !CF.prio; chatBar(); chatFeed(); }
  else if (k === 'strip') { CF.strip = !CF.strip; chatStrip(); }
  else if (k === 'clr') { chatTarget = null; chatCompose(); }
  CF.save();
});
