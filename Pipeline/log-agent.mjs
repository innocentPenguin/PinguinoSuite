// The log agent: lets the website's mod-only "Chat logs" page (innocentpenguin.com/mod/chatlogs) search the chat logs that live on THIS PC, so the logs
// never have to be stored online. It only ever calls OUT to the website (long polling), nothing on this PC is opened to the internet.
//
//   node Pipeline\log-agent.mjs        run it by hand (it keeps running; Ctrl+C stops it)
//
// WHO STARTS IT: update-logs.mjs (the 5-minute scheduled task) starts it, hidden, whenever it is not running, so normally you do nothing.
// Only one copy runs (it exits if another one touched Pipeline\.log-agent.alive in the last 30 s). To stop it, end the node.exe process whose command line
// contains log-agent.mjs (Task Manager > Details); it comes back at the next 5-minute update.
// The website address and key come from %AppData%\BVQ\settings.json (WebSyncUrl / WebSyncKey, the same ones PinguinoB0t uses). Nothing secret is printed.
import { readFileSync, writeFileSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { searchLogs } from './lib-logsearch.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const alive = join(here, '.log-agent.alive'), root = join(here, '..', 'Data', 'chat_logs');
try { if (Date.now() - statSync(alive).mtimeMs < 30000) { console.log('another log agent is already running'); process.exit(0); } } catch { /* none */ }

const settings = JSON.parse(readFileSync(join(process.env.APPDATA || '', 'BVQ', 'settings.json'), 'utf8'));
const base = String(settings.WebSyncUrl || '').replace(/\/$/, ''), key = settings.WebSyncKey || '';
if (!base || !key) { console.error('WebSyncUrl / WebSyncKey are not set in settings.json'); process.exit(1); }
const head = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key };
const touch = () => { try { writeFileSync(alive, String(process.pid)); } catch { /* ignore */ } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
console.log('log agent running, asking ' + base);

let failures = 0;
for (;;) {
  touch();
  try {
    const r = await fetch(base + '/api/bot/logjobs?wait=1', { headers: head, signal: AbortSignal.timeout(35000) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    failures = 0;
    for (const job of (await r.json()).jobs || []) {
      let body;
      try { body = { id: job.id, result: searchLogs(root, job.params || {}) }; }
      catch (e) { body = { id: job.id, error: String(e.message || e).slice(0, 150) }; }
      await fetch(base + '/api/bot/logresult', { method: 'POST', headers: head, body: JSON.stringify(body), signal: AbortSignal.timeout(20000) }).catch(() => {});
    }
  } catch {
    failures++;
    await sleep(Math.min(30000, 2000 * failures));   // website down / no internet: wait a little longer each time
  }
}
