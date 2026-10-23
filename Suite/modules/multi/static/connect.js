/* Kick + YouTube sign-in cards for the launcher (worker 42). Self-contained: watches #body and adds a box under the platform list.
   Ivan clicks "Sign in" and approves on the platform's own page; Multi only builds the link and receives the code. Secrets are never shown. */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const NAMES = {kick: 'Kick', youtube: 'YouTube'};
  const HELP = {
    kick: 'kick.com &rarr; Settings &rarr; Developer: create an app, set its redirect address to the one below, paste its client id and secret here. Lets Multi send chat, set the title and (later) receive Kick events.',
    youtube: 'Google Cloud: enable "YouTube Data API v3", publish the consent screen to <b>production</b> (otherwise the sign-in expires after 7 days), create an OAuth client of type <b>Desktop app</b>, paste its client id and secret here. Chat is read at most every 10 s to stay inside the daily quota.'
  };
  const j = (u, o) => fetch(u, o).then(r => r.json());
  const post = (u, b) => j(u, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(b || {})});

  function state(st) {
    if (st.signed_in) return 'Signed in' + (st.can_refresh ? ' (renews itself)' : ' (cannot renew: sign in again when it stops working)');
    if (!st.client_id_set || !st.client_secret_set) return 'Not set up: ' + [!st.client_id_set && 'client id', !st.client_secret_set && 'client secret'].filter(Boolean).join(' and ') + ' missing';
    return 'Ready: click Sign in';
  }

  async function card(p) {
    const st = await j('/auth/' + p + '/status');
    return `<div class="box conn42" data-p="${p}"><b>${NAMES[p]} sign-in</b> <small class="mut">${esc(state(st))}</small>
      <details><summary class="mut">How to set it up</summary><small class="mut">${HELP[p]}<br>Redirect address: <code>${esc(st.redirect_uri || '')}</code></small></details>
      <div><input class="c42-id" placeholder="client id" autocomplete="off" size="26"> <input class="c42-sec" type="password" placeholder="client secret" autocomplete="new-password" size="20">
        <button type="button" class="c42-save">Save</button>
        <button type="button" class="c42-go p">Sign in to ${NAMES[p]}</button></div>
      <div class="c42-msg mut"></div></div>`;
  }

  async function inject() {
    const body = document.getElementById('body');
    if (!body || !body.querySelector('.launch') || body.querySelector('.conn42-wrap')) return;
    const anchor = body.querySelector('.act');
    if (!anchor) return;
    const wrap = document.createElement('div');
    wrap.className = 'conn42-wrap';
    wrap.innerHTML = (await card('kick')) + (await card('youtube'));
    if (body.querySelector('.conn42-wrap')) return;
    anchor.parentNode.insertBefore(wrap, anchor);
    wrap.addEventListener('click', async e => {
      const box = e.target.closest('.conn42'); if (!box) return;
      const p = box.dataset.p, msg = box.querySelector('.c42-msg');
      if (e.target.classList.contains('c42-save')) {
        const id = box.querySelector('.c42-id').value, sec = box.querySelector('.c42-sec').value;
        if (!id && !sec) { msg.textContent = 'Type a client id and/or secret first.'; return; }
        await post('/auth/' + p + '/client', {client_id: id, client_secret: sec});
        box.querySelector('.c42-sec').value = '';
        msg.textContent = 'Saved.';
        const st = await j('/auth/' + p + '/status'); box.querySelector('small').textContent = state(st);
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
