// INDEX paths.mjs: what a release is allowed to write. Every name inside a release zip goes through safeRel() before anything touches disk.
import path from 'node:path';

const SECRET_RE = /^(\.env.*|.*\.(pem|key|pfx|p12|vault)|secrets?\.(json|txt|ini|dat|enc)|tokens?\.(json|txt|dat)|vault\.(json|dat|enc|db)|credentials?\.(json|txt|ini)|oauth.*\.json)$/i;   // data-like secret files only: source files such as vault.py are normal code
export const PROTECTED_TOP = new Set(['data', '.git', '.venv', 'node_modules']);

/** Returns the clean forward-slash relative path, or throws with the reason. */
export function safeRel(name) {
  if (typeof name !== 'string' || !name || name.length > 240) throw new Error(`bad path in release: ${String(name).slice(0, 60)}`);
  if (name.includes('\0') || name.includes('\\') || name.startsWith('/') || /^[a-zA-Z]:/.test(name) || name.includes(':')) throw new Error(`absolute or odd path in release: ${name}`);
  const parts = name.replace(/\/+$/, '').split('/');
  for (const p of parts) if (p === '' || p === '.' || p === '..' || p.endsWith('.') || p.endsWith(' ')) throw new Error(`path escapes the install folder: ${name}`);
  if (PROTECTED_TOP.has(parts[0].toLowerCase())) throw new Error(`release may not write into ${parts[0]}: ${name}`);
  if (SECRET_RE.test(parts[parts.length - 1])) throw new Error(`release contains a secret-looking file name: ${name}`);
  return parts.join('/');
}

/** Absolute path inside root for a clean relative path (second line of defence). */
export function within(root, rel) {
  const base = path.resolve(root), full = path.resolve(base, rel);
  if (full !== base && !full.startsWith(base + path.sep)) throw new Error(`path escapes the install folder: ${rel}`);
  return full;
}
