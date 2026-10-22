/* Chat comfort: AUTO scroll pill + hotkey, up/down hold-scroll buttons (double-tap-hold sprint), follow / welcome-back quick card.
   Loaded after chat.js. State: window.AUTO (false = autoscroll paused). chat.js / dash.js check `window.AUTO !== false`. */
(function () {
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } },
  };
  window.AUTO = ls.get('multi-auto', '1') !== '0';
  let hotkey = ls.get('multi-autokey', 'Alt+S');
  const FEEDS = ['#cfeed', '#d-l-chat', '#d-l-chat-a', '#d-l-chat-b', '#feed'];
  const feeds = () => FEEDS.map(s => document.querySelector(s)).filter(el => el && el.offsetParent !== null && el.clientHeight > 40);
  const atEnd = f => f.scrollTop + f.clientHeight >= f.scrollHeight - 40;

  const css = document.createElement('style');
  css.textContent = `
.cux{position:fixed;z-index:50;display:flex;flex-direction:column;gap:4px;align-items:flex-end;pointer-events:none}
.cux>*{pointer-events:auto}
.cux .pill{font:700 10px/1 system-ui,sans-serif;letter-spacing:.08em;padding:4px 8px;border-radius:99px;cursor:pointer;user-select:none;border:1px solid #5a3a14;background:#1a1208;color:#8a6a40;opacity:.8}
.cux .pill.on{background:#ff8a1f;color:#1a1208;border-color:#ff8a1f;opacity:1}
.cux button.sc{width:28px;height:28px;border-radius:50%;border:1px solid #5a3a14;background:#1a1208cc;color:#ff8a1f;font-size:13px;line-height:1;cursor:pointer;touch-action:none;user-select:none;padding:0}
.cux button.sc.hot{background:#ff8a1f;color:#1a1208}
.cux-card{position:fixed;z-index:60;left:50%;transform:translate(-50%,-12px);top:10px;min-width:220px;max-width:min(92vw,360px);padding:8px 14px;border-radius:10px;background:#1a1208f2;border:1px solid #ff8a1f;box-shadow:0 4px 18px #0009;color:#ffe9cc;font:13px/1.35 system-ui,sans-serif;opacity:0;transition:opacity .25s,transform .25s;pointer-events:none}
.cux-card.show{opacity:1;transform:translate(-50%,0)}
.cux-card b{font-size:15px}.cux-card .k{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#ff8a1f;font-weight:700}
.cux-card .s{color:#c9a577;font-size:12px}`;
  document.head.appendChild(css);

  // ---- overlays per feed
  const boxes = new Map();
  function ensureBox(f) {
    let b = boxes.get(f);
    if (b) return b;
    b = document.createElement('div'); b.className = 'cux';
    b.innerHTML = `<span class="pill" title="Autoscroll. Click or press the hotkey to toggle; right-click to change the hotkey">AUTO</span><button class="sc" data-d="-1" title="Scroll up (hold to keep going, tap-tap-hold to sprint)">&#9650;</button><button class="sc" data-d="1" title="Scroll down (hold to keep going, tap-tap-hold to sprint)">&#9660;</button>`;
    document.body.appendChild(b);
    b.querySelector('.pill').addEventListener('click', () => setAuto(!window.AUTO, true));
    b.querySelector('.pill').addEventListener('contextmenu', e => { e.preventDefault(); rebind(); });
    b.querySelectorAll('.sc').forEach(btn => holdScroll(btn, f, +btn.dataset.d));
    boxes.set(f, b);
    return b;
  }
  function layout() {
    const live = new Set(feeds());
    for (const [f, b] of boxes) if (!live.has(f) || !document.body.contains(f)) { b.remove(); boxes.delete(f); }
    live.forEach(f => {
      const b = ensureBox(f), r = f.getBoundingClientRect();
      b.style.left = Math.max(0, r.right - b.offsetWidth - 14) + 'px';
      b.style.top = Math.max(0, r.bottom - b.offsetHeight - 10) + 'px';
      const pill = b.querySelector('.pill'), eff = window.AUTO && atEnd(f);
      pill.classList.toggle('on', eff);
      pill.title = window.AUTO ? (eff ? 'Autoscroll on' : 'Autoscroll paused: you scrolled up. Scroll to the bottom to resume') : 'Autoscroll off. Click or press ' + hotkey;
    });
  }
  function setAuto(on, jump) {
    window.AUTO = on; ls.set('multi-auto', on ? '1' : '0');
    if (on && jump) feeds().forEach(f => { f.scrollTop = f.scrollHeight; });
    layout();
  }

  // ---- hotkey
  const keyName = e => (e.ctrlKey ? 'Ctrl+' : '') + (e.altKey ? 'Alt+' : '') + (e.shiftKey ? 'Shift+' : '') + (e.key.length === 1 ? e.key.toUpperCase() : e.key);
  let binding = false;
  function rebind() {
    binding = true;
    const t = document.createElement('div'); t.className = 'cux-card show'; t.innerHTML = '<span class="k">Autoscroll hotkey</span><br>Press the new key combination (Esc to cancel)'; document.body.appendChild(t);
    const done = () => { binding = false; t.remove(); };
    const h = e => {
      if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return;
      e.preventDefault(); e.stopPropagation(); document.removeEventListener('keydown', h, true);
      if (e.key !== 'Escape') { hotkey = keyName(e); ls.set('multi-autokey', hotkey); }
      done(); layout();
    };
    document.addEventListener('keydown', h, true);
  }
  document.addEventListener('keydown', e => {
    if (binding || ['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '') || (e.target && e.target.isContentEditable);
    if (typing && !(e.ctrlKey || e.altKey)) return;
    if (keyName(e) === hotkey) { e.preventDefault(); setAuto(!window.AUTO, true); }
  });

  // ---- hold-to-scroll with sprint
  const BASE = 600, SPRINT = 3.5, RAMP = 600, HOLD_MS = 180, DOUBLE_MS = 350;
  function holdScroll(btn, f, dir) {
    let raf = 0, t0 = 0, sprint = false, last = 0, holdTimer = 0, lastDown = 0, moved = false;
    const step = () => {
      const ts = performance.now();
      const dt = Math.min(50, ts - last) / 1000; last = ts;
      let v = BASE;
      if (sprint) { const k = Math.min(1, (ts - t0) / RAMP); v = BASE * (1 + (SPRINT - 1) * k * k * (3 - 2 * k)); }   // smoothstep ease-in
      const before = f.scrollTop; f.scrollTop += dir * v * dt; if (f.scrollTop !== before) moved = true;
    };
    const stop = () => { clearTimeout(holdTimer); clearInterval(raf); raf = 0; btn.classList.remove('hot'); };
    btn.addEventListener('pointerdown', e => {
      e.preventDefault(); try { btn.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ }
      const now = performance.now(); sprint = now - lastDown < DOUBLE_MS; lastDown = now; moved = false;
      btn.classList.add('hot');
      holdTimer = setTimeout(() => { t0 = last = performance.now(); raf = setInterval(step, 16); }, sprint ? 0 : HOLD_MS);
    });
    const up = () => {
      const held = raf !== 0; stop();
      if (!held) f.scrollBy({ top: dir * Math.round(f.clientHeight * 0.4), behavior: 'smooth' });   // plain tap = one step
    };
    btn.addEventListener('pointerup', up); btn.addEventListener('pointercancel', stop); btn.addEventListener('lostpointercapture', stop);
    btn.addEventListener('contextmenu', e => e.preventDefault());
  }

  // ---- follow / welcome-back card
  const queue = []; let showing = false, lastShown = 0;
  const MIN_GAP = 1200, SHOW_MS = 5200, MAX_QUEUE = 6;
  const ago = ts => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 3600 ? Math.max(1, Math.round(s / 60)) + ' min ago' : s < 86400 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago'; };
  window.cardFollow = function (m) {
    if (!m || m.event !== 'follow') return;
    if (ls.get('multi-followcard', '1') === '0') return;
    if (queue.some(q => q.user_id === m.user_id && q.platform === m.platform)) return;      // same person twice in the queue
    if (queue.length >= MAX_QUEUE) queue.shift();
    queue.push(m); pump();
  };
  async function pump() {
    if (showing || !queue.length) return;
    showing = true;
    const m = queue.shift(), re = !!(m.flags && m.flags.includes('refollow'));
    let info = null;
    try { const r = await fetch(`/api/chatter/${encodeURIComponent(m.platform)}/${encodeURIComponent(m.user_id)}`); if (r.ok) info = await r.json(); } catch (e) { /* offline */ }
    const col = (info && info.color) || (typeof colourOf === 'function' ? colourOf(m) : '') || '#ff8a1f';
    const stat = [];
    if (info && info.last_seen) stat.push('last seen ' + ago(info.last_seen));
    if (info && info.messages) stat.push(info.messages + ' msgs');
    if (info && info.first_seen && !stat.length) stat.push('here since ' + new Date(info.first_seen * 1000).toLocaleDateString());
    const esc2 = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const card = document.createElement('div'); card.className = 'cux-card';
    card.innerHTML = `<span class="k">${re ? 'welcome back' : 'followed'}</span><br><b style="color:${/^#[0-9a-f]{3,8}$/i.test(col) ? col : '#ff8a1f'}">${esc2(m.display || m.user)}</b>${stat.length ? `<br><span class="s">${esc2(stat.join(' · '))}</span>` : ''}`;
    document.body.appendChild(card);
    setTimeout(() => card.classList.add("show"), 20);
    setTimeout(() => { card.classList.remove('show'); setTimeout(() => { card.remove(); showing = false; lastShown = Date.now(); setTimeout(pump, MIN_GAP); }, 300); }, SHOW_MS);
  }

  setInterval(layout, 500);
  window.addEventListener('resize', layout);
  window.chatUx = { setAuto, layout, hotkey: () => hotkey };
})();
