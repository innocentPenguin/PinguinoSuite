// Settings panel that slides out on the right of the chat page: look, highlights, sounds, split chat and pop-out, all previewed live against the
// real chat. Globals: $, esc, api, W, PANE, CS (style.js), DEFAULT_CS, lookGet (chat.js), dingBox/popBox/splitBox (launcher.js).
const SIDE = {open: false, q: '', secs: {text: true}, dg: null, pp: null, pn: null};
try { const s = JSON.parse(localStorage.getItem('multi-side') || '{}'); SIDE.open = !!s.open; SIDE.secs = s.secs || SIDE.secs; } catch (e) { /* storage may be blocked */ }
function sideSave() { try { localStorage.setItem('multi-side', JSON.stringify({open: SIDE.open, secs: SIDE.secs})); } catch (e) { /* ignore */ } }
const PLAIN_KEYS = ['size', 'family', 'line', 'spacing', 'bg', 'bgA', 'text', 'timestamps', 'badges', 'platformTag'];

const SIDE_SECTIONS = [
  {id: 'text', title: 'Text and layout', help: 'font size family line spacing density background colour times badges', body: () => `<p class="mut">${PANE ? 'This window only.' : 'All chat windows.'} Changes show in the chat right away.</p>${textControls()}`},
  {id: 'logos', title: 'Platform logos', help: 'logo marker platform twitch youtube discord tiktok word', body: () => {
    const b = CS.base;
    return `<label class="cf">Show as <select data-cs="base.marker" data-t="str">${[['text', 'Word'], ['logo', 'Logo'], ['both', 'Logo and word'], ['none', 'Nothing']].map(([v, t]) => `<option value="${v}" ${b.marker === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      ${CS_PLATFORMS.map(p => `<div class="cf">${p} logo ${CS.marker[p].size}px <input type="range" data-cs="marker.${p}.size" data-t="num" min="10" max="40" value="${CS.marker[p].size}">${optColor('marker.' + p + '.color', 'colour')}</div>`).join('')}`; }},
  {id: 'high', title: 'Highlights', help: 'highlight role event keyword mod vip sub raid gift follow animation strength colour new chatter first', body: () => `
    <label class="cf">Strength <input type="range" data-cs="base.intensity" data-t="num" min="0" max="250" step="5" value="${CS.base.intensity}"><b>${CS.base.intensity}%</b></label>
    <label class="cf">New event animation <select data-cs="base.anim" data-t="str">${[['none', 'None'], ['pulse', 'Glow'], ['slide', 'Slide in']].map(([v, t]) => `<option value="${v}" ${CS.base.anim === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <h4>People</h4>${Object.entries(CS_ROLES).map(([k, t]) => quickRow('role.' + k, t)).join('')}
    <h4>Stream events</h4>${Object.entries(CS_EVENTS).map(([k, t]) => quickRow('event.' + k, t, k === 'follow' || k === 'redeem' ? 'needs the bot Host to send these events' : '')).join('')}
    <h4>Words</h4><div class="act"><input id="kw-new" placeholder="word or phrase" style="width:170px"><button data-cs-act="addkw">Add</button></div>
    ${(CS.keywords || []).map((k, i) => quickRow('keywords.' + i + '.rule', '"' + k.word + '"') + `<div class="act"><button data-cs-act="delkw" data-i="${i}">Remove "${esc(k.word)}"</button></div>`).join('')}`},
  {id: 'mysound', title: 'Sounds for me (this page, not in OBS)', help: 'sound audio volume master first time chatter mention question sent message notification mute ding', body: () => soundsBox()},
  {id: 'sound', title: 'Sounds (server ding / chat pop)', help: 'sound audio ding pop volume new chatter returning mute notification', body: () => !SIDE.dg ? '<div class="empty">Loading...</div>' :
    `<h4>New-chatter ding</h4>${dingBox(SIDE.dg)}<h4>Chat pop</h4>${popBox(SIDE.pp)}`},
  {id: 'split', title: 'Split chat and pop-out', help: 'split pop out window monitor half top bottom always on top', body: () => SIDE.pn ? splitBox(SIDE.pn) : '<div class="empty">Loading...</div>'},
  {id: 'more', title: 'Connections and more', help: 'setup connect twitch youtube discord editor look presets', body: () => `<div class="act"><a href="/"><button type="button">Setup (connections)</button></a> <a href="/?type=style"><button type="button">Full look editor and presets</button></a> <a href="/?type=dash"><button type="button">Dashboard</button></a> <a href="/?type=obs&widget=chat"><button type="button">OBS chat widget</button></a> <a href="/?type=obs&widget=activity"><button type="button">OBS activity widget</button></a> <a href="/?type=obs&widget=follow"><button type="button">OBS follow alert</button></a></div>`},
];

// the text controls (shared with the A-/A+ buttons in the chat bar)
function textControls() {
  const g = lookGet, sl = (k, lab, lo, hi, step, unit = '') => `<label class="cf">${lab} <input type="range" data-lk="${k}" min="${lo}" max="${hi}" step="${step}" value="${g(k)}"><b>${g(k)}${unit}</b></label>`;
  const tog = (k, lab) => `<label class="cf"><input type="checkbox" data-lk="${k}" data-bool="1" ${g(k) ? 'checked' : ''}> ${lab}</label>`;
  return `<div class="rg"><span class="cf">Size <button class="chip2" data-lk-step="-1">A-</button><button class="chip2" data-lk-step="1">A+</button></span>
    ${sl('size', 'Text size', 9, 48, 1, 'px')}
    <label class="cf">Font <select data-lk="family">${FAMILIES.map(f => `<option ${g('family') === f ? 'selected' : ''} style="font-family:${f}">${f}</option>`).join('')}</select></label>
    ${sl('line', 'Line spacing', 1, 2.2, 0.05)}${sl('spacing', 'Space between messages', 0, 20, 1, 'px')}
    <span class="cf">Density <button class="chip2" data-lk-dens="tight">Tight</button><button class="chip2" data-lk-dens="normal">Normal</button><button class="chip2" data-lk-dens="roomy">Roomy</button></span>
    <label class="cf">Background <input type="color" data-lk="bg" value="${g('bg')}"></label>${sl('bgA', 'Background strength', 0, 100, 1, '%')}
    <label class="cf">Text colour <input type="color" data-lk="text" value="${g('text')}"></label>
    ${tog('timestamps', 'Times')}${tog('badges', 'Badges')}${tog('platformTag', 'Platform marker')}
    ${PANE ? '<button class="chip2" data-lk-reset="1">Follow main look</button>' : ''}</div>`;
}

function sideInit() {
  if (!$('#sidep')) {
    const d = document.createElement('div'); d.id = 'sidep';
    d.innerHTML = `<div class="sidehd"><b>&#9881; Settings</b><input id="side-q" type="search" placeholder="Search settings (font, sound, split...)"><button class="lnk" data-side="close" title="Close">&#10005;</button></div><div id="sidebody"></div>`;
    document.body.appendChild(d);
    const b = document.createElement('button'); b.id = 'sidebtn'; b.dataset.side = 'toggle'; b.title = 'Text, highlights, sounds, split chat and pop-out'; b.innerHTML = '&#9881; Settings';
    document.body.appendChild(b);
    $('#side-q').addEventListener('input', e => { SIDE.q = e.target.value.trim().toLowerCase(); sideFilter(); });
  }
  sideApply();
}
function sideApply() {
  document.body.classList.toggle('side-open', SIDE.open);
  const p = $('#sidep'); if (p) p.classList.toggle('open', SIDE.open);
  if (SIDE.open) sideRender();
}
function sideToggle(open, sec) {
  SIDE.open = open == null ? !SIDE.open : open;
  if (sec) SIDE.secs[sec] = true;
  sideSave(); sideApply();
}
let sideSeq = 0;
async function sideRender() {
  if (!$('#sidebody') || !SIDE.open || !CS) return;
  const seq = ++sideSeq;
  sideDraw();                                   // draw at once; the sound and split data fill in when they arrive
  try { [SIDE.dg, SIDE.pp, SIDE.pn] = await Promise.all([api('/api/ding'), api('/api/pop'), api('/api/panes')]); } catch (e) { return; }
  if (seq === sideSeq && !(document.activeElement && document.activeElement.closest && document.activeElement.closest('#sidebody'))) sideDraw();
}
function sideDraw() {
  const body = $('#sidebody'); if (!body) return;
  const keep = body.scrollTop;
  body.innerHTML = SIDE_SECTIONS.map(s => `<details class="sec" data-sec="${s.id}" ${SIDE.secs[s.id] ? 'open' : ''}><summary><b>${s.title}</b></summary><div class="sbody">${s.body()}</div>
    ${['more'].includes(s.id) ? '' : `<div class="act"><button class="chip2" data-side-reset="${s.id}">Reset this section</button></div>`}</details>`).join('');
  body.scrollTop = keep;
  body.querySelectorAll('details.sec').forEach(d => d.addEventListener('toggle', () => { SIDE.secs[d.dataset.sec] = d.open; sideSave(); }));
  sideFilter();
}
function sideFilter() {
  const q = SIDE.q, words = q.split(/\s+/).filter(Boolean);
  document.querySelectorAll('#sidebody details.sec').forEach(d => {
    const sec = SIDE_SECTIONS.find(s => s.id === d.dataset.sec), hay = ((sec ? sec.help + ' ' + sec.title : '') + ' ' + d.textContent).toLowerCase();
    const hit = !words.length || words.every(w => hay.includes(w));
    d.hidden = !hit; if (words.length && hit) d.open = true;
  });
}
async function sideReset(id) {
  const D = DEFAULT_CS;
  if (id === 'text') { if (PANE) { PANE.look = {}; api('/api/panes/' + PID, {b: {look: {}}}); } else { PLAIN_KEYS.forEach(k => { CS.base[k] = D.base[k]; }); scheduleSave(); } }
  else if (id === 'logos') { CS.base.marker = D.base.marker; CS.marker = JSON.parse(JSON.stringify(D.marker)); scheduleSave(); }
  else if (id === 'high') { ['role', 'event', 'keywords'].forEach(k => { CS[k] = JSON.parse(JSON.stringify(D[k])); }); CS.base.intensity = D.base.intensity; CS.base.anim = D.base.anim; scheduleSave(); }
  else if (id === 'sound') { await api('/api/sounds/reset', {b: {}}); }
  else if (id === 'split') { ['pane-split-a', 'pane-split-b'].forEach(popClose); for (const k of ['split-a', 'split-b']) await fetch('/api/panes/' + k, {method: 'DELETE'}); }
  applyStyle(); if (typeof chatFeed === 'function') chatFeed(); sideRender();
}
document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.side === 'toggle') sideToggle();
  else if (b.dataset.side === 'close') sideToggle(false);
  else if (b.dataset.sideReset) sideReset(b.dataset.sideReset);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && SIDE.open && W.type === 'chat') sideToggle(false); });
