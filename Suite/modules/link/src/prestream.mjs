// Pre-stream readiness checks for the Suite console: [{id,label,status: pass|warn|fail, detail}]. No secrets in output.
import * as ts from './tailscale.mjs';
import { obsConn } from './vault.mjs';

const item = (id, label, status, detail) => ({ id, label, status, detail });

export async function prestream(cfg) {
  const out = [];
  // 1. OBS WebSocket reachable + authenticated, and the scenes/inputs the macros use exist.
  try {
    const [, sc, inp] = await getData(await obsConn(cfg), ['GetVersion', 'GetSceneList', 'GetInputList']);
    out.push(item('obs', 'OBS WebSocket', 'pass', `reachable at ${cfg.obs.host}:${cfg.obs.port}`));
    const scenes = new Set((sc?.scenes || []).map(s => s.sceneName));
    const inputs = new Set((inp?.inputs || []).map(i => i.inputName));
    const missing = [];
    for (const [name, steps] of Object.entries(cfg.macros)) for (const s of steps) {
      if (s.data?.sceneName && !scenes.has(s.data.sceneName)) missing.push(`${name}: scene "${s.data.sceneName}"`);
      if (s.data?.inputName && !inputs.has(s.data.inputName)) missing.push(`${name}: input "${s.data.inputName}"`);
    }
    out.push(missing.length
      ? item('macros', 'OBS macro targets', 'fail', `not found in OBS: ${missing.join('; ')}. Edit macros in the Link config.`)
      : item('macros', 'OBS macro targets', 'pass', `${Object.keys(cfg.macros).length} macros match OBS scenes/inputs`));
  } catch (e) {
    out.push(item('obs', 'OBS WebSocket', 'fail', e.message));
    out.push(item('macros', 'OBS macro targets', 'warn', 'not checked (OBS unreachable)'));
  }
  // 2. Tailscale up (only matters for remote control).
  try {
    const t = await ts.status();
    if (t.state === 'Running') {
      const hub = t.peers?.find(p => p.name === cfg.hub);
      const peers = (t.peers || []).filter(p => p.online);
      out.push(item('tailscale', 'Tailscale', 'pass', `running, ${peers.length} peer(s) online`));
      if (cfg.role === 'client') out.push(!hub ? item('hub', 'Hub device', 'fail', `"${cfg.hub}" not on the tailnet`)
        : !hub.online ? item('hub', 'Hub device', 'fail', `"${cfg.hub}" is offline`)
        : item('hub', 'Hub device', 'pass', hub.direct ? 'online, direct path' : 'online, relayed path (higher latency)'));
    } else out.push(item('tailscale', 'Tailscale', 'warn', `${t.state || t.error || 'not running'}; remote control and file transfer unavailable, local use unaffected`));
  } catch (e) { out.push(item('tailscale', 'Tailscale', 'warn', e.message)); }
  // 3. Role sanity for a streaming PC.
  out.push(cfg.role === 'hub' ? item('role', 'Role', 'pass', 'hub (this PC controls OBS)')
    : item('role', 'Role', 'warn', 'client: macros are forwarded to the hub, not run on this PC'));
  return out;
}

// Small helper: one connection, returns each request's responseData.
import crypto from 'node:crypto';
const sha = s => crypto.createHash('sha256').update(s).digest('base64');
function getData({ host, port, password }, types, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://${host}:${port}`);
    const res = [];
    const timer = setTimeout(() => { ws.close(); reject(new Error('OBS timed out')); }, timeoutMs);
    const fail = e => { clearTimeout(timer); try { ws.close(); } catch {} reject(e); };
    ws.onerror = () => fail(new Error(`cannot reach OBS at ${host}:${port}`));
    ws.onclose = e => { if (e.code === 4009) fail(new Error('OBS WebSocket password is wrong')); };
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.op === 0) {
        const id = { rpcVersion: 1 };
        if (m.d.authentication) id.authentication = sha(sha(password + m.d.authentication.salt) + m.d.authentication.challenge);
        ws.send(JSON.stringify({ op: 1, d: id }));
      } else if (m.op === 2) types.forEach((t, i) => ws.send(JSON.stringify({ op: 6, d: { requestType: t, requestId: String(i) } })));
      else if (m.op === 7) {
        res[Number(m.d.requestId)] = m.d.responseData || {};
        if (res.filter(Boolean).length === types.length) { clearTimeout(timer); ws.close(); resolve(res); }
      }
    };
  });
}
