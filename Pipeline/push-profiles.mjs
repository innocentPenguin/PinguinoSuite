// Sends the chatter profiles (Data\profiles\*.json) to the website, where they show up in the public "What PinguinoB0t knows about them" section of every
// member profile (innocentpenguin.com/members/<name>).
//
//   node Pipeline\push-profiles.mjs            push everything (about 30 small requests); update-logs.mjs runs it once a day after the rebuilds
//   node Pipeline\push-profiles.mjs --dry      only show what would be sent
//
// WHAT IS SENT: the whole profile except "clash" (who argues with whom) and the example quotes behind likes / pets / hobbies (the website drops them too).
// Birthday (month and day only) and US state are included. WHO IS LEFT OUT: anyone who used !optmeout / !forgetme with the chat bot (Privacy "anon" / "forget").
// A member can also hide the section for themself in Settings. The notes field is sent as written: keep private things out of it.
// The website address and key come from <data folder>\settings.json (WebSyncUrl / WebSyncKey, the same ones PinguinoB0t uses). Nothing secret is printed.
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
// OPTED-OUT PEOPLE (Data\chat_logs\hidden_sources.json): the public log sites will not serve them, so their messages since the "since" day come from our own recording
// (Data\chat_logs\live, written by the Host; Chatty's own lines are copied in by the boards refresh). Day files are never touched.
{
  const hid = (() => { try { return JSON.parse(readFileSync(join(here, '..', 'Data', 'chat_logs', 'hidden_sources.json'), 'utf8').replace(/^\uFEFF/, '')).users || {}; } catch { return {}; } })();
  const liveDir = join(here, '..', 'Data', 'chat_logs', 'live'); let liveFiles = []; try { liveFiles = readdirSync(liveDir).filter(f => f.endsWith('.jsonl')).sort(); } catch { /* none yet */ }
  for (const [lg, info] of Object.entries(hid)) {
    const p = profiles[lg.toLowerCase()]; if (!p) continue;
    const cut = Date.parse((info.since || '') + 'T00:00:00Z') || 0; let n = Number(info.offset) || 0, lastAt = 0; const per = {};
    for (const f of liveFiles) for (const ln of readFileSync(join(liveDir, f), 'utf8').split('\n')) {
      if (!ln.includes('"u"')) continue; try { const j = JSON.parse(ln.replace(/^\uFEFF/, '')); if ((j.u || '').toLowerCase() !== lg.toLowerCase() || j.t < cut) continue; n++; lastAt = Math.max(lastAt, j.t); const mo = new Date(j.t).toISOString().slice(0, 7); per[mo] = (per[mo] || 0) + 1; } catch { /* bad line */ }
    }
    if (n === 0) continue; if (!p.activity) p.activity = {}; p.activity.messages = (p.activity.messages || 0) + n; p.activity.perMonth = p.activity.perMonth || {};
    for (const [mo, c] of Object.entries(per)) p.activity.perMonth[mo] = (p.activity.perMonth[mo] || 0) + c;
    if (lastAt && p.seen) p.seen.lastSeen = new Date(Math.max(lastAt, Date.parse(p.seen.lastSeen || '') || 0)).toISOString().replace(/\.\d+Z$/, 'Z');
    console.log(`Opted-out ${lg}: +${n} messages from our own recording.`);
  }
}
// LIVE DATA from the Host (refreshed every 10 min and on sub events): active subs straight from Twitch, profile pictures, bots.
const dataRoot = join(here, '..', 'Data');
const readJ = f => { try { return JSON.parse(readFileSync(f, 'utf8')); } catch { return null; } };
const liveSubs = readJ(join(dataRoot, 'subs', 'live_subs.json')), avatars = readJ(join(dataRoot, 'avatars.json')) || {}, botFile = readJ(join(dataRoot, 'profile_bots.json'));
const bots = new Set((botFile && botFile.bots) || []);
let subFlagged = 0, subRemoved = 0, subStubs = 0, avaSet = 0, botSet = 0;
if (liveSubs && liveSubs.users && liveSubs.count > 0) {
  const ageH = (Date.now() / 1000 - (liveSubs.at || 0)) / 3600;
  if (ageH > 1) console.log(`WARNING: the live sub list is ${ageH.toFixed(1)} h old (the Host refreshes it every 10 min while it runs).`);
  for (const [lg, u] of Object.entries(liveSubs.users)) {
    if (out.has(lg)) continue;
    const p = profiles[lg] || (profiles[lg] = { login: lg, name: u.name || lg, roles: {} }); if (!p.roles) p.roles = {};
    if (!readJ(join(profDir, lg + '.json'))) subStubs++;
    if (p.roles.sub !== true || p.roles.lapsed) subFlagged++;
    Object.assign(p.roles, { sub: true, subTier: u.tier || 1, subType: u.prime ? 'prime' : u.isGift ? 'gift' : 'paid', lapsed: false });
    if (u.isGift && u.gifter) p.roles.giftedBy = u.gifter; else delete p.roles.giftedBy;
  }
  // a profile that still says subbed while Twitch has no active sub for it: the sub ended
  for (const [lg, p] of Object.entries(profiles)) if (p.roles && p.roles.sub === true && !liveSubs.users[lg]) { p.roles.sub = false; p.roles.lapsed = true; subRemoved++; }
} else console.log('No live sub list from the Host yet: subs come from the csv import and chat badges only.');
for (const [lg, p] of Object.entries(profiles)) {
  const a = avatars[lg]; if (a && a.url) { p.avatar = a.url; avaSet++; }
  if (bots.has(lg)) { p.isBot = true; botSet++; }
}
console.log(`Live merge: ${liveSubs ? liveSubs.count : 0} active subs per Twitch (${subFlagged} fixed on profiles, ${subStubs} profiles created for subs without one, ${subRemoved} marked ended), ${avaSet} avatars, ${botSet} bots flagged isBot.`);
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
