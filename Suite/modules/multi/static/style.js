// Chat look: compiles the saved style (fonts, backgrounds, highlights per platform / role / event) into ONE stylesheet, so a busy
// chat costs nothing extra per message. Also the style editor page (/?type=style) with a live preview.
// Globals from index.html: $, esc, api, W, hhmm. From chat.js: chatMsg, isBot, mentionsMe, MYNAMES, PINS.
let CS = null, DEFAULT_CS = null;
const CS_PLATFORMS = ['twitch', 'youtube', 'discord', 'tiktok'];
const CS_ROLES = {streamer: 'Streamer (you)', mod: 'Moderator', vip: 'VIP', sub: 'Subscriber', new: 'New chatter (first time ever)', returning: 'Returning chatter (back after a long break)', bot: 'Bots'};
const CS_EVENTS = {first: 'First message (Twitch flag)', mention: 'Mentions me', sub: 'New subscriber', resub: 'Resub', gift: 'Gifted subs', cheer: 'Cheer / bits',
  raid: 'Raid', follow: 'Follow', redeem: 'Channel point redeem', highlighted: 'Highlighted message', announcement: 'Announcement', pinned: 'Pinned message', modaction: 'Mod action (timeout / ban / delete)'};
const EVENT_LABEL = {sub: 'SUB', resub: 'RESUB', gift: 'GIFT', cheer: 'BITS', raid: 'RAID', follow: 'FOLLOW', redeem: 'REDEEM', highlighted: 'HIGHLIGHT', announcement: 'NOTICE'};
const FAMILIES = ['system-ui', 'Segoe UI', 'Inter', 'Arial', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Georgia', 'Times New Roman', 'Consolas', 'Courier New', 'Comic Sans MS', 'Impact'];

async function loadStyle() {
  try { const r = await api('/api/chatstyle'); CS = r.style; DEFAULT_CS = r.defaults; } catch (e) { CS = CS || null; }
  applyStyle();
}
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${(a / 100).toFixed(2)})`; };

function ruleCss(r) {
  if (!r || r.on === false) return '';
  const d = [];
  if (r.bg) d.push(r.bg2 ? `background:linear-gradient(90deg,${rgba(r.bg, r.bgA)},${rgba(r.bg2, r.bg2A)})` : `background:${rgba(r.bg, r.bgA)}`);
  if (r.text) d.push(`color:${r.text}`);
  if (r.border && r.borderW) d.push(`border-left:${r.borderW}px solid ${rgba(r.border, r.borderA)};padding-left:6px`);
  if (r.bold) d.push('font-weight:700');
  if (r.italic) d.push('font-style:italic');
  if (r.size && r.size !== 100) d.push(`font-size:${r.size}%`);
  return d.join(';');
}
function compileStyle(s) {
  const b = s.base, out = [];
  out.push(`:root{--fs:${b.size}px;--sp:${b.spacing}px}`);
  out.push(`.msg,.pm{font-family:${b.family},system-ui,sans-serif;font-weight:${b.weight};line-height:${b.line};border-radius:${b.radius}px}`);
  out.push(`.cfeed,.pfeed,#feed{color:${b.text}}`);
  if (b.bgA > 0) out.push(`.cfeed,#feed{background:${rgba(b.bg, b.bgA)}}`);
  out.push(`.msg .u,.pm b{font-weight:${b.nameWeight}}.emo{height:${(b.emoteSize / 100).toFixed(2)}em}`);
  if (!b.timestamps) out.push('.msg .t{display:none}');
  if (!b.badges) out.push('.msg .bd,.pm .bd{display:none}');
  if (!b.platformTag) out.push('.msg .pf{display:none}');
  const add = (cls, r) => {
    const css = ruleCss(r);
    if (css) out.push(`.msg.${cls},.pm.${cls}{${css}}`);
    if (r && r.on !== false && r.name) out.push(`.msg.${cls} .u,.pm.${cls} b{color:${r.name}!important}`);
  };
  CS_PLATFORMS.forEach(p => {
    add('p-' + p, s.platform[p]);
    const c = s.platform[p].border; if (c) out.push(`.pf.pf-${p}{background:${c};color:#fff}`);
  });
  Object.keys(CS_ROLES).forEach(k => add('r-' + k, s.role[k]));
  Object.keys(CS_EVENTS).forEach(k => add('e-' + k, s.event[k]));
  (s.keywords || []).forEach((k, i) => add('kw' + i, k.rule));
  out.push('.notice.e-modaction{border-radius:4px}');
  return out.join('\n');
}
function applyStyle() {
  if (!CS) return;
  let el = document.getElementById('cstyle');
  if (!el) { el = document.createElement('style'); el.id = 'cstyle'; document.head.appendChild(el); }
  el.textContent = compileStyle(CS);
}

// Classes for one message: platform, roles, events, keywords. Cheap string work only; the look lives in the stylesheet.
function styleClasses(m) {
  const c = ['p-' + m.platform], bd = m.badges || [];
  const mine = bd.includes('broadcaster') || (typeof MYNAMES !== 'undefined' && MYNAMES.has((m.user || '').toLowerCase()));
  if (mine) c.push('r-streamer');
  if (bd.includes('moderator')) c.push('r-mod');
  if (bd.includes('vip')) c.push('r-vip');
  if (bd.includes('subscriber') || bd.includes('founder')) c.push('r-sub');
  const fl = m.flags || [];
  if (fl.includes('new')) c.push('r-new');
  if (fl.includes('returning')) c.push('r-returning');
  if (typeof isBot === 'function' && isBot(m)) c.push('r-bot');
  if (m.first_time) c.push('e-first');
  if (m.event) c.push('e-' + m.event);
  if (typeof mentionsMe === 'function' && mentionsMe(m)) c.push('e-mention');
  if (typeof PINS !== 'undefined' && PINS.some(p => p.id === m.id)) c.push('e-pinned');
  if (CS && CS.keywords && CS.keywords.length) {
    const t = (m.text || '').toLowerCase();
    CS.keywords.forEach((k, i) => { if (k.word && t.includes(k.word.toLowerCase())) c.push('kw' + i); });
  }
  return c.join(' ');
}
function eventLabel(m) {
  if (!m.event || !EVENT_LABEL[m.event]) return '';
  const n = m.amount && ['cheer', 'raid', 'gift', 'resub'].includes(m.event) ? ' ' + m.amount : '';
  return `<span class="evl">${EVENT_LABEL[m.event]}${n}</span>`;
}

// ---------------------------------------------------------------- editor
let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  const st = $('#cs-state'); if (st) st.textContent = 'Saving...';
  saveTimer = setTimeout(async () => {
    await api('/api/chatstyle', {b: {style: CS}});
    const s2 = $('#cs-state'); if (s2) s2.textContent = 'Saved - remembered after closing.';
  }, 500);
}
const getPath = (o, p) => p.split('.').reduce((x, k) => (x == null ? x : x[k]), o);
function setPath(o, p, v) { const ks = p.split('.'), last = ks.pop(); ks.reduce((x, k) => x[k], o)[last] = v; }

function optColor(path, label) {
  const v = getPath(CS, path);
  return `<label class="cf"><input type="checkbox" data-cs="${path}" data-t="optc" ${v ? 'checked' : ''}> ${label} <input type="color" data-cs="${path}" data-t="color" value="${v || '#ff9900'}"></label>`;
}
function ruleEditor(path, title, hint) {
  const r = getPath(CS, path), n = (k, lab, lo, hi, unit = '') => `<label class="cf">${lab} <input type="range" data-cs="${path}.${k}" data-t="num" min="${lo}" max="${hi}" value="${r[k]}"><b>${r[k]}${unit}</b></label>`;
  return `<div class="rule"><div class="rt"><label class="chk"><input type="checkbox" data-cs="${path}.on" data-t="bool" ${r.on !== false ? 'checked' : ''}> <b>${esc(title)}</b></label>${hint ? `<small class="mut">${esc(hint)}</small>` : ''}</div>
    <div class="rg">${optColor(path + '.bg', 'Background')}${n('bgA', 'See-through', 0, 100, '%')}${optColor(path + '.bg2', 'Fade to')}
    ${optColor(path + '.text', 'Text colour')}${optColor(path + '.name', 'Name colour')}${optColor(path + '.border', 'Side bar')}${n('borderW', 'Bar width', 0, 12, 'px')}
    ${n('size', 'Text size', 60, 250, '%')}<label class="cf"><input type="checkbox" data-cs="${path}.bold" data-t="bool" ${r.bold ? 'checked' : ''}> Bold</label><label class="cf"><input type="checkbox" data-cs="${path}.italic" data-t="bool" ${r.italic ? 'checked' : ''}> Italic</label></div></div>`;
}
function sampleMsgs() {
  const now = Date.now() / 1000, mk = (o) => Object.assign({id: 'sample:' + Math.random(), platform: 'twitch', user: 'viewer', display: 'Viewer', text: 'Sample message', ts: now, badges: [], tier: 'none', flags: [], emotes: []}, o);
  return [
    mk({display: 'ModMary', user: 'modmary', badges: ['moderator', 'subscriber'], color: '#3ddc97', text: 'Welcome in everyone! Kappa', emotes: [{id: '25', text: 'Kappa'}]}),
    mk({platform: 'youtube', display: 'TubeTim', user: 'tubetim', text: 'Hello from YouTube!'}),
    mk({platform: 'discord', display: 'DiscordDee', user: 'discorddee', text: 'Watching from the Discord'}),
    mk({platform: 'tiktok', display: 'TokTina', user: 'toktina', text: 'Hi from TikTok'}),
    mk({display: 'VipVic', user: 'vipvic', badges: ['vip'], text: 'VIP in the house'}),
    mk({display: 'SubSam', user: 'subsam', badges: ['subscriber'], text: 'Subscriber message'}),
    mk({display: 'NewNina', user: 'newnina', flags: ['new'], text: 'Hi! I am new here'}),
    mk({display: 'BackBen', user: 'backben', flags: ['returning'], text: 'I am back after a while'}),
    mk({display: 'FirstFay', user: 'firstfay', first_time: true, text: 'My very first message ever'}),
    mk({display: 'StreamerYou', user: 'innocentpenguin', badges: ['broadcaster'], text: 'Thanks for coming, everyone!'}),
    mk({display: 'PinguinoB0t', user: 'pinguinob0t', is_bot: true, text: 'Welcome to the stream!'}),
    mk({display: 'AskAl', user: 'askal', text: 'hey innocentpenguin what game is this?'}),
    mk({display: 'GiveawayGus', user: 'giveawaygus', text: 'is there a giveaway today?'}),
    mk({event: 'cheer', amount: 100, display: 'BitsBob', user: 'bitsbob', text: 'cheer100 take my bits!'}),
    mk({event: 'sub', display: 'SubSally', user: 'subsally', text: 'SubSally subscribed with Prime.'}),
    mk({event: 'resub', amount: 12, display: 'LoyalLou', user: 'loyallou', text: 'LoyalLou resubscribed for 12 months!'}),
    mk({event: 'gift', amount: 5, display: 'GiftyGil', user: 'giftygil', text: 'GiftyGil gifted 5 subs!'}),
    mk({event: 'raid', amount: 120, display: 'RaidRay', user: 'raidray', text: 'RaidRay is raiding with 120 viewers!'}),
    mk({event: 'follow', display: 'FollowFin', user: 'followfin', text: 'FollowFin followed'}),
    mk({event: 'redeem', display: 'PointsPat', user: 'pointspat', text: 'PointsPat redeemed Hydrate!'}),
    mk({event: 'highlighted', display: 'LoudLiz', user: 'loudliz', text: 'Highlighted with channel points'}),
    mk({event: 'announcement', display: 'ModMary', user: 'modmary', text: 'Raffle starts in 5 minutes'}),
  ];
}
function previewHtml() {
  const rows = sampleMsgs().map(m => chatMsg(m, {plain: true}));
  rows.push(`<div class="notice e-modaction msg">Mod action: ModMary timed out SpamSam for 10 minutes</div>`);
  return rows.join('');
}
function renderPreview() { const p = $('#cs-preview'); if (p) p.innerHTML = previewHtml(); }

function renderStyleEditor() {
  if (!CS) { $('#body').innerHTML = '<div class="empty">Loading...</div>'; loadStyle().then(renderStyleEditor); return; }
  const b = CS.base, num = (k, lab, lo, hi, step = 1, unit = '') => `<label class="cf">${lab} <input type="range" data-cs="base.${k}" data-t="num" min="${lo}" max="${hi}" step="${step}" value="${b[k]}"><b>${b[k]}${unit}</b></label>`;
  const chk = (k, lab) => `<label class="cf"><input type="checkbox" data-cs="base.${k}" data-t="bool" ${b[k] ? 'checked' : ''}> ${lab}</label>`;
  $('#body').innerHTML = `<div class="launch style-ed">
    <div class="intro"><h2>Chat look</h2><p>Change how chat looks: fonts, sizes, backgrounds with any colour, and highlights for different people and events. The preview below is exactly what the chat shows, and every change is saved automatically and remembered after closing.</p>
      <div class="act"><a href="/?type=chat"><button type="button">Back to chat</button></a> <a href="/"><button type="button">Setup</button></a> <button data-cs-act="reset">Reset everything to the default look</button> <span id="cs-state" class="mut"></span></div></div>
    <div class="cs-prev-wrap"><b>Live preview</b> <small class="mut">(platform tags, roles and events as they will appear)</small><div id="cs-preview" class="cfeed cs-preview"></div></div>
    <details open><summary><h3>Fonts and layout</h3></summary><div class="rg">
      <label class="cf">Font <select data-cs="base.family" data-t="str">${FAMILIES.map(f => `<option ${b.family === f ? 'selected' : ''} style="font-family:${f}">${f}</option>`).join('')}</select></label>
      ${num('size', 'Size', 9, 48, 1, 'px')}${num('weight', 'Weight', 300, 900, 100)}${num('nameWeight', 'Name weight', 300, 900, 100)}${num('line', 'Line spacing', 1, 2.2, 0.05)}${num('spacing', 'Space between messages', 0, 20, 1, 'px')}
      ${num('emoteSize', 'Emote size', 80, 300, 10, '%')}${num('radius', 'Corner roundness', 0, 24, 1, 'px')}
      ${optColor('base.text', 'Chat text colour')}${optColor('base.bg', 'Chat background')}${num('bgA', 'Background see-through', 0, 100, 1, '%')}
      ${chk('timestamps', 'Show times')}${chk('badges', 'Show badges')}${chk('platformTag', 'Show platform tags')}</div></details>
    <details open><summary><h3>Platforms ${T('', 'The coloured side bar and tag identify where a message came from.')}</h3></summary>${CS_PLATFORMS.map(p => ruleEditor('platform.' + p, p[0].toUpperCase() + p.slice(1), 'tag colour = side bar colour')).join('')}</details>
    <details><summary><h3>People (roles)</h3></summary>${Object.entries(CS_ROLES).map(([k, t]) => ruleEditor('role.' + k, t)).join('')}</details>
    <details open><summary><h3>Events and highlights ${T('', 'These win over platform and role styling, so important moments stand out.')}</h3></summary>${Object.entries(CS_EVENTS).map(([k, t]) => ruleEditor('event.' + k, t, k === 'follow' || k === 'redeem' ? 'needs the bot Host to send these events' : '')).join('')}</details>
    <details><summary><h3>Keyword highlights</h3></summary>
      <div class="act"><input id="kw-new" placeholder="word or phrase, e.g. giveaway" style="width:240px"><button data-cs-act="addkw">Add keyword</button></div>
      ${(CS.keywords || []).map((k, i) => ruleEditor('keywords.' + i + '.rule', 'Highlight "' + k.word + '"') + `<div class="act"><button data-cs-act="delkw" data-i="${i}">Remove "${esc(k.word)}"</button></div>`).join('') || '<div class="empty">No keywords yet. A message containing one of them gets its own highlight.</div>'}</details>
  </div>`;
  renderPreview();
}
function csChanged(el) {
  const path = el.dataset.cs, t = el.dataset.t; let v;
  if (t === 'optc') { const col = el.parentElement.querySelector('input[type=color]'); v = el.checked ? col.value : ''; setPath(CS, path, v); }
  else if (t === 'color') { v = el.value; const cb = el.parentElement.querySelector('input[type=checkbox]'); if (cb) cb.checked = true; setPath(CS, path, v); }
  else if (t === 'bool') { setPath(CS, path, el.checked); }
  else if (t === 'num') { setPath(CS, path, parseFloat(el.value)); const out = el.parentElement.querySelector('b'); if (out) out.textContent = el.value + (out.textContent.replace(/[-0-9.]/g, '')); }
  else setPath(CS, path, el.value);
  applyStyle(); renderPreview(); scheduleSave();
}
document.addEventListener('input', e => { if (W.type === 'style' && e.target.dataset && e.target.dataset.cs) csChanged(e.target); });
document.addEventListener('change', e => { if (W.type === 'style' && e.target.dataset && e.target.dataset.cs && e.target.type === 'checkbox') csChanged(e.target); });
document.addEventListener('click', async e => {
  if (W.type !== 'style') return;
  const b = e.target.closest('button[data-cs-act]'); if (!b) return;
  const a = b.dataset.csAct;
  if (a === 'reset') { if (!confirm('Reset the whole chat look to the default?')) return; const r = await api('/api/chatstyle/reset', {b: {}}); CS = r.style; applyStyle(); renderStyleEditor(); }
  else if (a === 'addkw') { const w = ($('#kw-new').value || '').trim(); if (!w) return; CS.keywords = (CS.keywords || []).concat({word: w, rule: JSON.parse(JSON.stringify(CS.event.mention))}); applyStyle(); renderStyleEditor(); scheduleSave(); }
  else if (a === 'delkw') { CS.keywords.splice(parseInt(b.dataset.i), 1); applyStyle(); renderStyleEditor(); scheduleSave(); }
});
