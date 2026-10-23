// INDEX apply.mjs: check + apply a release to an install folder. Steps: lock -> manifest -> LIVE GUARD -> download + sha256 -> validate every zip name ->
// back up each file the release will overwrite -> swap -> post-check -> (any failure: restore byte for byte). Never touches Data\, OBS, processes or secrets.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { openSource } from './sources.mjs';
import { cmpVersion } from './manifest.mjs';
import { readZip } from './zip.mjs';
import { safeRel, within } from './paths.mjs';
import { COMPONENTS, COMPONENT_IDS, componentOf } from './components.mjs';
import { partsOf, wants } from './profiles.mjs';

export const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');
const iso = () => new Date().toISOString();
const stamp = () => iso().replace(/[-:T]/g, '').slice(0, 14);
const writeJson = (f, o) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f + '.tmp', JSON.stringify(o, null, 2)); fs.renameSync(f + '.tmp', f); };
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };

export const dirs = installDir => { const u = path.join(installDir, 'Data', 'updates'); return { u, staging: path.join(u, 'staging'), backup: path.join(u, 'backup'), lock: path.join(u, 'updater.lock'), result: path.join(u, 'update_result.json'), deferred: path.join(u, 'update_deferred.json'), pending: path.join(u, 'pending.json'), swapping: path.join(u, 'swap_in_progress.json'), rollbackPending: path.join(u, 'rollback_pending.json'), install: path.join(installDir, 'install.json') }; };

/** Ask the Host whether the stream is live. Connection refused = the Host is not running = not live. Anything unclear = treat as live. */
export async function hostLiveCheck(url = process.env.PINGUINO_LIVE_URL || 'http://127.0.0.1:8770/api/live') {   // env override only for the release self-test
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

/** The lock file holds the pid of the updater that took it. Stale = that pid no longer exists (killed), or the file is empty / unreadable and older than 5 s (an updater died between creating and writing it).
 *  A lock whose owner is still alive is NEVER taken over, however old: a slow download is not a dead updater. */
const EMPTY_LOCK_MS = 5000;
function lockIsStale(file, staleMs) {
  let st, txt;
  try { st = fs.statSync(file); txt = fs.readFileSync(file, 'utf8'); } catch { return false; }
  const pid = parseInt(txt, 10), age = Date.now() - st.mtimeMs;
  if (!pid) return age > EMPTY_LOCK_MS;
  if (pid === process.pid) return false;
  try { process.kill(pid, 0); return false; } catch (e) { if (e.code === 'ESRCH') return true; return age > staleMs; }   // EPERM = alive but not ours: alive
}

function takeLock(file, staleMs = 30 * 60 * 1000) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const release = () => { try { if (parseInt(fs.readFileSync(file, 'utf8'), 10) === process.pid) fs.unlinkSync(file); } catch {} };   // never remove a lock somebody else took after ours was judged stale
  for (let i = 0; i < 3; i++) {
    try { const fd = fs.openSync(file, 'wx'); fs.writeSync(fd, String(process.pid)); fs.closeSync(fd); return release; }
    catch (e) {
      if (e.code !== 'EEXIST') throw e;
      if (!lockIsStale(file, staleMs)) return null;
      // Remove the stale lock by renaming it to a name only we use: of two updaters that both judged it stale, exactly one rename succeeds. Then re-check what we got.
      const mine = `${file}.stale-${process.pid}-${crypto.randomBytes(3).toString('hex')}`;
      try { fs.renameSync(file, mine); } catch { continue; }
      const stillStale = (() => { try { const pid = parseInt(fs.readFileSync(mine, 'utf8'), 10); if (!pid) return true; if (pid === process.pid) return false; try { process.kill(pid, 0); return false; } catch (e2) { return e2.code === 'ESRCH'; } } catch { return true; } })();
      if (!stillStale) { try { fs.linkSync(mine, file); } catch {} try { fs.unlinkSync(mine); } catch {} return null; }   // we grabbed a live lock that was created in between: put it back
      try { fs.unlinkSync(mine); } catch {}
    }
  }
  return null;
}

/** Parts of the release that differ from what is installed. Without per-part records (an older install) every part counts as changed when the version is newer. */
export function diffComponents(m, inst, current, also = []) {
  const newer = cmpVersion(m.version, current) > 0, have = inst && inst.components, parts = partsOf(inst);
  if (!m.components) return [];
  return COMPONENTS.filter(c => m.components[c.id] && (wants(parts, c.id) || also.includes(c.id))).map(c => {
    const mine = have && have[c.id] && have[c.id].hash, theirs = m.components[c.id];
    const changed = have ? mine !== theirs.hash : newer;
    return { id: c.id, name: c.name, restart: c.restart, module: c.module || null, changed, files: theirs.files, bytes: theirs.bytes };
  });
}

/** Parts the release has that this install does not keep (a minimal profile): offered as on-demand installs. */
export function optionalParts(m, inst) {
  const parts = partsOf(inst);
  if (!m.components || !parts) return [];
  return COMPONENTS.filter(c => m.components[c.id] && !parts.includes(c.id)).map(c => ({ optional: true, installed: false, id: c.id, name: c.name, restart: c.restart, module: c.module || null, files: m.components[c.id].files, bytes: m.components[c.id].bytes }));
}

export async function checkUpdate({ source, current, channel = 'stable', pubkey = null, installDir = null, also = [] }) {
  const src = await openSource(source, { pubkey });
  const m = src.manifest;
  if (m.channel !== channel && !(channel === 'beta' && m.channel === 'stable')) return { available: false, why: `release is on the ${m.channel} channel`, manifest: m };
  const inst = installDir ? readJson(dirs(installDir).install) : null;
  const parts = diffComponents(m, inst, current, also);
  const available = parts.length ? parts.some(c => c.changed) : cmpVersion(m.version, current) > 0;
  return { available, manifest: m, src, components: parts, optional: optionalParts(m, inst) };
}

export async function applyUpdate({ installDir, source, current, channel = 'stable', pubkey = null, liveCheck = hostLiveCheck, keepBackups = 3, postCheck = null, force = false, only = null, stageOnly = false, repair = false }) {
  const D = dirs(installDir), res = (ok, message, extra = {}) => { const r = { schema: 1, at: iso(), ok, message, from: current, ...extra }; writeJson(D.result, r); return r; };
  const unlock = takeLock(D.lock);
  if (!unlock) return { schema: 1, ok: true, message: 'another update is already running', skipped: true };
  let backupDir = null, started = false;
  try {
    recoverLocked(installDir);   // an earlier updater killed halfway through a swap: put the old files back before anything else
    const chk = await checkUpdate({ source, current, channel, pubkey, installDir, also: only || [] });   // a part named in --only is installed even if the profile did not keep it yet
    if (only) {
      if (!chk.manifest.components) return res(false, 'this release has no per-part information; update everything instead', { to: chk.manifest.version });
      const bad = only.filter(id => !COMPONENT_IDS.has(id) || !chk.manifest.components[id]);
      if (bad.length) return res(false, `unknown part: ${bad.join(', ')}`, { to: chk.manifest.version });
    }
    if (!chk.available && !(repair && only)) { try { fs.unlinkSync(D.deferred); } catch {} return res(true, chk.why || 'already up to date', { upToDate: true, to: chk.manifest.version }); }
    const m = chk.manifest, to = m.version;
    // never while live (or when we cannot tell)
    if (!force && !stageOnly) {
      const lv = await liveCheck();
      if (lv.live !== false) { writeJson(D.deferred, { schema: 1, at: iso(), to, reason: lv.live === true ? 'you are live' : `could not tell if you are live (${lv.why || 'unknown'})` }); return res(true, `update ${to} is waiting until you are off stream`, { deferred: true, to }); }
    }
    // download + verify every file, then re-verify right before use
    const stage = path.join(D.staging, to); fs.mkdirSync(stage, { recursive: true });
    const zips = [];
    for (const f of m.files) {
      const cached = path.join(stage, f.name);   // a staged copy from an earlier click is reused when it still matches
      let buf = null; try { const c = fs.readFileSync(cached); if (c.length === f.size && sha256(c) === f.sha256) buf = c; } catch {}
      if (!buf) buf = await chk.src.fetchFile(f);
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
    // a partial update keeps only the chosen parts' files
    const keptParts = partsOf(readJson(D.install));
    const keep = only ? plan.filter(p => only.includes(componentOf(p.rel))) : plan.filter(p => wants(keptParts, componentOf(p.rel)));   // a full update skips parts this install does not keep
    if (!keep.length) return res(false, 'nothing in the release belongs to the chosen parts; nothing was changed', { to });
    if (stageOnly) {   // files of the running app: verified and parked now, swapped by the next launch (updater launch) when nothing is running
      writeJson(D.pending, { schema: 1, at: iso(), to, only: only || null, channel, source: source.type === 'github' ? { type: 'github', repo: source.repo, tag: source.tag || null } : source });
      return res(true, `update ${to} is ready; it is applied the next time the Suite starts`, { to, staged: true });
    }
    // back up what will be overwritten
    prune(D.backup, Infinity);   // junk from a killed earlier run (we hold the lock, so nothing else is building one)
    let name = `${stamp()}-${current}`, n = 1; while (fs.existsSync(path.join(D.backup, name)) || fs.existsSync(path.join(D.backup, name + '.partial'))) name = `${stamp()}-${current}-${++n}`;
    backupDir = path.join(D.backup, name); const building = backupDir + '.partial';   // built under .partial and renamed once backup.json is written: a killed updater never leaves a folder that looks like a backup
    const list = { from: current, to, at: iso(), files: [], created: [] };
    for (const p of keep) {
      const dst = within(installDir, p.rel);
      if (fs.existsSync(dst)) { const b = path.join(building, 'files', p.rel); fs.mkdirSync(path.dirname(b), { recursive: true }); fs.copyFileSync(dst, b); list.files.push(p.rel); }
      else list.created.push(p.rel);
    }
    const prevInstall = readJson(D.install);
    writeJson(path.join(building, 'backup.json'), { ...list, only: only || null, install: prevInstall });
    fs.renameSync(building, backupDir);
    writeJson(D.swapping, { schema: 1, at: iso(), from: current, to, backup: backupDir });   // removed when the swap is finished or undone; if the process dies in between, recoverInterrupted() undoes it
    started = true;
    // swap
    for (const p of keep) {
      const dst = within(installDir, p.rel), tmp = dst + '.pinguino-new';
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.writeFileSync(tmp, p.data); fs.renameSync(tmp, dst);
    }
    // per-part record: what is installed now, so the next check shows only real differences
    const comps = { ...((prevInstall && prevInstall.components) || {}) };
    const nowParts = keptParts && only ? [...new Set([...keptParts, ...only])] : keptParts;   // adding a part to a minimal install
    if (m.components) {
      if (only) for (const id of only) comps[id] = { hash: m.components[id].hash };
      else for (const id of Object.keys(m.components)) if (wants(nowParts, id)) comps[id] = { hash: m.components[id].hash };
    }
    const allCurrent = !m.components || Object.keys(m.components).filter(id => wants(nowParts, id)).every(id => comps[id] && comps[id].hash === m.components[id].hash);
    writeJson(D.install, { ...(prevInstall || {}), schema: 1, version: allCurrent ? to : (prevInstall && prevInstall.version) || current, channel, updated_at: iso(), ...(nowParts ? { parts: nowParts } : {}), ...(m.components ? { components: comps } : {}) });
    if (postCheck && !(await postCheck({ installDir, version: to }))) throw new Error('the new version failed its post-check');
    try { fs.unlinkSync(D.swapping); } catch {}
    try { fs.unlinkSync(D.deferred); } catch {}
    try { fs.unlinkSync(D.pending); } catch {}
    prune(D.backup, keepBackups);
    return res(true, only ? `updated ${only.join(', ')} to ${to}` : `updated ${current} -> ${to}`, { to, backup: backupDir, only: only || null });
  } catch (e) {
    if (started) { try { restore(installDir, backupDir); try { fs.unlinkSync(D.swapping); } catch {} } catch (e2) { return res(false, `update failed (${e.message}) and the restore had a problem: ${e2.message}; run the updater again to retry the restore`, { backup: backupDir }); } }
    else if (backupDir) { for (const d of [backupDir, backupDir + '.partial']) { try { fs.rmSync(d, { recursive: true, force: true }); } catch {} } }   // a half-made backup (disk full while copying) must not become "the newest backup" that a rollback trips over
    return res(false, `update failed: ${String(e.message).slice(0, 200)}${started ? '; the old version was put back' : '; nothing was changed'}`, { backup: backupDir });
  } finally { unlock(); }
}

const JOURNAL_SLACK_MS = 10 * 60 * 1000;   // install.json is rewritten seconds after the journal inside one swap; a newer install than this is a LATER install
function dropJournal(D, message, extra = {}) {
  try { fs.unlinkSync(D.swapping); } catch {}
  const r = { schema: 1, at: iso(), ok: false, message, discarded: true, ...extra };
  writeJson(D.result, r);
  return r;
}
function recoverLocked(installDir) {
  const D = dirs(installDir);
  if (!fs.existsSync(D.swapping)) return null;
  const j = readJson(D.swapping);
  if (!j || typeof j !== 'object') return dropJournal(D, 'the update journal was unreadable and was removed; if something looks wrong, run Repair');
  const backup = typeof j.backup === 'string' && j.backup ? path.resolve(j.backup) : null;
  const rel = backup ? path.relative(path.resolve(D.backup), backup) : '..';
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel) || rel.includes(path.sep)) return dropJournal(D, 'the update journal pointed outside the backup folder and was removed; if something looks wrong, run Repair', { from: j.from, to: j.to });
  // A journal that does not belong to the install as it is now must never roll it back (that would DOWNGRADE a newer install).
  const inst = readJson(D.install), cur = inst && inst.version != null ? String(inst.version) : null;
  if (cur !== null && cur !== String(j.from) && cur !== String(j.to)) return dropJournal(D, `an old update journal (${j.from} -> ${j.to}) does not match the installed version ${cur}; it was removed and nothing was changed`, { from: j.from, to: j.to });
  const newest = inst ? Math.max(Date.parse(inst.updated_at) || 0, Date.parse(inst.installed_at) || 0) : 0, jat = Date.parse(j.at) || 0;
  if (jat && newest > jat + JOURNAL_SLACK_MS) return dropJournal(D, `an old update journal (${j.from} -> ${j.to}) is older than the current install; it was removed and nothing was changed`, { from: j.from, to: j.to });
  if (!readJson(path.join(backup, 'backup.json'))) return dropJournal(D, `an earlier update to ${j.to} was interrupted and its backup is gone, so it could not be undone; run Repair to check and fix the install`, { from: j.from, to: j.to });
  restore(installDir, backup);
  try { fs.unlinkSync(D.swapping); } catch {}
  const r = { schema: 1, at: iso(), ok: false, message: `an earlier update to ${j.to} was interrupted; the old version ${j.from} was put back`, from: j.from, to: j.to, recovered: true };
  writeJson(D.result, r);
  return r;
}

/** If an update was killed halfway through its swap (journal swap_in_progress.json), undo it from its backup. Returns the recovery record or null. */
export function recoverInterrupted(installDir) {
  const D = dirs(installDir);
  if (!fs.existsSync(D.swapping)) return null;
  const unlock = takeLock(D.lock);
  if (!unlock) return null;   // a live updater is working right now
  try { return recoverLocked(installDir); } finally { unlock(); }
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

/** What the newest backup would put back: {from, to, at, components:[ids]} or null. */
export function rollbackPlan(installDir) {
  const { valid } = listBackups(dirs(installDir).backup);
  if (!valid.length) return null;
  const b = valid[valid.length - 1].b;
  const comps = [...new Set([...(b.files || []), ...(b.created || [])].map(componentOf))];
  return { from: b.to, to: b.from, at: b.at, components: comps };
}

/** Restore the newest backup on request (under the same lock as an update, so it cannot run while one is swapping). */
export function rollbackLatest(installDir) {
  const D = dirs(installDir), unlock = takeLock(D.lock);
  if (!unlock) return { ok: false, message: 'an update is running right now; try the rollback again in a minute' };
  try {
    const { valid } = listBackups(D.backup);
    if (!valid.length) return { ok: false, message: 'there is no backup to restore' };
    const b = restore(installDir, valid[valid.length - 1].dir);
    try { fs.unlinkSync(D.swapping); } catch {}   // a leftover journal would otherwise undo this rollback on the next start
    writeJson(D.result, { schema: 1, at: iso(), ok: true, message: `rolled back to ${b.from}`, from: b.to, to: b.from });
    return { ok: true, message: `rolled back to ${b.from}` };
  } finally { unlock(); }
}

/** Usable backups, oldest first, ordered by the `at` inside backup.json (NOT by folder name: versions do not sort as text, 1.10.0 < 1.9.0). Folders still being built (.partial) or without backup.json are `junk`. */
export function listBackups(dir) {
  let names = [];
  try { names = fs.readdirSync(dir, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => e.name); } catch { return { valid: [], junk: [] }; }
  const valid = [], junk = [];
  for (const name of names) {
    const b = name.endsWith('.partial') ? null : readJson(path.join(dir, name, 'backup.json'));
    if (b) valid.push({ name, dir: path.join(dir, name), at: Date.parse(b.at) || 0, b }); else junk.push(path.join(dir, name));
  }
  valid.sort((x, y) => x.at - y.at || (x.name < y.name ? -1 : x.name > y.name ? 1 : 0));
  return { valid, junk };
}
/** Only called with the update lock held: keeps the newest `keep` backups and removes junk (half-built folders left by a killed updater). */
function prune(dir, keep) {
  try {
    const { valid, junk } = listBackups(dir);
    for (const d of junk) fs.rmSync(d, { recursive: true, force: true });
    for (const v of valid.slice(0, Math.max(0, valid.length - keep))) fs.rmSync(v.dir, { recursive: true, force: true });
  } catch {}
}
