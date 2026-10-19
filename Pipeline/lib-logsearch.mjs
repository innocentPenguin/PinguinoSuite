// Searches the chat log files (Data\chat_logs\<year>\<month>\<date>.txt, times in UTC) for the website's mod-only "Chat logs" page.
// Used by log-agent.mjs. Line formats:
//   [2026-10-19 22:41:07] #innocentpenguin_ snowyroses_: yo          a chat message
//   [2026-10-16 22:11:27] #innocentpenguin_ * 48 raiders ...         a notice (subs, gifts, raids, timeouts, bans)
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { dayFiles, dayOf } from './lib-logs.mjs';

const LINE = /^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\] #\S+ (.*)$/;
const COUNT_CAP = 20000;   // stop counting matches after this many (the page shows "20000+")

// p = {q, user, day, from, to, type: all|chat|notice, order: new|old, limit, offset}
export function searchLogs(root, p) {
  const t0 = Date.now();
  const files = dayFiles(root);
  const first = files.length ? dayOf(files[0]) : '', last = files.length ? dayOf(files[files.length - 1]) : '';
  const from = p.day || p.from || '', to = p.day || p.to || '';
  let sel = files.filter(f => { const d = dayOf(f); return (!from || d >= from) && (!to || d <= to); });
  if (p.order !== 'old') sel = sel.reverse();
  const words = String(p.q || '').toLowerCase().split(/\s+/).filter(Boolean);
  const user = String(p.user || '').toLowerCase();
  const type = p.type === 'chat' || p.type === 'notice' ? p.type : 'all';
  const limit = Math.max(1, Math.min(200, p.limit | 0 || 100)), offset = Math.max(0, p.offset | 0);
  const rows = [];
  let seen = 0, capped = false;
  for (const f of sel) {
    let text;
    try { text = readFileSync(join(root, f), 'utf8'); } catch { continue; }
    const low = text.toLowerCase();
    if (user && !low.includes(user)) continue;                       // quick skip of days that cannot match
    if (words.length && !words.every(w => low.includes(w))) continue;
    const lines = text.split('\n');
    const idx = p.order === 'old' ? i => i : i => lines.length - 1 - i;
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[idx(i)].replace(/\r$/, '');
      const m = LINE.exec(raw);
      if (!m) continue;
      const body = m[3], notice = body.startsWith('* ');
      if (type === 'chat' && notice) continue;
      if (type === 'notice' && !notice) continue;
      let u = '', msg = body;
      if (notice) msg = body.slice(2);
      else { const c = body.indexOf(': '); if (c > 0) { u = body.slice(0, c); msg = body.slice(c + 2); } }
      if (user) {
        if (!notice && u.toLowerCase() !== user) continue;
        if (notice && !msg.toLowerCase().includes(user)) continue;
      }
      if (words.length) { const ml = msg.toLowerCase(); if (!words.every(w => ml.includes(w))) continue; }
      if (seen >= offset && rows.length < limit) rows.push({ d: m[1], t: m[2], u, m: msg.slice(0, 600), n: notice });
      seen++;
      if (seen >= COUNT_CAP) { capped = true; break; }
    }
    if (capped) break;
  }
  return { rows, total: seen, capped, hasMore: seen > offset + rows.length, first, last, days: files.length, ms: Date.now() - t0 };
}
