import http from 'node:http';
import crypto from 'node:crypto';
import * as ts from './tailscale.mjs';
import { runRequests } from './obs.mjs';
import { log } from './log.mjs';
import { prestream } from './prestream.mjs';

/** Run a macro. Hub talks to OBS directly; clients forward to the hub over the tailnet. */
export async function runMacro(cfg, name) {
  const steps = cfg.macros[name];
  if (!steps) throw new Error(`unknown macro "${name}" (have: ${Object.keys(cfg.macros).join(', ')})`);
  if (cfg.role === 'hub') return runRequests(cfg.obs, steps);
  const st = await ts.status();
  const hub = st.peers?.find(p => p.name === cfg.hub);
  if (!hub) throw new Error(`hub "${cfg.hub}" not found on the tailnet`);
  if (!hub.online) { log('warn', 'relay', `hub ${cfg.hub} is offline`); throw new Error(`hub "${cfg.hub}" is offline`); }
  const r = await fetch(`http://${hub.ip}:${cfg.port}/api/macro/${name}`, {
    method: 'POST', headers: { 'x-link-token': cfg.token }, signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) { log('warn', 'relay', `hub answered ${r.status} for macro ${name}`); throw new Error(`hub said ${r.status}: ${await r.text()}`); }
  return r.json();
}

const PAGE = `<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>PinguinoLink</title>
<style>
:root{color-scheme:dark;--bg:#050506;--card:#0d0e10;--line:#1f2125;--fg:#ececef;--dim:#8d9199;--acc:#ff9900}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,Segoe UI,sans-serif}
main{max-width:1060px;margin:0 auto;padding:20px 16px}h1{font-size:20px;margin:0 0 14px}h3{margin:0 0 10px;font-size:13px;color:var(--acc);text-transform:uppercase;letter-spacing:.06em}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:14px}
ul{list-style:none;margin:8px 0 0;padding:0}li{padding:6px 0;border-top:1px solid var(--line)}
button{background:#14161a;color:var(--fg);border:1px solid var(--line);border-radius:8px;margin:4px 6px 4px 0;padding:9px 16px;font:inherit;cursor:pointer}
button:hover{border-color:var(--acc)}button.danger{border-color:#8a3a3a}button:hover{background:#1b1d21}.dim{color:var(--dim)}#msg{min-height:20px;margin-top:8px}
</style><body><main>
<h1>🐧 PinguinoLink</h1>
<div class=card><h3>Network</h3><div id=s>loading…</div></div>
<div class=card><h3>OBS macros</h3><div id=m></div><div id=msg class=dim></div></div>
<div class="card dim">File send/receive: use the CLI (<code>pinguinolink send</code> / <code>receive</code>); not yet in this page.</div>
</main>
<script>
const H={'x-link-token':'__TOKEN__'};
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){try{const s=await (await fetch('/api/status',{headers:H})).json();
document.getElementById('s').innerHTML='Role: <b>'+esc(s.role)+'</b> · '+esc(s.tailscale.state||s.tailscale.error)+'<ul>'+(s.tailscale.peers||[]).map(p=>'<li>'+esc(p.name)+' — '+(p.online?(p.direct?'🟢 direct':'🟡 relayed'):'⚫ offline')+'</li>').join('')+'</ul>';
document.getElementById('m').innerHTML=s.macros.map(n=>'<button class="'+(n==='stop'||n==='start'?'danger':'')+'" data-m="'+esc(n)+'">'+esc(n)+'</button>').join('');}
catch(e){document.getElementById('s').textContent='unavailable: '+e.message;}}
document.addEventListener('click',async e=>{const n=e.target.dataset&&e.target.dataset.m;if(!n)return;
if((n==='stop'||n==='start')&&!confirm(n+' the stream?'))return;
const r=await fetch('/api/macro/'+encodeURIComponent(n),{method:'POST',headers:H});
document.getElementById('msg').textContent=n+': '+(r.ok?'done':await r.text());});
load();setInterval(load,5000);</script>`;

// Suite desktop shell (Tauri webview) origins; the token is still required for anything but the page.
const TAURI = new Set(['tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost']);
const FRAME = "frame-ancestors 'self' tauri://localhost http://tauri.localhost https://tauri.localhost http://127.0.0.1:* http://localhost:*";
const LOOP = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const eq = (a, b) => {
  const x = crypto.createHash('sha256').update(String(a ?? '')).digest();
  const y = crypto.createHash('sha256').update(String(b ?? '')).digest();
  return crypto.timingSafeEqual(x, y);
};

/** Token check, constant time. Accepts the module token and the Suite core's PINGUINO_API_TOKEN. */
function tokenOk(cfg, given) {
  if (!given) return false;
  given = String(given).replace(/^Bearer /i, '');
  let ok = eq(given, cfg.token);
  const core = process.env.PINGUINO_API_TOKEN;
  if (core && eq(given, core)) ok = true;
  return ok;
}

/** Host header must be an IP literal, localhost, or a tailnet name; blocks DNS rebinding. */
function hostOk(host, selfName) {
  const h = String(host || '').replace(/:\d+$/, '').replace(/^\[|\]$/g, '').toLowerCase();
  if (!h) return false;
  if (h === 'localhost' || /^\d{1,3}(\.\d{1,3}){3}$/.test(h) || h.includes(':')) return true;
  return h.endsWith('.ts.net') || (!!selfName && h === selfName.toLowerCase());
}

export async function serve(cfg) {
  const port = Number(process.env.PINGUINO_LINK_PORT) || cfg.port;
  let selfName = '';
  const handler = async (req, res) => {
    const local = LOOP.has(req.socket.remoteAddress || '');
    const json = (code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
    try {
      if (!hostOk(req.headers.host, selfName)) { log('warn', 'http', 'rejected request: bad Host header (421)'); return json(421, { error: 'bad host' }); }
      // Liveness probe for the Suite core: no secrets, no Tailscale call.
      if (req.method === 'GET' && req.url === '/api/health') return json(200, { ok: true, role: cfg.role });
      const origin = req.headers.origin;
      if (origin) {
        let same = false;
        try { same = new URL(origin).host === req.headers.host || TAURI.has(origin); } catch {}
        if (!same) { log('warn', 'http', 'rejected request: foreign Origin (403)'); return json(403, { error: 'foreign origin' }); }
      }
      // The dashboard page on loopback gets the token injected (same-origin only; Host/Origin checks stop other sites).
      if (req.method === 'GET' && (req.url === '/' || req.url === '/index.html') && local) {
        res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-store', 'content-security-policy': FRAME });
        return res.end(PAGE.replace('__TOKEN__', cfg.token));
      }
      // Pre-stream readiness for the Suite console: no token, no secrets in the output.
      if (req.method === 'GET' && req.url === '/api/prestream') return json(200, { items: await prestream(cfg) });
      // Everything else needs the token, loopback included.
      if (!tokenOk(cfg, req.headers['x-link-token'] || req.headers.authorization)) { log('warn', 'http', `unauthorized ${req.method} ${req.url.split('?')[0]} (401)`); return json(401, { error: 'bad token' }); }
      if (req.method === 'GET' && req.url === '/api/status') {
        const t = await ts.status();
        selfName = t.self?.name || selfName;
        return json(200, { role: cfg.role, macros: Object.keys(cfg.macros), tailscale: t });
      }
      const m = req.method === 'POST' && req.url.match(/^\/api\/macro\/([\w-]+)$/);
      if (m) {
        try { const results = await runMacro(cfg, m[1]); log('info', 'macro', `ran ${m[1]}`); return json(200, { ok: true, results }); }
        catch (e) { log('error', 'macro', `${m[1]} failed: ${e.message}`); throw e; }
      }
      json(404, { error: 'not found' });
    } catch (e) { log('error', 'http', `${req.method} ${String(req.url).split('?')[0]}: ${e.message}`); json(500, { error: e.message }); }
  };

  const listen = (addr) => new Promise((resolve, reject) => {
    const s = http.createServer(handler);
    s.once('error', reject);
    s.listen(port, addr, () => resolve(s));
  });

  // Loopback must bind; if not, exit nonzero so the Suite shows the module as failed.
  try { await listen('127.0.0.1'); log('info', 'server', `listening on 127.0.0.1:${port} (role ${cfg.role})`); }
  catch (e) { log('error', 'server', `cannot listen on 127.0.0.1:${port} (${e.code})`); process.exit(1); }

  // Never 0.0.0.0: loopback plus the Tailscale address, bound as soon as Tailscale is up (re-checked every 15 s).
  let tailBound = null;
  const bindTail = async () => {
    const st = await ts.status();
    selfName = st.self?.name || selfName;
    const ip = st.state === 'Running' && st.self?.ip;
    if (!ip || ip === tailBound) return;
    try { await listen(ip); tailBound = ip; log('info', 'server', `listening on tailnet address ${ip}:${port}`); }
    catch (e) { log('warn', 'server', `could not listen on ${ip}:${port} (${e.code})`); }
  };
  await bindTail();
  if (!tailBound) log('warn', 'server', 'Tailscale is not running; only this machine can reach the service until it is');
  setInterval(bindTail, 15000).unref();
}
