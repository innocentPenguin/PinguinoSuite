// INDEX install.mjs: fresh install of a release into an empty (or new) folder. Same verification and path rules as the Updater; creates Data\ empty,
// writes install.json (version, channel, source) so the Updater knows where to look. Shortcuts are optional and only made when asked.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { openSource } from './sources.mjs';
import { readZip } from './zip.mjs';
import { safeRel, within } from './paths.mjs';
import { sha256, dirs } from './apply.mjs';
import { componentOf } from './components.mjs';
import { PROFILES, wants } from './profiles.mjs';

/** True when the folder holds no files at all, only (possibly nested) empty folders: what a stopped install leaves behind. */
export function onlyEmptyDirs(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) { if (!e.isDirectory() || !onlyEmptyDirs(path.join(d, e.name))) return false; }
  return true;
}
/** Remove empty folders below (and including, unless keepRoot) d; never touches a file. */
export function pruneEmptyDirs(d, keepRoot = false) {
  let kids; try { kids = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
  for (const e of kids) if (e.isDirectory()) pruneEmptyDirs(path.join(d, e.name));
  if (!keepRoot) { try { fs.rmdirSync(d); } catch {} }
}
/** A plain-words reason for a failed write: antivirus / another program holding a file, a full disk, missing permission. */
export function writeFailure(e) {
  const code = e && e.code, base = String((e && e.message) || e).slice(0, 160);
  if (code === 'ENOSPC') return `the disk is full (${base})`;
  if (['EBUSY', 'EPERM', 'EACCES'].includes(code)) return `Windows or an antivirus program blocked a file (${base}); close other programs, allow the folder in your antivirus, pick a folder you own (for example under your user folder) and try again`;
  if (code === 'ENAMETOOLONG') return `the folder path is too long (${base}); pick a shorter one such as C:\PinguinoSuite`;
  return base;
}

/** Free bytes on the drive that holds `dir` (or its nearest existing parent); null when it cannot be told. */
export function freeBytes(dir) {
  let d = path.resolve(dir);
  while (!fs.existsSync(d)) { const up = path.dirname(d); if (up === d) return null; d = up; }
  try { const s = fs.statfsSync(d); return Number(s.bavail) * Number(s.bsize); } catch { return null; }
}
/** Space an install needs: the download held in memory and written to disk, plus room for logs and Data. */
export const neededBytes = releaseBytes => releaseBytes * 2 + 500 * 1024 * 1024;
const mb = n => Math.round(n / 1048576);

/** Install from one source spec. Returns {ok, message, version}. Never overwrites an existing install (that is the Updater's job). */
export async function installRelease({ target, source, channel = 'stable', repairOver = false, pubkey = null, token = null, recordSource = null, profile = 'full', free = freeBytes }) {
  if (!PROFILES[profile]) return { ok: false, message: `unknown install profile: ${profile}` };
  const keepParts = PROFILES[profile].parts;   // null = everything
  const dst = path.resolve(target), D = dirs(dst);
  if (fs.existsSync(D.install) && !repairOver) return { ok: false, message: 'Suite is already installed here; use the Updater (or pick another folder)' };
  if (fs.existsSync(dst) && !fs.existsSync(D.install) && !onlyEmptyDirs(dst)) return { ok: false, message: 'that folder is not empty; pick an empty folder' };
  const src = await openSource(source, { pubkey, token }), m = src.manifest;
  if (m.channel !== channel && !(channel === 'beta' && m.channel === 'stable')) return { ok: false, message: `that release is on the ${m.channel} channel` };
  const need = neededBytes(m.files.reduce((a, f) => a + (f.size || 0), 0)), have = free(dst);
  if (have != null && have < need) return { ok: false, message: `not enough free space on ${path.parse(dst).root || dst}: the install needs about ${mb(need)} MB and ${mb(have)} MB are free; free some space or pick another drive` };
  const plan = [];
  for (const f of m.files) {
    const buf = await src.fetchFile(f);
    if (buf.length !== f.size || sha256(buf) !== f.sha256) return { ok: false, message: `${f.name} failed its sha256 check; nothing was installed` };
    if (!f.name.endsWith('.zip')) continue;
    for (const e of readZip(buf)) { if (e.dir) { safeRel(e.name); continue; } if (e.link) throw new Error(`release contains a link: ${e.name}`); plan.push({ rel: safeRel(e.name), data: e.data() }); }
  }
  if (keepParts && !m.components) return { ok: false, message: 'this release has no per-part information, so a minimal install is not possible; build the release with the current Build-Release' };
  const kept = keepParts ? plan.filter(p => wants(keepParts, componentOf(p.rel))) : plan;
  if (!kept.length) return { ok: false, message: 'the release has no files; nothing was installed' };
  const made = [], dstExisted = fs.existsSync(dst);
  try {
    fs.mkdirSync(dst, { recursive: true });
    for (const p of kept) { const f = within(dst, p.rel); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, p.data); made.push(f); }
    fs.mkdirSync(path.join(dst, 'Data', 'runtime'), { recursive: true });
    fs.writeFileSync(D.install, JSON.stringify({ schema: 1, version: m.version, channel, installed_at: new Date().toISOString(), ...(recordSource === false ? {} : { source: recordSource || source }), ...(pubkey ? { pubkey } : {}), profile, ...(keepParts ? { parts: keepParts } : {}), ...(m.components ? { components: Object.fromEntries(Object.entries(m.components).filter(([id]) => wants(keepParts, id)).map(([id, c]) => [id, { hash: c.hash }])) } : {}) }, null, 2));
  } catch (e) {
    for (const f of made) { try { fs.unlinkSync(f); } catch {} }   // a half install is removed, only files we wrote
    pruneEmptyDirs(dst, true); if (!dstExisted) { try { fs.rmdirSync(dst); } catch {} }   // and the empty folders it made, so a retry finds an empty folder
    return { ok: false, message: `install stopped: ${writeFailure(e)}; the files it wrote were removed` };
  }
  return { ok: true, message: `PinguinoSuite ${m.version} installed in ${dst}`, version: m.version, files: kept.length, profile };
}

/** Start-menu + desktop shortcuts via PowerShell/WScript. Opt-in; returns the paths made. PINGUINO_SHORTCUT_DIR (tests) puts them in <dir>\Desktop and <dir>\Programs instead. The folders come from Windows (GetFolderPath), so a OneDrive-redirected Desktop works.
 *  A lite-minimal install has no Suite exe: its shortcut starts PinguinoLite\Start-Lite.bat (which also applies a staged Lite update). */
export function shortcutSpec(profile) {
  return profile === 'lite-minimal' ? { exeRel: 'PinguinoLite/Start-Lite.bat', name: 'PinguinoLite' } : { exeRel: 'App/src-tauri/target/release/pinguino-suite.exe', name: 'PinguinoSuite' };
}
export function makeShortcuts({ target, exeRel = 'App/src-tauri/target/release/pinguino-suite.exe', name = 'PinguinoSuite', desktop = true, startMenu = true }) {
  if (process.platform !== 'win32') return [];
  const exe = within(path.resolve(target), exeRel), made = [];
  if (!fs.existsSync(exe)) throw new Error(`${exeRel} is not in this install, so no shortcut was made`);
  const places = [];
  if (startMenu) places.push('Programs');
  if (desktop) places.push('Desktop');
  for (const place of places) {
    const ps = `$d=if($env:PG_DIR){Join-Path $env:PG_DIR $env:PG_PLACE}elseif($env:PG_PLACE -eq 'Programs'){[Environment]::GetFolderPath('Programs')}else{[Environment]::GetFolderPath('Desktop')};New-Item -ItemType Directory -Force -Path $d | Out-Null;$l=Join-Path $d ($env:PG_NAME+'.lnk');$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l);$s.TargetPath=$env:PG_EXE;$s.WorkingDirectory=Split-Path $env:PG_EXE;$s.Save();Write-Output $l`;
    const r = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { env: { ...process.env, PG_PLACE: place, PG_NAME: name, PG_EXE: exe, PG_DIR: process.env.PINGUINO_SHORTCUT_DIR || '' }, windowsHide: true }).toString().trim();
    made.push(r);
  }
  return made;
}
