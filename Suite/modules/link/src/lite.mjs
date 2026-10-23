// INDEX lite.mjs: Link's side of the PinguinoLite contract (Docs/LITE_APP.md). File drop in <lite dir>. Package ops live in pkg.mjs; tests litecheck.mjs + pkgcheck.mjs.
// Writes: status.json (heartbeat), installed.json, modules_catalog.json, update_status.json. Reads+consumes: requests/*.json.
// Sources are LOCAL only (Suite/modules/*/module.json, optional <lite dir>/packages). No internet, no downloads, no executing anything.
// install/update/uninstall/rollback: local zip packages (pkg.mjs), only for a stopped module. selfupdate-apply starts the detached
// applyupdate.mjs helper (hash re-check, backup, silent install, relaunch, auto-restore). start/stop/restart drop the Suite core's
// control file (Data/runtime/control/<action>-<id>) and wait for the module's health to agree. Earlier note, no longer true: such requests are consumed and reported as an error, never silently dropped.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import { log } from './log.mjs';
import { testHook } from './testhook.mjs';
import { readCapped, jsonCapped } from './httpcap.mjs';
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

/** Where the Suite core watches for <start|stop|restart>-<module id> files (same folder the core uses). */
export const controlDir = () => path.join(process.env.PINGUINO_DATA_DIR || path.join(SUITE, 'Data', 'runtime'), 'control');

export function createLite({ getHealth, peers, version = '0.3.0', dir = liteDir(), modulesRoot = MODULES, control = controlDir(), settleMs = 20000 } = {}) {
  const busy = {};
  let timer = null, polling = false, lastError = null, mstate = {};
  const since = {};                                            // id@version -> when Link first saw it installed
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
    for (const m of scanModules(modulesRoot)) { const state = await moduleState(m); mods[m.id] = { version: m.version, installed_at: (since[m.id + '@' + m.version] ??= iso()), path: m.path, state, ...(errors[m.id] ? { error: errors[m.id] } : {}) }; mstate[m.id] = { state, detail: state === 'running' ? 'answers on its health check' : 'not answering', ...(state === 'stopped' ? { fix_hint: 'Start it from the full Suite' } : {}) }; }
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
    try { for (const f of fs.readdirSync(path.join(dir, 'staging'))) { const m = installerRe().exec(f); if (m && (!best || cmpVersion(m[1], best.v) > 0)) best = { v: m[1], f }; } } catch {}
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
    if (!peers || peers.enabled?.() !== true) return { fetched: 0 };
    let fetched = 0;
    for (const peer of peers.names()) {
      let items;
      try { const r = await peers.post(peer, '/api/mesh/updates/list', {}, 8000); if (!r.ok) continue; items = (await jsonCapped(r)).files || []; } catch { continue; }
      const installed = Object.fromEntries(scanModules(modulesRoot).map(m => [m.id, m.version]));
      const live = process.env.PINGUINO_LITE_VERSION || '0.0.0';
      for (const it of items.slice(0, 50)) {
        if (!SHARE_RE.test(it?.name || '') || !/^[0-9a-f]{64}$/.test(it.sha256 || '') || !(it.size <= MAX_SHARE)) continue;
        const zip = /^([a-z0-9_-]+)-(\d+(?:\.\d+)*)\.zip$/.exec(it.name), exe = installerRe().exec(it.name);
        const ver = zip ? zip[2] : exe[1];
        if (zip ? (zip[1] === 'link' || (installed[zip[1]] && cmpVersion(ver, installed[zip[1]]) <= 0)) : cmpVersion(ver, live) <= 0) continue;
        const dest = path.join(shareDir(dir, it.name), it.name);
        if (fs.existsSync(dest)) { if (sidecarHash(dest) !== it.sha256) log('warn', 'lite', `${peer} offers ${it.name} with a different hash than the file already here; kept the old one`); continue; }   // never overwrite
        if (shareBytes(dir) + it.size > MAX_TOTAL) { log('warn', 'lite', `update folders are full (${Math.round(MAX_TOTAL / 1e6)} MB limit); ${it.name} from ${peer} skipped`); continue; }
        try {
          const r = await peers.post(peer, '/api/mesh/updates/get', { name: it.name }, 120000);
          if (!r.ok) continue;
          const buf = await readCapped(r, Math.min(MAX_SHARE, it.size + 1));   // stops reading as soon as the peer sends more than it announced
          if ( crypto.createHash('sha256').update(buf).digest('hex') !== it.sha256) { log('warn', 'lite', `${it.name} from ${peer} failed the hash check; discarded`); continue; }
          fs.mkdirSync(path.dirname(dest), { recursive: true });
          fs.writeFileSync(dest + '.tmp', buf); fs.renameSync(dest + '.tmp', dest);
          fs.writeFileSync(dest + '.sha256.tmp', it.sha256 + '\n'); fs.renameSync(dest + '.sha256.tmp', dest + '.sha256');
          fs.writeFileSync(dest + '.from', peer + '\n');                       // where it came from, for the install prompt
          fetched++; log('info', 'lite', `fetched ${it.name} from ${peer} (integrity checked, not signed)`);
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
    if (action === 'selfupdate-apply') { await applyLiteUpdate(); return; }
    if (['start', 'stop', 'restart'].includes(action)) { await controlModule(action, id); return; }
    log('warn', 'lite', 'ignored a request with an unknown action');
  }

  /** start/stop/restart a module: drop the core's control file (the core consumes it and acts), then wait until the module's health agrees. */
  async function controlModule(action, id) {
    if (!ID.test(id || '')) { fail(`${action}: missing or bad module id`); return; }
    const verb = { start: 'starting', stop: 'stopping', restart: 'restarting' }[action];
    busy[id] = verb; writeStatus();
    try {
      const cur = scanModules(modulesRoot).find(m => m.id === id);
      if (!cur) throw new Error(`${id} is not installed`);
      if (id === 'link' && action !== 'start') throw new Error('Link cannot stop or restart itself from here; use the Suite (Modules > Link)');
      if (!readJson(path.join(cur.path, 'module.json'))?.port) throw new Error(`${id} has no port, so its state cannot be checked; use the Suite`);
      const before = await moduleState(cur);
      if (action === 'start' && before === 'running') { delete errors[id]; await refresh(); return; }
      if (action === 'stop' && before === 'stopped') { delete errors[id]; await refresh(); return; }
      fs.mkdirSync(control, { recursive: true });
      const f = path.join(control, `${action}-${id}`);
      fs.writeFileSync(f, '');
      const t0 = Date.now();
      while (fs.existsSync(f)) { if (Date.now() - t0 > 6000) { try { fs.unlinkSync(f); } catch {} throw new Error('the Suite core did not pick up the request (is the Suite running?)'); } await new Promise(r => setTimeout(r, 200)); }
      const want = action === 'stop' ? 'stopped' : 'running';
      if (action === 'restart') await new Promise(r => setTimeout(r, Math.min(1500, settleMs)));   // let the old one go down before judging
      const t1 = Date.now();
      while ((await moduleState(cur)) !== want) { if (Date.now() - t1 > settleMs) throw new Error(`${id} did not become ${want} within ${Math.round(settleMs / 1000)} s; check its log in the Suite`); await new Promise(r => setTimeout(r, 500)); }
      delete errors[id];
      log('info', 'lite', `${action} ${id} ok`);
      await refresh();
    } catch (e) {
      errors[id] = String(e.message || e).slice(0, 200);
      fail(`${action} ${id}: ${errors[id]}`, true);
      await refresh('error', errors[id]).catch(() => {});
    } finally { delete busy[id]; writeStatus(); }
  }

  /** Where the running PinguinoLite.exe lives (so the helper can back it up and relaunch it). */
  function findLiteExe() {
    return new Promise(res => {
      if (process.env.PINGUINO_LITE_EXE) return res(process.env.PINGUINO_LITE_EXE);
      if (litePlatform() !== 'win32') return res(unixLiteExe());
      const fallback = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'PinguinoLite', 'PinguinoLite.exe') : '';
      execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', "(Get-Process -Name PinguinoLite -ErrorAction SilentlyContinue | Select-Object -First 1).Path"], { timeout: 8000, windowsHide: true },
        (e, out) => { const p = String(out || '').trim(); res(!e && /PinguinoLite.exe$/i.test(p) ? p : (fallback && fs.existsSync(fallback) ? fallback : '')); });
    });
  }
  /** The user clicked Update in Lite. Re-verify the staged installer, then hand over to the detached helper (Lite is exiting and takes Link with it). */
  async function applyLiteUpdate() {
    if (busy.lite === 'updating') { log('warn', 'lite', 'Lite update already in progress; extra request ignored'); return; }
    if (!checkLiteUpdate()) { fail(`Lite update: no verified installer is staged (needs PinguinoLite-<version>-setup.${installerExt()} with a matching .sha256)`); return; }
    const man = readJson(path.join(dir, 'update_manifest.json'));
    const installer = path.join(dir, ...String(man.staged_file || '').split(/[\\/]/));
    const exe = await findLiteExe();
    if (!exe) { fail(`Lite update: cannot find the installed ${litePlatform() === 'win32' ? 'PinguinoLite.exe' : 'PinguinoLite'} to update`); return; }
    const job = { liteDir: dir, installer, sha256: man.sha256, exe, platform: litePlatform(), from: process.env.PINGUINO_LITE_VERSION || '0.0.0', to: man.latest_version };
    if (testHook('PINGUINO_LITE_TEST') && process.env.PINGUINO_LITE_TEST_JOB) Object.assign(job, JSON.parse(process.env.PINGUINO_LITE_TEST_JOB));
    const jf = path.join(dir, 'lite_apply_job.json');
    fs.writeFileSync(jf, JSON.stringify(job, null, 2));
    busy.lite = 'updating'; writeStatus();
    const helper = spawn(process.execPath, [fileURLToPath(new URL('./applyupdate.mjs', import.meta.url)), jf], { detached: true, stdio: 'ignore', windowsHide: true, env: process.env });
    helper.on('error', e => { delete busy.lite; fail(`Lite update: could not start the helper (${e.code || e.message})`); writeStatus(); });
    helper.on('exit', () => { delete busy.lite; reportApply(); writeStatus(); });   // only reached when Link survives (update refused/failed)
    helper.unref();
    log('warn', 'lite', `Lite update ${job.from} -> ${job.to} handed to the helper (Lite must close; it relaunches itself)`);
  }
  /** After a restart: report what the helper did. */
  function reportApply() {
    const f = path.join(dir, 'lite_apply_result.json'), r = readJson(f);
    if (!r) return;
    try { fs.renameSync(f, f.replace(/.json$/, '.seen.json')); } catch {}
    log(r.ok ? 'info' : 'warn', 'lite', `last Lite update: ${r.message}`);
    if (!r.ok) fail(`Lite update failed: ${r.message}`);
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
      await refresh(); reportApply(); writeStatus();
      let n = 0;
      timer = setInterval(() => { poll().catch(() => {}); if (++n % 15 === 0) { writeStatus(); } if (n % 300 === 0) syncFromPeers().catch(() => {}).then(() => refresh()).catch(() => {}); }, 1000);
      timer.unref?.();
      log('info', 'lite', `PinguinoLite contract folder: ${dir}`);
    },
    stop() { clearInterval(timer); },
    poll, refresh, handle, writeStatus, syncFromPeers,
  };
}

// ---- platform: Windows installs PinguinoLite-<v>-setup.exe (/S); macOS/Linux install PinguinoLite-<v>-setup.sh (run with /bin/sh)
/** The OS the apply path targets. Tests may fake it with PINGUINO_LITE_PLATFORM (only when PINGUINO_LITE_TEST=1). */
export const litePlatform = () => (testHook('PINGUINO_LITE_TEST') && process.env.PINGUINO_LITE_PLATFORM) || process.platform;
export const installerExt = () => litePlatform() === 'win32' ? 'exe' : 'sh';
export const installerRe = () => new RegExp('^PinguinoLite-(' + '\\d+(?:\\.\\d+)*' + ')-setup\\.' + installerExt() + '$');
/** Where an installed PinguinoLite lives on macOS/Linux when nothing says otherwise ('' = not found). */
function unixLiteExe() {
  const home = process.env.HOME || '';
  const c = litePlatform() === 'darwin'
    ? ['/Applications/PinguinoLite.app', home && path.join(home, 'Applications', 'PinguinoLite.app')]
    : [home && path.join(home, '.local', 'share', 'PinguinoLite', 'PinguinoLite'), '/opt/PinguinoLite/PinguinoLite'];
  return c.find(p => p && fs.existsSync(p)) || '';
}

// ---- sharing update files between this user's own paired PCs (served only to paired peers, see server.mjs) ----
const SHARE_RE = /^(?:[a-z0-9_-]{1,40}-\d+(?:\.\d+)*\.zip|PinguinoLite-\d+(?:\.\d+)*-setup\.(?:exe|sh))$/;
const MAX_SHARE = 300 * 1024 * 1024;
const MAX_TOTAL = 2 * 1024 * 1024 * 1024;     // all fetched + local update files together
function shareBytes(dir) {
  let n = 0;
  for (const sub of ['packages', 'staging']) { try { for (const f of fs.readdirSync(path.join(dir, sub))) { try { n += fs.statSync(path.join(dir, sub, f)).size; } catch {} } } catch {} }
  return n;
}
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
