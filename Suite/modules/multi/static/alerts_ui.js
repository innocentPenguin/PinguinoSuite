// Alert editor + tester: /?type=alerts. Edits the central alert engine (Multi alerts.py): profiles, per-type template, per-user overrides, tests, log.
// The preview is the real /obs/alerts page in an iframe (works offline); all edits save automatically (debounced) and show in OBS instantly.
const AL = {d: null, sel: 'follow', who: '', timer: null, last: null, logT: 0};
const alGet = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
function alSet(o, p, v) { const ks = p.split('.'); let c = o; ks.slice(0, -1).forEach(k => { c = c[k] = c[k] || {}; }); c[ks[ks.length - 1]] = v; }
const alProf = () => AL.d.config.profiles[AL.d.config.active];
const alBase = () => alProf().types[AL.sel];
function alEff() {                       // what the editor shows: profile values, with the selected viewer's override on top
  const b = JSON.parse(JSON.stringify(alBase()));
  const ov = AL.who && (AL.d.config.overrides[AL.who] || {});
  const merge = (a, o) => { Object.keys(o || {}).forEach(k => { if (o[k] && typeof o[k] === 'object' && !Array.isArray(o[k])) merge(a[k] = a[k] || {}, o[k]); else a[k] = o[k]; }); };
  if (ov) { merge(b, ov['*']); merge(b, ov[AL.sel]); }
  return b;
}
function alTarget() {                    // where an edit is written
  if (!AL.who) return alBase();
  const o = AL.d.config.overrides[AL.who] = AL.d.config.overrides[AL.who] || {};
  return o[AL.sel] = o[AL.sel] || {};
}

async function renderAlertsEditor() {
  $('#hdr').style.display = 'none';
  $('#body').innerHTML = '<div class="empty">Loading...</div>';
  AL.d = await fetch('/api/alerts').then(r => r.json());
  alDraw();
  clearInterval(AL.logT); AL.logT = setInterval(alLog, 2000);
}
function alUrl() { return location.origin + '/obs/alerts'; }
function alDraw() {
  const d = AL.d, c = d.config, e = alEff(), s = e.style, so = e.sound, me = e.media;
  const f = (p, lab, kind, extra = {}) => {
    const v = alGet(e, p);
    if (kind === 'chk') return `<label class="cf"><input type="checkbox" data-al="${p}" data-k="b" ${v ? 'checked' : ''}> ${lab}</label>`;
    if (kind === 'num') return `<label class="cf">${lab} <input type="range" data-al="${p}" data-k="n" min="${extra.lo}" max="${extra.hi}" step="${extra.st || 1}" value="${v}"><b>${v}${extra.unit || ''}</b></label>`;
    if (kind === 'col') return `<label class="cf">${lab} <input type="color" data-al="${p}" data-k="s" value="${esc(v || '#000000')}"></label>`;
    if (kind === 'sel') return `<label class="cf">${lab} <select data-al="${p}" data-k="s">${extra.opts.map(o => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></label>`;
    return `<label class="cf">${lab} <input type="text" data-al="${p}" data-k="s" value="${esc(v || '')}" style="width:100%" ${extra.ph ? `placeholder="${esc(extra.ph)}"` : ''}></label>`;
  };
  const types = d.types.map(t => `<button type="button" class="${t === AL.sel ? 'p' : ''}" data-alsel="${t}">${esc(d.labels[t])}${c.profiles[c.active].types[t].enabled ? '' : ' (off)'}</button>`).join(' ');
  const profs = Object.keys(c.profiles).map(p => `<option ${p === c.active ? 'selected' : ''}>${esc(p)}</option>`).join('');
  const users = Object.keys(c.overrides).sort().map(u => `<option value="${esc(u)}" ${u === AL.who ? 'selected' : ''}>${esc(u)}</option>`).join('');
  const hasOv = AL.who && c.overrides[AL.who] && c.overrides[AL.who][AL.sel];
  const tiers = ['1', '2', '3', 'prime'].map(t => `<label class="cf"><input type="checkbox" data-altier="${t}" ${e.conditions.tiers.includes(t) ? 'checked' : ''}> T${t}</label>`).join('');
  const variants = d.variants.map(v => `<label class="cf"><input type="checkbox" data-alvar="${v}"> ${v}</label>`).join(' ');
  $('#body').innerHTML = `<div style="padding:10px;overflow:auto;height:100%;box-sizing:border-box">
    <div class="act"><b>Alerts</b> <label class="cf">Profile <select id="al-prof">${profs}</select></label>
      <button data-alact="dup">Duplicate profile</button> <button data-alact="del">Delete profile</button> <a href="/?type=dash"><button type="button">Back to dashboard</button></a> <span id="al-state" class="mut"></span></div>
    <div class="box"><b>OBS browser source</b> (800 x 600) <input readonly value="${esc(alUrl())}" style="width:100%" onclick="this.select()">
      <div class="act"><button data-alact="copy">Copy address</button> <a href="${esc(alUrl())}?bg=1" target="_blank" rel="noopener"><button type="button">Open (preview works offline)</button></a>
      <small class="mut">Real events only arrive while live; tests and this preview always work.</small></div></div>
    <div class="act" style="margin-top:8px">${types}</div>
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:10px">
      <div style="flex:0 0 480px"><div class="box"><b>Preview</b>
        <div style="width:480px;height:360px;position:relative;margin:6px 0"><iframe id="al-pv" src="/obs/alerts?bg=1&pv=1" style="width:800px;height:600px;border:1px solid var(--line);transform:scale(.6);transform-origin:0 0;position:absolute"></iframe></div>
        <div class="act"><button data-alact="pv" class="p">Show preview</button> <button data-alact="test">Queue test</button> <button data-alact="testall">Test all</button>
        <button data-alact="stress">Stress (30)</button> <button data-alact="skip">Skip</button> <button data-alact="clear">Clear queue</button> <button data-alact="pause">Pause/resume</button></div>
        <div class="act"><label class="cf">Viewer <input id="al-tuser" value="${esc(AL.who || 'penguin')}" style="width:110px"></label>
        <label class="cf">Amount <input id="al-tamt" type="number" style="width:70px" placeholder="auto"></label> ${variants}</div>
        <small class="mut">Tests are flagged: they never reach credits, stats, points or chat. In chat (mods): <code>!alert test follow penguin</code>, <code>!alert test sub penguin tier3</code>, <code>!alert test gift penguin 50</code></small></div>
        <div class="box"><b>What fired</b> <div id="al-log" style="max-height:230px;overflow:auto;font-size:12px"></div></div></div>
      <div style="flex:1 1 380px;min-width:340px"><div class="box"><b>${esc(d.labels[AL.sel])}</b>
        <div class="act"><label class="cf">Edit for <select id="al-who"><option value="">everyone (profile)</option>${users}</select></label>
        <input id="al-newuser" placeholder="add viewer login" style="width:130px"><button data-alact="adduser">Add override</button>${hasOv ? '<button data-alact="clrov">Clear this override</button>' : ''}</div>
        ${f('enabled', 'Enabled', 'chk')} ${f('silent', 'Silent (no sound)', 'chk')}
        ${f('text', 'Text', 'txt')}${f('subtext', 'Second line', 'txt')}
        <div class="act">${d.vars.map(v => `<button type="button" data-alvarins="${v}">${v}</button>`).join('')}</div>
        ${f('priority', 'Priority (higher plays first)', 'num', {lo: 1, hi: 9})}${f('duration', 'Duration', 'num', {lo: 1, hi: 30, unit: ' s'})}
        ${f('min_amount', 'Minimum amount', 'num', {lo: 0, hi: 1000})}${f('cooldown_s', 'Per-viewer cooldown', 'num', {lo: 0, hi: 600, unit: ' s'})}${f('max_per_min', 'Max per minute (0 = no limit)', 'num', {lo: 0, hi: 60})}
        ${f('conditions.first_time_only', 'Only first-time viewers', 'chk')}<div class="act">Tiers (none = all): ${tiers}</div>
        <b>Look</b>${f('style.layout', 'Layout', 'sel', {opts: d.layouts})}${f('style.anim_in', 'Animation in', 'sel', {opts: d.anims})}${f('style.anim_out', 'Animation out', 'sel', {opts: d.anims})}
        ${f('style.font', 'Font', 'sel', {opts: d.fonts})}${f('style.size', 'Text size', 'num', {lo: 14, hi: 80, unit: ' px'})}
        ${f('style.bg', 'Background', 'col')}${f('style.fg', 'Text colour', 'col')}${f('style.accent', 'Accent / border', 'col')}
        ${f('style.opacity', 'Box opacity', 'num', {lo: 0, hi: 100, unit: '%'})}${f('style.radius', 'Corner radius', 'num', {lo: 0, hi: 60})}${f('style.border', 'Border', 'num', {lo: 0, hi: 12})}
        <b>Sound</b>${f('sound.enabled', 'Play a sound', 'chk')}${f('sound.url', 'Sound file address (empty = built-in chime). http(s):// or /', 'txt')}${f('sound.volume', 'Volume', 'num', {lo: 0, hi: 100, unit: '%'})}
        ${['1', '2', '3'].map(t => f('sound.tier_urls.' + t, 'Tier ' + t + ' sound (optional)', 'txt')).join('')}
        <b>Image / GIF / video</b>${f('media.url', 'Media address (png, gif, webm, mp4). http(s):// or /', 'txt')}${f('media.kind', 'Type', 'sel', {opts: ['image', 'video']})}
        ${f('media.position', 'Position', 'sel', {opts: ['above', 'left', 'bg']})}${f('media.size', 'Size', 'num', {lo: 40, hi: 600, unit: ' px'})}
      </div></div></div></div>`;
  alLog(); alPreview();
}
function alState(t) { const el = $('#al-state'); if (el) { el.textContent = t; setTimeout(() => { if (el.textContent === t) el.textContent = ''; }, 2500); } }
function alSave() {
  clearTimeout(AL.timer);
  AL.timer = setTimeout(async () => {
    const r = await fetch('/api/alerts/config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({config: AL.d.config})}).then(r => r.json());
    AL.d.config = r.config; alState('Saved'); alPreview();
  }, 350);
}
async function alPreview() {
  clearTimeout(AL.pvT);
  const user = ($('#al-tuser') || {}).value || 'penguin';
  const j = await fetch('/api/alerts/preview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({type: AL.sel, event: {user: user.toLowerCase(), display: user}})}).then(r => r.json());
  const fr = $('#al-pv'); if (fr && fr.contentWindow) fr.contentWindow.postMessage({type: 'alert-preview', alert: Object.assign(j.alert, {duration: 60})}, '*');
}
async function alLog() {
  const el = $('#al-log'); if (!el) { clearInterval(AL.logT); return; }
  const d = await fetch('/api/alerts').then(r => r.json()); AL.d.status = d.status;
  el.innerHTML = `<div class="mut">queued: ${d.status.queued}${d.status.paused ? ' (PAUSED)' : ''}</div>` + d.log.slice(0, 40).map(l => `<div>${new Date(l.ts * 1000).toLocaleTimeString()} <b>${esc(l.type || '?')}</b> ${esc(l.user || '')} ${l.amount ? esc(l.amount) : ''} - ${esc(l.status)} <span class="mut">${esc(l.why || '')}${l.test ? ' [test]' : ''}</span></div>`).join('');
}
async function alPost(u, b) { return fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b || {})}).then(r => r.json()); }
document.addEventListener('change', e => {
  if (W.type !== 'alerts') return; const t = e.target;
  if (t.id === 'al-prof') { AL.d.config.active = t.value; alSave(); alDraw(); return; }
  if (t.id === 'al-who') { AL.who = t.value; alDraw(); return; }
  if (t.dataset.altier) {
    const tg = alTarget(), cur = new Set(alGet(alEff(), 'conditions.tiers')); t.checked ? cur.add(t.dataset.altier) : cur.delete(t.dataset.altier);
    alSet(tg, 'conditions.tiers', [...cur]); alSave(); return;
  }
  if (t.dataset.al) {
    const v = t.dataset.k === 'b' ? t.checked : t.dataset.k === 'n' ? +t.value : t.value;
    alSet(alTarget(), t.dataset.al, v); alSave(); if (t.type === 'range') { const b = t.parentElement.querySelector('b'); if (b) b.textContent = t.value + (b.textContent.replace(/[-\d.]+/, '')); }
  }
});
document.addEventListener('input', e => {
  if (W.type !== 'alerts') return; const t = e.target;
  if (t.dataset.al && (t.type === 'range' || t.type === 'text' || t.type === 'color')) {
    alSet(alTarget(), t.dataset.al, t.type === 'range' ? +t.value : t.value); alSave();
    if (t.type === 'range') { const b = t.parentElement.querySelector('b'); if (b) b.textContent = t.value + b.textContent.replace(/^[-\d.]+/, ''); }
  }
});
let alLastText = null;
document.addEventListener('focusin', e => { if (W.type === 'alerts' && e.target.dataset && e.target.dataset.al && e.target.type === 'text') alLastText = e.target; });
document.addEventListener('click', async e => {
  if (W.type !== 'alerts') return;
  const sel = e.target.closest('[data-alsel]'); if (sel) { AL.sel = sel.dataset.alsel; alDraw(); return; }
  const vi = e.target.closest('[data-alvarins]');
  if (vi) { const t = alLastText && document.contains(alLastText) ? alLastText : document.querySelector('[data-al="text"]'); const p = t.selectionStart == null ? t.value.length : t.selectionStart; t.value = t.value.slice(0, p) + vi.dataset.alvarins + t.value.slice(p); t.dispatchEvent(new Event('input', {bubbles: true})); return; }
  const b = e.target.closest('[data-alact]'); if (!b) return; const a = b.dataset.alact, c = AL.d.config;
  const user = ($('#al-tuser').value || 'penguin').trim().toLowerCase(), amt = $('#al-tamt').value, vars = [...document.querySelectorAll('[data-alvar]:checked')].map(x => x.dataset.alvar);
  if (a === 'copy') { navigator.clipboard && navigator.clipboard.writeText(alUrl()); alState('Address copied'); }
  else if (a === 'pv') alPreview();
  else if (a === 'test') { const r = await alPost('/api/alerts/test', {type: AL.sel, user, amount: amt === '' ? null : +amt, variant: vars}); alState(r.text); alLog(); }
  else if (a === 'testall') { const r = await alPost('/api/alerts/testall'); alState(r.text); alLog(); }
  else if (a === 'stress') { const r = await alPost('/api/alerts/stress', {n: 30}); alState(r.text); alLog(); }
  else if (a === 'skip' || a === 'clear') { await alPost('/api/alerts/control', {action: a}); alLog(); }
  else if (a === 'pause') { await alPost('/api/alerts/control', {action: AL.d.status.paused ? 'resume' : 'pause'}); alLog(); }
  else if (a === 'dup') { const n = prompt('Name for the copy', c.active + ' copy'); if (n && n.trim()) { c.profiles[n.trim().slice(0, 30)] = JSON.parse(JSON.stringify(alProf())); c.active = n.trim().slice(0, 30); alSave(); alDraw(); } }
  else if (a === 'del') { if (Object.keys(c.profiles).length > 1 && confirm('Delete profile ' + c.active + '?')) { delete c.profiles[c.active]; c.active = Object.keys(c.profiles)[0]; alSave(); alDraw(); } }
  else if (a === 'adduser') { const n = ($('#al-newuser').value || '').trim().toLowerCase(); if (n) { c.overrides[n] = c.overrides[n] || {}; AL.who = n; alDraw(); } }
  else if (a === 'clrov') { if (AL.who && c.overrides[AL.who]) { delete c.overrides[AL.who][AL.sel]; if (!Object.keys(c.overrides[AL.who]).length) { delete c.overrides[AL.who]; AL.who = ''; } alSave(); alDraw(); } }
});
