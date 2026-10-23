// INDEX safefile.mjs: crash-safe JSON files for secrets (config.json, mesh.json): tmp + rename, one .bak, never silently reset.
import fs from 'node:fs';

/** Write via a temp file and rename, keeping the previous good file as <file>.bak. A power cut leaves either the old or the new file, never half. */
export function writeJsonAtomic(file, data) {
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), { mode: 0o600 });
  try { if (fs.existsSync(file)) fs.copyFileSync(file, file + '.bak'); } catch {}
  fs.renameSync(tmp, file);
}

/**
 * Read a JSON object file. Missing or empty -> `fallback`. Damaged -> the .bak if that parses (reported through `warn`),
 * otherwise throws: a damaged secrets file must stop Link, not silently become a new token, a new device id and zero peers.
 */
export function readJsonSafe(file, fallback = {}, warn = () => {}) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch (e) { if (e.code === 'ENOENT') return fallback; throw e; }
  if (!text.trim()) return fallback;
  try { const v = JSON.parse(text); if (v && typeof v === 'object' && !Array.isArray(v)) return v; } catch {}
  try {
    const v = JSON.parse(fs.readFileSync(file + '.bak', 'utf8'));
    if (v && typeof v === 'object' && !Array.isArray(v)) { warn(`${file} was damaged; restored from the last good copy (.bak)`); try { fs.copyFileSync(file, file + '.damaged'); } catch {} return v; }
  } catch {}
  throw new Error(`${file} is damaged and has no usable .bak. Fix or delete it by hand (a copy of the damaged file is not overwritten); Link will not reset it silently.`);
}
