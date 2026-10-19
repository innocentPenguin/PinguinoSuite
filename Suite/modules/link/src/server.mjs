import http from 'node:http';
import * as ts from './tailscale.mjs';
import { runRequests } from './obs.mjs';

/** Run a macro. Hub talks to OBS directly; clients forward to the hub over the tailnet. */
export async function runMacro(cfg, name) {
  const steps = cfg.macros[name];
  if (!steps) throw new Error(`unknown macro "${name}" (have: ${Object.keys(cfg.macros).join(', ')})`);
  if (cfg.role === 'hub') return runRequests(cfg.obs, steps);
  const st = await ts.status();
  const hub = st.peers?.find(p => p.name === cfg.hub);
  if (!hub) throw new Error(`hub "${cfg.hub}" not found on the tailnet`);
  if (!hub.online) throw new Error(`hub "${cfg.hub}" is offline`);
  const r = await fetch(`http://${hub.ip}:${cfg.port}/api/macro/${name}`, {
    method: 'POST', headers: { 'x-link-token': cfg.token }, signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`hub said ${r.status}: ${await r.text()}`);
  return r.json();
}

const PAGE = `<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>PinguinoLink</title><body style="font:16px system-ui;max-width:640px;margin:2rem auto;padding:0 16px">
<h1>🐧 PinguinoLink</h1><div id=s>loading…</div><h3>Macros</h3><div id=m></div>
<script>
async function load(){const s=await (await fetch('/api/status')).json();
document.getElementById('s').innerHTML='<p>Role: <b>'+s.role+'</b> · '+(s.tailscale.state||s.tailscale.error)+'</p><ul>'+(s.tailscale.peers||[]).map(p=>'<li>'+p.name+' — '+(p.online?(p.direct?'🟢 direct':'🟡 relayed'):'⚫ offline')+'</li>').join('')+'</ul>';
document.getElementById('m').innerHTML=s.macros.map(n=>'<button onclick="go(\\''+n+'\\')" style="margin:4px;padding:10px 16px">'+n+'</button>').join('');}
async function go(n){const r=await fetch('/api/macro/'+n,{method:'POST'});alert(r.ok?'done':await r.text());}
load();setInterval(load,5000);</script>`;

export async function serve(cfg) {
  const st = await ts.status();
  const server = http.createServer(async (req, res) => {
    const remote = req.socket.remoteAddress || '';
    const local = remote === '127.0.0.1' || remote === '::1' || remote === '::ffff:127.0.0.1';
    // Loopback is trusted (Stream Deck on this machine); tailnet callers must present the token.
    if (!local && req.headers['x-link-token'] !== cfg.token) { res.writeHead(401); return res.end('bad token'); }
    const json = (code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
    try {
      if (req.method === 'GET' && req.url === '/') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE); }
      if (req.method === 'GET' && req.url === '/api/status')
        return json(200, { role: cfg.role, macros: Object.keys(cfg.macros), tailscale: await ts.status() });
      const m = req.method === 'POST' && req.url.match(/^\/api\/macro\/([\w-]+)$/);
      if (m) return json(200, { ok: true, results: await runMacro(cfg, m[1]) });
      json(404, { error: 'not found' });
    } catch (e) { json(500, { error: e.message }); }
  });
  // Never 0.0.0.0: only loopback and the Tailscale address, so the service is invisible on school/hotspot LANs.
  const up = st.state === 'Running' && st.self?.ip;
  const addrs = ['127.0.0.1', ...(up ? [st.self.ip] : [])];
  for (const a of addrs) {
    const s = a === '127.0.0.1' ? server : http.createServer(server.listeners('request')[0]);
    try { await new Promise((r, j) => { s.once('error', j); s.listen(cfg.port, a, r); }); console.log(`listening on http://${a}:${cfg.port}`); }
    catch (e) { console.log(`! could not listen on ${a}:${cfg.port} (${e.code})`); }
  }
  if (!up) console.log('! Tailscale is not running, so only this PC can reach the dashboard. Run: pinguinolink setup');
}
