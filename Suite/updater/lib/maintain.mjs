// INDEX maintain.mjs: repair and uninstall for an existing install (used by Installer/install.mjs --repair / --uninstall).
// Repair = verify every installed part against the release, then re-apply each damaged one with the updater's own repair mode (backup first, hash-checked).
// Uninstall MOVES (never deletes) the install's contents into Data/updates/ejected/uninstall-<time>/ inside the install folder itself; Data\ (settings, tokens, vault) stays
// unless purgeData is set, and nothing happens without apply = true (the default is a list of what would move).
import fs from 'node:fs';
import path from 'node:path';
import { verifyParts } from './parts.mjs';
import { applyUpdate, dirs } from './apply.mjs';

const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };
const stamp = () => new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);

/** Part ids that are not ok in a verify result. */
export const damagedParts = v => (v && v.parts || []).filter(p => p.state !== 'ok').map(p => p.id);

export async function repairInstall({ installDir, source, channel = 'stable', pubkey = null, liveCheck }) {
  const D = dirs(installDir), inst = readJson(D.install);
  if (!inst) return { ok: false, message: 'there is no install.json here, so this folder is not an install' };
  if (!source) return { ok: false, message: 'no update source is set (install.json has none); give --source <folder|zip|https manifest>' };
  const v = await verifyParts({ installDir, source, channel, pubkey });
  if (!v.ok) return { ok: false, message: v.message || 'verify failed', verify: v };
  const bad = damagedParts(v);
  if (!bad.length) return { ok: true, message: 'every installed part is intact; nothing to repair', repaired: [] };
  const repaired = [], failed = [];
  for (const id of bad) {
    const r = await applyUpdate({ installDir, source, current: inst.version || '0.0.0', channel, pubkey, only: [id], repair: true, ...(liveCheck ? { liveCheck } : {}) });
    (r.ok ? repaired : failed).push(r.ok ? id : { id, message: r.message });
  }
  return { ok: failed.length === 0, message: failed.length ? `repaired ${repaired.length}, failed ${failed.length}` : `repaired ${repaired.join(', ')}`, repaired, failed };
}

export function uninstallInstall({ installDir, purgeData = false, apply = false, now = stamp }) {
  const root = path.resolve(installDir), D = dirs(root);
  if (!fs.existsSync(D.install)) return { ok: false, message: 'there is no install.json here, so this folder is not an install' };
  const dest = path.join(D.u, 'ejected', `uninstall-${now()}`);
  const top = fs.readdirSync(root).filter(n => n !== 'Data');
  const dataKids = purgeData && fs.existsSync(path.join(root, 'Data')) ? fs.readdirSync(path.join(root, 'Data')).filter(n => n !== 'updates') : [];
  const plan = [...top, ...dataKids.map(n => `Data/${n}`)];
  if (!apply) return { ok: true, dryRun: true, message: `nothing moved yet. Add --yes to move ${plan.length} items into ${dest}${purgeData ? ' (including your Data folder)' : '; Data\ stays'}`, items: plan, dest };
  const moved = [], failed = [];
  const move = rel => {
    const from = path.join(root, ...rel.split('/')), to = path.join(dest, ...rel.split('/'));
    try { fs.mkdirSync(path.dirname(to), { recursive: true }); fs.renameSync(from, to); moved.push(rel); }
    catch (e) { failed.push({ item: rel, message: e.code === 'EBUSY' || e.code === 'EPERM' ? 'in use (close the app first)' : String(e.message).slice(0, 120) }); }
  };
  // install.json goes last, so an interrupted run still looks like an install and can be run again
  for (const n of top.filter(n => n !== 'install.json')) move(n);
  for (const n of dataKids) move(`Data/${n}`);
  if (!failed.length && top.includes('install.json')) move('install.json');
  fs.mkdirSync(dest, { recursive: true });
  fs.writeFileSync(path.join(dest, 'uninstalled.json'), JSON.stringify({ schema: 1, at: new Date().toISOString(), moved, failed, purgeData }, null, 2));
  return { ok: failed.length === 0, message: failed.length ? `moved ${moved.length}, ${failed.length} could not be moved (close the Suite/Lite and run it again)` : `moved ${moved.length} items to ${dest}; nothing was deleted`, moved, failed, dest };
}
