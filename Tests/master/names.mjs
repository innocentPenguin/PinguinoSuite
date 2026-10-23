// Hostile-name check (batch U): queue, match teams, team names, wheel entries and chat names that are very long, emoji, RTL, empty, spaces only,
// or HTML-looking. Loads the real page in headless Chrome against the in-process mock. Fails if anything renders as markup / runs script / widens the page.
// Usage: node names.mjs [chrome path]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os'; import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url';
import { startMock } from './mock-host.mjs';
const here = path.dirname(fileURLToPath(import.meta.url)), root = path.join(here, '..', '..', 'App', 'src');
const chrome = process.argv[2] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const mock = await startMock(8795), st = mock.st;
const HTML = '<b id="zz">x</b><img src=x onerror="window.__xss=1">', Q = 'say "hi" & \'bye\' <script>window.__xss=1</script>';
const NAMES = ['W'.repeat(80), '🔥'.repeat(40), 'א'.repeat(30) + ' ' + 'ب'.repeat(30), '   ', '', HTML, Q, 'long name with spaces '.repeat(6)];
st.customs.queue = NAMES.map((n, i) => ({ username: 'u' + i, display: n, mmr: 1000 + i }));
st.customs.match = { id: 1, status: 'live', orange: NAMES.slice(0, 4), blue: NAMES.slice(4) };
st.customs.teams = { orange: { name: 'O'.repeat(70) + HTML, color: '#ff7a00' }, blue: { name: '🔥'.repeat(40), color: '#1e8fff' } };
st.wheel = Object.assign({}, st.wheel, { names: NAMES, pool: NAMES, entrantCount: NAMES.length, teams: [{ name: HTML, players: NAMES.slice(0, 2) }] });
for (const n of NAMES) mock.addChat(n || 'x', HTML + ' ' + Q + ' ' + 'W'.repeat(120));
const web = http.createServer((q, r) => { const f = path.join(root, decodeURIComponent(new URL(q.url, 'http://x').pathname)); fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': /\.js$/.test(f) ? 'text/javascript' : /\.css$/.test(f) ? 'text/css' : 'text/html' }); r.end(b); }); });
await new Promise(r => web.listen(8813, '127.0.0.1', r));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'names-'));
const ch = spawn(chrome, ['--headless=new', '--remote-debugging-port=9334', '--window-size=900,800', '--user-data-dir=' + prof, '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tab; for (let i = 0; i < 40 && !tab; i++) { await sleep(500); try { tab = (await (await fetch('http://127.0.0.1:9334/json')).json()).find(t => t.type === 'page'); } catch { } }
if (!tab) { console.log('chrome did not start'); process.exit(2); }
const ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map(); ws.onmessage = m => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;
await cdp('Emulation.setDeviceMetricsOverride', { width: 900, height: 800, deviceScaleFactor: 1, mobile: false });
await cdp('Page.navigate', { url: 'http://127.0.0.1:8813/master/master.html?host=http://127.0.0.1:8795&music=http://127.0.0.1:8795&multi=http://127.0.0.1:8795' });
await sleep(3500);
const probe = `(async () => { const out = {}; const w = ms => new Promise(r => setTimeout(r, ms));
 for (const t of ['customs', 'feed', 'cmds', 'overlays', 'stream']) { document.querySelector('[data-tab=' + t + ']').click(); await w(1500);
  const root = document.querySelector('#tab-' + t), wide = [];
  for (const e of root.querySelectorAll('*')) if (e.offsetParent && e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflowX === 'visible') wide.push((e.id || e.className || e.tagName) + ':' + e.scrollWidth + '>' + e.clientWidth);
  if (t === 'customs' || t === 'feed') { out.literal = (out.literal || false) || document.body.innerText.includes('<b id="zz">'); if (t === 'customs') out.shown = root.innerText.length; }
  out[t] = { wide: wide.slice(0, 6), rootX: root.scrollWidth - root.clientWidth, markup: root.querySelectorAll('#zz, img[src=x], script').length }; }
 const sc = document.querySelector('#scenes'); out.docX = document.documentElement.scrollWidth - innerWidth; out.xss = !!window.__xss; out.zz = !!document.getElementById('zz');
 return JSON.stringify(out); })()`;
const out = JSON.parse(await ev(probe)); console.log(JSON.stringify(out, null, 1));
const bad = out.literal !== true || !(out.shown > 200) ||  out.xss || out.zz || out.docX > 2 || Object.values(out).some(v => v && typeof v === 'object' && (v.markup || v.rootX > 2 || (v.wide && v.wide.length)));
if (out.literal !== true || !(out.shown > 200)) console.log('page did not render the hostile names (literal=' + out.literal + ', customs text length=' + out.shown + ')');
console.log(bad ? 'FAIL' : 'PASS (nothing rendered as markup, nothing widened the page)');
try { await cdp('Browser.close'); } catch { } ch.kill(); web.close(); mock.close(); process.exit(bad ? 1 : 0);
