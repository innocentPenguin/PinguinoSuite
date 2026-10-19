// Shared helpers for the log tools: the logs live in Data\chat_logs\<year>\<month>\<year-month-day>.txt (older flat files cyex-<date>.txt are found too).
// Folders whose name starts with "_" (for example _original-downloads) are ignored.
import { readdirSync } from 'node:fs';
import { join } from 'node:path';

export const dayOf = f => /(\d{4}-\d\d-\d\d)\.txt$/.exec(f)[1];

// relative paths of every day file under root, oldest day first
export function dayFiles(root) {
  const out = [];
  const walk = rel => {
    for (const e of readdirSync(join(root, rel), { withFileTypes: true })) {
      if (e.name.startsWith('_')) continue;
      const r = rel ? join(rel, e.name) : e.name;
      if (e.isDirectory()) walk(r);
      else if (/^(cyex-)?\d{4}-\d\d-\d\d\.txt$/.test(e.name)) out.push(r);
    }
  };
  walk('');
  return out.sort((a, b) => dayOf(a).localeCompare(dayOf(b)) || a.localeCompare(b));
}
