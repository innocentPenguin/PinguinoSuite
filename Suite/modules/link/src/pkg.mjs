// INDEX pkg.mjs: local module packages for PinguinoLite. extractZip (safe unzip, no shell), sha256 check, install/update/uninstall/rollback.
// Package = <lite dir>/packages/<id>-<version>.zip with module.json at its root, plus <same name>.zip.sha256 (hex hash, required).
// Nothing in a package is ever executed. Replaced/removed module folders are MOVED to <lite dir>/backup, never deleted.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

const ID = /^[a-z0-9_-]{1,40}$/;
const MAX_FILES = 5000, MAX_TOTAL = 300 * 1024 * 1024;
export const KEEP = ['data'];                       // folders kept from the old version on update (user data)

/** Extract a zip into an EMPTY dir. Rejects encrypted/zip64/odd entries and any path that would leave dir. */
export function extractZip(file, dest) {
  const buf = fs.readFileSync(file);
  let e = buf.length - 22;
  while (e >= 0 && buf.readUInt32LE(e) !== 0x06054b50) e--;
  if (e < 0) throw new Error('not a zip file');
  const count = buf.readUInt16LE(e + 10);
  let p = buf.readUInt32LE(e + 16);
  if (count > MAX_FILES) throw new Error('package has too many files');
  const root = path.resolve(dest) + path.sep;
  let total = 0;
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('damaged zip');
    const flags = buf.readUInt16LE(p + 8), method = buf.readUInt16LE(p + 10), crc = buf.readUInt32LE(p + 16);
    const csize = buf.readUInt32LE(p + 20), usize = buf.readUInt32LE(p + 24);
    const nl = buf.readUInt16LE(p + 28), xl = buf.readUInt16LE(p + 30), cl = buf.readUInt16LE(p + 32), lo = buf.readUInt32LE(p + 42);
    const name = buf.toString('utf8', p + 46, p + 46 + nl);
    p += 46 + nl + xl + cl;
    if (flags & 1) throw new Error('encrypted zips are not supported');
    if (csize === 0xffffffff || usize === 0xffffffff) throw new Error('zip64 is not supported');
    const clean = name.replace(/\\/g, '/');
    if (!clean || clean.startsWith('/') || /^[a-zA-Z]:/.test(clean) || clean.split('/').includes('..')) throw new Error(`unsafe path in package: ${name.slice(0, 60)}`);
    const out = path.resolve(dest, clean);
    if (!(out + path.sep).startsWith(root)) throw new Error('unsafe path in package');
    if (clean.endsWith('/')) { fs.mkdirSync(out, { recursive: true }); continue; }
    total += usize; if (total > MAX_TOTAL) throw new Error('package is too large');
    if (buf.readUInt32LE(lo) !== 0x04034b50) throw new Error('damaged zip');
    const start = lo + 30 + buf.readUInt16LE(lo + 26) + buf.readUInt16LE(lo + 28);
    const raw = buf.subarray(start, start + csize);
    let data;
    if (method === 0) data = raw; else if (method === 8) data = zlib.inflateRawSync(raw); else throw new Error('unsupported compression');
    if (data.length !== usize) throw new Error('damaged zip (size)');
    if (zlib.crc32 && zlib.crc32(data) !== crc) throw new Error('damaged zip (crc)');
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, data);
  }
}

export function sha256File(f) { return crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'); }

/** Expected hash from <zip>.sha256 ("hex" or "hex  name"). Required: no sidecar, no install. */
export function expectedHash(zip) {
  let t; try { t = fs.readFileSync(zip + '.sha256', 'utf8'); } catch { throw new Error('package has no .sha256 file; refusing to install'); }
  const h = (t.trim().split(/\s+/)[0] || '').toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(h)) throw new Error('the .sha256 file is not a valid hash');
  return h;
}

/** Newest package for id in <lite>/packages -> {version, file} or null. */
export function findPackage(liteDir, id, cmp) {
  let best = null;
  try {
    for (const f of fs.readdirSync(path.join(liteDir, 'packages'))) {
      const m = /^([a-z0-9_-]{1,40})-(\d+(?:\.\d+)*)\.zip$/.exec(f);
      if (m && m[1] === id && (!best || cmp(m[2], best.version) > 0)) best = { version: m[2], file: path.join(liteDir, 'packages', f) };
    }
  } catch {}
  return best;
}

let seq = 0;
const stamp = () => new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
const backupPath = (liteDir, id) => path.join(liteDir, 'backup', `${id}-${stamp()}${seq++ ? '-' + seq : ''}`);
const readManifest = d => { try { return JSON.parse(fs.readFileSync(path.join(d, 'module.json'), 'utf8').replace(/^﻿/, '')); } catch { return null; } };

/** Install (target missing) or update (target present). Returns {version, backup?}. Throws a plain message; the old folder is restored on failure. */
export function installPackage({ liteDir, modulesRoot, id, cmp, update }) {
  if (!ID.test(id || '')) throw new Error('bad module id');
  if (id === 'link') throw new Error('Link updates itself through the Lite updater, not here');
  const pkg = findPackage(liteDir, id, cmp);
  if (!pkg) throw new Error(`no package for ${id} in the packages folder`);
  if (sha256File(pkg.file) !== expectedHash(pkg.file)) throw new Error('package hash does not match; refusing to install');
  const target = path.join(modulesRoot, id), exists = fs.existsSync(target);
  if (!update && exists) throw new Error(`${id} is already installed`);
  if (update && !exists) throw new Error(`${id} is not installed`);
  if (update) { const cur = readManifest(target); if (cur?.version && cmp(pkg.version, cur.version) <= 0) throw new Error(`already at ${cur.version} or newer`); }
  const stage = path.join(modulesRoot, '.staging', `${id}-${pkg.version}-${process.pid}`);
  fs.rmSync(stage, { recursive: true, force: true });
  fs.mkdirSync(stage, { recursive: true });
  try {
    extractZip(pkg.file, stage);
    const mf = readManifest(stage);
    if (!mf || mf.id !== id) throw new Error('package module.json is missing or its id does not match');
  } catch (e) { fs.rmSync(stage, { recursive: true, force: true }); try { fs.rmdirSync(path.join(modulesRoot, '.staging')); } catch {} throw e; }
  let backup = null;
  try {
    if (exists) {
      backup = backupPath(liteDir, id);
      fs.mkdirSync(path.dirname(backup), { recursive: true });
      fs.renameSync(target, backup);
      for (const k of KEEP) if (fs.existsSync(path.join(backup, k)) && !fs.existsSync(path.join(stage, k))) fs.cpSync(path.join(backup, k), path.join(stage, k), { recursive: true });
    }
    fs.renameSync(stage, target);
  } catch (e) {
    fs.rmSync(stage, { recursive: true, force: true });
    if (backup && !fs.existsSync(target) && fs.existsSync(backup)) fs.renameSync(backup, target);   // put the old one back
    throw new Error(`could not swap files (${e.code || e.message}); the old version was restored`);
  }
  try { fs.rmdirSync(path.join(modulesRoot, '.staging')); } catch {}
  return { version: pkg.version, backup };
}

/** Move the module folder to backup (never deletes). */
export function uninstallModule({ liteDir, modulesRoot, id }) {
  if (!ID.test(id || '')) throw new Error('bad module id');
  if (id === 'link') throw new Error('Link cannot uninstall itself');
  const target = path.join(modulesRoot, id);
  if (!fs.existsSync(target)) throw new Error(`${id} is not installed`);
  const backup = backupPath(liteDir, id);
  fs.mkdirSync(path.dirname(backup), { recursive: true });
  fs.renameSync(target, backup);
  return { backup };
}

/** Restore the newest backup of id; a current folder is moved to backup first. */
export function rollbackModule({ liteDir, modulesRoot, id }) {
  if (!ID.test(id || '') || id === 'link') throw new Error('bad module id');
  const bdir = path.join(liteDir, 'backup');
  let list = [];
  try { list = fs.readdirSync(bdir).filter(n => n.startsWith(id + '-') && /^\d{14}(-\d+)?$/.test(n.slice(id.length + 1))).sort(); } catch {}
  if (!list.length) throw new Error(`no backup of ${id} to restore`);
  const target = path.join(modulesRoot, id), pick = path.join(bdir, list.at(-1));
  if (fs.existsSync(target)) fs.renameSync(target, backupPath(liteDir, id));
  fs.renameSync(pick, target);
  return { restored: list.at(-1) };
}

const SKIP_DIRS = new Set(['data', 'node_modules', '__pycache__', '.git', '.staging']);
const SKIP_FILE = /\.(db|db-shm|db-wal|log|tmp|pyc)$/i;
/** Zip writer (deflate). entries: [{name, data}] */
export function writeZip(entries) {
  const parts = [], cd = []; let off = 0;
  for (const { name, data } of entries) {
    const comp = zlib.deflateRawSync(data), nm = Buffer.from(name), crc = zlib.crc32(data);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8); lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(comp.length, 18); lh.writeUInt32LE(data.length, 22); lh.writeUInt16LE(nm.length, 26);
    parts.push(lh, nm, comp);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(comp.length, 20); ch.writeUInt32LE(data.length, 24); ch.writeUInt16LE(nm.length, 28); ch.writeUInt32LE(off, 42);
    cd.push(ch, nm); off += 30 + nm.length + comp.length;
  }
  const cdb = Buffer.concat(cd), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10); end.writeUInt32LE(cdb.length, 12); end.writeUInt32LE(off, 16);
  return Buffer.concat([...parts, cdb, end]);
}
/** Pack Suite/modules/<id> into <lite>/packages/<id>-<version>.zip + .sha256. Skips data/, caches, logs and db files (user state belongs in data/). */
export function packModule({ liteDir, modulesRoot, id }) {
  if (!ID.test(id || '')) throw new Error('bad module id');
  const src = path.join(modulesRoot, id), mf = readManifest(src);
  if (!mf || mf.id !== id) throw new Error(`${id}: no valid module.json`);
  if (!/^\d+(\.\d+)*$/.test(String(mf.version || ''))) throw new Error(`${id}: module.json needs a "version" like 1.2.0`);
  const entries = [];
  const walk = (d, rel) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.isDirectory()) { if (!SKIP_DIRS.has(e.name)) walk(path.join(d, e.name), rel + e.name + '/'); }
      else if (e.isFile() && !SKIP_FILE.test(e.name)) entries.push({ name: rel + e.name, data: fs.readFileSync(path.join(d, e.name)) });
    }
  };
  walk(src, '');
  if (entries.length > MAX_FILES) throw new Error('too many files');
  const zip = writeZip(entries), file = path.join(liteDir, 'packages', `${id}-${mf.version}.zip`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file + '.tmp', zip); fs.renameSync(file + '.tmp', file);
  const h = crypto.createHash('sha256').update(zip).digest('hex');
  fs.writeFileSync(file + '.sha256', `${h}  ${path.basename(file)}\n`);
  return { file, version: String(mf.version), files: entries.length, sha256: h };
}
