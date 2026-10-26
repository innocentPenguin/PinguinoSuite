// Pinguino Console logging: one JSON line per event in <PINGUINO_DATA_DIR>/console/link.jsonl. Never log tokens, passwords or full URLs with secrets.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.join(process.env.PINGUINO_DATA_DIR || path.resolve(here, '..', '..', '..', '..', 'Data', 'runtime'), 'console');
const FILE = path.join(DIR, 'link.jsonl');
const LEVELS = new Set(['debug', 'info', 'warn', 'error']);
let ready = false, minLevel = 'info', writes = 0;
// Without the Suite core nothing else trims this file (Lite-only PCs), so Link rotates it itself: 2 MB x 3 (same names as the core's Console: link.jsonl.1 ..).
export const MAX_BYTES = 2_000_000, KEEP = 3;
export function rotateIfBig(file, max = MAX_BYTES, keep = KEEP) {
  try {
    if (fs.statSync(file).size <= max) return false;
    for (let i = keep; i >= 1; i--) {
      const src = i === 1 ? file : `${file}.${i - 1}`;
      if (fs.existsSync(src)) fs.renameSync(src, `${file}.${i}`);
    }
    return true;
  } catch { return false; }   // missing file, or a reader holds it: try again later
}
const ORDER = { debug: 0, info: 1, warn: 2, error: 3 };
export const setLevel = l => { if (ORDER[l] !== undefined) minLevel = l; };

// Identical lines inside 30 s are collapsed (a peer retrying every 3 s must not flood the Console).
const recent = new Map();
export function log(level, source, msg) {
  if (!LEVELS.has(level)) level = 'info';
  if (ORDER[level] < ORDER[minLevel]) return;
  const key = `${level}|${source}|${msg}`, now = Date.now(), r = recent.get(key);
  if (r && now - r.at < 30000) { r.n++; return; }
  if (recent.size > 200) recent.clear();
  recent.set(key, { at: now, n: 0 });
  if (r?.n) msg = `${msg} (repeated ${r.n}x before)`;
  const line = JSON.stringify({ ts: Date.now() / 1000, module: 'link', level, source, msg: String(msg).slice(0, 2000) });
  if (level !== 'debug') (level === 'info' ? console.log : console.error)(`${new Date().toISOString().slice(0, 19).replace('T', ' ')}Z [${level}] ${source}: ${msg}`);
  try {
    if (process.env.PINGUINO_NEVER_REAL_OBS && !process.env.PINGUINO_DATA_DIR) return;   // in-process tests must not write to the real Console
    if (!ready) { fs.mkdirSync(DIR, { recursive: true }); ready = true; }
    if (writes++ % 200 === 0) rotateIfBig(FILE);   // first write of a run, then every 200 lines
    fs.appendFileSync(FILE, line + '\n');
  } catch {}   // logging must never break the service
}
export const logFile = FILE;
