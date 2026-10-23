// INDEX morning.mjs: the plain-language "morning check" (GET /api/morning). One screen, read-only, no secrets.
// Builds on the pre-stream items (OBS, macro names, Tailscale, hub) and adds role, devices, stream safety and the OBS port 4455 state.
import os from 'node:os';
import net from 'node:net';

/** Is the OBS WebSocket port reachable on this PC's own network addresses (not loopback)? Only a TCP connect, no OBS protocol. */
export async function probeObsPort(port, timeoutMs = 700) {
  if (process.env.PINGUINO_NEVER_REAL_OBS && Number(port) === 4455) return { state: 'skipped' };   // tests never touch the real OBS port
  const addrs = Object.values(os.networkInterfaces()).flat().filter(a => a && a.family === 'IPv4' && !a.internal).map(a => a.address);
  const tryOne = (host) => new Promise(res => {
    const s = net.connect({ host, port }); const done = ok => { s.destroy(); res(ok); };
    s.setTimeout(timeoutMs, () => done(false)); s.on('connect', () => done(true)); s.on('error', () => done(false));
  });
  const open = []; for (const a of addrs) if (await tryOne(a)) open.push(a);
  if (open.length) return { state: 'open', addrs: open };
  const local = await new Promise(res => { const s = net.connect({ host: '127.0.0.1', port }); const d = ok => { s.destroy(); res(ok); }; s.setTimeout(timeoutMs, () => d(false)); s.on('connect', () => d(true)); s.on('error', () => d(false)); });
  return { state: local ? 'closed' : 'obs-off', addrs: [] };
}

const L = (status, label, text) => ({ status, label, text });   // status: good | note | bad

/** items = the pre-stream items; mesh = mesh.status(); probe = result of probeObsPort (hub only). */
export function morning(cfg, { items = [], mesh = { peers: [] }, probe = null } = {}) {
  const by = id => items.find(i => i.id === id);
  const lines = [];
  const hub = cfg.role === 'hub';
  lines.push(L('good', 'This PC', hub ? 'It is the HUB: it runs OBS and carries out the buttons.' : `It is a CLIENT: its buttons are sent to the hub PC "${cfg.hub}".`));

  const peers = mesh.peers || [], on = peers.filter(p => p.online);
  lines.push(!peers.length ? L('note', 'Other PCs', 'No other PC is paired yet. Fine if you only use this one.')
    : on.length === peers.length ? L('good', 'Other PCs', `${on.length} paired PC${on.length > 1 ? 's' : ''}, all online.`)
    : L('bad', 'Other PCs', `${on.length} of ${peers.length} paired PCs online. Offline: ${peers.filter(p => !p.online).map(p => p.name).join(', ')}.`));

  const obs = by('obs') || by('hub-obs');
  lines.push(!obs ? L('note', 'OBS', 'Not checked on this PC.')
    : obs.status === 'pass' ? L('good', 'OBS', hub ? 'OBS is running and Link can control it.' : 'The hub reports OBS is running and reachable.')
    : L('bad', 'OBS', `${hub ? 'Link cannot control OBS' : 'The hub cannot reach OBS'}: ${obs.detail}`));

  const nm = by('macros') || by('hub-macros');
  lines.push(!nm ? L('note', 'Scene and mic names', 'Not checked (OBS not reachable or not asked).')
    : nm.status === 'pass' ? L('good', 'Scene and mic names', 'Every scene and input the buttons use exists in OBS.')
    : nm.status === 'warn' ? L('note', 'Scene and mic names', nm.detail)
    : L('bad', 'Scene and mic names', `Some names do not exist in OBS: ${nm.detail}`));

  const ts = by('tailscale');
  lines.push(!ts ? L('note', 'Tailscale', 'Not checked.') : ts.status === 'pass' ? L('good', 'Tailscale', ts.detail) : L('note', 'Tailscale', ts.detail));

  lines.push(cfg.safety?.allowStartStream === true ? L('note', 'Going live', 'Buttons CAN start the stream (setting is on). Turn it off in Settings if you did not mean that.')
    : L('good', 'Going live', 'Buttons cannot start the stream (safe default). Stopping needs a click on the hub.'));
  if (cfg.mesh?.remoteRisky === true) lines.push(L('note', 'Remote stop', 'Other paired PCs may press stop-stream style buttons (setting is on).'));

  if (hub) {
    const p = probe || { state: 'unknown' };
    lines.push(p.state === 'closed' ? L('good', 'OBS port 4455', 'Closed to the network; only this PC can reach OBS directly.')
      : p.state === 'open' ? L('note', 'OBS port 4455', `Reachable from the network (${p.addrs.join(', ')}). The OBS password protects it; closing it is optional (see Docs\\PinguinoLink\\OBS_PORT_AND_MACOS.md).`)
      : p.state === 'obs-off' ? L('note', 'OBS port 4455', 'Nothing is listening: OBS is not running or its WebSocket is off.')
      : L('note', 'OBS port 4455', 'Not checked.'));
  }

  const bad = lines.filter(l => l.status === 'bad').length, note = lines.filter(l => l.status === 'note').length;
  return {
    verdict: bad ? 'problem' : note ? 'attention' : 'good',
    headline: bad ? `${bad} thing${bad > 1 ? 's' : ''} need fixing before you stream.` : note ? 'Ready, with a few notes.' : 'All good. Ready to stream.',
    lines,
  };
}
