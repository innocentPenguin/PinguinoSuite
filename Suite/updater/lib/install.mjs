// INDEX install.mjs: fresh install of a release into an empty (or new) folder. Same verification and path rules as the Updater; creates Data\ empty,
// writes install.json (version, channel, source) so the Updater knows where to look. Shortcuts are optional and only made when asked.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { openSource } from './sources.mjs';
import { readZip } from './zip.mjs';
import { safeRel, within } from './paths.mjs';
import { sha256, dirs } from './apply.mjs';

/** Install from one source spec. Returns {ok, message, version}. Never overwrites an existing install (that is the Updater's job). */
export async function installRelease({ target, source, channel = 'stable', repairOver = false }) {
  const dst = path.resolve(target), D = dirs(dst);
  if (fs.existsSync(D.install) && !repairOver) return { ok: false, message: 'Suite is already installed here; use the Updater (or pick another folder)' };
  if (fs.existsSync(dst) && fs.readdirSync(dst).length && !fs.existsSync(D.install)) return { ok: false, message: 'that folder is not empty; pick an empty folder' };
  const src = await openSource(source), m = src.manifest;
  if (m.channel !== channel && !(channel === 'beta' && m.channel === 'stable')) return { ok: false, message: `that release is on the ${m.channel} channel` };
  const plan = [];
  for (const f of m.files) {
    const buf = await src.fetchFile(f);
    if (buf.length !== f.size || sha256(buf) !== f.sha256) return { ok: false, message: `${f.name} failed its sha256 check; nothing was installed` };
    if (!f.name.endsWith('.zip')) continue;
    for (const e of readZip(buf)) { if (e.dir) { safeRel(e.name); continue; } if (e.link) throw new Error(`release contains a link: ${e.name}`); plan.push({ rel: safeRel(e.name), data: e.data() }); }
  }
  if (!plan.length) return { ok: false, message: 'the release has no files; nothing was installed' };
  const made = [];
  try {
    fs.mkdirSync(dst, { recursive: true });
    for (const p of plan) { const f = within(dst, p.rel); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, p.data); made.push(f); }
    fs.mkdirSync(path.join(dst, 'Data', 'runtime'), { recursive: true });
    fs.writeFileSync(D.install, JSON.stringify({ schema: 1, version: m.version, channel, installed_at: new Date().toISOString(), source }, null, 2));
  } catch (e) {
    for (const f of made) { try { fs.unlinkSync(f); } catch {} }   // a half install is removed, only files we wrote
    return { ok: false, message: `install stopped: ${String(e.message).slice(0, 160)}; the files it wrote were removed` };
  }
  return { ok: true, message: `PinguinoSuite ${m.version} installed in ${dst}`, version: m.version, files: plan.length };
}

/** Start-menu + desktop shortcuts to the app exe via PowerShell/WScript. Opt-in; returns the paths made. */
export function makeShortcuts({ target, exeRel = 'App/src-tauri/target/release/pinguino-suite.exe', name = 'PinguinoSuite', desktop = true, startMenu = true }) {
  if (process.platform !== 'win32') return [];
  const exe = within(path.resolve(target), exeRel), made = [];
  const places = [];
  if (startMenu) places.push(path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs', `${name}.lnk`));
  if (desktop) places.push(path.join(process.env.USERPROFILE || '', 'Desktop', `${name}.lnk`));
  for (const lnk of places) {
    const ps = `$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PG_LNK);$s.TargetPath=$env:PG_EXE;$s.WorkingDirectory=Split-Path $env:PG_EXE;$s.Save()`;
    execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { env: { ...process.env, PG_LNK: lnk, PG_EXE: exe }, windowsHide: true });
    made.push(lnk);
  }
  return made;
}
