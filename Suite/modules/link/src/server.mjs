// INDEX server.mjs: HTTP server of the Link module. runMacro (macro runner + stream guards), readJson, tokenOk/hostOk (auth),
// serve (all routes: peer routes first, then token-gated /api/*). Related: mesh.mjs (devices), obs.mjs (OBS), settings.mjs, macros.mjs, page.html.
// Docs: Docs/PinguinoLink/INDEX.md
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import { createLite, listShared, sharedPath, liteDir } from './lite.mjs';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import * as ts from './tailscale.mjs';
import { runRequests, goesLive, obsState, forgetState, diagnoseObs } from './obs.mjs';
import { log, setLevel } from './log.mjs';
import { prestream } from './prestream.mjs';
import { createMesh } from './mesh.mjs';
import * as settings from './settings.mjs';
import * as macros from './macros.mjs';
import { obsConn } from './vault.mjs';

/** Run a macro. Hub talks to OBS directly; clients forward to the hub over the tailnet. */
export async function runMacro(cfg, name) {
  const steps = cfg.macros[name];
  if (!steps) throw new Error(`unknown macro "${name}" (have: ${Object.keys(cfg.macros).join(', ')})`);
  if (cfg.role === 'hub') {
    const conn = await obsConn(cfg);
    // State-aware guard so a double press cannot end or restart a live stream by mistake.
    const wants = t => steps.some(s => s.type === t);
    const allowStartStream = cfg.safety?.allowStartStream === true;
    if (goesLive(steps) && !allowStartStream) throw Object.assign(new Error('Start Stream is turned off. Turn on "Allow Start Stream" in Link settings (Buttons and safety) to use it.'), { status: 403 });
    if (wants('StartStream') || wants('StopStream')) {
      const st = await obsState(conn, { fresh: true });   // never trust a cached value for a guard
      if (!st.connected) throw Object.assign(new Error(`OBS not reachable: ${st.error}`), { status: 502 });
      if (wants('StartStream') && st.streaming) throw Object.assign(new Error('already live; start ignored'), { status: 409 });
      if (wants('StopStream') && !st.streaming) throw Object.assign(new Error('not streaming; stop ignored'), { status: 409 });
    }
    try { return await runRequests(conn, steps, 5000, { allowStartStream }); } finally { forgetState(); }
  }
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

const PAGE = fs.readFileSync(new URL('./page.html', import.meta.url), 'utf8');

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
const CORE_URL = (process.env.PINGUINO_CORE_URL || 'http://127.0.0.1:8760').replace(/[/]$/, '');
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
  const lastRun = new Map(), activity = [];
  const act = (kind, name, ok, detail = '') => { activity.unshift({ t: Date.now(), kind, name, ok, detail }); activity.length = Math.min(activity.length, 50); };
  /** Cooldown, activity and logging around one macro press. Used by the local route and by paired devices. */
  async function guarded(name, via) {
    const risky = macros.isRisky(cfg, name), now = Date.now();
    const cd = risky ? (cfg.cooldown?.riskyMs ?? 3000) : (cfg.cooldown?.macroMs ?? 600);
    if (cfg.macros[name] && now - (lastRun.get(name) || 0) < cd) { act('macro', name, false, 'ignored: pressed again too fast'); throw Object.assign(new Error(`"${name}" was just pressed; ignored (repeat guard ${cd} ms)`), { status: 429 }); }
    if (cfg.macros[name]) lastRun.set(name, now);
    try {
      const results = cfg.role === 'hub' || !mesh.hasPeer(cfg.hub) ? await runMacro(cfg, name) : await viaHub(name);
      log('info', 'macro', `ran ${name}${via === 'page/api' ? '' : ' (' + via + ')'}`); act('macro', name, true, via === 'page/api' ? '' : via); return results;
    } catch (e) { act('macro', name, false, e.message); log(e.status && e.status < 500 ? 'warn' : 'error', 'macro', `${name} failed: ${e.message}`); throw e; }
  }
  const allItems = async () => [...await prestream(cfg), ...(cfg.prestream?.devices === false ? [] : mesh.prestreamItems()), ...(cfg.role === 'client' && cfg.prestream?.obs !== false ? await mesh.hubPrestream(cfg.hub) : [])];
  /** A client presses a macro on the hub it is paired with (no shared token to copy around). */
  async function viaHub(name) {
    if (!cfg.macros[name]) throw new Error(`unknown macro "${name}" (have: ${Object.keys(cfg.macros).join(', ')})`);
    const r = await mesh.callByName(cfg.hub, '/api/mesh/macro', { name });
    if (r.status !== 200) throw Object.assign(new Error(r.json?.error || `hub answered ${r.status}`), { status: r.status === 401 ? 502 : r.status });
    return r.json.results;
  }
  const sctx = { getName: mesh.getName, setName: mesh.setName };
  setLevel(cfg.log?.level);
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
      if (req.method === 'POST' && req.url === '/api/mesh/macro') {      // a paired device presses one of THIS PC's macros
        const p = mesh.peerAuth(...peer), b = await readJson(req), name = String(b.name || '');
        if (cfg.role !== 'hub') throw Object.assign(new Error('this device is not a hub'), { status: 409 });
        if (cfg.mesh?.allowRemoteMacros === false) throw Object.assign(new Error(`remote macros are turned off on this PC (Link > Settings > Devices)`), { status: 403 });
        if (!cfg.macros[name]) throw Object.assign(new Error(`no macro "${name}" on the hub`), { status: 404 });
        if (macros.isRisky(cfg, name) && !cfg.mesh?.remoteRisky) throw Object.assign(new Error('remote start/stop of the stream is turned off on the hub (Link > Settings > Devices)'), { status: 403 });
        return json(200, { ok: true, results: await guarded(name, `from ${p.name}`) });
      }
      if (req.method === 'POST' && req.url === '/api/mesh/forget') return json(200, mesh.peerUnpaired(...peer));
      if (req.method === 'POST' && (req.url === '/api/mesh/updates/list' || req.url === '/api/mesh/updates/get')) {   // paired PCs fetch update files from this PC
        mesh.peerAuth(...peer);
        if (cfg.mesh?.shareUpdates === false) throw Object.assign(new Error('this PC does not share updates (Link > Settings > Devices)'), { status: 403 });
        if (req.url.endsWith('/list')) { await readJson(req); return json(200, { files: listShared() }); }
        const f = sharedPath(liteDir(), (await readJson(req)).name);
        if (!f) throw Object.assign(new Error('no such update file'), { status: 404 });
        res.writeHead(200, { 'content-type': 'application/octet-stream', 'content-length': fs.statSync(f).size, 'cache-control': 'no-store' });
        return fs.createReadStream(f).pipe(res);
      }
      // The dashboard page on loopback gets the token injected (same-origin only; Host/Origin checks stop other sites).
      if (req.method === 'GET' && (req.url === '/' || req.url === '/index.html') && local) {
        res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-store', 'content-security-policy': FRAME });
        return res.end(PAGE.replace('__TOKEN__', cfg.token).replace('__CORE__', CORE_URL));
      }
      // Pre-stream readiness for the Suite console: no token, no secrets in the output.
      if (req.method === 'GET' && req.url === '/api/prestream') return json(200, { items: await allItems() });
      // Everything else needs the token, loopback included.
      if (!tokenOk(cfg, req.headers['x-link-token'] || req.headers.authorization)) { log('warn', 'http', `unauthorized ${req.method} ${req.url.split('?')[0]} (401)`); return json(401, { error: 'bad token' }); }
      if (req.method === 'GET' && req.url === '/api/status') {
        const t = await ts.status();
        selfName = t.self?.name || selfName;
        return json(200, { role: cfg.role, macros: Object.keys(cfg.macros), macro_buttons: macros.buttons(cfg), ui: { refreshSec: cfg.ui?.refreshSec ?? 4, compact: !!cfg.ui?.compact, accent: cfg.ui?.accent || '', activityCount: cfg.ui?.activityCount ?? 15, showReadiness: cfg.ui?.showReadiness !== false }, tailscale: t, peers: mesh.status().peers });
      }
      if (req.method === 'GET' && req.url === '/api/integrations') {   // Integrations tab (module token)
        const items = (await allItems()).map(i => ({ id: i.id, name: i.label, group: 'PinguinoLink', status: i.status === 'pass' ? 'connected' : i.status === 'fail' ? 'error' : 'off', detail: i.detail, help: i.help }));
        return json(200, { items });
      }
      if (req.method === 'GET' && req.url === '/api/settings') return json(200, { groups: settings.view(cfg, sctx), peers: ((await ts.status()).peers || []).map(p => p.name) });
      if (req.method === 'POST' && req.url === '/api/settings') { const b = await readJson(req); return json(200, settings.apply(cfg, sctx, b.changes, { confirmRole: b.confirm_role === true })); }
      if (req.method === 'GET' && req.url === '/api/macros') {
        const o = cfg.role === 'hub' ? await obsState(await obsConn(cfg)) : { connected: false };
        return json(200, { macros: macros.list(cfg), kinds: Object.entries(macros.KINDS).map(([kind, k]) => ({ kind, label: k.label, param: k.param || null, risky: !!k.risky })), scenes: o.scenes || [], inputs: o.inputs || [], connected: !!o.connected, cli: { node: process.execPath, script: fileURLToPath(new URL('./cli.mjs', import.meta.url)) } });
      }
      if (req.method === 'POST' && req.url.startsWith('/api/macros/')) {
        const b = await readJson(req), act = req.url.slice('/api/macros/'.length);
        if (act === 'set') return json(200, macros.set(cfg, b));
        if (act === 'delete') return json(200, macros.remove(cfg, String(b.name)));
        if (act === 'move') return json(200, macros.move(cfg, String(b.name), Number(b.dir)));
        if (act === 'check') {
          if (cfg.role !== 'hub') return json(200, { ok: null, note: 'This device is a client; names are checked on the hub.' });
          const o = await obsState(await obsConn(cfg));
          if (!o.connected) return json(200, { ok: null, note: `OBS not reachable: ${o.error}` });
          const miss = macros.missing(cfg, String(b.name), o);
          return json(200, { ok: !miss.length, missing: miss });
        }
        return json(404, { error: 'not found' });
      }
      if (req.method === 'GET' && req.url === '/api/activity') return json(200, { items: activity.slice(0, cfg.ui?.activityCount ?? 15) });
      if (req.method === 'POST' && req.url === '/api/scene') {
        const b = await readJson(req);
        if (cfg.role !== 'hub') throw Object.assign(new Error('Scene buttons work on the hub (the PC running OBS)'), { status: 409 });
        const conn = await obsConn(cfg), o = await obsState(conn), name = String(b.name || '');
        if (!o.connected) throw Object.assign(new Error(`OBS not reachable: ${o.error}`), { status: 502 });
        if (!o.scenes.includes(name)) throw Object.assign(new Error('no such scene in OBS'), { status: 404 });
        await runRequests(conn, [{ type: 'SetCurrentProgramScene', data: { sceneName: name } }]);
        forgetState(); act('scene', name, true); log('info', 'scene', `switched to "${name}"`);
        return json(200, { ok: true });
      }
      if (req.method === 'GET' && req.url === '/api/export') {
        const ex = macros.exportAll(cfg), changed = settings.view(cfg, sctx).flatMap(g => g.fields).filter(f => f.changed && f.key !== 'role');
        return json(200, { format: 'pinguinolink-settings', version: 1, settings: Object.fromEntries(changed.map(f => [f.key, f.value])), macros: ex.macros, skipped_custom_steps: ex.skipped });
      }
      if (req.method === 'POST' && req.url === '/api/import') {
        const b = await readJson(req), d = b.data || {};
        if (d.format !== 'pinguinolink-settings') throw Object.assign(new Error('not a PinguinoLink settings file'), { status: 400 });
        const res = settings.apply(cfg, sctx, Object.fromEntries(Object.entries(d.settings || {}).filter(([k]) => k !== 'role')), {});
        const n = macros.importAll(cfg, d.macros || []);
        act('settings', 'import', true, `${res.changed.length} settings, ${n} macros`); log('info', 'settings', `imported ${res.changed.length} settings and ${n} macros`);
        return json(200, { ok: true, settings: res.changed.length, macros: n });
      }
      if (req.method === 'POST' && req.url === '/api/test-obs') {      // Test button next to OBS_WS_PASSWORD in the key vault
        const d = await diagnoseObs(await obsConn(cfg));
        return json(d.ok ? 200 : 424, d.ok ? { ok: true, detail: d.detail } : { error: d.detail, code: d.code });
      }
      if (req.method === 'GET' && req.url === '/api/obs') {            // read-only OBS state for the page
        if (cfg.role !== 'hub') return json(200, { connected: false, role: cfg.role, error: 'this device is a client; OBS runs on the hub' });
        const { scenes, inputs, ...st } = await obsState(await obsConn(cfg));
        return json(200, cfg.ui?.sceneButtons ? { ...st, scenes } : st);
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
        return json(200, { ok: true, results: await guarded(m[1], 'page/api') });
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
  // PinguinoLite contract folder (Docs/LITE_APP.md): local listing/checking only for now.
  const inTest = process.env.PINGUINO_MESH_TEST || (process.env.PINGUINO_DATA_DIR || '').toLowerCase().startsWith(os.tmpdir().toLowerCase());
  if (!inTest || process.env.PINGUINO_LITE_DIR) {
    const probe = async m => { try { return (await fetch(`http://127.0.0.1:${m.port}${m.health || '/'}`, { signal: AbortSignal.timeout(800) })).status < 500; } catch { return false; } };
    const lite = createLite({ getHealth: probe, peers: { names: () => mesh.peerNames(), enabled: () => cfg.mesh?.fetchUpdates !== false, post: (n, route, body, t) => mesh.rawByName(n, route, body, t) } });
    lite.start().catch(e => log('warn', 'lite', `could not start: ${e.message}`));
    for (const sig of ['SIGTERM', 'SIGINT', 'SIGBREAK']) process.on(sig, () => { lite.stop(); log('info', 'server', `stopping (${sig})`); process.exit(0); });
  }
  mesh.start();
  await bindTail();
  if (!tailBound) log('warn', 'server', 'Tailscale is not running; only this machine can reach the service until it is');
  setInterval(bindTail, 15000).unref();
}
