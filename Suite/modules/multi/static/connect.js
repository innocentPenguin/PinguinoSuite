/* Kick + YouTube sign-in cards for the launcher (worker 42). Self-contained: watches #body and adds a box under the platform list.
   Ivan clicks "Sign in" and approves on the platform's own page; Multi only builds the link and receives the code. Secrets are never shown. */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const NAMES = {kick: 'Kick', youtube: 'YouTube'};
  const HELP = {
    kick: 'kick.com &rarr; Settings &rarr; Developer: create an app, set its redirect address to the one below, paste its client id and secret here. Lets Multi send chat, set the title and (later) receive Kick events.',
    youtube: 'Google Cloud: enable "YouTube Data API v3", publish the consent screen to <b>production</b> (otherwise the sign-in expires after 7 days), create an OAuth client of type <b>Desktop app</b>, paste its client id and secret here. <b>Reading chat needs no sign-in:</b> once the channel below is set, messages arrive in about 1-3 seconds. <b>The sign-in is the account that SENDS</b> (replies, moderation): sign in with the bot account (PinguinoB0t, a second Google account), not your own. It never changes which channel is read. Tip: do it in a private/incognito window while logged in as the bot.'
  };
  const j = (u, o) => fetch(u, o).then(r => r.json());
  const post = (u, b) => j(u, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(b || {})});

  function state(st) {
    if (st.signed_in) return 'Signed in' + (st.can_refresh ? ' (renews itself)' : ' (cannot renew: sign in again when it stops working)');
    if (!st.client_id_set || !st.client_secret_set) return 'Not set up: ' + [!st.client_id_set && 'client id', !st.client_secret_set && 'client secret'].filter(Boolean).join(' and ') + ' missing';
    return 'Ready: click Sign in';
  }

  const ready = st => !!(st.client_id_set && st.client_secret_set);
  const redirectFor = p => location.origin + '/auth/' + p + '/callback';     // what THIS Multi instance actually listens on

  // YouTube fast read (needs a backend whose /api/settings has youtube_channel; older backends keep only the sign-in card)
  async function ytRead() {
    try {
      const [cfg, stat] = await Promise.all([j('/api/settings'), j('/api/status').catch(() => ({}))]);
      if (!cfg || !('youtube_channel' in cfg)) return '';
      const c = ((stat && stat.connectors) || []).find(x => x.platform === 'youtube');
      return `<div class="c42-yt"><b>YouTube channel</b> <small class="mut c42-ytst">${c ? esc('Chat reading: ' + c.status + (c.detail ? ' - ' + c.detail : '')) : 'Chat reading: not started'}</small>
        <div><input class="c42-ch" aria-label="YouTube channel" placeholder="@yourhandle, channel id or youtube link" value="${esc(cfg.youtube_channel || '')}" size="34"></div>
        <div><input class="c42-vid" aria-label="YouTube live video id or link (optional)" placeholder="live video id or link (optional, only to pin one stream)" value="${esc(cfg.youtube_video_id || '')}" size="34">
          <button type="button" class="c42-ytsave">Save channel</button></div>
        <small class="mut">With the channel set, Multi reads your live chat in about 1-3 s without signing in. Leave the video box empty: Multi finds your current live stream by itself.</small></div>`;
    } catch (e) { return ''; }
  }

  async function sendAs() {
    try {
      const stat = await j('/api/status'), c = ((stat && stat.connectors) || []).find(x => x.platform === 'youtube');
      return c && c.send_as ? 'sending as: ' + c.send_as : 'sending as: nobody yet (not signed in)';
    } catch (e) { return 'sending as: unknown'; }
  }

  async function card(p) {
    const st = await j('/auth/' + p + '/status');
    const yt = p === 'youtube' ? await ytRead() : '';
    return `<div class="box conn42" data-p="${p}"><b>${NAMES[p]} sign-in</b> <small class="mut">${esc(state(st))}</small>
      <details><summary class="mut">How to set it up</summary><small class="mut">${HELP[p]}<br>Redirect address (saved when you click Save): <code>${esc(redirectFor(p))}</code>${st.redirect_uri && st.redirect_uri !== redirectFor(p) ? ' <b>currently set to ' + esc(st.redirect_uri) + '</b>' : ''}</small></details>
      <div><input class="c42-id" aria-label="${NAMES[p]} client id" placeholder="client id" autocomplete="off" size="26"> <input class="c42-sec" type="password" aria-label="${NAMES[p]} client secret" placeholder="client secret" autocomplete="new-password" size="20">
        <button type="button" class="c42-save">Save</button>
        <button type="button" class="c42-go p"${ready(st) ? '' : ' disabled title="Save the client id and secret first"'}>${p === 'youtube' ? 'Sign in the account that will SEND (use the bot)' : 'Sign in to ' + NAMES[p]}</button></div>
      ${p === 'youtube' ? '<div class="c42-sendas mut" aria-live="polite">' + esc(await sendAs()) + '</div>' : ''}
      <div class="c42-msg mut"></div>${yt}</div>`;
  }

  async function inject() {
    const body = document.getElementById('body');
    if (!body || !body.querySelector('.launch') || body.querySelector('.conn42-wrap')) return;
    const anchor = body.querySelector('.launch > .act');     // the "Test my setup" row, not a button inside a platform card
    if (!anchor) return;
    const wrap = document.createElement('div');
    wrap.className = 'conn42-wrap';
    wrap.innerHTML = (await card('kick')) + (await card('youtube'));
    if (body.querySelector('.conn42-wrap')) return;
    anchor.parentNode.insertBefore(wrap, anchor);
    wrap.addEventListener('click', async e => {
      const box = e.target.closest('.conn42'); if (!box) return;
      const p = box.dataset.p, msg = box.querySelector('.c42-msg');
      if (e.target.classList.contains('c42-ytsave')) {
        const r = await fetch('/api/settings', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({youtube_channel: box.querySelector('.c42-ch').value.trim(), youtube_video_id: box.querySelector('.c42-vid').value.trim()})});
        msg.textContent = r.ok ? 'Channel saved. Chat reading picks it up within a few seconds.' : 'Could not save the channel.';
        return;
      }
      if (e.target.classList.contains('c42-save')) {
        const id = box.querySelector('.c42-id').value, sec = box.querySelector('.c42-sec').value;
        if (!id && !sec) { msg.textContent = 'Type a client id and/or secret first.'; return; }
        await post('/auth/' + p + '/client', {client_id: id, client_secret: sec, redirect_uri: redirectFor(p)});
        box.querySelector('.c42-sec').value = '';
        msg.textContent = 'Saved.';
        const st = await j('/auth/' + p + '/status'); box.querySelector('small').textContent = state(st);
        const go = box.querySelector('.c42-go'); go.disabled = !ready(st); go.title = ready(st) ? '' : 'Save the client id and secret first';
      } else if (e.target.classList.contains('c42-go')) {
        const r = await post('/auth/' + p + '/start');
        if (!r.ok) { msg.textContent = r.error || 'Could not start.'; return; }
        msg.innerHTML = 'Opening ' + NAMES[p] + ' in a new tab. Approve there, then come back and reopen this page. <a target="_blank" rel="noopener" href="' + esc(r.url) + '">Open again</a>';
        window.open(r.url, '_blank', 'noopener');
      }
    });
  }

  // Pre-live check: one line per platform from the live connector status. Read-only, feature-detected (an old backend shows nothing).
  const PRE = ['twitch', 'tiktok', 'youtube'], PRE_NAME = {twitch: 'Twitch', tiktok: 'TikTok', youtube: 'YouTube'};
  const short = t => String(t || '').replace(/\s+/g, ' ').trim().slice(0, 70);
  function preLine(p, c, cfg) {
    const st = c ? c.status : '', d = short(c && c.detail);
    if (!c) return ['off', 'off'];
    if (st === 'disabled') return ['off', 'off'];
    const noHandle = p === 'tiktok' && cfg && cfg.tiktok_enabled && !String(cfg.tiktok_user || '').trim();
    const noYt = p === 'youtube' && cfg && 'youtube_channel' in cfg && !String(cfg.youtube_channel || '').trim() && !String(cfg.youtube_video_id || '').trim();
    if (p === 'tiktok' && (st === 'needs_setup' || noHandle)) return ['todo', 'not set (needs @handle)'];
    if (p === 'youtube' && (st === 'needs_setup' || (noYt && st !== 'connected'))) return ['todo', 'not set (needs channel or video id)'];
    if (st === 'connected') return ['ok', 'chat reading: ok'];
    if (st === 'waiting') return ['wait', 'waiting for live'];
    if (st === 'needs_auth') return ['todo', 'not set (' + (d || 'sign in needed') + ')'];
    if (st === 'connecting') return ['wait', 'connecting...'];
    return ['bad', 'reconnecting / problem' + (d ? ': ' + d : '')];
  }
  async function preHtml() {
    const [stat, cfg] = await Promise.all([j('/api/status').catch(() => null), j('/api/settings').catch(() => null)]);
    const list = stat && stat.connectors;
    if (!Array.isArray(list)) return '';
    const rows = PRE.map(p => {
      const c = list.find(x => x.platform === p), [k, t] = preLine(p, c, cfg);
      const mark = {ok: '&#10003;', wait: '&#8230;', todo: '!', bad: '&#10007;', off: '&ndash;'}[k];
      return `<li class="pre42-${k}"><span class="pre42-m" aria-hidden="true">${mark}</span><b>${PRE_NAME[p]}</b> <span>${esc(t)}</span></li>`;
    }).join('');
    return '<b>Before you go live</b> <small class="mut">updates by itself</small><ul class="pre42-l">' + rows + '</ul>';
  }
  function preStyle() {
    if (document.getElementById('pre42-css')) return;
    const st = document.createElement('style'); st.id = 'pre42-css';
    st.textContent = '.pre42{border:1px solid var(--line,#444);border-radius:8px;padding:8px 12px;margin:0 0 10px}.pre42-l{list-style:none;margin:6px 0 0;padding:0}.pre42-l li{padding:2px 0}'
      + '.pre42-m{display:inline-block;width:1.4em;font-weight:700}.pre42-ok .pre42-m{color:#3fb950}.pre42-wait .pre42-m{color:#d29922}.pre42-todo .pre42-m{color:#f0883e}.pre42-bad .pre42-m{color:#f85149}.pre42-off{opacity:.6}';
    document.head.appendChild(st);
  }
  async function preInject() {
    const body = document.getElementById('body');
    const root = body && body.querySelector('.launch');
    if (!root || root.querySelector('.pre42')) return;
    const h = await preHtml();
    if (!h || root.querySelector('.pre42')) return;
    preStyle();
    const box = document.createElement('div'); box.className = 'pre42'; box.setAttribute('aria-live', 'polite'); box.innerHTML = h;
    root.insertBefore(box, root.firstChild);
  }
  setInterval(async () => {
    const sa = document.querySelector('#body .c42-sendas');
    if (sa && !document.hidden) { try { const t = await sendAs(); if (sa.textContent !== t) sa.textContent = t; } catch (e) { /* keep */ } }
    const box = document.querySelector('#body .pre42');
    if (!box || document.hidden) return;
    try { const h = await preHtml(); if (h && box.isConnected && box.innerHTML !== h) box.innerHTML = h; } catch (e) { /* keep the last lines */ }
  }, 3000);
  window.__pre42 = {preLine};

  new MutationObserver(() => { inject().catch(() => {}); preInject().catch(() => {}); }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener('DOMContentLoaded', () => { inject().catch(() => {}); preInject().catch(() => {}); });
})();
