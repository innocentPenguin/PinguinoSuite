// Editor for the OBS browser-source widgets (/obs/chat, /obs/activity): /?type=obs&widget=chat|activity
// Settings use Synchra's field names, so a Synchra widget export imports directly. Live preview = the real widget page in an iframe with test messages.
const OBS = {kind: 'chat', cfg: null, S: null, timer: null};
const OBS_PLATS = ['twitch', 'youtube', 'kick', 'discord', 'tiktok'];
const OBS_ACT = ['follow', 'redeem', 'sub', 'resub', 'gift', 'cheer', 'raid', 'announcement'];

async function renderObsEditor() {
  OBS.kind = q.get('widget') === 'activity' ? 'activity' : 'chat';
  $('#hdr').style.display = 'none';
  $('#body').innerHTML = '<div class="empty">Loading...</div>';
  OBS.cfg = await fetch('/api/obs/' + OBS.kind).then(r => r.json());
  OBS.S = JSON.parse(JSON.stringify(OBS.cfg.settings));
  obsDraw();
}
function obsUrl() { return location.origin + '/obs/' + OBS.kind; }
function obsDraw() {
  const S = OBS.S, c = OBS.cfg, k = OBS.kind;
  const sel = (key, opts, lab) => `<label class="cf">${lab} <select data-ob="${key}">${opts.map(([v, t]) => `<option value="${v}" ${String(S[key]) === String(v) ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
  const rng = (key, lab, lo, hi, st, unit = '') => `<label class="cf">${lab} <input type="range" data-ob="${key}" data-n="1" min="${lo}" max="${hi}" step="${st}" value="${S[key]}"><b>${S[key]}${unit}</b></label>`;
  const col = (key, lab) => `<label class="cf">${lab} <input type="color" data-ob="${key}" value="${S[key] || '#000000'}"></label>`;
  const chk = (key, lab) => `<label class="cf"><input type="checkbox" data-ob="${key}" data-b="1" ${S[key] ? 'checked' : ''}> ${lab}</label>`;
  const nobg = `<label class="cf"><input type="checkbox" data-obnobg="1" ${S.background_color ? '' : 'checked'}> No background box</label>`;
  const left = `
    <div class="act"><a href="/?type=obs&widget=chat"><button class="${k === 'chat' ? 'p' : ''}" type="button">Chat widget</button></a> <a href="/?type=obs&widget=activity"><button class="${k === 'activity' ? 'p' : ''}" type="button">Activity widget</button></a>
      <a href="/?type=chat"><button type="button">Back to chat</button></a> <span id="ob-state" class="mut"></span></div>
    <div class="box"><b>OBS browser source address</b><br><input id="ob-url" readonly value="${esc(obsUrl())}" style="width:100%" onclick="this.select()">
      <div class="act"><button data-ob-act="copy">Copy address</button> <a href="${esc(obsUrl())}" target="_blank" rel="noopener"><button type="button">Open</button></a></div>
      <small class="mut">In OBS: Sources &gt; + &gt; Browser &gt; paste this address. Width/height = your canvas area, nothing else needed. Changes here show in OBS instantly.</small></div>
    <h4>Presets</h4><div class="act">${c.presets.map((p, i) => `<button data-ob-act="preset" data-i="${i}" title="${esc(p.desc)}">${esc(p.name)}</button>`).join('')}<button data-ob-act="reset">Reset to defaults</button></div>
    <h4>Text</h4>${sel('size', Object.keys(c.sizes).map(s => [s, s.toUpperCase() + ' (' + c.sizes[s] + 'px)']), 'Size')}${rng('canvas_scale', 'Scale', 0.25, 3, 0.05, 'x')}
    ${sel('font_family_id', c.fonts.map(f => [f, f]), 'Font')}${col('text_color', 'Text colour')}${col('text_shadow_color', 'Shadow colour')}${col('accent_color', 'Accent colour')}
    ${k === 'chat' ? sel('name_color_mode', [['platform', 'Viewer colour, else platform colour'], ['own', 'Viewer colour, else text colour'], ['none', 'All text colour']], 'Names') : ''}
    <h4>Look</h4>${sel('style_type', [['simple', 'Simple (no box per message)'], ['bubble', 'Bubble'], ['boxed', 'Boxed']], 'Style')}${nobg}${col('background_color', 'Background colour')}${rng('background_opacity', 'Background opacity', 0, 1, 0.05)}
    ${rng('border_width', 'Border width', 0, 12, 1, 'px')}${col('border_color', 'Border colour')}${rng('border_radius', 'Corner radius', 0, 40, 1, 'px')}
    <h4>Behaviour</h4>${sel('entrance_animation_type', [['none', 'None'], ['fade', 'Fade'], ['slide', 'Slide'], ['pop', 'Pop']], 'Entrance')}
    ${sel('message_order', [['bottom', 'Newest at the bottom'], ['top', 'Newest at the top']], 'Order')}${sel('message_alignment', [['left', 'Left'], ['center', 'Centre'], ['right', 'Right']], 'Align')}
    ${rng('max_messages', 'Rows shown', 1, 100, 1)}${rng('message_fade_duration_seconds', 'Disappear after (0 = never)', 0, 300, 1, ' s')}${rng('message_delay_seconds', 'Delay before showing', 0, 30, 0.5, ' s')}
    <h4>Show</h4>${chk('provider_logo', 'Platform logo')}${k === 'chat' ? chk('badges', 'Badges (mod, VIP, sub)') + chk('username_colon', 'Colon after name') + chk('notices', 'Notices (subs, raids, follows)') : chk('show_age', 'Age (10h)')}
    <div class="cf">Platforms ${['all', ...OBS_PLATS].map(p => `<label class="chk"><input type="checkbox" data-obp="${p}" ${S.providers.includes(p) ? 'checked' : ''}> ${p}</label>`).join(' ')}</div>
    ${k === 'activity' ? `<div class="cf">Types ${OBS_ACT.map(t => `<label class="chk"><input type="checkbox" data-obt="${t}" ${S.types.includes(t) ? 'checked' : ''}> ${t}</label>`).join(' ')}</div>` : ''}
    <h4>Ignore list</h4><textarea id="ob-ig" rows="4" style="width:100%" placeholder="one name per line">${esc(S.ignore_names.join('\n'))}</textarea><small class="mut">These accounts never appear (bots). Case does not matter.</small>
    <h4>Custom CSS</h4><textarea id="ob-css" rows="9" style="width:100%;font-family:Consolas,monospace" spellcheck="false" placeholder=".chat-message-container { ... }">${esc(S.custom_css)}</textarea>
    <small class="mut">Classes: .chat-message-container .chat-username .chat-text .chat-badge .chat-provider ${k === 'activity' ? '.activity-row .act-pill .act-user .act-chip .act-age' : '.chat-notice'}. @import works for web fonts.</small>
    <h4>Import / export (Synchra compatible)</h4>
    <div class="act"><button data-ob-act="export">Export file</button> <button data-ob-act="import-file">Import file...</button><input id="ob-file" type="file" accept=".json,application/json" hidden>
      <button data-ob-act="import-paste">Import pasted text</button></div><textarea id="ob-paste" rows="3" style="width:100%" placeholder="Paste a Synchra widget export here (chat widget only)"></textarea>`;
  const prev = `<div style="position:sticky;top:8px"><b>Live preview</b> <small class="mut">test messages only</small>
    <div style="height:620px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:repeating-conic-gradient(#2a2622 0% 25%,#1d1a17 0% 50%) 0 0/24px 24px"><iframe id="ob-prev" src="/obs/${k}?preview=1" style="width:100%;height:100%;border:0;background:transparent"></iframe></div></div>`;
  const keep = $('#ob-pane') ? $('#ob-pane').scrollTop : 0;
  $('#body').innerHTML = `<div id="ob-wrap" style="display:grid;grid-template-columns:minmax(360px,520px) 1fr;gap:16px;padding:12px;height:100vh;box-sizing:border-box"><div id="ob-pane" style="overflow:auto;padding-right:8px">${left}</div>${prev}</div>`;
  $('#ob-pane').scrollTop = keep;
  $('#ob-file').addEventListener('change', async e => { const f = e.target.files[0]; if (f) obsImport(await f.text()); });
}
function obsPush() { const f = $('#ob-prev'); if (f && f.contentWindow) f.contentWindow.postMessage({obsSettings: OBS.S}, '*'); }
function obsSave() {
  clearTimeout(OBS.timer);
  $('#ob-state') && ($('#ob-state').textContent = 'saving...');
  OBS.timer = setTimeout(async () => {
    const r = await api('/api/obs/' + OBS.kind, {b: {settings: OBS.S}});
    OBS.S = r.settings; if ($('#ob-state')) $('#ob-state').textContent = 'saved';
  }, 450);
}
function obsChanged(redraw) { obsPush(); obsSave(); if (redraw) obsDraw(); }
async function obsImport(text) {
  let doc; try { doc = JSON.parse(text); } catch (e) { alert('That is not valid JSON.'); return; }
  const r = await fetch('/api/obs/chat/import', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({doc})}).then(r => r.json());
  if (r.detail) { alert('Import failed: ' + r.detail); return; }
  OBS.S = r.settings; obsDraw(); $('#ob-state').textContent = 'imported and saved';
}
document.addEventListener('input', e => {
  if (W.type !== 'obs') return; const t = e.target;
  if (t.dataset.ob) { OBS.S[t.dataset.ob] = t.dataset.b ? t.checked : t.dataset.n ? parseFloat(t.value) : t.value; const b = t.parentElement.querySelector('b'); if (b && t.type === 'range') b.textContent = t.value; if (t.dataset.ob === 'background_color' && t.value) { /* colour picked: box on */ const nb = document.querySelector('[data-obnobg]'); if (nb) nb.checked = false; } obsChanged(false); }
  else if (t.id === 'ob-ig') { OBS.S.ignore_names = t.value.split('\n').map(x => x.trim()).filter(Boolean); obsChanged(false); }
  else if (t.id === 'ob-css') { OBS.S.custom_css = t.value; obsChanged(false); }
});
document.addEventListener('change', e => {
  if (W.type !== 'obs') return; const t = e.target;
  if (t.dataset.obnobg) { OBS.S.background_color = t.checked ? '' : (OBS.S.background_color || '#14110d'); obsChanged(true); }
  else if (t.dataset.obp) { const p = t.dataset.obp, cur = new Set(OBS.S.providers); t.checked ? cur.add(p) : cur.delete(p); if (p !== 'all' && t.checked) cur.delete('all'); if (!cur.size) cur.add('all'); OBS.S.providers = [...cur]; obsChanged(true); }
  else if (t.dataset.obt) { const cur = new Set(OBS.S.types); t.checked ? cur.add(t.dataset.obt) : cur.delete(t.dataset.obt); OBS.S.types = [...cur]; obsChanged(false); }
  else if (t.dataset.ob && t.tagName === 'SELECT') obsPush();
});
window.addEventListener('message', e => { if (e.data && e.data.obsReady && W.type === 'obs') obsPush(); });
document.addEventListener('click', async e => {
  if (W.type !== 'obs') return; const b = e.target.closest('button'); if (!b || !b.dataset.obAct) return;
  const a = b.dataset.obAct;
  if (a === 'copy') { try { await navigator.clipboard.writeText(obsUrl()); } catch (x) { $('#ob-url').select(); document.execCommand('copy'); } $('#ob-state').textContent = 'address copied'; }
  else if (a === 'preset') { OBS.S = Object.assign({}, OBS.cfg.defaults, OBS.cfg.presets[+b.dataset.i].settings); obsChanged(true); }
  else if (a === 'reset') { if (confirm('Reset this widget to its defaults?')) { OBS.S = JSON.parse(JSON.stringify(OBS.cfg.defaults)); obsChanged(true); } }
  else if (a === 'export') {
    const doc = await fetch('/api/obs/' + OBS.kind + '/export').then(r => r.json());
    const u = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], {type: 'application/json'})), l = document.createElement('a');
    l.href = u; l.download = 'pinguino-' + OBS.kind + '-widget.json'; l.click(); setTimeout(() => URL.revokeObjectURL(u), 2000);
  }
  else if (a === 'import-file') $('#ob-file').click();
  else if (a === 'import-paste') { if ($('#ob-paste').value.trim()) obsImport($('#ob-paste').value); }
});
