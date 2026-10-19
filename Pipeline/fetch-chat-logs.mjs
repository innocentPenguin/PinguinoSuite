// Downloads the channel's chat logs (every day the public log sites have) into Data\chat_logs, organised by year / month / day, fills the bot's
// event memory (subs, resubs, gifted subs, raids, bits) and builds a profile of every chatter (first seen, messages, active days, roles, who they talk with).
//
//   node Pipeline\fetch-chat-logs.mjs                       every logged day not downloaded yet (today + yesterday are always refreshed)
//   node Pipeline\fetch-chat-logs.mjs --since 2026-09-01    only days from that date on
//   node Pipeline\fetch-chat-logs.mjs --list                just show which days are available (and from which site)
//   node Pipeline\fetch-chat-logs.mjs --rebuild             download every day again and rebuild the chatter profiles from zero
//   node Pipeline\fetch-chat-logs.mjs --no-events           do not touch chat_events.json
//   node Pipeline\fetch-chat-logs.mjs --for-study           also copy new day files to <data folder>\chat_logs\import (the bot learns from them at
//                                                      its next study; this costs a few AI calls)
//   options: --channel innocentpenguin_   --out D:\PinguinoSuite\Data\chat_logs   --host https://a.example,https://b.example
//
// WHERE THE LOGS GO (readable by hand, one text file per day, UTC):
//   Data\chat_logs\2026\10\2026-10-19.txt      Data\chat_logs\INDEX.md (days and message counts per month)      Data\chat_logs\README.md
//   a message:  [2026-10-19 22:41:07] #innocentpenguin_ snowyroses_: yo
//   a notice:   [2026-10-16 22:11:27] #innocentpenguin_ * 48 raiders from DoctorNopeRope have joined!      (subs, gifts, raids, milestones)
//               [2026-10-17 01:14:09] #innocentpenguin_ * snowyroses_ was timed out for 600s                (timeouts, bans, chat clears)
//
// SOURCES: public Twitch chat-log services built on the "rustlog" API (default: https://logs.cyex.app, then https://logs.zonian.dev and
// https://logs.potat.app). Together they have innocentpenguin_ from 2026-02-15 on (the earliest day any of them has; nothing older exists
// anywhere I could find, Twitch VODs expire). API: GET /list?channel=<c> (available days) and GET /channel/<c>/<yyyy>/<m>/<d>?raw (raw IRC lines).
// For every day the first site that has it is used. The bot reads every *.txt under chat_logs by itself (shows times in Central, skips duplicate lines).
// Also written to <data folder>\: chat_events.json (subs / raids / bits, last 400 days) and chat_profiles.json (one profile per chatter).
// Run it now and then (e.g. every few days) to keep everything up to date. Only public chat is stored.
import { readFileSync, writeFileSync, existsSync, mkdirSync, copyFileSync, readdirSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { dataDir } from './lib-paths.mjs';
import { dayFiles, dayOf } from './lib-logs.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const channel = String(arg('channel', 'innocentpenguin_')).toLowerCase();
const outDir = String(arg('out', 'D:\\PinguinoSuite\\Data\\chat_logs'));
const hosts = String(arg('host', 'https://logs.cyex.app,https://logs.zonian.dev,https://logs.potat.app')).split(',').map(h => h.trim().replace(/\/$/, '')).filter(Boolean);
const since = String(arg('since', ''));
const listOnly = arg('list', false) === true;
const noEvents = arg('no-events', false) === true;
const forStudy = arg('for-study', false) === true;
const rebuild = arg('rebuild', false) === true;   // download EVERY day again and rebuild the chatter profiles from zero
const LOG_FORMAT = 2;   // 2 = year/month/day folders + notice / timeout lines in the files
const sleep = ms => new Promise(r => setTimeout(r, ms));
const pad = n => String(n).padStart(2, '0');
const stamp = t => { const d = new Date(t); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`; };
const appData = dataDir();
const dayPath = day => join(outDir, day.slice(0, 4), day.slice(5, 7), day + '.txt');

async function get(url, as = 'text') {
  for (let i = 0; i < 4; i++) {
    try {
      const r = await fetch(url, { headers: { 'User-Agent': 'PinguinoBot-log-import/1.0' }, signal: AbortSignal.timeout(60000) });
      if (r.ok) return as === 'json' ? r.json() : r.text();
      if (r.status === 404) return null;
      if (r.status !== 429 && r.status < 500) throw new Error('HTTP ' + r.status);
    } catch (e) { if (i === 3) throw e; }
    await sleep(1500 * (i + 1));
  }
  throw new Error('kept failing: ' + url);
}

// IRC tags: "@a=b;c=d" with \s \: \\ escapes
const unesc = s => String(s || '').replace(/\\(s|:|\\|r|n)/g, (m, c) => ({ s: ' ', ':': ';', '\\': '\\', r: '\r', n: '\n' }[c]));
function parse(line) {
  if (!line.startsWith('@')) return null;
  const sp = line.indexOf(' ');
  const tags = {};
  for (const kv of line.slice(1, sp).split(';')) { const i = kv.indexOf('='); if (i > 0) tags[kv.slice(0, i)] = kv.slice(i + 1); }
  const rest = line.slice(sp + 1);
  let m;
  if ((m = /^:([^!\s]+)![^ ]* PRIVMSG #\S+ :(.*)$/.exec(rest))) return { kind: 'msg', tags, user: m[1].toLowerCase(), text: m[2] };
  if ((m = /^:\S+ USERNOTICE #\S+(?: :(.*))?$/.exec(rest))) return { kind: 'notice', tags, text: m[1] || '' };
  if ((m = /^:\S+ CLEARCHAT #\S+(?: :(\S+))?$/.exec(rest))) return { kind: 'clear', tags, user: (m[1] || '').toLowerCase() };
  return null;
}
const tier = p => (p === 'Prime' ? 1 : Math.max(1, Math.min(3, Math.round((parseInt(p, 10) || 1000) / 1000))));
const BOTS = new Set(['nightbot', 'streamelements', 'pinguinob0t', 'potatbotat', 'sery_bot', 'synchrabot', 'soundalerts', 'streamlabs', 'moobot', 'fossabot']);
const noticeText = p => {
  const sys = unesc(p.tags['system-msg']).trim();
  const base = sys || ({ raid: `${p.tags['msg-param-viewerCount']} raiders from ${p.tags['msg-param-displayName'] || p.tags['login']} have joined!`, sub: `${p.tags['login']} subscribed`, resub: `${p.tags['login']} resubscribed` }[p.tags['msg-id']] || `${p.tags['msg-id'] || 'notice'} ${p.tags['login'] || ''}`.trim());
  const extra = p.text ? ` - "${p.text.replace(/[\r\n]+/g, ' ').trim()}"` : '';
  return (base + extra).replace(/[\r\n]+/g, ' ');
};

(async () => {
  // which site has which day (the first site in --host order that has it wins)
  const dayHost = new Map();
  for (const h of hosts) {
    try {
      const list = await get(`${h}/list?channel=${encodeURIComponent(channel)}`, 'json');
      for (const d of list?.availableLogs || []) { const k = `${d.year}-${pad(+d.month)}-${pad(+d.day)}`; if (!dayHost.has(k)) dayHost.set(k, h); }
    } catch (e) { console.log('  (site ' + h + ' not reachable: ' + e.message + ')'); }
  }
  const days = [...dayHost.keys()].sort().filter(d => !since || d >= since);
  if (!days.length) { console.log('No logged days found for ' + channel); return; }
  console.log(`${days.length} logged day(s) for ${channel}: ${days[0]} .. ${days[days.length - 1]}`);
  if (listOnly) { const by = {}; for (const d of days) by[dayHost.get(d)] = (by[dayHost.get(d)] || 0) + 1; console.log(by); return; }
  mkdirSync(outDir, { recursive: true }); mkdirSync(appData, { recursive: true });

  // move older flat files (cyex-YYYY-MM-DD.txt) into the year/month folders; the downloads you gave me by hand go to _original-downloads
  let moved = 0;
  for (const f of readdirSync(outDir)) {
    const m = /^cyex-(\d{4}-\d\d-\d\d)\.txt$/.exec(f);
    if (m) { const to = dayPath(m[1]); mkdirSync(join(to, '..'), { recursive: true }); if (!existsSync(to)) { renameSync(join(outDir, f), to); moved++; } continue; }
    if (/^(\d\d-\d\d|combined_chat_7days)\.txt$/.test(f)) { mkdirSync(join(outDir, '_original-downloads'), { recursive: true }); renameSync(join(outDir, f), join(outDir, '_original-downloads', f)); }
  }
  if (moved) console.log(`Moved ${moved} older day file(s) into the year/month folders.`);

  const importDir = join(appData, 'chat_logs', 'import');
  const evFile = join(appData, 'chat_events.json'), profFile = join(appData, 'chat_profiles.json');
  let events = []; try { events = JSON.parse(readFileSync(evFile, 'utf8')); } catch { /* new */ }
  let prof = { channel, users: {}, processedDays: [] }; try { prof = JSON.parse(readFileSync(profFile, 'utf8')); } catch { /* new */ }
  if (rebuild) prof = { channel, users: {}, processedDays: [] };
  const done = new Set(prof.processedDays || []);
  const upToDate = prof.logFormat === LOG_FORMAT && !rebuild;   // older day files have no notice lines: fetch them once more
  const addEv = (type, user, amount, to, t) => {
    const at = Math.floor(t / 1000); user = String(user || '').toLowerCase(); to = String(to || '').toLowerCase();
    if (!user) return false;
    if (events.some(e => e.Type === type && e.User === user && e.To === to && e.Amount === amount && Math.abs(e.At - at) < 20)) return false;   // same announcement twice
    events.push({ At: at, Type: type, User: user, Amount: amount, To: to }); return true;
  };
  const today = new Date().toISOString().slice(0, 10), yday = new Date(Date.now() - 864e5).toISOString().slice(0, 10);
  let files = 0, msgs = 0, evAdded = 0, skipped = 0;
  for (const day of days) {
    const file = dayPath(day);
    const refresh = day === today || day === yday;
    if (existsSync(file) && upToDate && done.has(day) && !refresh) { skipped++; continue; }
    const [y, mo, d] = day.split('-');
    const raw = await get(`${dayHost.get(day)}/channel/${encodeURIComponent(channel)}/${y}/${+mo}/${+d}?raw`);
    if (raw == null) { console.log('  ' + day + ': not available'); continue; }
    const rows = [], dayProf = {};
    for (const line of raw.split(/\r?\n/)) {
      const p = parse(line); if (!p) continue;
      const t = Number(p.tags['tmi-sent-ts']); if (!t) continue;
      if (p.kind === 'msg') {
        const text = p.text.replace(/^\u0001ACTION (.*)\u0001$/, '$1').replace(/[\r\n]+/g, ' ').trim();
        if (!text) continue;
        rows.push({ t, u: p.user, m: text });
        const pr = dayProf[p.user] || (dayProf[p.user] = { name: p.tags['display-name'] || p.user, msgs: 0, first: t, last: t, mod: false, vip: false, sub: false, subMonths: 0, bits: 0, talks: {} });
        pr.msgs++; pr.last = t; pr.first = Math.min(pr.first, t);
        const b = p.tags.badges || '';
        if (/(^|,)moderator\//.test(b)) pr.mod = true; if (/(^|,)vip\//.test(b)) pr.vip = true;
        if (/(^|,)subscriber\//.test(b)) { pr.sub = true; const sm = /subscriber\/(\d+)/.exec(p.tags['badge-info'] || ''); if (sm) pr.subMonths = Math.max(pr.subMonths, +sm[1]); }
        if (p.tags.bits && +p.tags.bits > 0) { pr.bits += +p.tags.bits; if (!noEvents && addEv('cheer', p.user, +p.tags.bits, '', t)) evAdded++; }
        for (const m of text.matchAll(/@([A-Za-z0-9_]{3,25})/g)) { const o = m[1].toLowerCase(); if (o !== p.user) pr.talks[o] = (pr.talks[o] || 0) + 1; }
      } else if (p.kind === 'notice') {
        rows.push({ t, u: '*', m: noticeText(p) });
        if (!noEvents) {
          const id = p.tags['msg-id'], login = (p.tags['login'] || '').toLowerCase();
          if (id === 'raid') { if (addEv('raidin', login, +p.tags['msg-param-viewerCount'] || 0, '', t)) evAdded++; }
          else if (id === 'sub' || id === 'resub') { if (addEv(id, login, tier(p.tags['msg-param-sub-plan']), '', t)) evAdded++; }
          else if (id === 'subgift') { if (addEv('gift', login, 1, p.tags['msg-param-recipient-user-name'], t)) evAdded++; }
          else if (id === 'submysterygift') { if (addEv('gift', login, +p.tags['msg-param-mass-gift-count'] || 1, '', t)) evAdded++; }
        }
      } else if (p.kind === 'clear') {
        const dur = p.tags['ban-duration'];
        rows.push({ t, u: '*', m: p.user ? (dur ? `${p.user} was timed out for ${dur}s` : `${p.user} was banned`) : 'chat was cleared' });
      }
    }
    rows.sort((a, b) => a.t - b.t);
    mkdirSync(join(file, '..'), { recursive: true });
    writeFileSync(file, rows.map(r => `[${stamp(r.t)}] #${channel} ${r.u === '*' ? '* ' + r.m : r.u + ': ' + r.m}`).join('\n') + '\n', 'utf8');
    // merge this day into the chatter profiles (once per day; today / yesterday are still growing and are merged on a later run)
    if (!done.has(day) && !refresh) {
      for (const [u, p] of Object.entries(dayProf)) {
        const g = prof.users[u] || (prof.users[u] = { name: p.name, msgs: 0, activeDays: 0, first: p.first, last: p.last, mod: false, vip: false, sub: false, subMonths: 0, bits: 0, bot: BOTS.has(u), talks: {} });
        g.name = p.name; g.msgs += p.msgs; g.activeDays++; g.first = Math.min(g.first, p.first); g.last = Math.max(g.last, p.last);
        g.mod = g.mod || p.mod; g.vip = g.vip || p.vip; g.sub = g.sub || p.sub; g.subMonths = Math.max(g.subMonths, p.subMonths); g.bits += p.bits;
        for (const [o, n] of Object.entries(p.talks)) g.talks[o] = (g.talks[o] || 0) + n;
      }
      done.add(day);
    }
    if (forStudy && process.env.APPDATA && day !== today) { mkdirSync(importDir, { recursive: true }); copyFileSync(file, join(importDir, `cyex-${day}.txt`)); }
    files++; msgs += rows.filter(r => r.u !== '*').length;
    if (files % 10 === 0 || refresh) process.stdout.write(`  ${day}: ${rows.length} lines\n`);
    await sleep(150);
  }
  // keep each profile's "talks with" list short
  for (const g of Object.values(prof.users)) g.talks = Object.fromEntries(Object.entries(g.talks).sort((a, b) => b[1] - a[1]).slice(0, 12));
  prof.processedDays = [...done].sort(); prof.updated = new Date().toISOString(); prof.logFormat = LOG_FORMAT;
  writeFileSync(profFile, JSON.stringify(prof));
  if (!noEvents) {
    const cut = Math.floor(Date.now() / 1000) - 400 * 86400;   // the bot keeps 400 days of events
    events = events.filter(e => e.At >= cut).sort((a, b) => a.At - b.At);
    writeFileSync(evFile, JSON.stringify(events, null, 1));
  }

  // INDEX.md + README.md in the logs folder
  const byMonth = {};
  for (const rel of dayFiles(outDir)) {
    const day = dayOf(rel), ym = day.slice(0, 7);
    const txt = readFileSync(join(outDir, rel), 'utf8');
    let n = 0, ev = 0; for (const l of txt.split('\n')) { if (!l.startsWith('[')) continue; if (/^\[[^\]]+\] #\S+ \* /.test(l)) ev++; else n++; }
    const e = byMonth[ym] || (byMonth[ym] = { days: 0, msgs: 0, ev: 0, first: day, last: day });
    e.days++; e.msgs += n; e.ev += ev; e.last = day;
  }
  const idx = ['# Chat logs index', '', `Channel ${channel}. One text file per day (UTC) in year/month folders. Updated ${new Date().toISOString().slice(0, 16)}Z.`, '', '| Month | Days | Messages | Notices | Folder |', '|---|---|---|---|---|'];
  let tm = 0, td = 0;
  for (const [ym, e] of Object.entries(byMonth).sort()) { idx.push(`| ${ym} | ${e.days} | ${e.msgs} | ${e.ev} | \`${ym.slice(0, 4)}\\${ym.slice(5)}\\\` |`); tm += e.msgs; td += e.days; }
  idx.push('', `Total: ${td} days, ${tm} messages.`);
  writeFileSync(join(outDir, 'INDEX.md'), idx.join('\n') + '\n');
  writeFileSync(join(outDir, 'README.md'), `# Chat logs (innocentpenguin_)

Every day of chat the public log sites have, from ${Object.keys(byMonth).sort()[0]} on, one text file per day:

    chat_logs\\2026\\10\\2026-10-19.txt

* Times are UTC (the stream starts around 22:00 UTC = 5 PM Central).
* A message:  \`[2026-10-19 22:41:07] #innocentpenguin_ snowyroses_: yo\`
* A notice:   \`[2026-10-16 22:11:27] #innocentpenguin_ * 48 raiders from DoctorNopeRope have joined!\` (subs, gifts, raids, milestones, timeouts, bans)
* \`INDEX.md\` lists the days and message counts per month. Folders starting with "_" (like _original-downloads) are not read by the bot.
* The chat bot searches all of these by itself. To update: \`node Pipeline\\fetch-chat-logs.mjs\` (new days only), then the other build scripts (see CHANGES.md).
`);
  console.log(`Done: ${files} day file(s) written (${msgs} messages), ${skipped} already up to date` + (noEvents ? '' : `, ${evAdded} new event(s) in chat_events.json (${events.length} total)`) + `, ${Object.keys(prof.users).length} chatter profiles. INDEX.md written.`);
})().catch(e => { console.error('ERROR: ' + e.message); process.exit(1); });
