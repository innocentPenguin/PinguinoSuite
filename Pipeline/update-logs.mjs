// Keeps the chat logs up to date. Meant to run every 5 minutes (a Windows scheduled task, see below), but it can also be run by hand:
//   node Pipeline\update-logs.mjs            quick update: new days + today and yesterday (a few seconds), and once a day the heavier rebuilds
//   node Pipeline\update-logs.mjs --all      also redo the rebuilds right now (nicknames, profiles, lore, stream history)
//
// WHAT IT DOES
//  1. node Pipeline\fetch-chat-logs.mjs   downloads the new chat into Data\chat_logs\<year>\<month>\<date>.txt and updates chat_events.json + chat_profiles.json
//  2. once per calendar day (or with --all): build-nicknames, build-profiles, build-lore, build-history (about 40 s in total), then push-profiles (sends the
//     profiles to the website)
//  0. starts Pipeline\log-agent.mjs if it is not running (the website's Chat logs page asks it to search these logs)
//  Only one update runs at a time (a lock file); output goes to Pipeline\update-logs.log (trimmed so it never grows big).
//
// THE SCHEDULE: a Windows scheduled task "PinguinoBot Log Update" runs Pipeline\update-logs-hidden.vbs every 5 minutes (hidden, no window) while you are
// logged in. Look at it with   schtasks /Query /TN "PinguinoBot Log Update"   and remove it with   schtasks /Delete /TN "PinguinoBot Log Update" /F
import { existsSync, readFileSync, writeFileSync, unlinkSync, statSync, appendFileSync } from 'node:fs';
import { spawnSync, spawn } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const lock = join(here, '.update-logs.lock'), marker = join(here, '.last-rebuild'), logFile = join(here, 'update-logs.log');
const all = process.argv.includes('--all');
const log = s => { const line = `[${new Date().toISOString().slice(0, 19)}Z] ${s}\n`; process.stdout.write(line); try { appendFileSync(logFile, line); } catch { /* ignore */ } };

// the log agent (log-agent.mjs: lets the website's mod-only Chat logs page search these logs) is started here when it is not running (it touches .log-agent.alive)
try {
  let up = false; try { up = Date.now() - statSync(join(here, '.log-agent.alive')).mtimeMs < 30000; } catch { /* never started */ }
  if (!up) { spawn(process.execPath, [join(here, 'log-agent.mjs')], { detached: true, stdio: 'ignore', windowsHide: true }).unref(); log('started the log agent'); }
} catch (e) { log('could not start the log agent: ' + e.message); }

// one run at a time (a lock older than 20 minutes is left over from a crash)
if (existsSync(lock) && Date.now() - statSync(lock).mtimeMs < 20 * 60e3) { log('another update is still running, skipping'); process.exit(0); }
writeFileSync(lock, String(process.pid));
const run = (script, args = []) => { const t0 = Date.now(); const r = spawnSync(process.execPath, [join(here, script), ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }); const out = (r.stdout || '').trim().split('\n').slice(-1)[0] || ''; log(`${script}: ${r.status === 0 ? 'ok' : 'FAILED (' + r.status + ')'} in ${Math.round((Date.now() - t0) / 1000)}s ${out.slice(0, 160)}${r.status === 0 ? '' : ' ' + String(r.stderr || '').trim().split('\n').slice(-1)[0]}`); return r.status === 0; };
try {
  run('fetch-chat-logs.mjs');
  const today = new Date().toISOString().slice(0, 10);   // UTC date = the log day
  let last = ''; try { last = readFileSync(marker, 'utf8').trim(); } catch { /* none */ }
  if (all || last !== today) {
    const ok = ['build-nicknames.mjs', 'build-profiles.mjs', 'build-lore.mjs', 'build-history.mjs'].map(s => run(s)).every(Boolean);
    if (ok) { run('push-profiles.mjs'); writeFileSync(marker, today); }   // send the fresh profiles to the website (public 'What PinguinoB0t knows' section)
  }
} finally {
  try { unlinkSync(lock); } catch { /* ignore */ }
  try { const lines = readFileSync(logFile, 'utf8').split('\n'); if (lines.length > 400) writeFileSync(logFile, lines.slice(-300).join('\n')); } catch { /* ignore */ }
}
