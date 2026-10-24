/* Kick + YouTube sign-in cards for the launcher (worker 42). Self-contained: watches #body and adds a box under the platform list.
   Ivan clicks "Sign in" and approves on the platform's own page; Multi only builds the link and receives the code. Secrets are never shown. */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const NAMES = {kick: 'Kick', youtube: 'YouTube'};
  const HELP = {
    kick: 'kick.com &rarr; Settings &rarr; Developer: create an app, set its redirect address to the one below, paste its client id and secret here. Lets Multi send chat, set the title and (later) receive Kick events.',
    youtube: 'Google Cloud: enable "YouTube Data API v3", publish the consent screen to <b>production</b> (otherwise the sign-in expires after 7 days), create an OAuth client of type <b>Desktop app</b>, paste its client id and secret here. <b>Reading chat needs no sign-in:</b> once the channel above is set, messages arrive in about 1-3 seconds. Signing in is only for sending chat and moderating (the official API), or as a fallback if the fast read stops working.'
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

  async function card(p) {
    const st = await j('/auth/' + p + '/status');
    const yt = p === 'youtube' ? await ytRead() : '';
    return `<div class="box conn42" data-p="${p}"><b>${NAMES[p]} sign-in</b> <small class="mut">${esc(state(st))}</small>
      <details><summary class="mut">How to set it up</summary><small class="mut">${HELP[p]}<br>Redirect address (saved when you click Save): <code>${esc(redirectFor(p))}</code>${st.redirect_uri && st.redirect_uri !== redirectFor(p) ? ' <b>currently set to ' + esc(st.redirect_uri) + '</b>' : ''}</small></details>
      <div><input class="c42-id" aria-label="${NAMES[p]} client id" placeholder="client id" autocomplete="off" size="26"> <input class="c42-sec" type="password" aria-label="${NAMES[p]} client secret" placeholder="client secret" autocomplete="new-password" size="20">
        <button type="button" class="c42-save">Save</button>
        <button type="button" class="c42-go p"${ready(st) ? '' : ' disabled title="Save the client id and secret first"'}>Sign in to ${NAMES[p]}</button></div>
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

  new MutationObserver(() => { inject().catch(() => {}); }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener('DOMContentLoaded', () => inject().catch(() => {}));
})();
