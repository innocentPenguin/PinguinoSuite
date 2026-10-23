// Per-source outage matrix (batch W): Host / Spotify / Multi each get their own mock; for every failure mode the page must show a clear per-source state,
// keep the last good data, never blank, and recover without a reload. Headless Chrome over CDP. Usage: node outage.mjs [chrome path]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os'; import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url';
import { startMock } from './mock-host.mjs';
const here = path.dirname(fileURLToPath(import.meta.url)), root = path.join(here, '..', '..', 'App', 'src');
const chrome = process.argv[2] || ["C:","Program Files","Google","Chrome","Application","chrome.exe"].join(String.fromCharCode(92));
const M = { host: await startMock(8801), music: await startMock(8802), multi: await startMock(8803) }; M.host.addChat('a', 'hello'); M.host.addChat('b', 'world');
const P = { host: 8801, music: 8802, multi: 8803 };
const mode = (src, m) => fetch('http://127.0.0.1:' + P[src] + '/__mode?m=' + m).then(r => r.text());
const web = http.createServer((q, r) => { const f = path.join(root, decodeURIComponent(new URL(q.url, 'http://x').pathname)); fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': /\.js$/.test(f) ? 'text/javascript' : /\.css$/.test(f) ? 'text/css' : 'text/html' }); r.end(b); }); });
await new Promise(r => web.listen(8814, '127.0.0.1', r));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'outage-'));
const ch = spawn(chrome, ['--headless=new', '--remote-debugging-port=9335', '--window-size=1280,800', '--user-data-dir=' + prof, '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tab; for (let i = 0; i < 40 && !tab; i++) { await sleep(500); try { tab = (await (await fetch('http://127.0.0.1:9335/json')).json()).find(t => t.type === 'page'); } catch { } }
if (!tab) { console.log('chrome did not start'); process.exit(2); }
const ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map(); ws.onmessage = m => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;
await cdp('Page.enable'); await cdp('Page.addScriptToEvaluateOnNewDocument', { source: "window.addEventListener('error', () => window.__err = 1); window.addEventListener('unhandledrejection', () => window.__err = 1)" });
await cdp('Page.navigate', { url: 'http://127.0.0.1:8814/master/master.html?host=http://127.0.0.1:8801&music=http://127.0.0.1:8802&multi=http://127.0.0.1:8803' });
await sleep(4000);
await ev("document.querySelector('[data-tab=feed]').click()");
const snap = () => ev(`JSON.stringify({ link: document.querySelector('#p-link').innerText, banner: document.querySelector('#offline').hidden ? '' : document.querySelector('#offline').innerText,
  scenes: document.querySelectorAll('#scenes .r').length, feed: document.querySelector('#feedlist').children.length, body: document.body.innerText.length, tabs: document.querySelectorAll('[data-tab]').length, err: !!window.__err })`).then(JSON.parse);
const base = await snap(); console.log('baseline', JSON.stringify(base));
if (!(base.scenes > 0 && base.feed > 0 && base.body > 200)) { console.log('FAIL baseline page is empty; nothing below would mean anything'); process.exit(1); }
const hostOff = s => /Host offline|old/.test(s.link) && /Host is not answering/.test(s.banner), spo = s => /Spotify/.test(s.banner), mul = s => /Multi/.test(s.banner);
const none = s => !/Spotify|Multi|Host is not/.test(s.banner);
const cases = [
  ['host down', { host: 'down' }, s => hostOff(s) && !spo(s) && !mul(s)],
  ['spotify down', { music: 'down' }, s => spo(s) && !mul(s) && !/Host is not/.test(s.banner)],
  ['multi down', { multi: 'down' }, s => mul(s) && !spo(s) && !/Host is not/.test(s.banner)],
  ['all three down', { host: 'down', music: 'down', multi: 'down' }, s => hostOff(s) && spo(s) && mul(s)],
  ['host 500s (stale badge, no false offline)', { host: '500' }, s => /old/.test(s.link)],
  ['spotify 500s', { music: '500' }, spo],
  ['multi 500s', { multi: '500' }, mul],
  ['host malformed JSON (stale badge)', { host: 'bad' }, s => /old/.test(s.link)],
  ['spotify malformed JSON', { music: 'bad' }, spo],
  ['multi malformed JSON', { multi: 'bad' }, mul],
  // Intentionally weak: 3 s answers are slower than usual but inside the 4 s timeout, so the page may or may not show a banner. This case only requires: page kept, never blank, no banner left over afterwards.
  ['all slow (3 s)', { host: 'slow', music: 'slow', multi: 'slow' }, () => true],
];
let failed = 0; const rows = [];
for (const [name, set, want] of cases) {
  for (const k of Object.keys(P)) await mode(k, 'ok');
  await sleep(1500);
  await ev("document.querySelector('[data-tab=" + (set.multi ? 'stream' : 'feed') + "]').click()"); await sleep(1500);
  for (const [k, m] of Object.entries(set)) await mode(k, m);
  let s, shown = false; const t0 = Date.now();
  while (Date.now() - t0 < 45000) { await sleep(1500); s = await snap(); if (want(s)) { shown = true; break; } }
  const kept = s.scenes >= base.scenes && s.feed >= 1 && s.body > 200 && s.tabs >= 5 && !s.err;
  const slowCase = name.includes('slow');
  for (const k of Object.keys(P)) await mode(k, 'ok');
  let rec = false; const t1 = Date.now(); let r;
  while (Date.now() - t1 < 60000) { await sleep(1500); r = await snap(); if (none(r) && !/offline|old/.test(r.link)) { rec = true; break; } }
  const ok = (slowCase ? true : shown) && kept && rec; if (!ok) failed++;
  rows.push({ name, shown: slowCase ? 'n/a (' + (s.banner || 'no banner') + ')' : shown, kept, recovered: rec, secsToShow: Math.round((Date.now() - t0) / 1000), link: s.link, banner: s.banner.slice(0, 70) });
  console.log((ok ? 'ok   ' : 'FAIL ') + JSON.stringify(rows[rows.length - 1]));
}
console.log(failed ? 'FAIL ' + failed + ' case(s)' : 'PASS all ' + cases.length + ' cases');
try { await cdp('Browser.close'); } catch { } ch.kill(); web.close(); for (const m of Object.values(M)) m.close(); process.exit(failed ? 1 : 0);
