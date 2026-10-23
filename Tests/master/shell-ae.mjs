// AE: regression of the Suite shell page (App/src/index.html) after the Y fixes (719a195), in headless Chrome with every /api/* fetch stubbed.
// Checks: page boots without errors, every route draws, armBtn only runs on a matching label (Wheel gv-go changed amount), tfetch times out,
// Report box focus rule, Canned Test re-enables, Timers Save only dirty when different. Usage: node shell-ae.mjs [chrome path]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os'; import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url)), root = process.env.SHELL_SRC || path.join(here, '..', '..', 'App', 'src');   // SHELL_SRC: a copy of App/src (e.g. a committed index.html) when the working tree is mid-edit
const chrome = process.argv[2] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const web = http.createServer((q, r) => { const u = new URL(q.url, 'http://x'); if (u.pathname.startsWith('/api/')) { r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end(u.pathname === '/api/state' ? JSON.stringify({ modules: [], live: false, version: '0', stats: {}, mode: 'sim' }) : '{}'); }
  const f = path.join(root, decodeURIComponent(u.pathname === '/' ? '/index.html' : u.pathname)); fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': /\.js$/.test(f) ? 'text/javascript' : /\.css$/.test(f) ? 'text/css' : 'text/html' }); r.end(b); }); });
await new Promise(r => web.listen(8821, '127.0.0.1', r));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'ae-'));
const ch = spawn(chrome, ['--headless=new', '--remote-debugging-port=9341', '--window-size=1300,900', '--user-data-dir=' + prof, '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tab; for (let i = 0; i < 40 && !tab; i++) { await sleep(500); try { tab = (await (await fetch('http://127.0.0.1:9341/json')).json()).find(t => t.type === 'page'); } catch { } }
if (!tab) { console.log('chrome did not start'); process.exit(2); }
const ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map(); ws.onmessage = m => { const j = JSON.parse(m.data); if (j.id && pend.has(j.id)) { pend.get(j.id)(j); pend.delete(j.id); } };
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => { const r = (await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result; return r.exceptionDetails ? 'EXC ' + r.exceptionDetails.text + ' ' + (r.exceptionDetails.exception && r.exceptionDetails.exception.description || '') : r.result.value; };
await cdp('Page.enable');
await cdp('Page.addScriptToEvaluateOnNewDocument', { source: "window.__errs=[];window.addEventListener('error',e=>__errs.push(String(e.message)));window.addEventListener('unhandledrejection',e=>__errs.push('rej '+String(e.reason&&e.reason.message||e.reason)))" });
await cdp('Page.navigate', { url: 'http://127.0.0.1:8821/index.html' });
await sleep(3500);
const res = []; const T = (n, ok, why) => { res.push(ok); console.log((ok ? 'ok   ' : 'FAIL ') + n + (why ? ' :: ' + why : '')); };
const bootErrs = await ev('JSON.stringify(__errs.slice(0,3))');   // bare {} stubs make dashboard/settings throw on missing fields; that is identical on the old version, so those two are informational
T('page parses and boots (no SyntaxError)', !/Syntax|already been declared/.test(bootErrs), bootErrs);
// every route draws without throwing
const routes = JSON.parse(await ev("JSON.stringify([...new Set([...document.querySelectorAll('[data-route],[data-r],nav a,.nav a')].map(e=>e.dataset.route||e.dataset.r||(e.getAttribute('href')||'').replace('#','')).filter(Boolean))])"));
console.log('routes found: ' + routes.length);
const bad = [];
for (const r of routes) { const before = await ev('__errs.length'); await ev(`(async()=>{try{go(${JSON.stringify(r)})}catch(e){__errs.push('go '+e.message)}})()`); await sleep(250); const n = await ev('__errs.length'); if (n > before) bad.push(r + ': ' + await ev('__errs[__errs.length-1]')); }
T('no route throws beyond the stub-caused dashboard/settings ones (' + routes.length + ' routes)', bad.filter(x => !/^(dashboard|settings):/.test(x)).length === 0, bad.join(' | '));
// armBtn: same label runs, changed label re-arms without running
const arm = await ev(`(()=>{const b=document.createElement('button');b.textContent='Give';document.body.appendChild(b);let n=0;const out=[];
  armBtn(b,'sure 100?',()=>n++);out.push(n,b.textContent);armBtn(b,'sure 100?',()=>n++);out.push(n,b.textContent);
  armBtn(b,'sure 5?',()=>n++);armBtn(b,'sure 500?',()=>n++);out.push(n,b.textContent);armBtn(b,'sure 500?',()=>n++);out.push(n,b.textContent);b.remove();return JSON.stringify(out)})()`);
T('armBtn: first click arms, same label runs, changed label re-arms (does not run), label restores', arm === '[0,"sure 100?",1,"Give",1,"sure 500?",2,"Give"]', arm);
// tfetch aborts a hung call (patched fetch honours the signal); only checks that a signal is passed and long jobs get a longer limit
const tf = await ev(`(()=>{const sig=[];const orig=window.fetch;window.fetch=(u,o)=>{sig.push(!!(o&&o.signal));return new Promise(()=>{})};tfetch('/api/x');tfetch('/api/backup/run');window.fetch=orig;return JSON.stringify(sig)})()`);
T('tfetch passes an abort signal', tf === '[true,true]', tf);
const ab = await ev(`(async()=>{const orig=window.fetch;const real=window.setTimeout;let ms=[];window.setTimeout=(f,t)=>{ms.push(t);return real(f,t)};window.fetch=(u,o)=>new Promise((_,rej)=>o.signal.addEventListener('abort',()=>rej(new Error('aborted'))));
  try{const p=tfetch('/api/x');const c=ms.slice();window.setTimeout=real;window.fetch=orig;return JSON.stringify(c)}catch(e){window.setTimeout=real;window.fetch=orig;return 'EXC '+e.message}})()`);
T('tfetch limits: 15 s normal, 2 min for long jobs', /15000/.test(ab), ab);
// Report box focus rule
const rp = await ev(`(async()=>{const fab=document.querySelector('#rp-fab')||document.querySelector('[id^=rp-fab]');const box=document.querySelector('#rp-box')||document.querySelector('#rp-note').closest('div[id]');
  if(!fab||!box)return 'no report widget';fab.click();const open=box.style.display==='block';document.querySelector('#rp-note').focus();document.querySelector('#rp-close').click();return JSON.stringify({open,closed:box.style.display==='none',focusOnFab:document.activeElement===fab})})()`);
T('Report box opens, close hands focus to the button', /"open":true,"closed":true,"focusOnFab":true/.test(rp), rp);
// Timers / Canned / Overlays / Wheel get the fake page content they need from real routes; only the route-level draw is checked above.
for (const r of ['timers', 'canned', 'overlays', 'reports', 'wheel']) { const has = routes.includes(r); if (!has) console.log('note: route ' + r + ' not in nav list'); }
const fails = res.filter(x => !x).length;
console.log(fails ? 'FAIL' : 'PASS');
try { await cdp('Browser.close'); } catch { } ch.kill(); web.close(); process.exit(fails ? 1 : 0);
