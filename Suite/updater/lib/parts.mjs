// INDEX parts.mjs: take one on-demand part out of an install (eject) and check an installed part against the release (verify).
// Eject MOVES the part's files to Data/updates/ejected/<part>-<time>/ (nothing is deleted; module data/ folders, Data\ and secrets are never touched).
// Verify is read-only: each installed part's files are compared with the release package (missing / different files are listed; extra local files are ignored).
import fs from 'node:fs';
import path from 'node:path';
import { openSource } from './sources.mjs';
import { readZip } from './zip.mjs';
import { safeRel, within } from './paths.mjs';
import { COMPONENTS, COMPONENT_IDS, componentOf, SKIP_DIR, SKIP_FILE } from './components.mjs';
import { dirs, sha256 } from './apply.mjs';
import { partsOf, wants, isOptionalPart } from './profiles.mjs';

const iso = () => new Date().toISOString();
const readJson = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };
const writeJson = (f, o) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f + '.tmp', JSON.stringify(o, null, 2)); fs.renameSync(f + '.tmp', f); };

/** Files (relative, forward slashes) under the install that belong to a part, honouring the same skip rules as the release builder. */
export function partFiles(installDir, id) {
  const c = COMPONENTS.find(x => x.id === id); if (!c || !c.match.length) return [];
  const out = [];
  const walk = (abs, rel) => {
    let st; try { st = fs.statSync(abs); } catch { return; }
    if (st.isDirectory()) { if (SKIP_DIR.test(rel + '/')) return; for (const n of fs.readdirSync(abs)) walk(path.join(abs, n), `${rel}/${n}`); return; }
    if (!SKIP_FILE.test(rel) && !rel.endsWith('.pinguino-new')) out.push(rel);
  };
  for (const m of c.match) walk(path.join(installDir, m), m.replace(/\/$/, ''));
  return out;
}

/** Move an optional part's files aside and drop it from install.json. The caller stops the module first. */
export function ejectPart(installDir, id) {
  if (!COMPONENT_IDS.has(id)) return { ok: false, message: `unknown part: ${id}` };
  if (!isOptionalPart(id)) return { ok: false, message: `${id} is not an on-demand part; it cannot be taken out` };
  const D = dirs(installDir), inst = readJson(D.install);
  if (!inst) return { ok: false, message: 'this is not a release install (no install.json)' };
  const parts = partsOf(inst);
  if (parts && !parts.includes(id)) return { ok: true, message: `${id} is not installed`, moved: 0 };
  const files = partFiles(installDir, id), folder = path.join(D.u, 'ejected', `${id}-${iso().replace(/[-:T]/g, '').slice(0, 14)}`);
  let moved = 0;
  for (const rel of files) {
    const src = within(installDir, safeRel(rel)), dst = path.join(folder, 'files', rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.renameSync(src, dst); moved++;
  }
  const all = COMPONENTS.map(c => c.id), next = (parts || all).filter(x => x !== id), comps = { ...(inst.components || {}) };
  delete comps[id];
  writeJson(D.install, { ...inst, parts: next, ...(inst.components ? { components: comps } : {}) });
  writeJson(path.join(folder, 'ejected.json'), { schema: 1, part: id, at: iso(), moved, from: inst.version });
  return { ok: true, message: moved ? `${id} taken out (${moved} files kept in ${path.relative(installDir, folder).replace(/\\/g, '/')})` : `${id} taken out`, moved, kept_in: moved ? folder : null };
}

/** Compare installed parts with the release. `only` = a list of part ids; default = every installed part except scripts/docs. */
export async function verifyParts({ installDir, source, channel = 'stable', pubkey = null, only = null }) {
  const D = dirs(installDir), inst = readJson(D.install) || {}, parts = partsOf(inst);
  const src = await openSource(source, { pubkey }), m = src.manifest;
  const ids = (only && only.length ? only : COMPONENTS.map(c => c.id).filter(id => id !== 'tools')).filter(id => wants(parts, id));
  const bad = ids.filter(id => !COMPONENT_IDS.has(id)); if (bad.length) return { ok: false, message: `unknown part: ${bad.join(', ')}` };
  const want = new Map();
  for (const f of m.files) {
    if (!f.name.endsWith('.zip')) continue;
    const buf = await src.fetchFile(f);
    if (buf.length !== f.size || sha256(buf) !== f.sha256) return { ok: false, message: `${f.name} failed its sha256 check` };
    for (const e of readZip(buf)) { if (e.dir || e.link) continue; const rel = safeRel(e.name); if (ids.includes(componentOf(rel))) want.set(rel, sha256(e.data())); }
  }
  const results = [];
  for (const id of ids) {
    const missing = [], changed = []; let total = 0;
    for (const [rel, h] of want) {
      if (componentOf(rel) !== id) continue;
      total++;
      let b; try { b = fs.readFileSync(within(installDir, rel)); } catch { missing.push(rel); continue; }
      if (sha256(b) !== h) changed.push(rel);
    }
    const state = total === 0 ? 'not-in-release' : (missing.length || changed.length) ? (missing.length === total ? 'missing' : 'damaged') : 'ok';
    results.push({ id, name: COMPONENTS.find(c => c.id === id).name, state, files: total, missing: missing.slice(0, 20), changed: changed.slice(0, 20), missing_count: missing.length, changed_count: changed.length });
  }
  return { ok: true, version: m.version, current: inst.version || null, parts: results, all_ok: results.every(r => r.state === 'ok') };
}
