// Local-only chat sounds, played by THIS page in the browser (never through OBS, so the stream cannot hear them).
// Settings live on the Multi server (/api/sounds, survive restarts) with a localStorage copy as fallback. One window plays at a time (leader lock),
// so a chat window and a dashboard open together do not double up. Globals used: $, esc, W, isBot, mentionsMe, isQuestionForMe (chat.js).
const SND_EVENTS = [
  ['person', 'Message from a real person (real people only)', 'Any viewer message. Never bots (Nightbot, StreamElements, Chatty, Helper, anything ending in bot/b0t, your bot list), never you or your own accounts.'],
  ['sent', 'A message I (or a bot of mine) sent', 'Plays when your own line appears in chat. Off by default.'],
  ['first', 'First-time chatter (real people only)', 'Someone chats here for the very first time (Twitch first-message flag, or never seen by Multi before).'],
  ['returning', 'Returning chatter (real people only)', 'Someone known from before who is back after a long absence (Multi has not seen them for the "new stream" gap, 6 h by default). Replaces the normal chat sound for that message.'],
  ['mention', 'Someone mentions me', 'Your name / channel is in a message.'],
  ['question', 'Question or priority for me', 'A question to you, a reply to you, a cheer, or a high-priority card.'],
  ['follow', 'New follow', 'Stream event (also shown in the activity feed).'],
  ['sub', 'Sub, resub or gift', ''],
  ['raid', 'Raid', ''],
];
const SND_TONES = ['chime', 'ping', 'soft', 'pop', 'bell', 'blip', 'coin', 'drum', 'harp', 'alert', 'droplet', 'sparkle'];
const SND_DEFAULT = {
  v: 2, master: 70, gap: 2,
  ev: {
    person: {on: true, vol: 80, tone: 'pop', notify: false}, sent: {on: false, vol: 60, tone: 'blip', notify: false}, first: {on: true, vol: 90, tone: 'harp', notify: true}, returning: {on: true, vol: 85, tone: 'chime', notify: false}, mention: {on: true, vol: 90, tone: 'bell', notify: true},
    question: {on: true, vol: 90, tone: 'alert', notify: true},
    follow: {on: false, vol: 70, tone: 'ping', notify: false}, sub: {on: false, vol: 80, tone: 'sparkle', notify: false}, raid: {on: false, vol: 80, tone: 'coin', notify: false},
  },
};
// tone = list of [frequency Hz, start s, length s, wave]; synthesised, no files
const SND_NOTES = {
  chime: [[880, 0, .25, 'sine'], [1320, .12, .45, 'sine']], ping: [[1568, 0, .3, 'sine']], soft: [[523, 0, .4, 'triangle'], [659, .1, .4, 'triangle']],
  pop: [[300, 0, .08, 'square'], [600, .03, .06, 'sine']], bell: [[1047, 0, .7, 'sine'], [1568, 0, .5, 'sine'], [2093, 0, .3, 'sine']], blip: [[740, 0, .07, 'square'], [988, .07, .07, 'square']],
  coin: [[988, 0, .08, 'square'], [1319, .08, .5, 'square']], drum: [[110, 0, .25, 'sine'], [80, .02, .3, 'sine']], harp: [[523, 0, .5, 'triangle'], [659, .1, .5, 'triangle'], [784, .2, .5, 'triangle'], [1047, .3, .7, 'triangle']],
  alert: [[880, 0, .15, 'sawtooth'], [660, .18, .15, 'sawtooth'], [880, .36, .2, 'sawtooth']], droplet: [[1200, 0, .12, 'sine'], [700, .05, .2, 'sine']],
  sparkle: [[1568, 0, .12, 'sine'], [2093, .08, .12, 'sine'], [2637, .16, .3, 'sine']],
};
const SND = {cfg: JSON.parse(JSON.stringify(SND_DEFAULT)), ctx: null, last: {}, id: Math.random().toString(36).slice(2), loaded: false, saveT: null, lead: false};

function sndMerge(src) {
  const c = JSON.parse(JSON.stringify(SND_DEFAULT));
  if (!src || typeof src !== 'object') return c;
  const n = (v, lo, hi, d) => { v = Number(v); return Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d; };
  c.master = n(src.master, 0, 100, c.master); c.gap = n(src.gap, 0, 60, c.gap);
  if ((src.v || 1) < 2) { c.migrated = true; return c; }        // one-time migration: v1 saved prefs (sent on, chat off) get the v2 defaults: real people on, sent off, 2 s gap
  c.migrated = false;
  for (const [k] of SND_EVENTS) {
    const s = (src.ev || {})[k] || {}, d = c.ev[k];
    d.on = s.on == null ? d.on : !!s.on; d.vol = n(s.vol, 0, 100, d.vol); d.notify = s.notify == null ? d.notify : !!s.notify;
    d.tone = SND_TONES.includes(s.tone) ? s.tone : d.tone;
  }
  return c;
}
async function sndLoad() {
  try { SND.cfg = sndMerge(JSON.parse(localStorage.getItem('multi-snd') || 'null')); } catch (e) { /* storage may be blocked */ }
  try { const r = await fetch('/api/sounds'); if (r.ok) SND.cfg = sndMerge((await r.json()).config); } catch (e) { /* server copy unavailable: keep local */ }
  if (SND.cfg.migrated) { delete SND.cfg.migrated; sndSave(); }
  SND.loaded = true;
}
function sndSave() {
  try { localStorage.setItem('multi-snd', JSON.stringify(SND.cfg)); } catch (e) { /* ignore */ }
  clearTimeout(SND.saveT);
  SND.saveT = setTimeout(() => fetch('/api/sounds', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({config: SND.cfg})}).catch(() => {}), 400);
}
// browsers block audio until the page got a click or key press: unlock on the first one
function sndCtx() {
  if (!SND.ctx) { try { SND.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return null; } }
  if (SND.ctx.state === 'suspended') SND.ctx.resume().catch(() => {});
  return SND.ctx;
}
['pointerdown', 'keydown', 'touchstart'].forEach(t => window.addEventListener(t, () => { sndCtx(); sndBanner(); }, {passive: true}));
function sndLocked() { return !SND.ctx || SND.ctx.state !== 'running'; }
function sndPlay(tone, vol, force) {
  const ctx = sndCtx(); if (!ctx || ctx.state !== 'running') return false;
  const g = (SND.cfg.master / 100) * (vol / 100); if (g <= 0) return true;
  const t0 = ctx.currentTime + .01;
  for (const [f, st, len, wave] of SND_NOTES[tone] || SND_NOTES.chime) {
    const o = ctx.createOscillator(), a = ctx.createGain();
    o.type = wave; o.frequency.value = f;
    a.gain.setValueAtTime(0, t0 + st); a.gain.linearRampToValueAtTime(.35 * g, t0 + st + .01); a.gain.exponentialRampToValueAtTime(.0001, t0 + st + len);
    o.connect(a); a.connect(ctx.destination); o.start(t0 + st); o.stop(t0 + st + len + .05);
  }
  return true;
}
// only one open Multi window makes the sound
function sndLeader() {
  try {
    const now = Date.now(), cur = JSON.parse(localStorage.getItem('multi-snd-lead') || 'null');
    if (!cur || cur.id === SND.id || now - cur.t > 3000) { localStorage.setItem('multi-snd-lead', JSON.stringify({id: SND.id, t: now})); return true; }
    return false;
  } catch (e) { return true; }
}
setInterval(() => { SND.lead = sndLeader(); }, 1000);
function sndNotify(title, body) {
  try { if ('Notification' in window && Notification.permission === 'granted') new Notification(title, {body: String(body || '').slice(0, 140), silent: true}); } catch (e) { /* ignore */ }
}
function sndFire(key, m) {
  const e = SND.cfg.ev[key]; if (!e || !e.on && !e.notify) return false;
  const now = Date.now(), gap = (['person', 'first', 'returning'].includes(key) ? SND.cfg.gap : .4) * 1000;
  if (gap && now - (SND.last[key] || 0) < gap) return false;
  SND.last[key] = now;
  if (e.on) sndPlay(e.tone, e.vol);
  if (e.notify) sndNotify(({first: 'First-time chatter', returning: 'Returning chatter', mention: 'Mention', question: 'For you', sent: 'Sent', person: 'Chat', follow: 'New follow', sub: 'New sub', raid: 'Raid'})[key], (m.display || m.user || '') + (m.text ? ': ' + m.text : ''));
  return true;
}
// a real person: not a bot (flag, your bot list, known bot names, *bot / *b0t), not the streamer, not one of your own accounts
const SND_BOTS = /(^|_)(b[o0]t|chatty|helper)$|b[o0]t$|^(nightbot|streamelements|streamlabs|moobot|fossabot|wizebot|pinguino\w*)$/;
function sndHuman(m) {
  const u = String(m.user || '').toLowerCase();
  if (!u || isBot(m) || m.is_self || SND_BOTS.test(u) || MYNAMES.has(u)) return false;
  return !(m.badges || []).includes('broadcaster');
}
// called for every LIVE message (index.html on()); history loaded at start never calls this
window.soundMsg = function (m) {
  if (!SND.loaded || !m || !SND.lead || !['chat', 'dash', 'popout'].includes(W.type)) return;
  if (m.event) { if (['follow', 'sub', 'resub', 'gift', 'raid'].includes(m.event)) sndFire(m.event === 'resub' || m.event === 'gift' ? 'sub' : m.event, m); else if (m.event === 'cheer') sndFire('question', m); return; }
  if (m.is_self) { sndFire('sent', m); return; }
  if (!sndHuman(m)) return;
  const fl = m.flags || [], isNew = m.first_time || fl.includes('new');
  if (isNew && SND.cfg.ev.first.on) { sndFire('first', m); return; }          // first / returning own the message: no second sound on top of it
  if (fl.includes('returning') && SND.cfg.ev.returning.on) { sndFire('returning', m); return; }
  if (isNew && sndFire('first', m)) return;                                    // notification-only setting
  if (fl.includes('returning') && sndFire('returning', m)) return;
  if (mentionsMe(m) && sndFire('mention', m)) return;
  if ((isQuestionForMe(m) || m.tier === 'high') && sndFire('question', m)) return;
  sndFire('person', m);
};
function sndBanner() {
  const b = $('#snd-lock'); if (b) b.style.display = sndLocked() ? '' : 'none';
}
function soundsBox() {
  const c = SND.cfg, notifyState = 'Notification' in window ? Notification.permission : 'unsupported';
  const row = ([k, label, hint]) => {
    const e = c.ev[k];
    return `<div class="cf" style="flex-wrap:wrap;gap:6px;align-items:center;border-top:1px solid var(--line);padding-top:6px" title="${esc(hint)}">
      <label style="min-width:170px"><input type="checkbox" data-snd="${k}.on" ${e.on ? 'checked' : ''}> <b>${esc(label)}</b></label>
      <select data-snd="${k}.tone">${SND_TONES.map(t => `<option ${e.tone === t ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <input type="range" data-snd="${k}.vol" min="0" max="100" step="5" value="${e.vol}" style="width:90px" title="Volume for this sound"><span class="mut" style="width:34px">${e.vol}%</span>
      <button class="chip2" data-snd-test="${k}">Test</button>
      <label class="mut"><input type="checkbox" data-snd="${k}.notify" ${e.notify ? 'checked' : ''}> notification</label>
      ${hint ? `<small class="mut" style="flex-basis:100%">${esc(hint)}</small>` : ''}</div>`;
  };
  return `<div class="box"><small class="mut">Plays from this page on this PC only, <b>never in OBS</b>. Saved automatically. One open Multi window plays at a time.</small>
    <div id="snd-lock" class="empty" style="display:${sndLocked() ? '' : 'none'}">Sound is asleep until you click anywhere in this window once (browser rule). <button class="chip2" data-snd-unlock="1">Enable sound</button></div>
    <label class="cf">Master volume <input type="range" data-snd="master" min="0" max="100" step="5" value="${c.master}"><b>${c.master}%</b></label>
    <label class="cf">Minimum gap between real-person message sounds <input type="range" data-snd="gap" min="0" max="30" step="1" value="${c.gap}"><b>${c.gap ? c.gap + "s" : "0 s (back to back)"}</b></label>
    ${SND_EVENTS.map(row).join('')}
    <div class="act" style="margin-top:8px"><button class="chip2" data-snd-notify="1">Allow desktop notifications</button> <small class="mut">now: ${esc(notifyState)}</small></div></div>`;
}
document.addEventListener('input', ev => {
  const t = ev.target.closest && ev.target.closest('[data-snd]'); if (!t) return;
  const [k, f] = t.dataset.snd.split('.'); const v = t.type === 'checkbox' ? t.checked : t.type === 'range' ? Number(t.value) : t.value;
  if (f == null) SND.cfg[k] = v; else SND.cfg.ev[k][f] = v;
  if (t.type === 'range') { const b = t.parentElement.querySelector('b') || t.nextElementSibling; if (b) b.textContent = t.dataset.snd === 'gap' ? (Number(t.value) ? t.value + 's' : '0 s (back to back)') : t.value + '%'; }
  sndSave();
});
document.addEventListener('click', ev => {
  const test = ev.target.closest && ev.target.closest('[data-snd-test]');
  if (test) { const e = SND.cfg.ev[test.dataset.sndTest]; sndCtx(); setTimeout(() => { if (!sndPlay(e.tone, e.vol)) sndBanner(); else sndBanner(); }, 30); return; }
  if (ev.target.closest && ev.target.closest('[data-snd-unlock]')) { sndCtx(); setTimeout(() => { sndPlay('chime', 40); sndBanner(); }, 30); return; }
  if (ev.target.closest && ev.target.closest('[data-snd-notify]')) { try { Notification.requestPermission().then(() => { if (typeof sideRender === 'function') sideRender(); }); } catch (e) { /* unsupported */ } }
});
sndLoad();
