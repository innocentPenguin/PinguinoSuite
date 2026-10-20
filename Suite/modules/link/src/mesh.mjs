// INDEX mesh.mjs: device mesh over Tailscale only. createMesh: addressing, pairing (code + Allow), peer messages, heartbeat, status.
// Related: server.mjs (routes /api/mesh/*), settings.mjs (mesh.*), Docs/PinguinoLink/11-DEVICE-MESH.md, Docs/PinguinoLink/INDEX.md
// Device mesh transport (P1): registry, pairing by code, per-message peer authentication, broadcast to peers and
// forwarding of peer messages to the Suite core. Election of the master is the CORE's job (MODULE_CONTRACT "Devices: master / auxiliary").
// Transport is Tailscale only: peers must be tailnet addresses. No custom crypto: the tailnet (WireGuard) encrypts,
// pairing hands each side a random per-peer token. See Docs/PinguinoLink/11-DEVICE-MESH.md.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { DIR } from './config.mjs';
import { log } from './log.mjs';
import * as ts from './tailscale.mjs';

const TEST = process.env.PINGUINO_MESH_TEST === '1';   // test hook only: allows loopback peers
const BEAT_MS = 3000, APPROVE_MS = 90000;
const CORE = process.env.PINGUINO_CORE_URL || 'http://127.0.0.1:8760';
const FILE = path.join(DIR, 'mesh.json');

const rnd = n => crypto.randomBytes(n).toString('hex');
const sha = s => crypto.createHash('sha256').update(String(s ?? '')).digest();
const eq = (a, b) => crypto.timingSafeEqual(sha(a), sha(b));
export const fail = (status, error, extra) => Object.assign(new Error(error), { status, extra });
const str = (v, n = 64) => String(v ?? '').replace(/[^\x20-\x7e]/g, '').slice(0, n);
const bare = ip => String(ip || '').replace(/^::ffff:/, '');
const urlHost = a => (a.includes(':') ? `[${a}]` : a);

const PEER_HELP = {
  title: 'Paired device',
  summary: 'Another PC paired with this one over Tailscale. Green = it answered Link within the last 12 seconds.',
  steps: [
    'Offline: check the device is on, Tailscale is running there and Link is started.',
    'If it says the peer no longer trusts this device, unpair on both sides (Link page > Devices) and pair again.',
    'Unpair a device you no longer use from the same card.',
  ],
  fix: { label: 'Open Link', route: 'm:link' },
};

export function isTailnetIp(ip) {
  ip = bare(ip);
  const m = ip.match(/^100\.(\d+)\./);
  if (m) return +m[1] >= 64 && +m[1] <= 127;
  return ip.toLowerCase().startsWith('fd7a:115c:a1e0:');
}

function cleanDevice(d) {
  const id = str(d?.id);
  if (!/^[\w-]{8,64}$/.test(id)) throw fail(400, 'bad device id');
  return { id, name: str(d.name) || 'device', os: str(d.os, 16) };
}

export function createMesh(cfg, { port }) {
  const OFFLINE_MS = () => (cfg.mesh?.offlineSec ?? 12) * 1000, CODE_MS = () => (cfg.mesh?.codeMinutes ?? 5) * 60000;
  let state = {};
  try { state = JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch {}
  state.self ||= { id: crypto.randomUUID(), name: os.hostname() };
  state.self.os = os.platform();
  state.peers ||= {};
  const rt = new Map();                 // runtime per peer: last_seen, online, fails, nextTry, error
  const R = id => { let r = rt.get(id); if (!r) rt.set(id, r = { last_seen: 0, online: false, fails: 0, nextTry: 0, error: '' }); return r; };
  let pairing = null;                   // {code, expires, attempts}
  const pending = new Map();            // id -> {id, device, remote, port, token, decide}
  let busy = false, coreErr = '';

  const save = () => {
    try { fs.mkdirSync(DIR, { recursive: true }); fs.writeFileSync(FILE, JSON.stringify(state, null, 2), { mode: 0o600 }); }
    catch (e) { log('error', 'mesh', `cannot save mesh.json: ${e.code || e.message}`); }
  };
  save();
  const peerList = () => Object.values(state.peers);
  const headersFor = p => ({ 'content-type': 'application/json', 'x-link-peer': state.self.id, 'x-link-token': p.outbound });
  const url = (p, route) => `http://${urlHost(p.addr)}:${p.port}${route}`;

  function seen(p) {
    const r = R(p.id);
    r.last_seen = Date.now(); r.fails = 0; r.error = '';
    if (!r.online) { r.online = true; log('info', 'peer', `${p.name} is online`); }
  }
  function markOnline() {
    for (const p of peerList()) {
      const r = R(p.id), on = Date.now() - r.last_seen < OFFLINE_MS();
      if (r.online && !on) log('warn', 'peer', `${p.name} is offline${r.error ? ` (${r.error})` : ''}`);
      r.online = on;
    }
  }
  /** POST to a peer with its token. Updates liveness and backoff. Returns the parsed JSON body. */
  async function call(p, route, body, timeout = 1500) {
    const r = R(p.id);
    try {
      const res = await fetch(url(p, route), { method: 'POST', headers: headersFor(p), body: JSON.stringify(body), signal: AbortSignal.timeout(timeout) });
      if (res.status === 401) throw new Error('peer no longer trusts this device (unpair and pair again)');
      if (!res.ok) throw new Error(`peer answered ${res.status}`);
      seen(p);
      return await res.json().catch(() => ({}));
    } catch (e) {
      r.fails++; r.nextTry = Date.now() + Math.min(15000, 1000 * 2 ** r.fails);
      const msg = e.name === 'TimeoutError' ? 'no answer' : (e.cause?.code || e.message);
      if (r.error !== msg) log('warn', 'peer', `${route} to ${p.name} failed: ${msg}`);
      r.error = msg;
      throw e;
    }
  }
  /** Like call(), but returns {status, json} for any HTTP answer so the caller can show the peer's own error text. */
  async function callByName(name, route, body, timeout = 8000) {
    const p = peerList().find(x => x.name.toLowerCase() === String(name).toLowerCase());
    if (!p) return null;
    try {
      const res = await fetch(url(p, route), { method: 'POST', headers: headersFor(p), body: JSON.stringify(body), signal: AbortSignal.timeout(timeout) });
      if (res.status !== 401) seen(p);
      return { status: res.status, json: await res.json().catch(() => ({})) };
    } catch (e) { throw Object.assign(new Error(`cannot reach ${p.name}: ${e.name === 'TimeoutError' ? 'no answer' : (e.cause?.code || e.message)}`), { status: 502 }); }
  }
  /** Items from the hub's own pre-stream report (client view), prefixed so they read as "Hub: ...". */
  async function hubPrestream(name) {
    const p = peerList().find(x => x.name.toLowerCase() === String(name).toLowerCase());
    if (!p) return [{ id: 'hub-obs', label: 'OBS on the hub', status: 'warn', detail: `no hub is paired. If this PC runs OBS and is the only streaming PC: Link page > Settings > Role > hub > confirm. Otherwise pair with "${name}" (needs Tailscale).` }];
    try {
      const res = await fetch(url(p, '/api/prestream'), { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`hub answered ${res.status}`);
      seen(p);
      return ((await res.json()).items || []).filter(i => ['obs', 'macros'].includes(i.id)).map(i => ({ id: `hub-${i.id}`, label: `${p.name}: ${i.label}`, status: i.status, detail: i.detail, help: i.help }));
    } catch (e) { return [{ id: 'hub-obs', label: `OBS on ${p.name}`, status: 'fail', detail: `cannot ask ${p.name}: ${e.cause?.code || e.message}` }]; }
  }
  async function tick() {
    if (busy) return;
    busy = true;
    try {
      await Promise.all(peerList().filter(p => Date.now() >= R(p.id).nextTry).map(p => call(p, '/api/mesh/heartbeat', { device: state.self }).catch(() => {})));
      markOnline();
    } finally { busy = false; }
  }

  // ---- addressing: tailnet only ----
  async function resolveAddr(input) {
    const a = String(input || '').trim();
    if (TEST && /^(127\.0\.0\.1|localhost)$/.test(a)) return '127.0.0.1';
    if (isTailnetIp(a)) return a;
    const want = a.toLowerCase(), st = await ts.status();
    const p = st.peers?.find(x => x.name.toLowerCase() === want || x.name.toLowerCase() === want.replace(/\..*$/, ''));
    if (p?.ip && isTailnetIp(p.ip)) return p.ip;
    throw fail(400, 'address must be a Tailscale device (its name or 100.x address). Other networks are not allowed.');
  }

  // ---- pairing ----
  const attempts = [];                  // global limiter for unauthenticated pair requests
  async function pairRequest(remote, body) {
    const now = Date.now();
    while (attempts.length && now - attempts[0] > 60000) attempts.shift();
    if (attempts.length >= 10) throw fail(429, 'too many pairing attempts');
    attempts.push(now);
    if (!pairing || now > pairing.expires) throw fail(403, 'no pairing in progress on this device');
    if (!TEST && !isTailnetIp(remote)) throw fail(403, 'pairing is only accepted over Tailscale');
    if (!eq(body?.code, pairing.code)) {
      pairing.attempts++;
      log('warn', 'pairing', `wrong pairing code from ${bare(remote)} (${pairing.attempts}/3)`);
      if (pairing.attempts >= 3) { pairing = null; log('warn', 'pairing', 'pairing code cancelled after 3 wrong tries'); }
      throw fail(403, 'wrong code');
    }
    const device = cleanDevice(body.device);
    if (device.id === state.self.id) throw fail(400, 'cannot pair with itself');
    const peerPort = Number(body.port), token = str(body.token, 128);
    if (!Number.isInteger(peerPort) || peerPort < 1 || peerPort > 65535 || token.length < 32) throw fail(400, 'bad request');
    const id = rnd(8);
    log('info', 'pairing', `${device.name} (${device.os}) asks to pair; waiting for approval`);
    const ok = await new Promise(decide => {
      pending.set(id, { id, device, remote: bare(remote), port: peerPort, token, decide });
      setTimeout(() => { if (pending.delete(id)) decide(false); }, APPROVE_MS).unref();
    });
    if (!ok) { log('warn', 'pairing', `pairing with ${device.name} denied or timed out`); throw fail(403, 'pairing denied or timed out'); }
    pairing = null;                                      // single use
    const mine = rnd(24);
    state.peers[device.id] = { ...device, addr: bare(remote), port: peerPort, inbound: token, outbound: mine, paired: new Date().toISOString() };
    save();
    log('info', 'pairing', `paired with ${device.name}`);
    return { device: state.self, token: mine };
  }
  function approve(id, allow) {
    const p = pending.get(id);
    if (!p) throw fail(404, 'no such pairing request');
    pending.delete(id);
    p.decide(!!allow);
    return { ok: true };
  }
  async function join(addrInput, code) {
    let addr = String(addrInput || '').trim(), peerPort = cfg.port;
    const pm = addr.match(/^([^[\]:]+):(\d+)$/);
    if (pm) { addr = pm[1]; peerPort = Number(pm[2]); }
    const ip = await resolveAddr(addr);
    const mine = rnd(24);
    log('info', 'pairing', `asking ${ip}:${peerPort} to pair; waiting for approval there`);
    let res;
    try {
      res = await fetch(`http://${urlHost(ip)}:${peerPort}/api/mesh/pair/request`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ code: String(code || '').trim(), device: state.self, port, token: mine }), signal: AbortSignal.timeout(APPROVE_MS + 10000),
      });
    } catch (e) { throw fail(502, `cannot reach ${ip}:${peerPort} (${e.cause?.code || e.message})`); }
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw fail(res.status === 403 ? 403 : 502, j.error || `peer answered ${res.status}`);
    const device = cleanDevice(j.device);
    state.peers[device.id] = { ...device, addr: ip, port: peerPort, inbound: str(j.token, 128), outbound: mine, paired: new Date().toISOString() };
    save();
    log('info', 'pairing', `paired with ${device.name}`);
    tick();
    return { ok: true, device: { id: device.id, name: device.name } };
  }

  // ---- peer messages ----
  const authPeer = (peerId, token) => {
    const p = state.peers[str(peerId)];
    if (!p || !eq(token, p.inbound)) throw fail(401, 'unknown peer or bad token');
    return p;
  };
  function heartbeat(peerId, token, body) {
    const p = authPeer(peerId, token);
    if (body?.device?.name) { const n = str(body.device.name); if (n && n !== p.name) { p.name = n; save(); } }
    seen(p);
    return { ok: true, device: state.self };
  }
  /** Send {type,payload} unchanged to every paired peer (core -> Link). Returns how many accepted it. */
  async function broadcast(body) {
    const ps = peerList().filter(p => Date.now() >= R(p.id).nextTry || R(p.id).online);
    const res = await Promise.all(ps.map(p => call(p, '/api/mesh/msg', body).then(() => 1, () => 0)));
    markOnline();
    return res.reduce((a, b) => a + b, 0);
  }
  /** A peer's message arrived: authenticate it, hand it to the core (Link -> core). */
  async function receive(peerId, token, body) {
    const p = authPeer(peerId, token);
    seen(p);
    if (!body || typeof body.type !== 'string' || typeof body.payload !== 'object') throw fail(400, 'bad message');
    const t = process.env.PINGUINO_API_TOKEN || '';
    try {
      const r = await fetch(`${CORE}/api/device/peer`, {
        method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${t}`, 'x-link-token': t },
        body: JSON.stringify({ type: body.type, payload: body.payload, from: p.name }), signal: AbortSignal.timeout(2000),
      });
      if (!r.ok) throw new Error(`core answered ${r.status}`);
      coreErr = '';
    } catch (e) {
      const msg = e.cause?.code || e.message;
      if (msg !== coreErr) log('warn', 'core', `cannot hand a peer message to the core: ${msg}`);
      coreErr = msg;
      throw fail(502, 'core not reachable');
    }
    return { ok: true };
  }
  /** Peer asks us to forget it (it unpaired from its side). */
  function peerUnpaired(peerId, token) {
    const p = authPeer(peerId, token);
    delete state.peers[p.id]; rt.delete(p.id); save();
    log('warn', 'pairing', `${p.name} unpaired this device`);
    return { ok: true };
  }
  async function removePeer(id) {
    const p = state.peers[id];
    if (!p) throw fail(404, 'no such device');
    await call(p, '/api/mesh/forget', {}, 1500).catch(() => {});     // best effort; if it is offline it will see a 401 later
    delete state.peers[id]; rt.delete(id); save();
    log('warn', 'pairing', `unpaired ${p.name}`);
    return { ok: true };
  }

  // ---- UI/status ----
  function status() {
    return {
      self: state.self,
      peers: peerList().map(p => ({ id: p.id, name: p.name, os: p.os, online: R(p.id).online, last_seen: R(p.id).last_seen || null, error: R(p.id).error })),
      pairing: pairing && Date.now() < pairing.expires ? { code: pairing.code, expires: pairing.expires } : null,
      pending: [...pending.values()].map(p => ({ id: p.id, name: p.device.name, os: p.device.os, from: p.remote })),
    };
  }
  function startPairing() {
    pairing = { code: String(crypto.randomInt(0, 1e6)).padStart(6, '0'), expires: Date.now() + CODE_MS(), attempts: 0 };
    log('info', 'pairing', `pairing code created (valid ${CODE_MS() / 60000} minutes)`);
    return { code: pairing.code, expires: pairing.expires };
  }
  const getName = () => state.self.name;
  function setName(name) {
    state.self.name = str(name) || state.self.name; save();
    return { ok: true };
  }
  function prestreamItems() {
    const peers = peerList();
    if (!peers.length) return [{ id: 'mesh', label: 'Device mesh', status: 'pass', detail: 'no paired devices; this device runs alone' }];
    return peers.map(p => { const r = R(p.id);
      return { id: `peer-${p.id.slice(0, 8)}`, label: `Device ${p.name}`, status: r.online ? 'pass' : 'warn', detail: r.online ? 'online' : `offline${r.error ? `: ${r.error}` : ''}`, help: PEER_HELP }; });
  }
  function start() {
    log('info', 'mesh', `device "${state.self.name}" id ${state.self.id.slice(0, 8)}, ${peerList().length} paired`);
    setInterval(tick, BEAT_MS).unref();
    tick();
  }
  return { hubPrestream, hasPeer: name => peerList().some(p => p.name.toLowerCase() === String(name).toLowerCase()), peerAuth: authPeer, callByName, start, tick, status, pairRequest, approve, join, heartbeat, broadcast, receive, peerUnpaired, removePeer, startPairing, setName, getName, prestreamItems };
}
