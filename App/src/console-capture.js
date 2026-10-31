// Persists webview errors so bug-checks can see the shell: window errors, unhandled rejections and console.error/warn (the originals still run)
// go in batches to POST /api/shell-log (core appends redacted lines to Data\logs\shell.log). Same message at most once per 10 s with a count,
// 200 entries per session, long text cut, tokens and URL query strings removed. Same-origin module iframes are hooked when they load.
(function (root) {
  'use strict';
  var DEDUPE_MS = 10000, MAX_ENTRIES = 200, MAX_MSG = 200, FLUSH_MS = 5000;

  function redact(s) {
    s = String(s);
    s = s.replace(/(https?:\/\/[^\s?#"')]+)\?[^\s"')]*/g, '$1?…');
    s = s.replace(/\b(bearer\s+)[A-Za-z0-9._~+\/=-]{8,}/gi, '$1[redacted]');
    s = s.replace(/\b(authorization|token|api[_-]?key|apikey|secret|password|passwd|access_token)(\s*[=:]\s*)(?:bearer\s+)?[^\s,;&"']+/gi, '$1$2[redacted]');
    s = s.replace(/\b[A-Za-z0-9_-]{32,}\b/g, '[redacted]');
    s = s.replace(/\s+/g, ' ').trim();
    return s.length > MAX_MSG ? s.slice(0, MAX_MSG) + '…' : s;
  }

  function fmt(a) {
    if (a instanceof Error) return a.name + ': ' + a.message;
    if (a && typeof a === 'object') { try { return JSON.stringify(a); } catch (e) { return Object.prototype.toString.call(a); } }
    return String(a);
  }

  function create(opts) {
    var send = opts.send, now = opts.now || Date.now;
    var seen = {}, pending = [], total = 0, timer = null;

    function record(level, msg, src) {
      msg = redact(msg);
      if (!msg) return;
      var key = level + '|' + msg, t = now(), s = seen[key];
      if (s && t - s.t < DEDUPE_MS) { if (pending.indexOf(s.entry) >= 0) s.entry.n++; else s.sup++; return; }
      if (total >= MAX_ENTRIES) return;
      total++;
      var entry = { level: level, msg: msg, n: 1 + (s ? s.sup : 0), src: src ? redact(src) : '' };
      seen[key] = { t: t, entry: entry, sup: 0 };
      pending.push(entry);
      if (!timer && opts.schedule) timer = opts.schedule(flush, FLUSH_MS);
    }

    function flush() {
      timer = null;
      if (!pending.length) return;
      var batch = pending; pending = [];
      try { var p = send(batch); if (p && p.catch) p.catch(function () {}); } catch (e) { /* never throw from the logger */ }
    }

    function attach(win, label) {
      if (!win || win.__consoleCaptured) return;
      win.__consoleCaptured = true;
      ['error', 'warn'].forEach(function (lv) {
        var orig = win.console && win.console[lv];
        if (!orig) return;
        win.console[lv] = function () {
          try { record(lv, Array.prototype.map.call(arguments, fmt).join(' '), label); } catch (e) { /* ignore */ }
          return orig.apply(this, arguments);
        };
      });
      win.addEventListener('error', function (ev) {
        var where = ev.filename ? String(ev.filename).split('?')[0].split('/').pop() + ':' + ev.lineno + ':' + ev.colno : label;
        record('error', ev.message || (ev.error && fmt(ev.error)) || 'error event', where);
      });
      win.addEventListener('unhandledrejection', function (ev) {
        record('error', 'Unhandled rejection: ' + fmt(ev.reason), label);
      });
    }

    return { record: record, flush: flush, attach: attach, stats: function () { return { total: total, pending: pending.length }; } };
  }

  if (typeof module !== 'undefined' && module.exports) { module.exports = { create: create, redact: redact }; return; }

  var cap = create({
    send: function (entries) { return root.fetch('/api/shell-log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entries: entries }) }); },
    schedule: function (fn, ms) { return setTimeout(fn, ms); }
  });
  cap.attach(root, 'shell');
  root.addEventListener('pagehide', function () { cap.flush(); });
  document.addEventListener('load', function (ev) {      // load does not bubble: capture phase sees every iframe
    var f = ev.target;
    if (!f || f.tagName !== 'IFRAME') return;
    try { cap.attach(f.contentWindow, 'module:' + (f.getAttribute('data-mod') || f.id || 'frame')); } catch (e) { /* cross-origin frame: not ours to hook */ }
  }, true);
})(typeof window !== 'undefined' ? window : globalThis);
