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
    <label>Bot token ${has.discord ? '<b class="okc">(saved)</b>' : ''}<input id="dc-token" type="password" autocomplete="off" placeholder="${has.discord ? 'leave empty to keep the saved token' : 'paste bot token'}"></label>
    <label>Channel IDs (comma separated)<input id="dc-chans" value="${esc((s.discord_channels || []).join(', '))}" placeholder="123456789012345678"></label>
    <div class="act"><button class="p" data-act="save-discord">Save Discord</button> ${has.discord ? '<button data-act="clear-discord">Forget token</button>' : ''}</div>`;
  if (c.platform === 'youtube') return `<p class="how">Paste a Google access token with the YouTube live-chat permission. Multi reads your active broadcast's chat. Tokens expire, so this needs re-pasting until automatic sign-in is added. Replies are plain messages (YouTube has no reply threads).</p>
    <label>Access token ${has.youtube ? '<b class="okc">(saved)</b>' : ''}<input id="yt-token" type="password" autocomplete="off" placeholder="paste token"></label>
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
    <b>Show chat on your stream (OBS) ${T('', 'Public chat only: no priority cards, notes, scores, reply box or muted viewers.')}</b>
    <small class="mut">In OBS: Sources &gt; + &gt; Browser, paste the address, set width 500 and height 800. Or Docks &gt; Custom Browser Docks. Change <code>size</code>, <code>max</code>, <code>platforms</code> in the address as you like; add <code>bots=show</code> to include bot replies.</small>
    <label>Address<input id="pop-url" readonly value="${esc(location.origin)}/popout?size=22&max=14" onclick="this.select()"></label>
    <div class="act"><button data-act="copy-pop">Copy address</button> <a href="/popout?size=22&max=14" target="_blank" rel="noopener"><button type="button">Preview</button></a></div></div>

  <h3>Smart features</h3>
  <div class="box"><b>How messages are ranked ${T('', 'Local rules always work with no internet and no account. AI only double-checks borderline messages.')}</b>
    ${[['local', 'Local only', 'Free and instant. Explainable rules; nothing leaves your PC.'],
       ['auto', 'Local + AI when unsure', 'AI only checks borderline messages; any failure falls back to local.'],
       ['ai', 'AI assisted', 'Always lets AI refine borderline messages (still capped by cost).']].map(([v, n, d]) =>
      `<label class="chk"><input type="radio" name="mode" value="${v}" ${s.priority_mode === v ? 'checked' : ''}> <b>${n}</b> <small>${d}</small></label>`).join('')}
    <details ${s.priority_mode !== 'local' ? 'open' : ''}><summary>AI settings</summary>
      <label>Provider <select id="ai-prov">${['anthropic', 'openai', 'ollama'].map(p => `<option ${s.ai_provider === p ? 'selected' : ''}>${p}</option>`).join('')}</select></label>
      <label>Model<input id="ai-model" value="${esc(s.ai_model)}"></label>
      <label>API key ${setup.has.ai ? '<b class="okc">(saved)</b>' : ''}<input id="ai-key" type="password" autocomplete="off" placeholder="${setup.has.ai ? 'leave empty to keep' : 'not needed for ollama'}"></label>
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
  const t = e.target.closest('button'); if (!t || W.type !== 'launcher') return;
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
    else if (a === 'copy-pop') { const i = $('#pop-url'); i.select(); try { await navigator.clipboard.writeText(i.value); toast('Address copied.'); } catch (x) { document.execCommand('copy'); toast('Address selected - press Ctrl+C.'); } return; }
    else if (a === 'restore') await api('/api/windows/restore');
    else if (a === 'save-profile') { const n = prompt('Name this layout'); if (n) { await api('/api/profiles/' + encodeURIComponent(n) + '/save'); toast('Layout saved: ' + n); } }
    else return;
  } catch (err) { toast('Something went wrong: ' + err, false); return; }
  setTimeout(renderLauncher, 300);
});
