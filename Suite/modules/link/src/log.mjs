// Pinguino Console logging: one JSON line per event in <PINGUINO_DATA_DIR>/console/link.jsonl. Never log tokens, passwords or full URLs with secrets.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.join(process.env.PINGUINO_DATA_DIR || path.resolve(here, '..', '..', '..', '..', 'Data', 'runtime'), 'console');
const FILE = path.join(DIR, 'link.jsonl');
const LEVELS = new Set(['debug', 'info', 'warn', 'error']);
let ready = false, minLevel = 'info';
const ORDER = { debug: 0, info: 1, warn: 2, error: 3 };
export const setLevel = l => { if (ORDER[l] !== undefined) minLevel = l; };

export function log(level, source, msg) {
  if (!LEVELS.has(level)) level = 'info';
  if (ORDER[level] < ORDER[minLevel]) return;
  const line = JSON.stringify({ ts: Date.now() / 1000, module: 'link', level, source, msg: String(msg).slice(0, 2000) });
  if (level !== 'debug') (level === 'info' ? console.log : console.error)(`[${level}] ${source}: ${msg}`);
  try {
    if (!ready) { fs.mkdirSync(DIR, { recursive: true }); ready = true; }
    fs.appendFileSync(FILE, line + '\n');
  } catch {}   // logging must never break the service
}
export const logFile = FILE;
