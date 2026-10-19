// Pre-stream readiness checks for the Suite console: [{id,label,status: pass|warn|fail, detail}]. No secrets in output.
import * as ts from './tailscale.mjs';
import { obsConn } from './vault.mjs';
import { getData } from './obs.mjs';

const item = (id, label, status, detail) => ({ id, label, status, detail });

export async function prestream(cfg) {
  const out = [], on = k => cfg.prestream?.[k] !== false;
  if (cfg.role !== 'client' && (on('obs') || on('macros'))) {
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
  }
  if (!on('obs')) { const i = out.findIndex(x => x.id === 'obs'); if (i >= 0) out.splice(i, 1); }
  if (!on('macros')) { const i = out.findIndex(x => x.id === 'macros'); if (i >= 0) out.splice(i, 1); }
  // 2. Tailscale up (only matters for remote control).
  if (on('tailscale')) try {
    const t = await ts.status();
    if (t.state === 'Running') {
      const hub = t.peers?.find(p => p.name === cfg.hub);
      const peers = (t.peers || []).filter(p => p.online);
      out.push(item('tailscale', 'Tailscale', 'pass', `running, ${peers.length} peer(s) online`));
      if (cfg.role === 'client') out.push(!hub ? item('hub', 'Hub device', 'fail', `"${cfg.hub}" not on the tailnet`)
        : !hub.online ? item('hub', 'Hub device', 'fail', `"${cfg.hub}" is offline`)
        : item('hub', 'Hub device', 'pass', hub.direct ? 'online, direct path' : 'online, relayed path (higher latency)'));
    } else out.push(item('tailscale', 'Tailscale', cfg.prestream?.tailscaleRequired ? 'fail' : 'warn', `${t.state || t.error || 'not running'}; remote control and file transfer unavailable, local use unaffected`));
  } catch (e) { out.push(item('tailscale', 'Tailscale', 'warn', e.message)); }
  // 3. Role sanity for a streaming PC.
  out.push(cfg.role === 'hub' ? item('role', 'Role', 'pass', 'hub (this PC controls OBS)')
    : item('role', 'Role', 'warn', 'client: macros are forwarded to the hub, not run on this PC'));
  return out;
}
