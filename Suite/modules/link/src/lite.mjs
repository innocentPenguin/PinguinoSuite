// INDEX lite.mjs: Link's side of the PinguinoLite contract (Docs/LITE_APP.md). File drop in <lite dir>. Package ops live in pkg.mjs; tests litecheck.mjs + pkgcheck.mjs.
// Writes: status.json (heartbeat), installed.json, modules_catalog.json, update_status.json. Reads+consumes: requests/*.json.
// Sources are LOCAL only (Suite/modules/*/module.json, optional <lite dir>/packages). No internet, no downloads, no executing anything.
// install/update/uninstall/rollback: local zip packages (pkg.mjs), only for a stopped module. start/stop/restart/selfupdate-apply are
// not implemented yet: such requests are consumed and reported as an error, never silently dropped.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { log } from './log.mjs';
import { installPackage, uninstallModule, rollbackModule } from './pkg.mjs';

const SUITE = fileURLToPath(new URL('../../../../', import.meta.url));   // .../PinguinoSuite/
const MODULES = path.join(SUITE, 'Suite', 'modules');
const ID = /^[a-z0-9_-]{1,40}$/;
const iso = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z');

export const liteDir = () => process.env.PINGUINO_LITE_DIR || path.join(SUITE, 'Data', 'lite');

/** Atomic JSON write: tmp file then rename. */
function writeJson(dir, name, obj) {
  fs.mkdirSync(dir, { recursive: true });
  const f = path.join(dir, name), t = f + '.tmp';
  fs.writeFileSync(t, JSON.stringify({ schema: 1, ...obj }, null, 2));
  fs.renameSync(t, f);
}
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8').replace(/^﻿/, '')); } catch { return null; } };

/** 1.10.0 > 1.9.0 */
export function cmpVersion(a, b) {
  const p = v => String(v).split('.').map(n => parseInt(n, 10) || 0);
  const x = p(a), y = p(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d < 0 ? -1 : 1; }
  return 0;
}

/** Modules found on disk under Suite/modules. */
export function scanModules(root = MODULES) {
  const out = [];
  let names = []; try { names = fs.readdirSync(root); } catch {}
  for (const n of names) {
    const dir = path.join(root, n), m = readJson(path.join(dir, 'module.json'));
    if (!m || !ID.test(m.id || '')) continue;
    const pkg = readJson(path.join(dir, 'package.json'));
    out.push({ id: m.id, name: m.name || m.id, description: String(m.desc || '').slice(0, 200), version: String(m.version || pkg?.version || '1.0.0'), path: dir });
  }
  return out;
}

export function createLite({ getHealth, peers, version = '0.3.0', dir = liteDir(), modulesRoot = MODULES } = {}) {
  const busy = {};
  let timer = null, polling = false, lastError = null, mstate = {};
  const errors = {};                                           // last failure per module id (shown in installed.json)
  const fail = (msg, keepStatus) => {
    lastError = msg; log('warn', 'lite', msg);
    writeJson(dir, 'update_status.json', { ...(readJson(path.join(dir, 'update_status.json')) || {}), result: 'error', error: msg });
  };

  async function moduleState(m) {
    if (m.id === 'link') return 'running';                       // we are Link
    try { const mod = readJson(path.join(m.path, 'module.json')); if (mod?.port && getHealth) return (await getHealth(mod)) ? 'running' : 'stopped'; } catch {}
    return 'stopped';
  }

  async function writeInstalled() {
    const mods = {};
    mstate = {};
    for (const m of scanModules(modulesRoot)) { const state = await moduleState(m); mods[m.id] = { version: m.version, installed_at: iso(), path: m.path, state, ...(errors[m.id] ? { error: errors[m.id] } : {}) }; mstate[m.id] = { state, detail: state === 'running' ? 'answers on its health check' : 'not answering', ...(state === 'stopped' ? { fix_hint: 'Start it from the full Suite' } : {}) }; }
    writeJson(dir, 'installed.json', { updated_at: iso(), modules: mods });
    return mods;
  }

  /** Catalog: what exists. Local source = the modules on disk, plus <dir>/packages/<id>-<ver>.zip as newer versions. */
  function writeCatalog() {
    const best = {};
    for (const m of scanModules(modulesRoot)) best[m.id] = { id: m.id, name: m.name, description: m.description, latest_version: m.version };
    let pk = []; try { pk = fs.readdirSync(path.join(dir, 'packages')); } catch {}
    for (const f of pk) {
      const mm = /^([a-z0-9_-]{1,40})-(\d+(?:\.\d+)*)\.zip$/.exec(f); if (!mm) continue;
      const [, id, v] = mm, cur = best[id] || { id, name: id, description: '', latest_version: '0' };
      if (cmpVersion(v, cur.latest_version) > 0) { let sha; try { sha = fs.readFileSync(path.join(dir, 'packages', f + '.sha256'), 'utf8').trim().split(/\s+/)[0]; } catch {} best[id] = { ...cur, latest_version: v, size_bytes: fs.statSync(path.join(dir, 'packages', f)).size, package: 'packages/' + f, ...(sha ? { sha256: sha } : {}) }; }
    }
    writeJson(dir, 'modules_catalog.json', { generated_at: iso(), channel: 'stable', source: 'local', modules: Object.values(best) });
    return Object.values(best);
  }

  /** Lite's own update from a LOCAL file: <dir>/staging/PinguinoLite-<ver>-setup.exe + .sha256. Verified hash -> update_manifest.json. Never executed here. */
  function checkLiteUpdate() {
    const cur = process.env.PINGUINO_LITE_VERSION || '0.0.0';
    let best = null;
    try { for (const f of fs.readdirSync(path.join(dir, 'staging'))) { const m = /^PinguinoLite-(\d+(?:\.\d+)*)-setup\.exe$/.exec(f); if (m && (!best || cmpVersion(m[1], best.v) > 0)) best = { v: m[1], f }; } } catch {}
    if (!best || cmpVersion(best.v, cur) <= 0) { try { fs.unlinkSync(path.join(dir, 'update_manifest.json')); } catch {} return false; }
    const file = path.join(dir, 'staging', best.f);
    let want = ''; try { want = fs.readFileSync(file + '.sha256', 'utf8').trim().split(/\s+/)[0].toLowerCase(); } catch {}
    const got = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    if (!/^[0-9a-f]{64}$/.test(want) || want !== got) { log('warn', 'lite', `staged Lite ${best.v} has no valid .sha256 or the hash differs; not offered`); return false; }
    writeJson(dir, 'update_manifest.json', { app: 'pinguino-lite', latest_version: best.v, published_at: iso(), notes: 'local file', staged_file: 'staging\\' + best.f, sha256: got, min_os: '10.0' });
    return true;
  }

  function writeUpdateStatus(installed, catalog, result = 'ok', error) {
    const n = catalog.filter(c => installed[c.id] && cmpVersion(c.latest_version, installed[c.id].version) > 0).length;
    writeJson(dir, 'update_status.json', { last_check_at: iso(), result, ...(error ? { error } : {}), updates_available: n, lite_update_available: checkLiteUpdate() });
    return n;
  }

  /** Fetch newer packages / Lite installers from paired PCs into the local folders. Hash-checked; nothing is installed or run. */
  async function syncFromPeers() {
    if (!peers || peers.enabled?.() === false) return { fetched: 0 };
    let fetched = 0;
    for (const peer of peers.names()) {
      let items;
      try { const r = await peers.post(peer, '/api/mesh/updates/list', {}, 8000); if (!r.ok) continue; items = (await r.json()).files || []; } catch { continue; }
      const installed = Object.fromEntries(scanModules(modulesRoot).map(m => [m.id, m.version]));
      const live = process.env.PINGUINO_LITE_VERSION || '0.0.0';
      for (const it of items.slice(0, 50)) {
        if (!SHARE_RE.test(it?.name || '') || !/^[0-9a-f]{64}$/.test(it.sha256 || '') || !(it.size <= MAX_SHARE)) continue;
        const zip = /^([a-z0-9_-]+)-(\d+(?:\.\d+)*)\.zip$/.exec(it.name), exe = /^PinguinoLite-(\d+(?:\.\d+)*)-setup\.exe$/.exec(it.name);
        const ver = zip ? zip[2] : exe[1];
        if (zip ? (zip[1] === 'link' || (installed[zip[1]] && cmpVersion(ver, installed[zip[1]]) <= 0)) : cmpVersion(ver, live) <= 0) continue;
        const dest = path.join(shareDir(dir, it.name), it.name);
        if (fs.existsSync(dest) && sidecarHash(dest) === it.sha256) continue;
        try {
          const r = await peers.post(peer, '/api/mesh/updates/get', { name: it.name }, 120000);
          if (!r.ok) continue;
          const buf = Buffer.from(await r.arrayBuffer());
          if (buf.length > MAX_SHARE || crypto.createHash('sha256').update(buf).digest('hex') !== it.sha256) { log('warn', 'lite', `${it.name} from ${peer} failed the hash check; discarded`); continue; }
          fs.mkdirSync(path.dirname(dest), { recursive: true });
          fs.writeFileSync(dest + '.tmp', buf); fs.renameSync(dest + '.tmp', dest);
          fs.writeFileSync(dest + '.sha256.tmp', it.sha256 + '\n'); fs.renameSync(dest + '.sha256.tmp', dest + '.sha256');
          fetched++; log('info', 'lite', `fetched ${it.name} from ${peer} (hash verified)`);
        } catch (e) { log('warn', 'lite', `could not fetch ${it.name} from ${peer}: ${e.message}`); }
      }
    }
    return { fetched };
  }

  async function refresh(result = 'ok', error) {
    const installed = await writeInstalled(), catalog = writeCatalog();
    return writeUpdateStatus(installed, catalog, result, error);
  }

  function writeStatus() {
    writeJson(dir, 'status.json', { writer: { name: 'PinguinoLink', version, pid: process.pid, heartbeat_at: iso() },
      connector: { state: 'connected', detail: 'local sources only (no update server)' }, busy: { ...busy }, modules: mstate, ...(lastError ? { last_error: lastError } : {}) });
  }

  /** Handle one request file (already parsed). */
  async function handle(req) {
    const action = req?.action, id = req?.id;
    if (action === 'check') { busy.lite = 'checking'; writeStatus(); try { await syncFromPeers().catch(() => {}); await refresh(); } finally { delete busy.lite; } return; }
    if (['install', 'update', 'uninstall', 'rollback'].includes(action)) {
      if (!ID.test(id || '')) { fail(`${action}: missing or bad module id`); return; }
      const verb = { install: 'installing', update: 'updating', uninstall: 'uninstalling', rollback: 'updating' }[action];
      busy[id] = verb; writeStatus();
      try {
        const cur = scanModules(modulesRoot).find(m => m.id === id);
        if (cur && action !== 'install' && (await moduleState(cur)) === 'running') throw new Error(`${id} is running; stop it first, then try again`);
        const a = { liteDir: dir, modulesRoot, id, cmp: cmpVersion };
        const r = action === 'install' ? installPackage(a) : action === 'update' ? installPackage({ ...a, update: true }) : action === 'uninstall' ? uninstallModule(a) : rollbackModule(a);
        delete errors[id];
        log('info', 'lite', `${action} ${id} ok${r.version ? ' -> ' + r.version : ''}`);
        await refresh();
      } catch (e) {
        errors[id] = String(e.message || e).slice(0, 200);
        fail(`${action} ${id}: ${errors[id]}`, true);
        await refresh('error', errors[id]).catch(() => {});
      } finally { delete busy[id]; writeStatus(); }
      return;
    }
    if (['start', 'stop', 'restart', 'selfupdate-apply'].includes(action)) {
      const msg = `${action} is not available yet (Link currently supports local listing and checking only)`;
      lastError = msg; log('warn', 'lite', msg + (id && ID.test(id) ? ` [${id}]` : ''));
      writeJson(dir, 'update_status.json', { ...(readJson(path.join(dir, 'update_status.json')) || {}), result: 'error', error: msg });
      return;
    }
    log('warn', 'lite', 'ignored a request with an unknown action');
  }

  async function poll() {
    if (polling) return; polling = true;
    try {
      const rd = path.join(dir, 'requests');
      let files = []; try { files = fs.readdirSync(rd); } catch {}
      files = files.filter(f => f.endsWith('.json') && !f.endsWith('.tmp')).sort((a, b) => (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));
      for (const f of files) {
        const p = path.join(rd, f), req = readJson(p);
        try { fs.unlinkSync(p); } catch { continue; }            // taken
        if (req && req.schema === 1) { try { await handle(req); } catch (e) { lastError = String(e.message || e).slice(0, 200); log('error', 'lite', lastError); } }
        writeStatus();
      }
    } finally { polling = false; }
  }

  return {
    async start() {
      fs.mkdirSync(path.join(dir, 'requests'), { recursive: true });
      await refresh(); writeStatus();
      let n = 0;
      timer = setInterval(() => { poll().catch(() => {}); if (++n % 15 === 0) { writeStatus(); } if (n % 300 === 0) syncFromPeers().catch(() => {}).then(() => refresh()).catch(() => {}); }, 1000);
      timer.unref?.();
      log('info', 'lite', `PinguinoLite contract folder: ${dir}`);
    },
    stop() { clearInterval(timer); },
    poll, refresh, handle, writeStatus, syncFromPeers,
  };
}

// ---- sharing update files between this user's own paired PCs (served only to paired peers, see server.mjs) ----
const SHARE_RE = /^(?:[a-z0-9_-]{1,40}-\d+(?:\.\d+)*\.zip|PinguinoLite-\d+(?:\.\d+)*-setup\.exe)$/;
const MAX_SHARE = 300 * 1024 * 1024;
const shareDir = (dir, name) => path.join(dir, name.endsWith('.zip') ? 'packages' : 'staging');
const sidecarHash = f => { try { const h = fs.readFileSync(f + '.sha256', 'utf8').trim().split(/\s+/)[0].toLowerCase(); return /^[0-9a-f]{64}$/.test(h) ? h : ''; } catch { return ''; } };

/** Files this PC offers to paired PCs: only hash-sidecar'd packages and staged Lite installers. */
export function listShared(dir = liteDir()) {
  const out = [];
  for (const sub of ['packages', 'staging']) {
    let names = []; try { names = fs.readdirSync(path.join(dir, sub)); } catch {}
    for (const name of names) {
      if (!SHARE_RE.test(name)) continue;
      const f = path.join(dir, sub, name), sha = sidecarHash(f);
      let st; try { st = fs.statSync(f); } catch { continue; }
      if (sha && st.isFile() && st.size <= MAX_SHARE) out.push({ name, size: st.size, sha256: sha });
    }
  }
  return out;
}
/** Absolute path of a shared file, or null. The name is checked against a strict pattern: nothing else can be read. */
export function sharedPath(dir, name) {
  const n = String(name || '');
  const base = n.endsWith('.sha256') ? n.slice(0, -7) : n;
  if (!SHARE_RE.test(base)) return null;
  const f = path.join(shareDir(dir, base), n);
  return fs.existsSync(f) && fs.statSync(f).isFile() ? f : null;
}
