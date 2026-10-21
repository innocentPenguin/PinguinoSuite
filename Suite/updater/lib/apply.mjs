// INDEX apply.mjs: check + apply a release to an install folder. Steps: lock -> manifest -> LIVE GUARD -> download + sha256 -> validate every zip name ->
// back up each file the release will overwrite -> swap -> post-check -> (any failure: restore byte for byte). Never touches Data\, OBS, processes or secrets.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { openSource } from './sources.mjs';
import { cmpVersion } from './manifest.mjs';
import { readZip } from './zip.mjs';
import { safeRel, within } from './paths.mjs';

export const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');
const iso = () => new Date().toISOString();
const stamp = () => iso().replace(/[-:T]/g, '').slice(0, 14);
const writeJson = (f, o) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f + '.tmp', JSON.stringify(o, null, 2)); fs.renameSync(f + '.tmp', f); };
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };

export const dirs = installDir => { const u = path.join(installDir, 'Data', 'updates'); return { u, staging: path.join(u, 'staging'), backup: path.join(u, 'backup'), lock: path.join(u, 'updater.lock'), result: path.join(u, 'update_result.json'), deferred: path.join(u, 'update_deferred.json'), install: path.join(installDir, 'install.json') }; };

/** Ask the Host whether the stream is live. Connection refused = the Host is not running = not live. Anything unclear = treat as live. */
export async function hostLiveCheck(url = 'http://127.0.0.1:8770/api/live') {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return { live: null, why: `Host answered ${r.status}` };
    const j = await r.json();
    return typeof j.live === 'boolean' ? { live: j.live } : { live: null, why: 'Host did not say' };
  } catch (e) {
    const code = e && e.cause && e.cause.code;
    return code === 'ECONNREFUSED' ? { live: false, why: 'Host not running' } : { live: null, why: 'Host did not answer' };
  }
}

function takeLock(file, staleMs = 30 * 60 * 1000) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  for (let i = 0; i < 2; i++) {
    try { const fd = fs.openSync(file, 'wx'); fs.writeSync(fd, String(process.pid)); fs.closeSync(fd); return () => { try { fs.unlinkSync(file); } catch {} }; }
    catch (e) { if (e.code !== 'EEXIST') throw e; try { if (Date.now() - fs.statSync(file).mtimeMs > staleMs) fs.unlinkSync(file); else return null; } catch { return null; } }
  }
  return null;
}

export async function checkUpdate({ source, current, channel = 'stable' }) {
  const src = await openSource(source);
  const m = src.manifest;
  if (m.channel !== channel && !(channel === 'beta' && m.channel === 'stable')) return { available: false, why: `release is on the ${m.channel} channel`, manifest: m };
  return { available: cmpVersion(m.version, current) > 0, manifest: m, src };
}

export async function applyUpdate({ installDir, source, current, channel = 'stable', liveCheck = hostLiveCheck, keepBackups = 3, postCheck = null, force = false }) {
  const D = dirs(installDir), res = (ok, message, extra = {}) => { const r = { schema: 1, at: iso(), ok, message, from: current, ...extra }; writeJson(D.result, r); return r; };
  const unlock = takeLock(D.lock);
  if (!unlock) return { schema: 1, ok: true, message: 'another update is already running', skipped: true };
  let backupDir = null, started = false;
  try {
    const chk = await checkUpdate({ source, current, channel });
    if (!chk.available) { try { fs.unlinkSync(D.deferred); } catch {} return res(true, chk.why || 'already up to date', { upToDate: true, to: chk.manifest.version }); }
    const m = chk.manifest, to = m.version;
    // never while live (or when we cannot tell)
    if (!force) {
      const lv = await liveCheck();
      if (lv.live !== false) { writeJson(D.deferred, { schema: 1, at: iso(), to, reason: lv.live === true ? 'you are live' : `could not tell if you are live (${lv.why || 'unknown'})` }); return res(true, `update ${to} is waiting until you are off stream`, { deferred: true, to }); }
    }
    // download + verify every file, then re-verify right before use
    const stage = path.join(D.staging, to); fs.mkdirSync(stage, { recursive: true });
    const zips = [];
    for (const f of m.files) {
      const buf = await chk.src.fetchFile(f);
      if (buf.length !== f.size || sha256(buf) !== f.sha256) return res(false, `${f.name} failed its sha256 check; nothing was changed`, { to });
      fs.writeFileSync(path.join(stage, f.name), buf);
      if (f.name.endsWith('.zip')) zips.push(f.name);
    }
    if (!zips.length) return res(false, 'the release has no .zip package; nothing was changed', { to });
    const plan = [];
    for (const z of zips) {
      const buf = fs.readFileSync(path.join(stage, z)), f = m.files.find(x => x.name === z);
      if (sha256(buf) !== f.sha256) return res(false, `${z} changed after download; nothing was changed`, { to });
      for (const e of readZip(buf)) { if (e.dir) { safeRel(e.name); continue; } if (e.link) throw new Error(`release contains a link: ${e.name}`); plan.push({ rel: safeRel(e.name), data: e.data() }); }
    }
    if (!plan.length) return res(false, 'the release package is empty; nothing was changed', { to });
    // back up what will be overwritten
    backupDir = path.join(D.backup, `${current}-${stamp()}`);
    const list = { from: current, to, at: iso(), files: [], created: [] };
    for (const p of plan) {
      const dst = within(installDir, p.rel);
      if (fs.existsSync(dst)) { const b = path.join(backupDir, 'files', p.rel); fs.mkdirSync(path.dirname(b), { recursive: true }); fs.copyFileSync(dst, b); list.files.push(p.rel); }
      else list.created.push(p.rel);
    }
    const prevInstall = readJson(D.install);
    writeJson(path.join(backupDir, 'backup.json'), { ...list, install: prevInstall });
    started = true;
    // swap
    for (const p of plan) {
      const dst = within(installDir, p.rel), tmp = dst + '.pinguino-new';
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.writeFileSync(tmp, p.data); fs.renameSync(tmp, dst);
    }
    writeJson(D.install, { ...(prevInstall || {}), schema: 1, version: to, channel, updated_at: iso(), source: source.type });
    if (postCheck && !(await postCheck({ installDir, version: to }))) throw new Error('the new version failed its post-check');
    try { fs.unlinkSync(D.deferred); } catch {}
    prune(D.backup, keepBackups);
    return res(true, `updated ${current} -> ${to}`, { to, backup: backupDir });
  } catch (e) {
    if (started) { try { restore(installDir, backupDir); } catch (e2) { return res(false, `update failed (${e.message}) and the restore had a problem: ${e2.message}`, { backup: backupDir }); } }
    return res(false, `update failed: ${String(e.message).slice(0, 200)}${started ? '; the old version was put back' : '; nothing was changed'}`, { backup: backupDir });
  } finally { unlock(); }
}

/** Put every backed-up file back and remove files the release created. */
export function restore(installDir, backupDir) {
  const b = readJson(path.join(backupDir, 'backup.json')); if (!b) throw new Error('backup is missing its list');
  for (const rel of b.files) { const dst = within(installDir, safeRel(rel)); fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.copyFileSync(path.join(backupDir, 'files', rel), dst); }
  for (const rel of b.created) { const dst = within(installDir, safeRel(rel)); for (const suffix of ['', '.pinguino-new']) { try { fs.unlinkSync(dst + suffix); } catch {} } }
  for (const rel of b.files) { try { fs.unlinkSync(within(installDir, rel) + '.pinguino-new'); } catch {} }
  const D = dirs(installDir); if (b.install) writeJson(D.install, b.install); else { try { fs.unlinkSync(D.install); } catch {} }
  return b;
}

/** Restore the newest backup on request. */
export function rollbackLatest(installDir) {
  const D = dirs(installDir);
  const list = fs.existsSync(D.backup) ? fs.readdirSync(D.backup).sort() : [];
  if (!list.length) return { ok: false, message: 'there is no backup to restore' };
  const b = restore(installDir, path.join(D.backup, list[list.length - 1]));
  writeJson(D.result, { schema: 1, at: iso(), ok: true, message: `rolled back to ${b.from}`, from: b.to, to: b.from });
  return { ok: true, message: `rolled back to ${b.from}` };
}

function prune(dir, keep) { try { const l = fs.readdirSync(dir).sort(); for (const d of l.slice(0, Math.max(0, l.length - keep))) fs.rmSync(path.join(dir, d), { recursive: true, force: true }); } catch {} }
