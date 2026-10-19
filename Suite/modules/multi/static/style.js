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

function ruleCss(r, k = 1) {
  if (!r || r.on === false) return '';
  const d = [], A = a => Math.max(0, Math.min(100, Math.round(a * k)));      // k = highlight strength (base.intensity / 100)
  if (r.bg) d.push(r.bg2 ? `background:linear-gradient(90deg,${rgba(r.bg, A(r.bgA))},${rgba(r.bg2, A(r.bg2A))})` : `background:${rgba(r.bg, A(r.bgA))}`);
  if (r.text) d.push(`color:${r.text}`);
  if (r.border && r.borderW) d.push(`border-left:${r.borderW}px solid ${rgba(r.border, r.borderA)};padding-left:6px`);
  if (r.bold) d.push('font-weight:700');
  if (r.italic) d.push('font-style:italic');
  if (r.size && r.size !== 100) d.push(`font-size:${r.size}%`);
  return d.join(';');
}
const EVENT_ANIM = ['first', 'sub', 'resub', 'gift', 'cheer', 'raid', 'follow', 'redeem', 'highlighted', 'announcement'];
// scope = '' for the live chat; a selector such as '.pv-3' to style a small preview card without touching the page.
function compileStyle(s, scope = '') {
  const b = s.base, k = (b.intensity == null ? 100 : b.intensity) / 100, out = [];
  const R = (sel, body) => out.push(sel.split(',').map(x => (scope ? scope + ' ' : '') + x).join(',') + '{' + body + '}');
  out.push(scope ? `${scope}{--fs:${b.size}px;--sp:${b.spacing}px;color:${b.text};${b.bgA > 0 ? 'background:' + rgba(b.bg, b.bgA) : ''}}` : `:root{--fs:${b.size}px;--sp:${b.spacing}px}`);
  R('.msg,.pm', `font-family:${b.family},system-ui,sans-serif;font-weight:${b.weight};line-height:${b.line};border-radius:${b.radius}px`);
  if (!scope) {
    out.push(`.cfeed,.pfeed,#feed{color:${b.text}}`);
    if (b.bgA > 0) out.push(`.cfeed,#feed{background:${rgba(b.bg, b.bgA)}}`);
  }
  R('.msg', `font-size:${b.size}px`);
  R('.msg .u,.pm b', `font-weight:${b.nameWeight}`);
  R('.emo', `height:${(b.emoteSize / 100).toFixed(2)}em`);
  if (!b.timestamps) R('.msg .t', 'display:none');
  if (!b.badges) R('.msg .bd,.pm .bd', 'display:none');
  if (!b.platformTag) R('.msg .pf,.msg .pl', 'display:none');
  CS_PLATFORMS.forEach(p => { const mk = (s.marker || {})[p] || {size: 14, color: ''}; R(`.pl.pl-${p}`, `width:${mk.size}px;height:${mk.size}px;vertical-align:middle;margin-right:5px;color:${mk.color || {twitch: '#9146ff', youtube: '#ff4d4d', discord: '#5865f2', tiktok: '#25f4ee'}[p]}`); });
  const add = (cls, r) => {
    const css = ruleCss(r, k);
    if (css) R(`.msg.${cls},.pm.${cls}`, css);
    if (r && r.on !== false && r.name) R(`.msg.${cls} .u,.pm.${cls} b`, `color:${r.name}!important`);
  };
  CS_PLATFORMS.forEach(p => {
    add('p-' + p, s.platform[p]);
    const c = s.platform[p].border; if (c) R(`.pf.pf-${p}`, `background:${c};color:#fff`);
  });
  Object.keys(CS_ROLES).forEach(x => add('r-' + x, s.role[x]));
  Object.keys(CS_EVENTS).forEach(x => add('e-' + x, s.event[x]));
  (s.keywords || []).forEach((x, i) => add('kw' + i, x.rule));
  R('.notice.e-modaction', 'border-radius:4px');
  if (b.anim === 'pulse') { out.push('@keyframes mpulse{from{filter:brightness(2) saturate(1.5)}to{filter:none}}'); R(EVENT_ANIM.map(x => '.msg.e-' + x).join(','), 'animation:mpulse .9s ease-out'); }
  if (b.anim === 'slide') { out.push('@keyframes mslide{from{opacity:0;transform:translateX(-16px)}to{opacity:1;transform:none}}'); R(EVENT_ANIM.map(x => '.msg.e-' + x).join(','), 'animation:mslide .45s ease-out'); }
  return out.join('\n');
}
// This window's own look: the main chat look with the pane's small overrides on top (a split half can have its own size, background...).
let PANE = null, EFF = null;
function effectiveStyle() {
  if (!CS) return null;
  if (!PANE || !PANE.look || !Object.keys(PANE.look).length) return CS;
  return Object.assign({}, CS, {base: Object.assign({}, CS.base, PANE.look)});
}
// Run fn while the chat renderer sees style s (used for the small preview cards).
function withStyle(s, fn) { const keep = EFF; EFF = s; try { return fn(); } finally { EFF = keep; } }
// Simple original glyphs drawn as inline SVG (no external files, no fetching). They hint at each platform, they are not the brand artwork.
const LOGOS = {
  twitch: '<path fill="currentColor" d="M3 2h18v12l-5 5h-4l-3 3H6v-3H3z"/><rect x="9" y="6" width="2.2" height="6" fill="#fff"/><rect x="14" y="6" width="2.2" height="6" fill="#fff"/>',
  youtube: '<rect x="1.5" y="5" width="21" height="14" rx="4.5" fill="currentColor"/><path fill="#fff" d="M10 8.8v6.4l5.6-3.2z"/>',
  discord: '<path fill="currentColor" d="M6 3h12a4 4 0 0 1 4 4v9a4 4 0 0 1-4 4H11l-5 3v-3a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4z"/><circle cx="9" cy="11" r="1.8" fill="#fff"/><circle cx="15" cy="11" r="1.8" fill="#fff"/>',
  tiktok: '<path fill="currentColor" d="M14 2h3.200c.3 2.300 1.700 3.800 4 4v3.300c-1.500 0-2.900-.5-4-1.300v6.300a6 6 0 1 1-6-6c.4 0 .700 0 1 .1v3.400a2.700 2.700 0 1 0 1.800 2.500z"/>',
};
function markerHtml(platform) {
  const mode = ((EFF || CS) && (EFF || CS).base.marker) || 'text';
  if (mode === 'none') return '';
  const word = `<span class="pf pf-${esc(platform)}">${esc(platform)}</span>`;
  const logo = LOGOS[platform] ? `<svg class="pl pl-${esc(platform)}" viewBox="0 0 24 24" aria-label="${esc(platform)}"><title>${esc(platform)}</title>${LOGOS[platform]}</svg>` : '';
  if (mode === 'logo') return logo || word;
  if (mode === 'both') return logo + word;
  return word;
}
function applyStyle() {
  if (!CS) return;
  EFF = effectiveStyle();
  let el = document.getElementById('cstyle');
  if (!el) { el = document.createElement('style'); el.id = 'cstyle'; document.head.appendChild(el); }
  el.textContent = compileStyle(EFF);
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
// Preview: sample messages or the real recent chat, on a choice of backdrops (so a see-through overlay look can be judged).
let edView = {real: false, bg: 'dark'}, EDP = null;
const BACKDROP = {dark: '#09090a', light: '#f1f1f1', game: 'linear-gradient(135deg,#1b3a2b,#2a2250 60%,#40261a)', checker: 'repeating-conic-gradient(#3a3a3e 0 25%,#2a2a2e 0 50%) 0 0/20px 20px'};
function previewHtml() {
  const real = edView.real && msgs.length ? msgs.slice(-24) : sampleMsgs();
  const rows = real.map(m => chatMsg(m, {plain: true}));
  if (!(edView.real && msgs.length)) rows.push(`<div class="notice e-modaction msg">Mod action: ModMary timed out SpamSam for 10 minutes</div>`);
  return rows.join('');
}
function renderPreview() {
  const p = $('#cs-preview'); if (!p) return;
  p.innerHTML = withStyle(CS, previewHtml);
  const w = $('#cs-pwrap'); if (w) w.style.background = BACKDROP[edView.bg] || BACKDROP.dark;
}
async function loadPresets() { try { EDP = await api('/api/chatstyle/presets'); } catch (e) { EDP = {builtin: [], mine: [], can_undo: false}; } }
const sameStyle = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function presetCard(p, mine, idx) {
  const cur = sameStyle(p.style, CS);
  const sample = [{platform: 'twitch', display: 'ModMary', user: 'm', badges: ['moderator'], text: 'Welcome in everyone!', flags: []},
    {platform: 'youtube', display: 'TubeTim', user: 't', text: 'Hello from YouTube', flags: []},
    {event: 'sub', platform: 'twitch', display: 'SubSally', user: 's', text: 'SubSally subscribed!', flags: []}];
  const html = withStyle(p.style, () => sample.map(m => chatMsg(Object.assign({id: '', ts: Date.now() / 1000, badges: [], tier: 'none', emotes: []}, m), {plain: true})).join(''));
  const css = compileStyle(p.style, '.pv-' + (mine ? 'm' : 'b') + idx);
  return `<div class="pcardl ${cur ? 'cur' : ''}"><style>${css}</style>
    <div class="pv pv-${mine ? 'm' : 'b'}${idx} cfeed" style="${p.style.base.bgA > 0 ? '' : 'background:#09090a'}">${html}</div>
    <div class="pmeta"><b>${esc(p.name)}</b> ${cur ? '<span class="chip">in use</span>' : ''}<div class="mut" style="font-size:.82em">${esc(p.desc || '')}</div>
    <div class="act"><button class="${cur ? '' : 'p'}" data-cs-act="usepreset" data-name="${esc(p.name)}" ${cur ? 'disabled' : ''}>${cur ? 'In use' : 'Use this look'}</button>
    ${mine ? `<button data-cs-act="delpreset" data-name="${esc(p.name)}" title="Delete this saved look">Delete</button>` : ''}</div></div></div>`;
}
function quickRow(path, title, hint) {
  const r = getPath(CS, path), col = r.bg || r.border || r.name || '#ff9900';
  return `<div class="qrow"><label class="chk" title="${esc(hint || '')}"><input type="checkbox" data-cs="${path}.on" data-t="bool" ${r.on !== false ? 'checked' : ''}> ${esc(title)}</label>
    <input type="color" data-cs="${path}" data-t="quick" value="${col}" title="One colour for the background, side bar and name">
    <input type="range" data-cs="${path}.bgA" data-t="num" min="0" max="100" value="${r.bgA}" title="How strong the background is" style="width:90px"><b class="qv">${r.bgA}%</b>
    <details class="more"><summary>more</summary>${ruleEditor(path, 'Details for ' + title, hint)}</details></div>`;
}
function edLeft() {
  const b = CS.base, num = (k, lab, lo, hi, step = 1, unit = '', tip = '') => `<label class="cf" title="${esc(tip)}">${lab} <input type="range" data-cs="base.${k}" data-t="num" min="${lo}" max="${hi}" step="${step}" value="${b[k]}"><b>${b[k]}${unit}</b></label>`;
  const chk = (k, lab, tip) => `<label class="cf" title="${esc(tip || '')}"><input type="checkbox" data-cs="base.${k}" data-t="bool" ${b[k] ? 'checked' : ''}> ${lab}</label>`;
  const sel = (k, lab, opts, tip) => `<label class="cf" title="${esc(tip || '')}">${lab} <select data-cs="base.${k}" data-t="str">${opts.map(([v, t]) => `<option value="${v}" ${String(b[k]) === String(v) ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
  const builtin = (EDP ? EDP.builtin : []).map((p, i) => presetCard(p, false, i)).join('');
  const mine = (EDP ? EDP.mine : []).map((p, i) => presetCard(p, true, i)).join('');
  return `
    <section><h3>1. Pick a look</h3><p class="mut">Click one to try it. Your chat changes at once and you can undo it.</p>
      <div class="pgrid">${builtin}</div>
      ${mine ? `<h4>Your saved looks</h4><div class="pgrid">${mine}</div>` : ''}</section>
    <section><h3>2. Make it yours</h3><p class="mut">The usual tweaks. Everything saves by itself.</p>
      <div class="act"><b>Spacing</b> <button data-cs-act="density" data-v="tight">Tight</button><button data-cs-act="density" data-v="normal">Normal</button><button data-cs-act="density" data-v="roomy">Roomy</button></div>
      <div class="rg">
        <label class="cf" title="The font used for chat messages">Font <select data-cs="base.family" data-t="str">${FAMILIES.map(f => `<option ${b.family === f ? 'selected' : ''} style="font-family:${f}">${f}</option>`).join('')}</select></label>
        ${num('size', 'Text size', 9, 48, 1, 'px', 'Size of chat text')}
        ${optColor('base.text', 'Text colour')}${optColor('base.bg', 'Background')}${num('bgA', 'Background strength', 0, 100, 1, '%', '0 = see-through (for overlays), 100 = solid')}
        ${num('intensity', 'Highlight strength', 0, 250, 5, '%', 'Scales every role and event highlight at once: 0 = none, 100 = as designed, more = bolder')}
        ${sel('anim', 'New event animation', [['none', 'None'], ['pulse', 'Glow'], ['slide', 'Slide in']], 'How subs, raids, gifts and other events appear')}
        ${sel('marker', 'Platform marker', [['text', 'Word'], ['logo', 'Logo'], ['both', 'Logo and word'], ['none', 'Nothing']], 'How each message shows which platform it came from')}
        ${chk('timestamps', 'Show times')}${chk('badges', 'Show badges')}${chk('platformTag', 'Show platform marker')}</div></section>
    <section><h3>3. Highlights</h3><p class="mut">Who and what stands out. Switch one off, change its colour or strength; "more" has every detail.</p>
      <h4>People</h4>${Object.entries(CS_ROLES).map(([k, t]) => quickRow('role.' + k, t)).join('')}
      <h4>Stream events</h4>${Object.entries(CS_EVENTS).map(([k, t]) => quickRow('event.' + k, t, k === 'follow' || k === 'redeem' ? 'needs the bot Host to send these events' : '')).join('')}</section>
    <section><h3>4. Words to highlight</h3>
      <div class="act"><input id="kw-new" placeholder="word or phrase, e.g. giveaway" style="width:220px"><button data-cs-act="addkw">Add</button></div>
      ${(CS.keywords || []).map((k, i) => quickRow('keywords.' + i + '.rule', '"' + k.word + '"') + `<div class="act"><button data-cs-act="delkw" data-i="${i}">Remove "${esc(k.word)}"</button></div>`).join('') || '<div class="empty">None yet. A message containing one of these words gets its own highlight.</div>'}</section>
    <details class="adv"><summary><h3>Advanced</h3></summary><div class="rg">
      ${num('weight', 'Text weight', 300, 900, 100)}${num('nameWeight', 'Name weight', 300, 900, 100)}${num('line', 'Line height', 1, 2.2, 0.05)}${num('spacing', 'Space between messages', 0, 20, 1, 'px')}
      ${num('emoteSize', 'Emote size', 80, 300, 10, '%')}${num('radius', 'Corner roundness', 0, 24, 1, 'px')}
      ${CS_PLATFORMS.map(p => `<label class="cf">${p} logo ${CS.marker[p].size}px <input type="range" data-cs="marker.${p}.size" data-t="num" min="10" max="40" value="${CS.marker[p].size}">${optColor('marker.' + p + '.color', 'colour')}</label>`).join('')}</div>
      <h4>Platform colours</h4>${CS_PLATFORMS.map(p => ruleEditor('platform.' + p, p[0].toUpperCase() + p.slice(1), 'tag colour = side bar colour')).join('')}</details>
    <section><h3>5. Save, share, start over</h3>
      <div class="act"><input id="preset-name" placeholder="name this look" style="width:200px"><button class="p" data-cs-act="savepreset">Save my look</button>
        <button data-cs-act="undo" ${EDP && EDP.can_undo ? '' : 'disabled'} title="Go back to how it was before the last look you picked, imported or reset">Undo last look change</button>
        <button data-cs-act="reset">Reset to default</button></div>
      <div class="act"><button data-cs-act="export">Show look as text (to share or back up)</button><button data-cs-act="import">Load look from text</button></div>
      <textarea id="cs-io" rows="4" placeholder="Export puts the look here as text. To load a look, paste it here and press Load." style="width:100%"></textarea></section>`;
}
function renderEdLeft() { const l = $('#ed-left'); if (l) l.innerHTML = edLeft(); }
async function renderStyleEditor() {
  if (!CS) { $('#body').innerHTML = '<div class="empty">Loading...</div>'; await loadStyle(); }
  if (!EDP) await loadPresets();
  const bgBtn = (v, t) => `<button class="${edView.bg === v ? 'p' : ''}" data-cs-act="pvbg" data-v="${v}">${t}</button>`;
  $('#body').innerHTML = `<div class="launch style-ed"><div class="ed-top"><h2>Chat look</h2>
      <span class="act"><button data-cs-act="popout" title="Open this editor in its own window - drag it to any monitor">Pop out</button> <a href="/?type=chat"><button type="button">Back to chat</button></a> <a href="/"><button type="button">Setup</button></a> <span id="cs-state" class="mut"></span></span></div>
    <div class="ed-grid"><div id="ed-left" class="ed-left"></div>
      <div class="ed-right"><div class="act"><b>Preview</b> <button data-cs-act="pvreal" class="${edView.real ? 'p' : ''}" title="Show your real recent chat instead of the samples">My real chat</button> ${bgBtn('dark', 'Dark')}${bgBtn('light', 'Light')}${bgBtn('game', 'Over a game')}${bgBtn('checker', 'See-through')}</div>
        <div id="cs-pwrap" class="cs-pwrap"><div id="cs-preview" class="cfeed cs-preview"></div></div></div></div></div>`;
  renderEdLeft(); renderPreview();
}
function csChanged(el, final) {
  const path = el.dataset.cs, t = el.dataset.t; let v;
  if (t === 'optc') { const col = el.parentElement.querySelector('input[type=color]'); v = el.checked ? col.value : ''; setPath(CS, path, v); }
  else if (t === 'color') { v = el.value; const cb = el.parentElement.querySelector('input[type=checkbox]'); if (cb) cb.checked = true; setPath(CS, path, v); }
  else if (t === 'quick') {
    const r = getPath(CS, path); ['bg', 'border', 'name'].forEach(k => { if (r[k]) r[k] = el.value; });
    if (!r.bg && !r.border && !r.name) { r.bg = el.value; r.border = el.value; }
    if (!r.borderW && r.border) r.borderW = 4;
  }
  else if (t === 'bool') { setPath(CS, path, el.checked); }
  else if (t === 'num') { setPath(CS, path, parseFloat(el.value)); const out = el.parentElement.querySelector('b'); if (out) out.textContent = el.value + (out.textContent.replace(/[-0-9.]/g, '')); }
  else setPath(CS, path, el.value);
  applyStyle(); renderPreview(); scheduleSave();
  if (final && (t === 'quick' || t === 'str' || t === 'optc' || t === 'color')) { renderEdLeft(); if (W.type !== 'style' && typeof sideRender === 'function') sideRender(); }     // refresh fields that mirror each other
}
const csActive = () => W.type === 'style' || (typeof SIDE !== 'undefined' && SIDE.open && W.type === 'chat');
document.addEventListener('input', e => { if (csActive() && e.target.dataset && e.target.dataset.cs) csChanged(e.target, false); });
document.addEventListener('change', e => { if (csActive() && e.target.dataset && e.target.dataset.cs) csChanged(e.target, true); });
const DENSITY = {tight: {spacing: 1, line: 1.2}, normal: {spacing: 4, line: 1.35}, roomy: {spacing: 9, line: 1.5}};
function edNote(t) { const s = $('#cs-state'); if (s) s.textContent = t; }
document.addEventListener('click', async e => {
  if (!csActive()) return;
  const b = e.target.closest('button[data-cs-act]'); if (!b) return;
  const a = b.dataset.csAct;
  const took = async (r) => { if (r && r.style) { CS = r.style; applyStyle(); } await loadPresets(); renderEdLeft(); renderPreview(); };
  try {
    if (a === 'reset') { if (!confirm('Reset the whole chat look to the default? You can undo this.')) return; await took(await api('/api/chatstyle/apply', {b: {name: 'Pinguino'}})); edNote('Reset. "Undo last look change" brings your look back.'); }
    else if (a === 'usepreset') { await took(await api('/api/chatstyle/apply', {b: {name: b.dataset.name}})); edNote('Now using "' + b.dataset.name + '". Undo is below if you do not like it.'); }
    else if (a === 'undo') { const r = await fetch('/api/chatstyle/undo', {method: 'POST', headers: {'content-type': 'application/json'}, body: '{}'}); if (r.ok) { await took(await r.json()); edNote('Went back to your previous look.'); } else edNote('Nothing to undo.'); }
    else if (a === 'savepreset') { const n = ($('#preset-name').value || '').trim(); if (!n) { edNote('Type a name first.'); return; } await api('/api/chatstyle/save-preset', {b: {name: n, style: CS}}); await took(); edNote('Saved as "' + n + '".'); }
    else if (a === 'delpreset') { if (!confirm('Delete the saved look "' + b.dataset.name + '"?')) return; await api('/api/chatstyle/delete-preset', {b: {name: b.dataset.name}}); await took(); }
    else if (a === 'export') { const r = await api('/api/chatstyle/export'); $('#cs-io').value = JSON.stringify(r); $('#cs-io').select(); try { await navigator.clipboard.writeText($('#cs-io').value); edNote('Copied. Paste it anywhere to keep or share it.'); } catch (x) { edNote('Selected - press Ctrl+C.'); } }
    else if (a === 'import') {
      let j; try { j = JSON.parse($('#cs-io').value); } catch (x) { edNote('That is not a look: paste the exported text into the box first.'); return; }
      const r = await fetch('/api/chatstyle/import', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(j)}); const jj = await r.json();
      if (!r.ok) { edNote(jj.detail || 'Could not load that.'); return; } await took(jj); edNote('Loaded. "Undo last look change" goes back.'); }
    else if (a === 'density') { Object.assign(CS.base, DENSITY[b.dataset.v]); applyStyle(); renderPreview(); renderEdLeft(); scheduleSave(); }
    else if (a === 'pvreal') { edView.real = !edView.real; renderStyleEditor(); }
    else if (a === 'pvbg') { edView.bg = b.dataset.v; renderStyleEditor(); }
    else if (a === 'popout') popOut('look-editor', location.origin + '/?type=style', 'Chat look', {w: 1180, h: 860});
    else if (a === 'addkw') { const w = ($('#kw-new').value || '').trim(); if (!w) return; CS.keywords = (CS.keywords || []).concat({word: w, rule: JSON.parse(JSON.stringify(CS.event.mention))}); applyStyle(); renderEdLeft(); renderPreview(); scheduleSave(); if (W.type !== 'style') { sideRender(); chatFeed(); } }
    else if (a === 'delkw') { CS.keywords.splice(parseInt(b.dataset.i), 1); applyStyle(); renderEdLeft(); renderPreview(); scheduleSave(); if (W.type !== 'style') { sideRender(); chatFeed(); } }
  } catch (err) { edNote('Something went wrong: ' + err); }
});
