// Sends the chatter profiles (Data\profiles\*.json) to the website, where they show up in the public "What PinguinoB0t knows about them" section of every
// member profile (innocentpenguin.com/members/<name>).
//
//   node Pipeline\push-profiles.mjs            push everything (about 30 small requests); update-logs.mjs runs it once a day after the rebuilds
//   node Pipeline\push-profiles.mjs --dry      only show what would be sent
//
// WHAT IS SENT: the whole profile except "clash" (who argues with whom) and the example quotes behind likes / pets / hobbies (the website drops them too).
// Birthday (month and day only) and US state are included. WHO IS LEFT OUT: anyone who used !optmeout / !forgetme with the chat bot (Privacy "anon" / "forget").
// A member can also hide the section for themself in Settings. The notes field is sent as written: keep private things out of it.
// The website address and key come from %AppData%\BVQ\settings.json (WebSyncUrl / WebSyncKey, the same ones PinguinoB0t uses). Nothing secret is printed.
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { dataDir } from './lib-paths.mjs';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const profDir = join(here, '..', 'Data', 'profiles');
const appData = dataDir();
const dry = process.argv.includes('--dry');
const settings = JSON.parse(readFileSync(join(appData, 'settings.json'), 'utf8'));
const base = String(settings.WebSyncUrl || '').replace(/\/$/, ''), key = settings.WebSyncKey || '';
if (!dry && (!base || !key)) { console.error('WebSyncUrl / WebSyncKey are not set in settings.json'); process.exit(1); }

// viewers who opted out of the chat bot's memory
const out = new Set();
try {
  const mem = JSON.parse(readFileSync(join(appData, 'chat_memory.json'), 'utf8'));
  for (const v of Object.values(mem)) if (v && (v.Privacy === 'anon' || v.Privacy === 'forget')) { if (v.Login) out.add(String(v.Login).toLowerCase()); for (const a of v.Aliases || []) out.add(String(a).toLowerCase()); }
} catch { /* no memory file */ }

const profiles = {};
for (const f of readdirSync(profDir)) {
  if (!/\.json$/.test(f) || f === 'index.json') continue;
  const login = f.slice(0, -5).toLowerCase();
  if (out.has(login)) continue;
  try {
    const p = JSON.parse(readFileSync(join(profDir, f), 'utf8'));
    delete p.clash;
    if (p.seen) { delete p.seen.lastMessage; delete p.seen.seenBeforeTheLogsStart; }
    profiles[login] = p;
  } catch { /* skip a broken file */ }
}
const logins = Object.keys(profiles);
console.log(`${logins.length} profiles ready (${out.size} opted-out people left out).`);
if (dry) process.exit(0);

async function post(body) {
  for (let i = 0; i < 4; i++) {
    try {
      const r = await fetch(base + '/api/bot/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key }, body: JSON.stringify(body), signal: AbortSignal.timeout(60000) });
      if (r.ok) return r.json();
      if (r.status === 404) throw new Error('the website does not have /api/bot/profiles yet (deploy it first)');
      if (r.status === 401) throw new Error('the website refused the key (WebSyncKey)');
    } catch (e) { if (i === 3 || /deploy|refused/.test(e.message)) throw e; }
    await new Promise(r => setTimeout(r, 1500 * (i + 1)));
  }
}
const CHUNK = 50;
let sent = 0, last = null;
for (let i = 0; i < logins.length; i += CHUNK) {
  const part = {};
  for (const l of logins.slice(i, i + CHUNK)) part[l] = profiles[l];
  last = await post({ profiles: part, reset: i === 0 });
  sent += last.count;
}
console.log(`Done: ${sent} profiles sent, the website now holds ${last?.total}.`);
