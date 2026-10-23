// Timer / handle soak for the Master View (batch V): headless Chrome (not throttled like the app pane) loads the page against the in-process mock Host
// while the Host flaps (503 + dropped event stream) and chat/events keep arriving. Counters injected before the page scripts count live setInterval /
// setTimeout handles, in-flight fetches and DOM size; the run fails if they keep growing. Usage: node soak.mjs [seconds=600] [chrome path]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os'; import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url';
import { startMock } from './mock-host.mjs';
const here = path.dirname(fileURLToPath(import.meta.url)), root = path.join(here, '..', '..', 'App', 'src');
const secs = +process.argv[2] || 600, chrome = process.argv[3] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const mock = await startMock(8797); mock.addChat('a', 'hi');
const web = http.createServer((q, r) => { const f = path.join(root, decodeURIComponent(new URL(q.url, 'http://x').pathname)); fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': /\.js$/.test(f) ? 'text/javascript' : /\.css$/.test(f) ? 'text/css' : 'text/html' }); r.end(b); }); });
await new Promise(r => web.listen(8812, '127.0.0.1', r));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'soak-'));
const ch = spawn(chrome, ['--headless=new', '--remote-debugging-port=9333', '--user-data-dir=' + prof, '--enable-precise-memory-info', '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tab; for (let i = 0; i < 40 && !tab; i++) { await sleep(500); try { tab = (await (await fetch('http://127.0.0.1:9333/json')).json()).find(t => t.type === 'page'); } catch { } }
if (!tab) { console.log('chrome did not start'); process.exit(2); }
const ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map(); ws.onmessage = m => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const inject = `(() => { const S = window.__s = { si: new Set(), st: new Set(), fin: 0 }; const osi = setInterval, ocl = clearInterval, ost = setTimeout, oct = clearTimeout, of = fetch.bind(window);
 window.setInterval = (f, m, ...a) => { const i = osi(f, m, ...a); S.si.add(i); return i; }; window.clearInterval = i => { S.si.delete(i); return ocl(i); };
 window.setTimeout = (f, m, ...a) => { let i; i = ost((...x) => { S.st.delete(i); return typeof f === 'function' ? f(...x) : 0; }, m, ...a); S.st.add(i); return i; }; window.clearTimeout = i => { S.st.delete(i); return oct(i); };
 window.fetch = (...a) => { S.fin++; return of(...a).finally(() => S.fin--); }; })()`;
await cdp('Page.enable'); await cdp('Page.addScriptToEvaluateOnNewDocument', { source: inject });
await cdp('Page.navigate', { url: 'http://127.0.0.1:8812/master/master.html?host=http://127.0.0.1:8797&music=http://127.0.0.1:8797&multi=http://127.0.0.1:8797' });
await sleep(3000); await cdp('Runtime.evaluate', { expression: "document.querySelector('[data-tab=feed]').click()" });
const sample = async () => (await cdp('Runtime.evaluate', { expression: 'JSON.stringify({nodes:document.getElementsByTagName("*").length,feed:document.querySelector("#feedlist").children.length,si:__s.si.size,st:__s.st.size,fin:__s.fin,heap:Math.round(performance.memory.usedJSHeapSize/1e5)/10})', returnByValue: true })).result.result.value;
const rows = [], t0 = Date.now(); let n = 0;
while (Date.now() - t0 < secs * 1000) {
  n++; if (n % 2) { await fetch('http://127.0.0.1:8797/__down?ms=3000'); } await fetch('http://127.0.0.1:8797/__load?chat=30&events=5');
  if (n % 8 === 0) { const s = JSON.parse(await sample()); s.t = Math.round((Date.now() - t0) / 1000); rows.push(s); console.log(JSON.stringify(s)); }
  await sleep(7500);
}
const f = rows.slice(Math.floor(rows.length / 3)), mx = k => Math.max(...f.map(r => r[k])), mn = k => Math.min(...f.map(r => r[k]));
const grow = { nodes: mx('nodes') - mn('nodes'), si: mx('si') - mn('si'), st: mx('st') - mn('st'), heap: +(mx('heap') - mn('heap')).toFixed(1) };
const last = rows[rows.length - 1];
const dead = rows.length < 3 || !last || !(last.si > 0) || !(last.nodes > 500);   // too short a run, or the page never started its pollers
if (dead) console.log('soak invalid: rows=' + rows.length + ' (need >= 3, i.e. run >= ~3 min), pollers/nodes missing in the last sample');
const bad = dead || grow.si > 0 || grow.st > 60 || grow.nodes > 400 || grow.heap > 15;
console.log('growth after warm-up (max-min):', JSON.stringify(grow), bad ? 'FAIL' : 'FLAT');
try { await cdp('Browser.close'); } catch { } ch.kill(); web.close(); mock.close(); process.exit(bad ? 1 : 0);
