// Pinguino Console logging: one JSON line per event in Data/runtime/console/link.jsonl. Never log tokens, passwords or full URLs with secrets.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const DIR = process.env.PINGUINO_CONSOLE_DIR || path.resolve(here, '..', '..', '..', '..', 'Data', 'runtime', 'console');
const FILE = path.join(DIR, 'link.jsonl');
const LEVELS = new Set(['debug', 'info', 'warn', 'error']);
let ready = false;

export function log(level, source, msg) {
  if (!LEVELS.has(level)) level = 'info';
  const line = JSON.stringify({ ts: new Date().toISOString(), module: 'link', level, source, msg: String(msg).slice(0, 500) });
  if (level !== 'debug') (level === 'info' ? console.log : console.error)(`[${level}] ${source}: ${msg}`);
  try {
    if (!ready) { fs.mkdirSync(DIR, { recursive: true }); ready = true; }
    fs.appendFileSync(FILE, line + '\n');
  } catch {}   // logging must never break the service
}
export const logFile = FILE;
