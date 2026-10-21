// INDEX lite.mjs: Link's side of the PinguinoLite contract (Docs/LITE_APP.md). File drop in <lite dir>.
// Writes: status.json (heartbeat), installed.json, modules_catalog.json, update_status.json. Reads+consumes: requests/*.json.
// Sources are LOCAL only (Suite/modules/*/module.json, optional <lite dir>/packages). No internet, no downloads, no executing anything.
// Install/update/uninstall/selfupdate are not implemented yet: such requests are consumed and reported as an error, never silently dropped.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { log } from './log.mjs';

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

export function createLite({ getHealth, version = '0.3.0', dir = liteDir(), modulesRoot = MODULES } = {}) {
  const busy = {};
  let timer = null, polling = false, lastError = null;

  async function moduleState(m) {
    if (m.id === 'link') return 'running';                       // we are Link
    try { const mod = readJson(path.join(m.path, 'module.json')); if (mod?.port && getHealth) return (await getHealth(mod)) ? 'running' : 'stopped'; } catch {}
    return 'stopped';
  }

  async function writeInstalled() {
    const mods = {};
    for (const m of scanModules(modulesRoot)) mods[m.id] = { version: m.version, installed_at: iso(), path: m.path, state: await moduleState(m) };
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
      if (cmpVersion(v, cur.latest_version) > 0) { best[id] = { ...cur, latest_version: v, size_bytes: fs.statSync(path.join(dir, 'packages', f)).size }; }
    }
    writeJson(dir, 'modules_catalog.json', { generated_at: iso(), channel: 'stable', source: 'local', modules: Object.values(best) });
    return Object.values(best);
  }

  function writeUpdateStatus(installed, catalog, result = 'ok', error) {
    const n = catalog.filter(c => installed[c.id] && cmpVersion(c.latest_version, installed[c.id].version) > 0).length;
    writeJson(dir, 'update_status.json', { last_check_at: iso(), result, ...(error ? { error } : {}), updates_available: n, lite_update_available: false });
    return n;
  }

  async function refresh(result = 'ok') {
    const installed = await writeInstalled(), catalog = writeCatalog();
    return writeUpdateStatus(installed, catalog, result);
  }

  function writeStatus() {
    writeJson(dir, 'status.json', { writer: { name: 'PinguinoLink', version, pid: process.pid, heartbeat_at: iso() },
      connector: { state: 'connected', detail: 'local sources only (no update server)' }, busy: { ...busy }, ...(lastError ? { last_error: lastError } : {}) });
  }

  /** Handle one request file (already parsed). */
  async function handle(req) {
    const action = req?.action, id = req?.id;
    if (action === 'check') { busy.lite = 'checking'; writeStatus(); try { await refresh(); } finally { delete busy.lite; } return; }
    if (['install', 'update', 'uninstall', 'selfupdate-apply'].includes(action)) {
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
      timer = setInterval(() => { poll().catch(() => {}); if (++n % 15 === 0) { writeStatus(); } if (n % 300 === 0) refresh().catch(() => {}); }, 1000);
      timer.unref?.();
      log('info', 'lite', `PinguinoLite contract folder: ${dir}`);
    },
    stop() { clearInterval(timer); },
    poll, refresh, handle, writeStatus,
  };
}
