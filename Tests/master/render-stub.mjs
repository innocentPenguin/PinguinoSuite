// Runs the real master-core.js + master.js in node against a stubbed DOM (no browser) and feeds the REAL Host customs/state body
// (fixtures-customs-real.json). Fails on any exception thrown while rendering, and checks the Teams / Settings / KOTH buttons get .cur.
// Usage: node render-stub.mjs [--throw]   (--throw makes setting #cu-act throw inside renderCustoms, to prove the guard shows the banner and the buttons are still highlighted)
import fs from 'node:fs'; import path from 'node:path'; import vm from 'node:vm'; import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url)), src = path.join(here, '..', '..', 'App', 'src', 'master');
const fixture = fs.readFileSync(path.join(here, 'fixtures-customs-real.json'), 'utf8');
const REAL = process.env.REAL_DIR;   // optional: a folder with real GET bodies saved as <path with / ? & = turned into _>.json (kept out of git: they hold viewer names)
const wantThrow = process.argv.includes('--throw');
const errors = []; const EW = e => { try { fs.writeSync(2, String(e && e.stack || e).slice(0, 600) + String.fromCharCode(10)); } catch { } }; process.on('uncaughtException', e => EW(e) || errors.push(String(e && e.stack || e).split('\n').slice(0, 3).join(' | ')));
process.on('unhandledRejection', e => errors.push('rejection: ' + String(e && e.stack || e).split('\n').slice(0, 3).join(' | ')));

const els = new Map(); let customsHtml = '';
const buttonsFor = () => [...customsHtml.matchAll(/<button[^>]*data-st="([^"]+)"[^>]*>/g)].map(m => mkBtn(m[1]));
const btns = new Map(); const mkBtn = st => { if (btns.has(st)) return btns.get(st); const cls = new Set(); const b = { dataset: { st }, disabled: false, textContent: '', style: { setProperty() { } }, classList: { toggle(k, on) { (on === undefined ? !cls.has(k) : on) ? cls.add(k) : cls.delete(k); }, add: k => cls.add(k), remove: k => cls.delete(k), contains: k => cls.has(k) }, _cls: cls }; btns.set(st, b); return b; };
function mk(sel) {
  const store = { dataset: {}, style: { setProperty() { }, removeProperty() { } }, hidden: false, value: '', textContent: '', className: '', children: [], _cls: new Set() };
  const cl = { toggle(k, on) { (on === undefined ? !store._cls.has(k) : on) ? store._cls.add(k) : store._cls.delete(k); }, add: k => store._cls.add(k), remove: k => store._cls.delete(k), contains: k => store._cls.has(k) };
  const self = new Proxy(function () { }, {
    get(_, k) {
      if (k === Symbol.iterator) return [][Symbol.iterator].bind([]); if (k === Symbol.toPrimitive) return () => ''; if (k === 'then') return undefined;
      if (k === 'classList') return cl; if (k in store) return store[k]; if (k === 'length') return 0; if (k === 'isConnected') return true;
      if (k === 'querySelectorAll') return s => /data-st/.test(s) ? buttonsFor() : []; if (k === 'querySelector') return s => sel + ' ' + s === 'x' ? null : mk(sel + ' ' + s);
      if (k === 'firstChild' || k === 'nextSibling' || k === 'firstElementChild') return null; if (k === 'closest') return () => null; if (k === 'getAttribute') return () => null; if (k === 'getBoundingClientRect') return () => ({ left: 0, top: 0, width: 0, height: 0 });
      if (k === 'offsetWidth' || k === 'clientWidth' || k === 'scrollWidth' || k === 'scrollTop' || k === 'scrollHeight' || k === 'clientHeight') return 0;
      return self;
    },
    set(_, k, v) { if (wantThrow && sel === '#cu-act' && k === 'textContent') throw new Error('boom (deliberate)'); store[k] = v; if (k === 'innerHTML' && sel === '#tab-customs') customsHtml = String(v); return true; },
    apply() { return self; },
  });
  store.children = self; return self;
}
const getEl = sel => { if (!els.has(sel)) els.set(sel, mk(sel)); return els.get(sel); };
const doc = { querySelector: getEl, querySelectorAll: s => /data-st/.test(s) ? buttonsFor() : [], createElement: () => mk('new'), body: mk('body'), documentElement: mk('html'), addEventListener() { }, hidden: false, activeElement: null, getElementById: id => getEl('#' + id), createTextNode: () => mk('t'), title: '' };
const realBody = u => { if (!REAL) return u.includes('/api/obs/tree') ? '{"connected":false,"scenes":[],"folders":[],"items":[]}' : '{}'; const p = (u.startsWith('http://m/') ? 'm_' : '') + u.replace(/^https?:\/\/[^/]+\/api\//, '').replace(/[/?&=]/g, '_'); try { return fs.readFileSync(path.join(REAL, p + (p.endsWith('.json') ? '' : '.json')), 'utf8'); } catch { return '{}'; } };
const store = new Map(); const ctx = {
  document: doc, localStorage: { getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) }, location: { search: '?host=http://h&music=http://m&multi=http://x', hash: '', href: 'http://t/master.html' },
  navigator: { clipboard: {}, userAgent: 'stub' }, console: { log() { }, error: (...a) => errors.push('console.error: ' + a.map(x => (x && x.stack) || x).join(' ').slice(0, 300)), warn() { } }, URLSearchParams, URL, Date, Math, JSON, Promise, setTimeout, clearTimeout, setInterval, clearInterval, Intl, AbortController, TextDecoder, TextEncoder,
  addEventListener() { }, removeEventListener() { }, requestAnimationFrame: f => setTimeout(f, 0), matchMedia: () => ({ matches: false, addEventListener() { } }), getComputedStyle: () => ({}), innerWidth: 900, innerHeight: 800, open() { },
  fetch: async (u, o) => { u = String(u);
    if (/\/api\/events/.test(u)) return new Promise(() => { });   // the live stream never connects: polling carries the page
    const body = /\/api\/customs\/state/.test(u) ? (fixture) : realBody(u);
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, text: async () => body, json: async () => JSON.parse(body) }; },
};
ctx.window = ctx; ctx.parent = ctx; ctx.self = ctx; ctx.globalThis = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(src, 'master-core.js'), 'utf8'), ctx, { filename: 'master-core.js' });
if (!ctx.MasterCore) { console.log('FAIL master-core.js did not define MasterCore in the stub'); process.exit(2); }
try { vm.runInContext(fs.readFileSync(path.join(src, 'master.js'), 'utf8'), ctx, { filename: 'master.js', timeout: 4000 }); } catch (e) { EW(e); process.exit(3); }
fs.writeSync(2, 'init ok\n'); await new Promise(r => setTimeout(r, 3500));
const cur = [...btns.values()].filter(b => b._cls.has('cur')).map(b => b.dataset.st).sort();
console.log('data line: ' + getEl('#cu-data').textContent);
const note = String(getEl('#cu-note').textContent || ''), shownNote = getEl('#cu-note').hidden === false;
console.log('buttons with .cur: ' + JSON.stringify(cur) + '   buttons seen: ' + btns.size);
console.log('errors: ' + (errors.length ? '\n  ' + errors.slice(0, 6).join('\n  ') : 'none'));
console.log('customs note: ' + (shownNote ? note : '(hidden)'));
let bad = false;
if (!/Customs data: (live|updated)/.test(String(getEl('#cu-data').textContent))) { bad = true; console.log('data line missing'); }
const relevant = REAL ? errors : errors.filter(e => /ustoms/.test(e));   // without real bodies the other panes get '{}' and may fail to draw; only Customs errors count then
if (!wantThrow) { for (const want of ['mode:balanced', 'format:2v2', 'gamemode:standard', 'koth:off']) if (!cur.includes(want)) { bad = true; console.log('MISSING highlight: ' + want); } if (relevant.length) bad = true; }
else { if (!/Customs failed to draw: boom/.test(note) || !shownNote) { bad = true; console.log('guard did not show the banner for a throwing render'); } for (const want of ['mode:balanced', 'format:2v2', 'gamemode:standard', 'koth:off']) if (!cur.includes(want)) { bad = true; console.log('a failing section stopped the highlight: ' + want); } if (!errors.some(e => /failed to draw/.test(e))) { bad = true; console.log('stack not logged to console.error'); } }
console.log(bad ? 'FAIL' : 'PASS'); process.exit(bad ? 1 : 0);
