import http from 'node:http';
import crypto from 'node:crypto';
import * as ts from './tailscale.mjs';
import { runRequests } from './obs.mjs';
import { log } from './log.mjs';
import { prestream } from './prestream.mjs';
import { createMesh } from './mesh.mjs';

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
ul{list-style:none;margin:8px 0 0;padding:0}li{padding:6px 0;border-top:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap}li .grow{flex:1}
button{background:#14161a;color:var(--fg);border:1px solid var(--line);border-radius:8px;margin:4px 6px 4px 0;padding:9px 16px;font:inherit;cursor:pointer}
button:hover{border-color:var(--acc);background:#1b1d21}button.danger{border-color:#8a3a3a}button.armed{border-color:var(--acc);color:var(--acc)}
input{background:#08090a;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit;margin:4px 6px 4px 0}
.dim{color:var(--dim)}#msg,#dmsg{min-height:20px;margin-top:8px}.code{font:700 26px/1 ui-monospace,Consolas,monospace;letter-spacing:.2em;color:var(--acc)}
</style><body><main>
<h1>🐧 PinguinoLink</h1>
<div class=card><h3>Network</h3><div id=s>loading…</div></div>
<div class=card><h3>Devices</h3><div id=d class=dim>loading…</div><div id=dmsg class=dim></div></div>
<div class=card><h3>OBS macros</h3><div id=m></div><div id=msg class=dim></div></div>
<div class="card dim">File send/receive: use the CLI (<code>pinguinolink send</code> / <code>receive</code>); not yet in this page.</div>
</main>
<script>
const H={'x-link-token':'__TOKEN__'};
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $=id=>document.getElementById(id);
let armed=null,armedAt=0;
const isArmed=k=>armed===k&&Date.now()-armedAt<4000;
const api=async(p,b)=>{const r=await fetch(p,b===undefined?{headers:H}:{method:'POST',headers:Object.assign({'content-type':'application/json'},H),body:JSON.stringify(b)});
const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j;};
async function load(){try{const s=await api('/api/status');
$('s').innerHTML='Role: <b>'+esc(s.role)+'</b> · '+esc(s.tailscale.state||s.tailscale.error)+'<ul>'+(s.tailscale.peers||[]).map(p=>'<li>'+esc(p.name)+' — '+(p.online?(p.direct?'🟢 direct':'🟡 relayed'):'⚫ offline')+'</li>').join('')+'</ul>';
$('m').innerHTML=s.macros.map(n=>{const risky=n==='stop'||n==='start';return '<button class="'+(risky?'danger':'')+(isArmed('m:'+n)?' armed':'')+'" data-m="'+esc(n)+'"'+(risky?' data-twice="m:'+esc(n)+'"':'')+'>'+(isArmed('m:'+n)?'Click again: '+esc(n)+' the stream':esc(n))+'</button>';}).join('');}
catch(e){$('s').textContent='unavailable: '+e.message;}
try{const d=await api('/api/mesh/status');
let h='<div>This device: <b>'+esc(d.self.name)+'</b> <span class=dim>('+esc(d.self.os)+')</span></div>';
h+='<ul>'+(d.peers.length?d.peers.map(p=>'<li><span class=grow>'+(p.online?'🟢':'⚫')+' <b>'+esc(p.name)+'</b> <span class=dim>'+esc(p.os)+(p.online?'':(p.error?' · '+esc(p.error):' · offline'))+'</span></span><button data-unpair="'+esc(p.id)+'" data-twice="u:'+esc(p.id)+'" class="danger'+(isArmed('u:'+p.id)?' armed':'')+'">'+(isArmed('u:'+p.id)?'Click again to unpair':'Unpair')+'</button></li>').join(''):'<li class=dim>No paired devices. Pair one to share the master role across your PCs.</li>')+'</ul>';
if(d.pending.length)h+='<h3 style="margin-top:12px">Pairing requests</h3><ul>'+d.pending.map(p=>'<li><span class=grow><b>'+esc(p.name)+'</b> ('+esc(p.os)+') from '+esc(p.from)+' wants to pair</span><button data-appr="'+esc(p.id)+'">Allow</button><button data-deny="'+esc(p.id)+'" class=danger>Deny</button></li>').join('')+'</ul>';
h+='<div style="margin-top:10px">'+(d.pairing?'Pairing code: <span class=code>'+esc(d.pairing.code)+'</span> <span class=dim>valid 5 minutes, Tailscale devices only</span>':'<button id=pstart>Show a pairing code</button>')+'</div>';
h+='<div style="margin-top:6px"><input id=ja placeholder="other device: name or 100.x address" size=34><input id=jc placeholder="code" size=8><button id=jgo>Pair</button></div>';
if(!document.activeElement||document.activeElement.tagName!=='INPUT'){const a=$('ja')&&$('ja').value,c=$('jc')&&$('jc').value;$('d').innerHTML=h;if(a)$('ja').value=a;if(c)$('jc').value=c;}
}catch(e){$('d').textContent='mesh unavailable: '+e.message;}}
document.addEventListener('click',async e=>{const t=e.target;if(!t.dataset&&!t.id)return;
const k=t.dataset&&t.dataset.twice;
if(k){if(!isArmed(k)){armed=k;armedAt=Date.now();load();return;}armed=null;}
try{
if(t.dataset.m){const r=await fetch('/api/macro/'+encodeURIComponent(t.dataset.m),{method:'POST',headers:H});$('msg').textContent=t.dataset.m+': '+(r.ok?'done':await r.text());load();return;}
if(t.dataset.unpair){await api('/api/mesh/unpair',{id:t.dataset.unpair});$('dmsg').textContent='Unpaired.';load();return;}
if(t.dataset.appr||t.dataset.deny){await api('/api/mesh/pair/approve',{id:t.dataset.appr||t.dataset.deny,allow:!!t.dataset.appr});load();return;}
if(t.id==='pstart'){await api('/api/mesh/pair/start',{});load();return;}
if(t.id==='jgo'){$('dmsg').textContent='Waiting for the other device to approve (up to 90 s)…';const r=await api('/api/mesh/pair/join',{addr:$('ja').value,code:$('jc').value});$('dmsg').textContent='Paired with '+r.device.name+'.';load();return;}
}catch(err){$('dmsg').textContent=err.message;$('msg').textContent=err.message;}});
load();setInterval(load,4000);</script>`;

// Suite desktop shell (Tauri webview) origins; the token is still required for anything but the page.
const TAURI = new Set(['tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost']);
const FRAME = "frame-ancestors 'self' tauri://localhost http://tauri.localhost https://tauri.localhost http://127.0.0.1:* http://localhost:*";
/** Read a small JSON body; mesh routes require application/json. */
async function readJson(req) {
  if (!String(req.headers['content-type'] || '').startsWith('application/json')) throw Object.assign(new Error('content-type must be application/json'), { status: 415 });
  let n = 0; const parts = [];
  for await (const c of req) { n += c.length; if (n > 16384) throw Object.assign(new Error('body too large'), { status: 413 }); parts.push(c); }
  try { return JSON.parse(Buffer.concat(parts).toString('utf8') || '{}'); } catch { throw Object.assign(new Error('bad JSON'), { status: 400 }); }
}
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
  const mesh = createMesh(cfg, { port });
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
      // Peer routes authenticate themselves (pairing code / per-peer token), not with the module token.
      const peer = [req.headers['x-link-peer'], req.headers['x-link-token']];
      if (req.method === 'POST' && req.url === '/api/mesh/pair/request') return json(200, await mesh.pairRequest(req.socket.remoteAddress, await readJson(req)));
      if (req.method === 'POST' && req.url === '/api/mesh/heartbeat') return json(200, mesh.heartbeat(...peer, await readJson(req)));
      if (req.method === 'POST' && req.url === '/api/mesh/msg') return json(200, await mesh.receive(...peer, await readJson(req)));
      if (req.method === 'POST' && req.url === '/api/mesh/forget') return json(200, mesh.peerUnpaired(...peer));
      // The dashboard page on loopback gets the token injected (same-origin only; Host/Origin checks stop other sites).
      if (req.method === 'GET' && (req.url === '/' || req.url === '/index.html') && local) {
        res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-store', 'content-security-policy': FRAME });
        return res.end(PAGE.replace('__TOKEN__', cfg.token));
      }
      // Pre-stream readiness for the Suite console: no token, no secrets in the output.
      if (req.method === 'GET' && req.url === '/api/prestream') return json(200, { items: [...await prestream(cfg), ...mesh.prestreamItems()] });
      // Everything else needs the token, loopback included.
      if (!tokenOk(cfg, req.headers['x-link-token'] || req.headers.authorization)) { log('warn', 'http', `unauthorized ${req.method} ${req.url.split('?')[0]} (401)`); return json(401, { error: 'bad token' }); }
      if (req.method === 'GET' && req.url === '/api/status') {
        const t = await ts.status();
        selfName = t.self?.name || selfName;
        return json(200, { role: cfg.role, macros: Object.keys(cfg.macros), tailscale: t, peers: mesh.status().peers });
      }
      if (req.url.startsWith('/api/mesh/') || req.url === '/api/peer/broadcast') {
        const post = req.method === 'POST';
        if (req.method === 'GET' && req.url === '/api/mesh/status') return json(200, mesh.status());
        if (post && req.url === '/api/peer/broadcast') {            // core -> Link: send unchanged to every paired peer
          const b = await readJson(req);
          if (typeof b.type !== 'string' || typeof b.payload !== 'object' || !b.payload) return json(400, { error: 'need {type, payload}' });
          return json(200, { sent: await mesh.broadcast({ type: b.type, payload: b.payload }) });
        }
        if (post && req.url === '/api/mesh/pair/start') return json(200, mesh.startPairing());
        if (post && req.url === '/api/mesh/pair/join') { const b = await readJson(req); return json(200, await mesh.join(b.addr, b.code)); }
        if (post && req.url === '/api/mesh/pair/approve') { const b = await readJson(req); return json(200, mesh.approve(b.id, b.allow)); }
        if (post && req.url === '/api/mesh/unpair') { const b = await readJson(req); return json(200, await mesh.removePeer(b.id)); }
        if (post && req.url === '/api/mesh/self') { const b = await readJson(req); return json(200, mesh.setName(b.name)); }
        return json(404, { error: 'not found' });
      }
      const m = req.method === 'POST' && req.url.match(/^\/api\/macro\/([\w-]+)$/);
      if (m) {
        try { const results = await runMacro(cfg, m[1]); log('info', 'macro', `ran ${m[1]}`); return json(200, { ok: true, results }); }
        catch (e) { log('error', 'macro', `${m[1]} failed: ${e.message}`); throw e; }
      }
      json(404, { error: 'not found' });
    } catch (e) {
      if (e.status && e.status < 500) { if (e.status !== 404) log('warn', 'http', `${req.method} ${String(req.url).split('?')[0]}: ${e.message} (${e.status})`); return json(e.status, { error: e.message, ...(e.extra || {}) }); }
      log('error', 'http', `${req.method} ${String(req.url).split('?')[0]}: ${e.message}`); json(e.status || 500, { error: e.message });
    }
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
  mesh.start();
  await bindTail();
  if (!tailBound) log('warn', 'server', 'Tailscale is not running; only this machine can reach the service until it is');
  setInterval(bindTail, 15000).unref();
}
