// Fills the bot's STREAM HISTORY (%AppData%\BVQ\chat_history.json: what was on stream each day) from the chat logs, for every day the logs cover:
//   * Nightbot's "The stream game has been updated to: X" / "The stream title has been updated to: X" announcements
//   * the bot's own "Stream is live! Today we are streaming X." line
// Days are Central dates (a stream starting 5 PM Central belongs to that date). Existing entries are kept; nothing is duplicated.
//
//   node Pipeline\build-history.mjs        (a few seconds; run it again after importing new logs)
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { dayFiles, dayOf } from './lib-logs.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : process.argv[i + 1]; };
const logsDir = arg('logs', 'D:\\PinguinoSuite\\Data\\chat_logs');
const appData = join(process.env.APPDATA || '', 'BVQ');
const file = join(appData, 'chat_history.json');
let hist = {}; try { hist = JSON.parse(readFileSync(file, 'utf8')); } catch { /* new */ }
const files = dayFiles(logsDir);
let added = 0;
const add = (day, item) => {
  item = item.replace(/\s+/g, ' ').trim().slice(0, 120); if (!item) return;
  const list = hist[day] || (hist[day] = []);
  if (list.some(x => x.toLowerCase().includes(item.toLowerCase()) || item.toLowerCase().includes(x.toLowerCase()))) return;
  list.push(item); added++;
};
for (const f of files) {
  const utcDay = dayOf(f);
  for (const l of readFileSync(join(logsDir, f), 'utf8').split('\n')) {
    const m = /^\[(\d{4}-\d\d-\d\d) (\d\d):(\d\d):\d\d\] #\S+ (\S+): (.*)$/.exec(l); if (!m) continue;
    const [, d, hh, , user, text] = m;
    const t = Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10), +hh);
    const off = (d >= '2026-03-08' && d < '2026-11-01') ? -5 : -6;
    const day = new Date(t + off * 3600e3).toISOString().slice(0, 10);   // Central date
    let g;
    if (user === 'nightbot' && (g = /stream game has been updated to:\s*(.+)$/i.exec(text))) add(day, g[1]);
    else if (user === 'nightbot' && (g = /stream title has been updated to:\s*(.+)$/i.exec(text))) add(day, 'title: ' + g[1]);
    else if (user === 'pinguinob0t' && (g = /Stream is live! Today we are streaming (.+?)\.?$/i.exec(text))) add(day, g[1]);
  }
}
mkdirSync(appData, { recursive: true });
writeFileSync(file, JSON.stringify(Object.fromEntries(Object.entries(hist).sort()), null, 1));
const days = Object.keys(hist).sort();
console.log(`${added} new entries; stream history now covers ${days.length} days (${days[0]} .. ${days[days.length - 1]}).`);
