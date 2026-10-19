// Launcher: a guided, self-explanatory home screen. Uses globals from index.html ($, esc, api, W).
const STATE_TEXT = {
  connected: ['ok', 'Connected - reading chat'],
  connecting: ['wait', 'Connecting...'],
  reconnecting: ['wait', 'Lost the connection, retrying automatically'],
  needs_auth: ['todo', 'Not set up yet'],
  disabled: ['off', 'Turned off'],
  disconnected: ['off', 'Not connected'],
  error: ['bad', 'Problem - see details'],
};
const PROFILE_HELP = {
  'Combined Chat': 'One window with everything: all platforms, bot replies, cards that need an answer, and a reply box.',
  'Streaming': 'Priority cards on top, a unified chat below. Stays on top of your game.',
  'Gaming': 'One small always-on-top window with only the cards that need an answer.',
  'Editing': 'A big unified chat plus a card window; nothing floats over your editor.',
  'IRL': 'One large, easy-to-read card window for a phone or tablet.',
  'Minimal': 'Only high-priority cards, small and see-through.',
  'Full Monitoring': 'Unified chat, cards, missed and a status window across the screen.',
};
const WINDOW_HELP = {
  chat: ['Combined chat', 'The all-in-one window: every platform, bot replies, priority cards and a reply box.'],
  unified: ['All chat', 'Every platform in one scrolling feed.'],
  priority: ['Needs an answer', 'Cards for messages worth replying to, with why.'],
  missed: ['Missed', 'Cards you did not answer in time. You can bring them back.'],
  composer: ['Reply box', 'Type a reply to ONE chosen platform. Never sent to all.'],
  status: ['Connections', 'Health of each platform connection.'],
  first: ['First-time chatters', 'Only people chatting for the first time.'],
};
const T = (id, text) => `<span class="hlp" title="${esc(text)}">?</span>`;

function platformSetup(c, setup) {
  const s = setup.settings, has = setup.has;
  if (c.platform === 'twitch') return `<p class="how">Log in to your site as the owner, then press <b>Connect Twitch</b>. Twitch asks permission once; the key is kept in Windows Credential Manager, not in a file.</p>
    <div class="act"><button class="p" data-act="open-connect">Connect Twitch</button> <button data-act="disconnect">Disconnect</button></div>`;
  if (c.platform === 'discord') return `<p class="how">Create a bot at discord.com/developers, turn on <b>Message Content Intent</b>, invite it to your server, then paste its token and the channel IDs you want to follow (Discord &gt; Settings &gt; Advanced &gt; Developer Mode, then right-click a channel &gt; Copy ID).</p>
    <label>Bot token ${has.discord ? `<b class="okc">(${setup.sources.discord_token === 'vault' ? 'in the Suite key vault' : 'saved'})</b>` : ''}<input id="dc-token" type="password" autocomplete="off" placeholder="${has.discord ? 'leave empty to keep the saved token' : 'paste bot token'}"></label>
    <label>Channel IDs (comma separated)<input id="dc-chans" value="${esc((s.discord_channels || []).join(', '))}" placeholder="123456789012345678"></label>
    <div class="act"><button class="p" data-act="save-discord">Save Discord</button> ${has.discord ? '<button data-act="clear-discord">Forget token</button>' : ''}</div>`;
  if (c.platform === 'youtube') return `<p class="how">Paste a Google access token with the YouTube live-chat permission. Multi reads your active broadcast's chat. Tokens expire, so this needs re-pasting until automatic sign-in is added. Replies are plain messages (YouTube has no reply threads).</p>
    <label>Access token ${has.youtube ? `<b class="okc">(${setup.sources.youtube_token === 'vault' ? 'in the Suite key vault' : 'saved'})</b>` : ''}<input id="yt-token" type="password" autocomplete="off" placeholder="paste token"></label>
    <div class="act"><button class="p" data-act="save-youtube">Save YouTube</button> ${has.youtube ? '<button data-act="clear-youtube">Forget token</button>' : ''}</div>`;
  if (c.platform === 'tiktok') return `<p class="how warn">UNOFFICIAL and read-only. TikTok has no official chat API, so this uses a third-party package that can break or break TikTok's rules. Off by default. You can read TikTok chat here but not reply.</p>
    <label class="chk"><input id="tt-on" type="checkbox" ${s.tiktok_enabled ? 'checked' : ''}> Read my TikTok LIVE chat</label>
    <label>TikTok username<input id="tt-user" value="${esc(s.tiktok_user)}" placeholder="yourname"></label>
    <div class="act"><button class="p" data-act="save-tiktok">Save TikTok</button></div>`;
  return '';
}

function platformCard(c, setup) {
  const [cls, label] = STATE_TEXT[c.status] || ['off', c.status];
  const can = Object.entries(c.capabilities).filter(([, v]) => v).map(([k]) => k);
  const open = c.status === 'needs_auth' || c.status === 'disabled';
  return `<details class="pcard" ${open ? 'open' : ''}><summary><span class="dot ${c.status}"></span> <b>${esc(c.label)}</b>
    <span class="st ${cls}">${esc(label)}</span> ${c.official ? '' : '<span class="tag">UNOFFICIAL</span>'}
    ${can.includes('send') ? '' : '<span class="tag">read-only</span>'}</summary>
    ${c.detail ? `<p class="detail">${esc(c.detail)}</p>` : ''}${platformSetup(c, setup)}</details>`;
}

async function renderLauncher() {
  const [ws, pf, st, setup, ai] = await Promise.all([api('/api/windows'), api('/api/profiles'), api('/api/status'), api('/api/setup'), api('/api/ai')]);
  const s = setup.settings;
  const connected = st.connectors.filter(c => c.status === 'connected').length;
  const step = n => `<span class="n">${n}</span>`;
  $('#body').innerHTML = `<div class="launch">
  <div class="intro"><h2>PinguinoMulti</h2>
    <p>One place for all your live chats. It highlights messages that need an answer, tells you <i>why</i>, and remembers what you replied to. A reply always goes to <b>one</b> platform you choose, never to all of them.</p>
    <p class="mut">${connected ? `${connected} platform${connected > 1 ? 's' : ''} connected.` : 'No platform is connected yet - start with step 1.'} Hover the <span class="hlp">?</span> marks for help.</p></div>
  <div id="toast">${lastToast ? `<div class="${lastToast.ok ? 'tok' : 'tbad'}">${esc(lastToast.msg)}</div>` : ''}</div>

  <h3>${step(1)} Connect your platforms</h3>
  ${st.connectors.map(c => platformCard(c, setup)).join('')}
  <div class="act"><button data-act="checks">Test my setup</button> <small class="mut">Checks the site, sign-in and token without sending anything.</small></div><div id="checks"></div>

  <h3>${step(2)} Pick a layout ${T('', 'A layout opens a set of windows in one click. It replaces your current windows.')}</h3>
  <div class="grid">${pf.builtin.concat(pf.saved.filter(p => !pf.builtin.includes(p))).map(p =>
    `<button class="tile" data-p="${esc(p)}"><b>${esc(p)}</b><small>${esc(PROFILE_HELP[p] || 'Your saved layout.')}</small></button>`).join('')}</div>
  <div class="act"><button data-act="save-profile">Save my windows as a layout</button> <button data-act="restore">Reopen all my windows</button></div>

  <h3>${step(3)} Your windows ${T('', 'Each window can sit on any monitor. Positions are remembered.')}</h3>
  ${ws.length ? ws.map(w => `<div class="wrow"><b>${esc((WINDOW_HELP[w.type] || [w.type])[0])}</b> <small class="mut">${esc(w.link_group ? 'linked feed ' + w.link_group : '')}</small>
     <span class="grow"></span><button data-l="${w.id}">Open</button> <button data-x="${w.id}">Remove</button></div>`).join('') : '<div class="empty">No windows yet. Pick a layout above or add one below.</div>'}
  <div class="grid small">${Object.entries(WINDOW_HELP).map(([t, [n, d]]) => `<button class="tile" data-t="${t}"><b>+ ${esc(n)}</b><small>${esc(d)}</small></button>`).join('')}</div>

  <h3>Chat page and stream overlay</h3>
  <div class="box"><div><a href="/?type=chat" target="_self"><button class="p" type="button">Open the full Chat page</button></a>
    <small class="mut">All platforms in one feed with badges, emotes, search, pins and quick mod actions.</small></div>
    <div><a href="/?type=style"><button type="button">Customize the chat look</button></a> <small class="mut">Fonts, sizes, any background colour, and highlights for new chatters, subs, raids, cheers, mentions and more.</small></div>
    <b>Show chat on your stream (OBS) ${T('', 'Public chat only: no priority cards, notes, scores, reply box or muted viewers.')}</b>
    <small class="mut">In OBS: Sources &gt; + &gt; Browser, paste the address, set width 500 and height 800. Or Docks &gt; Custom Browser Docks. Change <code>size</code>, <code>max</code>, <code>platforms</code> in the address as you like; add <code>bots=show</code> to include bot replies.</small>
    <label>Address<input id="pop-url" readonly value="${esc(location.origin)}/popout?size=22&max=14" onclick="this.select()"></label>
    <div class="act"><button data-act="copy-pop">Copy address</button> <a href="/popout?size=22&max=14" target="_blank" rel="noopener"><button type="button">Preview</button></a></div></div>

  <h3>Sounds, look, split chat and pop-out</h3>
  <div class="box">These moved next to the chat so you can preview them live. Open the chat and press the <b>&#9881; Settings</b> button on the right edge.
    <div class="act"><a href="/?type=chat"><button class="p" type="button">Open the chat</button></a></div></div>

  <h3>Smart features</h3>
  <div class="box"><b>How messages are ranked ${T('', 'Local rules always work with no internet and no account. AI only double-checks borderline messages.')}</b>
    ${[['local', 'Local only', 'Free and instant. Explainable rules; nothing leaves your PC.'],
       ['auto', 'Local + AI when unsure', 'AI only checks borderline messages; any failure falls back to local.'],
       ['ai', 'AI assisted', 'Always lets AI refine borderline messages (still capped by cost).']].map(([v, n, d]) =>
      `<label class="chk"><input type="radio" name="mode" value="${v}" ${s.priority_mode === v ? 'checked' : ''}> <b>${n}</b> <small>${d}</small></label>`).join('')}
    <details ${s.priority_mode !== 'local' ? 'open' : ''}><summary>AI settings</summary>
      <label>Provider <select id="ai-prov">${['anthropic', 'openai', 'ollama'].map(p => `<option ${s.ai_provider === p ? 'selected' : ''}>${p}</option>`).join('')}</select></label>
      <label>Model<input id="ai-model" value="${esc(s.ai_model)}"></label>
      <label>API key ${setup.has.ai ? `<b class="okc">(${setup.sources.ai_key === 'vault' ? 'in the Suite key vault' : 'saved'})</b>` : ''}<input id="ai-key" type="password" autocomplete="off" placeholder="${setup.has.ai ? 'leave empty to keep' : 'not needed for ollama'}"></label>
      <label>Daily spend limit (USD)<input id="ai-cap" type="number" step="0.1" min="0" value="${s.ai_daily_cap_usd}"></label>
      <small class="mut">Today: ${ai.calls ?? 0} AI checks, about $${Number(ai.usd || 0).toFixed(3)}, ${ai.fallbacks ?? 0} fell back to local.</small>
    </details>
    <div class="act"><button class="p" data-act="save-smart">Save smart features</button></div></div>
  <div class="box"><label class="chk"><input id="voice" type="checkbox" ${s.voice_enabled ? 'checked' : ''}> <b>Suggest answered cards from my voice</b>
    <small>Uses PinguinoListen's transcript on this PC. It only <i>suggests</i> "looks like you answered this" - you confirm. No audio is stored.</small></label>
    <div class="act"><button data-act="save-voice">Save</button></div></div>
  <div class="box"><b>What I learned from your choices</b> <small class="mut">Small, capped nudges after at least 5 of your actions per rule.</small>
    <div class="act"><button data-act="learn">Show</button> <button data-act="learn-reset">Reset learning</button></div><div id="learn"></div></div>

  <h3>After the stream</h3>
  <div class="act"><button data-act="recap">Show messages I never answered</button></div><div id="recap"></div>

  <p class="mut keys">Shortcuts in a card window: <b>A</b> answered, <b>D</b> dismiss, <b>S</b> snooze. Hotkey URLs for Stream Deck: /api/hotkey/answer, /dismiss, /snooze.</p>
  </div>`;
}

let lastToast = null;
function toast(msg, ok = true) {
  lastToast = {msg, ok}; setTimeout(() => { lastToast = null; }, 8000);
  const t = $('#toast'); if (!t) return;
  t.innerHTML = `<div class="${ok ? 'tok' : 'tbad'}">${esc(msg)}</div>`;
}

async function saveSecret(path, body, okMsg) {
  const r = await fetch(path, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { toast(j.detail || 'Could not save', false); return false; }
  toast(okMsg); return true;
}

document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t || !(W.type === 'launcher' || t.closest('#sidep'))) return;
  const v = id => ($('#' + id) || {}).value || '';
  const a = t.dataset.act;
  try {
    if (t.dataset.p) { await api('/api/profiles/' + encodeURIComponent(t.dataset.p) + '/apply'); toast('Layout opened: ' + t.dataset.p); }
    else if (t.dataset.t) { const w = await api('/api/windows', {b: {type: t.dataset.t}}); await api('/api/windows/' + w.id + '/launch'); }
    else if (t.dataset.l) await api('/api/windows/' + t.dataset.l + '/launch');
    else if (t.dataset.x) await api('/api/windows/' + t.dataset.x, {m: 'DELETE'});
    else if (a === 'open-connect') { await api('/api/open-connect', {b: {}}); toast('Opened your browser. Log in as owner, then approve Twitch.'); return; }
    else if (a === 'disconnect') { await api('/auth/disconnect', {b: {}}); toast('Twitch disconnected.'); }
    else if (a === 'save-discord') {
      const chans = v('dc-chans').split(/[,\s]+/).filter(Boolean);
      const body = {channels: chans}; if (v('dc-token').trim()) body.token = v('dc-token').trim();
      if (!await saveSecret('/api/secrets/discord', body, 'Discord saved. It connects in a few seconds.')) return;
    }
    else if (a === 'clear-discord') { await saveSecret('/api/secrets/discord', {clear: true}, 'Discord token removed.'); }
    else if (a === 'save-youtube') { if (!await saveSecret('/api/secrets/youtube', {token: v('yt-token')}, 'YouTube token saved.')) return; }
    else if (a === 'clear-youtube') { await saveSecret('/api/secrets/youtube', {clear: true}, 'YouTube token removed.'); }
    else if (a === 'save-tiktok') { await api('/api/settings', {b: {tiktok_enabled: $('#tt-on').checked, tiktok_user: v('tt-user').replace('@', '').trim()}}); toast('TikTok settings saved.'); }
    else if (a === 'save-smart') {
      const mode = (document.querySelector('input[name=mode]:checked') || {}).value || 'local';
      await api('/api/settings', {b: {priority_mode: mode, ai_provider: v('ai-prov'), ai_model: v('ai-model').trim(), ai_daily_cap_usd: parseFloat(v('ai-cap')) || 0}});
      if (v('ai-key').trim()) { if (!await saveSecret('/api/secrets/ai', {key: v('ai-key').trim()}, 'Saved. Key stored in Windows Credential Manager.')) return; }
      else toast('Smart features saved.');
    }
    else if (a === 'save-voice') { await api('/api/settings', {b: {voice_enabled: $('#voice').checked}}); toast($('#voice').checked ? 'Voice suggestions on.' : 'Voice suggestions off.'); }
    else if (a === 'checks') { const box = $('#checks'); box.textContent = 'Checking...'; const r = await api('/api/checks');
      box.innerHTML = r.checks.map(c => `<div class="chk-row"><span class="dot ${c.ok ? 'connected' : 'error'}"></span> <b>${esc(c.label)}</b> ${esc(c.detail)}${c.ok ? '' : `<br><small>How to fix: ${esc(c.fix)}</small>`}</div>`).join(''); return; }
    else if (a === 'learn') { const r = await api('/api/learning'); const k = Object.keys(r.rules);
      $('#learn').innerHTML = k.map(n => { const x = r.rules[n]; return `<div>${esc(n)}: <b>${x.delta > 0 ? '+' : ''}${x.delta} pts</b> <small class="mut">(${x.n} actions${x.delta ? '' : ', not enough yet'})</small></div>`; }).join('') || '<div class="empty">Nothing learned yet.</div>'; return; }
    else if (a === 'learn-reset') { await api('/api/learning/reset', {b: {}}); toast('Learning reset to defaults.'); return; }
    else if (a === 'recap') { const r = await api('/api/recap');
      $('#recap').innerHTML = r.count ? r.cards.map(c => `<div class="wrow"><b>${esc(c.display || c.user)}</b> <span class="mut">${esc(c.platform || '')}</span> ${esc(c.text)}</div>`).join('') : '<div class="empty">Nothing unanswered. Nice.</div>'; return; }
    else if (a === 'ding-save' || a === 'ding-test') {
      const plats = ['twitch', 'youtube'].filter(p => $('#dg-' + p).checked);
      const r = await fetch('/api/ding/settings', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({platforms: plats, first_ever: $('#dg-first').checked,
        returning: $('#dg-returning').checked, scope: (document.querySelector('input[name=dg-scope]:checked') || {}).value || 'stream',
        sound: v('dg-sound'), first_sound: v('dg-fsound'), returning_sound: v('dg-rsound'), volume: parseInt(v('dg-vol')),
        returning_volume: parseInt(v('dg-rvol')), master_volume: parseInt(v('dg-mvol')), cooldown_s: parseFloat(v('dg-gap'))})});
      const j = await r.json().catch(() => ({})); if (!r.ok) { toast(j.detail || 'Could not save', false); return; }
      if (a === 'ding-test') { await fetch('/api/ding/test', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({kind: t.dataset.kind})}); toast('Playing the ' + t.dataset.kind + ' ding on this PC (settings saved)...'); return; }
      toast(plats.length ? 'Saved. Ding is ON for ' + plats.join(' and ') + '.' : 'Saved. Ding is off.'); }
    else if (a === 'pop-save' || a === 'pop-test') {
      const plats = ['twitch', 'youtube', 'discord'].filter(p => $('#pp-' + p).checked);
      const r = await fetch('/api/pop/settings', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({platforms: plats, own: $('#pp-own').checked,
        sound: v('pp-sound'), volume: {twitch: parseInt(v('pp-v-twitch')), youtube: parseInt(v('pp-v-youtube')), discord: parseInt(v('pp-v-discord'))},
        master_volume: parseInt(v('pp-mvol')), cooldown_s: parseFloat(v('pp-gap')), roles: [...document.querySelectorAll('.pp-role:checked')].map(x => x.value)})});
      const j = await r.json().catch(() => ({})); if (!r.ok) { toast(j.detail || 'Could not save', false); return; }
      if (a === 'pop-test') { await fetch('/api/pop/test', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({platform: t.dataset.platform})}); toast('Playing the ' + t.dataset.platform + ' pop on this PC (settings saved)...'); return; }
      toast(plats.length ? 'Saved. Chat pop is ON for ' + plats.join(', ') + '.' : 'Saved. Chat pop is off.'); }
    else if (a === 'ding-reset') { await api('/api/ding/reset', {b: {}}); toast('Cleared. Everyone counts as new again.'); }
    else if (a === 'ding-pick') { toast('A file window opened on this PC...'); const r = await api('/api/ding/pick', {b: {}}); if (r.path) $('#' + t.dataset.target).value = r.path; return; }
    else if (a === 'pop-chat') { const r = await popOut('chat-main', location.origin + '/?type=chat', 'Chat', {w: 520, h: 900, aot: aotPref()}); toast(r === 'blocked' ? 'The browser blocked the pop-up - allow pop-ups for this page.' : 'Chat opened in its own window.', r !== 'blocked'); return; }
    else if (a === 'pop-look') { const r = await popOut('look-editor', location.origin + '/?type=style', 'Chat look', {w: 1180, h: 860, aot: aotPref()}); toast(r === 'blocked' ? 'The browser blocked the pop-up - allow pop-ups for this page.' : 'Chat look opened in its own window.', r !== 'blocked'); return; }
    else if (a === 'split-looks') {
      for (const k of ['a', 'b']) {
        const g = id => $('#sl-' + k + '-' + id), look = {};
        if (g('size').value !== '') look.size = +g('size').value;
        if (g('bgA').value !== '') look.bgA = +g('bgA').value;
        if (g('bgon').checked) look.bg = g('bg').value;
        if (g('marker').value) look.marker = g('marker').value;
        if (g('timestamps').value !== '') look.timestamps = g('timestamps').value === '1';
        if (g('intensity').value !== '') look.intensity = +g('intensity').value;
        const r = await fetch('/api/panes/split-' + k, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({look})});
        if (!r.ok) { toast('Save a split first (press "Open split chat"), then set each half\'s look.', false); return; }
      }
      toast('Saved. Open split windows update right away.'); return; }
    else if (a === 'split-open' || a === 'split-close') {
      if (a === 'split-close') { ['pane-split-a', 'pane-split-b'].forEach(popClose); toast('Split chat closed.'); return; }
      const mode = $('#sp-mode').value, dir = $('#sp-dir').value, aot = $('#sp-aot').checked, plats = [...document.querySelectorAll('.sp-pl:checked')].map(x => x.value);
      try { localStorage.setItem('multi-aot', aot ? '1' : ''); } catch (x) { /* ignore */ }
      const r = await fetch('/api/splits/apply', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({mode, platforms: plats, aot})});
      const j = await r.json(); if (!r.ok) { toast(j.detail || 'Could not set up the split', false); return; }
      const fresh = !$('#sp-keep').checked;
      const res = await Promise.all([['a', $('#sp-a').value], ['b', $('#sp-b').value]].map(([k, mon]) =>
        popOut('pane-split-' + k, location.origin + '/?type=chat&pane=split-' + k, j.panes['split-' + k].name, {w: 560, h: 520, monitor: mon, fresh, aot})));
      toast(res.includes('blocked') ? 'The browser blocked a pop-up - allow pop-ups for this page, then press Open again.' : 'Opening the split chat...', !res.includes('blocked')); return; }
    else if (a === 'copy-pop') { const i = $('#pop-url'); i.select(); try { await navigator.clipboard.writeText(i.value); toast('Address copied.'); } catch (x) { document.execCommand('copy'); toast('Address selected - press Ctrl+C.'); } return; }
    else if (a === 'restore') await api('/api/windows/restore');
    else if (a === 'save-profile') { const n = prompt('Name this layout'); if (n) { await api('/api/profiles/' + encodeURIComponent(n) + '/save'); toast('Layout saved: ' + n); } }
    else return;
  } catch (err) { toast('Something went wrong: ' + err, false); return; }
  if (W.type === 'launcher') setTimeout(renderLauncher, 300); else if (typeof sideRender === 'function') setTimeout(sideRender, 300);
});

document.addEventListener('input', e => { const n = e.target.dataset && e.target.dataset.live; if (n && $('#' + n)) $('#' + n).textContent = e.target.value; });

// monitors come from the shell (01): parent.postMessage({pinguino:'window',op:'monitors'}) -> {pinguino:'monitors', monitors:[...]}
window.addEventListener('message', e => {
  const d = e.data; if (!d || d.pinguino !== 'monitors' || !Array.isArray(d.monitors)) return;
  const opts = d.monitors.map(m => `<option value="${m.index}">${esc(m.name || 'Monitor ' + m.index)} ${m.width}x${m.height}${m.primary ? ' (main)' : ''}</option>`).join('');
  ['sp-a', 'sp-b'].forEach((id, i) => { const el = $('#' + id); if (el) { el.innerHTML = opts; if (d.monitors[i]) el.value = d.monitors[i].index; } });
  const st = $('#sp-state'); if (st) st.textContent = d.monitors.length + ' monitor(s) found';
});
function askMonitors() { if (parent !== window) parent.postMessage({pinguino: 'window', op: 'monitors'}, '*'); }
const _rl = renderLauncher; renderLauncher = async function () { await _rl(); askMonitors(); };


// pop-out windows: real windows in the Pinguino app (shell, Unit 01), browser pop-ups otherwise. Position is remembered per label.
const POPS = {};
function aotPref() { try { return !!localStorage.getItem('multi-aot'); } catch (e) { return false; } }
async function popOut(label, url, title, o = {}) {
  let g = null; try { g = ((await api('/api/panes')).geom || {})[label]; } catch (e) { /* offline: use defaults */ }
  const u = url + (url.includes('?') ? '&' : '?') + 'pop=' + encodeURIComponent(label), aot = o.aot != null ? o.aot : aotPref();
  if (parent !== window) {
    parent.postMessage({pinguino: 'window', op: 'open', label, url: u, title, remember: true, always_on_top: !!aot, monitor: o.monitor,
      place: !g || o.fresh ? (o.monitor != null ? 'full' : undefined) : undefined, bounds: !o.fresh && g ? g : undefined, size: {w: o.w, h: o.h}}, '*');
    return 'app';
  }
  const w = g && !o.fresh ? g : {x: 80, y: 60, w: o.w || 520, h: o.h || 800};
  const ref = window.open(u, label, `popup=yes,left=${w.x},top=${w.y},width=${w.w},height=${w.h}`);
  if (ref) { POPS[label] = ref; return 'browser'; }
  return 'blocked';
}
function popClose(label) { if (parent !== window) parent.postMessage({pinguino: 'window', op: 'close', label}, '*'); else if (POPS[label]) POPS[label].close(); }
document.addEventListener('change', e => { if (e.target.id === 'sp-mode') { const pl = $('#sp-plats'); if (pl) pl.hidden = e.target.value !== 'platform'; } });

// Boxes shared by the chat page's settings panel (side.js). They used to live in Setup.
function dingBox(dg) { return `  <div class="box"><small class="mut">Plays on this PC only${dg.master ? '' : ' (this PC is not the master, so it stays silent)'}. Everything you change here is saved and remembered after Multi or the app closes.</small>
    <div class="row"><b>On for:</b> <label class="chk"><input type="checkbox" id="dg-twitch" ${dg.platforms.includes('twitch') ? 'checked' : ''}> Twitch</label>
      <label class="chk"><input type="checkbox" id="dg-youtube" ${dg.platforms.includes('youtube') ? 'checked' : ''}> YouTube</label></div>
    <div class="row"><label class="chk"><input type="radio" name="dg-scope" value="stream" ${dg.scope !== 'ever' ? 'checked' : ''}> New chatter: once per person <b>per stream</b></label>
      <label class="chk"><input type="radio" name="dg-scope" value="ever" ${dg.scope === 'ever' ? 'checked' : ''}> once per person <b>ever</b> (like the old Streamer.bot bell)</label></div>
    <b>New chatter ding</b>
    <label>Sound (.mp3 or .wav) ${dg.sound_exists ? '' : '<b class="tbadc">(file not found)</b>'}<span class="row"><input id="dg-sound" value="${esc(dg.sound)}" style="flex:1"><button data-act="ding-pick" data-target="dg-sound">Choose...</button><button data-act="ding-test" data-kind="new">Test</button></span></label>
    <label>Volume <span id="dg-vol-n">${dg.volume}</span>%<input id="dg-vol" type="range" min="0" max="100" value="${dg.volume}" data-live="dg-vol-n"></label>
    <label class="chk"><input type="checkbox" id="dg-returning" ${dg.returning ? 'checked' : ''}> <b>Different ding for a returning chatter</b> <small class="mut">someone who chatted in an earlier stream and chats again in this one</small></label>
    <label>Returning sound (empty = same sound)<span class="row"><input id="dg-rsound" value="${esc(dg.returning_sound)}" style="flex:1"><button data-act="ding-pick" data-target="dg-rsound">Choose...</button><button data-act="ding-test" data-kind="returning">Test</button></span></label>
    <label>Returning volume <span id="dg-rvol-n">${dg.returning_volume}</span>%<input id="dg-rvol" type="range" min="0" max="100" value="${dg.returning_volume}" data-live="dg-rvol-n"></label>
    <label class="chk"><input type="checkbox" id="dg-first" ${dg.first_ever ? 'checked' : ''}> Own sound for a Twitch viewer's very first message ever</label>
    <label>First-ever sound (empty = same as new)<span class="row"><input id="dg-fsound" value="${esc(dg.first_sound)}" style="flex:1"><button data-act="ding-pick" data-target="dg-fsound">Choose...</button><button data-act="ding-test" data-kind="first">Test</button></span></label>
    <label>Master volume <span id="dg-mvol-n">${dg.master_volume}</span>% <small class="mut">multiplies both volumes above</small><input id="dg-mvol" type="range" min="0" max="100" value="${dg.master_volume}" data-live="dg-mvol-n"></label>
    <label>At most one ding every (seconds)<input id="dg-gap" type="number" min="0.2" max="30" step="0.1" value="${dg.cooldown_s}" style="width:90px"></label>
    <div class="act"><button class="p" data-act="ding-save">Save</button> <button data-act="ding-reset">New stream (everyone counts as returning)</button></div>
    <small class="mut">${dg.chatters_this_stream} chatter(s) counted this stream, ${dg.known_chatters} known from earlier, ${dg.played} ding(s) played${dg.dropped ? ', ' + dg.dropped + ' skipped during bursts' : ''}.</small></div>`; }
function popBox(pp) { return `  <div class="box"><small class="mut">Like the Streamer.bot "chat" sound. Bots never pop. Plays on this PC only${pp.master ? '' : ' (this PC is not the master, so it stays silent)'}. Saved and remembered after Multi or the app closes.</small>
    <div class="row"><b>On for:</b>${['twitch', 'youtube', 'discord'].map(p => `<label class="chk"><input type="checkbox" id="pp-${p}" ${pp.platforms.includes(p) ? 'checked' : ''}> ${p[0].toUpperCase() + p.slice(1)}</label>`).join('')}
      <label class="chk"><input type="checkbox" id="pp-own" ${pp.own ? 'checked' : ''}> also my own messages</label></div>
    <div class="row"><b>Only for:</b>${[['mod', 'mods'], ['vip', 'VIPs'], ['sub', 'subscribers'], ['viewer', 'everyone else']].map(([r, t]) => `<label class="chk"><input type="checkbox" class="pp-role" value="${r}" ${(pp.roles || []).includes(r) ? 'checked' : ''}> ${t}</label>`).join('')}<small class="mut">none ticked = everyone</small></div>
    <label>Sound (.mp3 or .wav) ${pp.sound_exists ? '' : '<b class="tbadc">(file not found)</b>'}<span class="row"><input id="pp-sound" value="${esc(pp.sound)}" style="flex:1"><button data-act="ding-pick" data-target="pp-sound">Choose...</button></span></label>
    ${['twitch', 'youtube', 'discord'].map(p => `<label>${p[0].toUpperCase() + p.slice(1)} volume <span id="pp-v-${p}-n">${pp.volume[p]}</span>% <button data-act="pop-test" data-platform="${p}" style="margin-left:6px">Test</button><input id="pp-v-${p}" type="range" min="0" max="100" value="${pp.volume[p]}" data-live="pp-v-${p}-n"></label>`).join('')}
    <label>Master volume for all chat sounds (pop and dings) <span id="pp-mvol-n">${pp.master_volume}</span>%<input id="pp-mvol" type="range" min="0" max="100" value="${pp.master_volume}" data-live="pp-mvol-n"></label>
    <label>At most one pop every (seconds)<input id="pp-gap" type="number" min="0.1" max="10" step="0.05" value="${pp.cooldown_s}" style="width:90px"></label>
    <div class="act"><button class="p" data-act="pop-save">Save</button></div>
    <small class="mut">${pp.played} pop(s) played${pp.dropped ? ', ' + pp.dropped + ' skipped during bursts' : ''}.</small></div>`; }
function splitBox(pn) { return `  <div class="box"><small class="mut">Inside the Pinguino app these are real windows you can drag to any monitor; each one remembers where you left it. In a normal browser they open as pop-up windows.</small>
    <div class="act"><button class="p" data-act="pop-chat">Pop out the chat</button> <button data-act="pop-look">Pop out the look editor</button>
      <label class="chk"><input type="checkbox" id="sp-aot" ${aotPref() ? 'checked' : ''}> keep pop-outs on top of other windows</label> <small class="mut">(app only)</small></div>
    <h4>Split chat in half</h4>
    <div class="row"><label>How to split <select id="sp-mode">
      <option value="flow">One feed: newest in B, older rows continue in A</option><option value="platform">By platform</option>
      <option value="events">Chat in A, stream events in B</option><option value="people">Streamer, mods and VIPs in A, viewers in B</option></select></label>
      <span id="sp-plats" class="row" hidden><b>A shows:</b>${['twitch', 'youtube', 'discord', 'tiktok'].map(x => `<label class="chk"><input type="checkbox" class="sp-pl" value="${x}" ${x === 'twitch' ? 'checked' : ''}> ${x}</label>`).join('')}<small class="mut">B shows the rest</small></span></div>
    <div class="row"><label>A (top / left) on <select id="sp-a"></select></label><label>B (bottom / right) on <select id="sp-b"></select></label>
      <label>Layout <select id="sp-dir"><option value="top">stacked (A above B)</option><option value="left">side by side (A left of B)</option></select></label>
      <label class="chk"><input type="checkbox" id="sp-keep" checked> use remembered positions</label></div>
    <div class="act"><button class="p" data-act="split-open">Open split chat</button> <button data-act="split-close">Close split chat</button> <span id="sp-state" class="mut"></span></div>
    <details><summary>Each half's own look</summary><small class="mut">Leave a box empty to follow the main chat look. Full control over the main look: <a href="/?type=style">Chat look</a>.</small>
      ${['a', 'b'].map(k => { const lk = ((pn.panes['split-' + k] || {}).look) || {}; return `<div class="rule"><b>Half ${k.toUpperCase()}</b><div class="rg">
        <label class="cf">Text size <input type="number" id="sl-${k}-size" min="9" max="48" value="${lk.size ?? ''}" style="width:70px" placeholder="main"></label>
        <label class="cf">Background strength % <input type="number" id="sl-${k}-bgA" min="0" max="100" value="${lk.bgA ?? ''}" style="width:70px" placeholder="main"></label>
        <label class="cf">Background colour <input type="checkbox" id="sl-${k}-bgon" ${lk.bg ? 'checked' : ''}><input type="color" id="sl-${k}-bg" value="${lk.bg || '#09090a'}"></label>
        <label class="cf">Platform marker <select id="sl-${k}-marker"><option value="">main</option>${[['text', 'Word'], ['logo', 'Logo'], ['both', 'Both'], ['none', 'Nothing']].map(([v, t]) => `<option value="${v}" ${lk.marker === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label class="cf">Times <select id="sl-${k}-timestamps"><option value="">main</option><option value="1" ${lk.timestamps === true ? 'selected' : ''}>show</option><option value="0" ${lk.timestamps === false ? 'selected' : ''}>hide</option></select></label>
        <label class="cf">Highlight strength % <input type="number" id="sl-${k}-intensity" min="0" max="250" value="${lk.intensity ?? ''}" style="width:70px" placeholder="main"></label></div></div>`; }).join('')}
      <div class="act"><button data-act="split-looks">Save the halves' looks</button></div></details></div>`; }

// the shell reports why a window could not open (for example a refused address)
window.addEventListener('message', e => { const d = e.data; if (d && d.pinguino === 'window-error') toast('The app could not open that window: ' + (d.error || 'unknown error'), false); });
