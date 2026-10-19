// Finds the NICKNAMES the community uses for each other by reading the chat logs (Data\chat_logs\*.txt) and writes <data folder>\chat_nicknames.json:
//   { "<login>": [ {"nick": "marsh", "count": 3170, "people": 116}, ... ] }
// The bot puts a viewer's community nicknames into its prompt and prefers them over inventing its own.
//
//   node Pipeline\build-nicknames.mjs            (about half a minute for 600k+ lines; run it again after importing new logs)
//   options: --logs D:\PinguinoSuite\Data\chat_logs   --min-count 10   --min-people 3   --min-ratio 2.5
//
// HOW A NICKNAME IS FOUND (nothing is guessed from thin air):
//  1. The nickname must LOOK like a short form of the chatter's login (a prefix or a part of it, letters/digits normalised: 0=o, 1=i, 3=e ...).
//  2. It must not be an ordinary English word (Data\common-words.txt) and not another chatter's login.
//  3. Other people (3+ different chatters) must use it, 10+ times.
//  4. It must go together with that chatter: when it is said, the chatter is part of the conversation (speaks within 20 lines, or is @mentioned)
//     at least 2.5x more often than chance. So "marsh" counts for lvlmarshmello, a word like "just" never does.
//  Explicit "call him X" / "X aka Y" lines are not used: too many jokes.
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { dataDir } from './lib-paths.mjs';
import { fileURLToPath } from 'node:url';
import { dayFiles, dayOf } from './lib-logs.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : process.argv[i + 1]; };
const logsDir = arg('logs', 'D:\\PinguinoSuite\\Data\\chat_logs');
const MIN_COUNT = Number(arg('min-count', 10)), MIN_PEOPLE = Number(arg('min-people', 3)), MIN_RATIO = Number(arg('min-ratio', 2.5));
const here = dirname(fileURLToPath(import.meta.url));
const appData = dataDir();
const prof = JSON.parse(readFileSync(join(appData, 'chat_profiles.json'), 'utf8')).users;
const common = new Set(readFileSync(join(here, '..', 'Data', 'common-words.txt'), 'utf8').split(/\r?\n/).map(w => w.trim().toLowerCase()).filter(Boolean));
const norm = s => s.toLowerCase().replace(/0/g, 'o').replace(/1/g, 'i').replace(/3/g, 'e').replace(/4/g, 'a').replace(/5/g, 's').replace(/[^a-z]/g, '');
const logins = new Set(Object.keys(prof));
const people = Object.entries(prof).filter(([, v]) => !v.bot && v.msgs >= 120).map(([k, v]) => ({ login: k, S: norm(k), msgs: v.msgs }));
const lev = (a, b) => { const d = Array.from({ length: a.length + 1 }, (_, i) => [i]); for (let j = 1; j <= b.length; j++) d[0][j] = j; for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); return d[a.length][b.length]; };
const related = (t, p) => t !== p.S && t !== p.login && p.S.length >= 5 && ((p.S.startsWith(t) && t.length >= 3) || (p.S.includes(t) && t.length >= 4) || (t.length >= 4 && lev(t, p.S.slice(0, t.length)) <= 1));

// pass 1: which tokens are candidates for which chatter (token must look like a short form, not be a common word / a login)
const days = dayFiles(logsDir);
const parse = l => { const m = /^\[[^\]]+\] #\S+ (\S+): (.*)$/.exec(l); return m ? { u: m[1], text: m[2] } : null; };
const freq = new Map();
for (const f of days) for (const l of readFileSync(join(logsDir, f), 'utf8').split('\n')) { const p = parse(l); if (!p || prof[p.u]?.bot) continue; for (const t of new Set(p.text.toLowerCase().replace(/@\w+/g, ' ').split(/[^a-z0-9_']+/))) if (t.length >= 3 && t.length <= 14) freq.set(t, (freq.get(t) || 0) + 1); }
const cand = new Map();   // token -> [people]
for (const [t, n] of freq) {
  if (n < MIN_COUNT || logins.has(t)) continue;
  const rel = people.filter(p => related(t, p));
  if (rel.length) cand.set(t, rel);
}
// pass 2: co-occurrence with the chatter inside a 41-line window, and how many different people use the token
const N = days.reduce((a, f) => a + 0, 0);
let total = 0;
const stats = new Map();   // "token|login" -> {n, co, spk:Set}
for (const f of days) {
  const lines = readFileSync(join(logsDir, f), 'utf8').split('\n').map(parse).filter(Boolean);
  total += lines.length;
  const W = 20;
  for (let i = 0; i < lines.length; i++) {
    const { u, text } = lines[i];
    if (prof[u]?.bot) continue;
    const toks = new Set(text.toLowerCase().replace(/@\w+/g, ' ').split(/[^a-z0-9_']+/));
    const ments = new Set([...text.toLowerCase().matchAll(/@([a-z0-9_]+)/g)].map(m => m[1]));
    for (const t of toks) {
      const rel = cand.get(t); if (!rel) continue;
      for (const p of rel) {
        if (p.login === u) continue;   // the person saying their own nickname does not count
        const key = t + '|' + p.login;
        let s = stats.get(key); if (!s) { s = { n: 0, co: 0, co3: 0, spk: new Set() }; stats.set(key, s); }
        s.n++; s.spk.add(u);
        let near3 = ments.has(p.login);
        for (let j = Math.max(0, i - 3); !near3 && j <= Math.min(lines.length - 1, i + 3); j++) if (lines[j].u === p.login) near3 = true;
        if (near3) s.co3++;
        let near = ments.has(p.login);
        for (let j = Math.max(0, i - W); !near && j <= Math.min(lines.length - 1, i + W); j++) if (lines[j].u === p.login) near = true;
        if (near) s.co++;
      }
    }
  }
}
const out = {};
for (const [key, s] of stats) {
  const [t, login] = key.split('|');
  const p = people.find(x => x.login === login);
  const base = 1 - Math.pow(1 - p.msgs / total, 41);   // chance the chatter is in a random 41-line window
  const base3 = 1 - Math.pow(1 - p.msgs / total, 7);   // same for a tight window of 7 lines (needed for very active chatters, whose wide window is always 'near')
  const ratio = Math.max((s.co / s.n) / base, (s.co3 / s.n) / base3 * (base > 0.7 ? 1 : 0.6));
  const ordinary = common.has(t);   // an ordinary English word only counts when it is used a lot and sticks to the chatter very strongly (marsh, snowy, piney...)
  // Very active chatters (base > 0.5) are in almost every window, so co-occurrence proves nothing for them: the short form itself has to carry it
  // (not an ordinary word, or an ordinary word used 300+ times that only fits this one chatter).
  const hyper = base > 0.5;
  if (s.spk.size < MIN_PEOPLE) continue;
  if (hyper) { if (s.n < (ordinary ? 300 : MIN_COUNT) || (ordinary && cand.get(t).length !== 1)) continue; }
  else if (s.n < (ordinary ? 100 : MIN_COUNT) || s.co < 8 || ratio < (ordinary ? 10 : MIN_RATIO)) continue;
  (out[login] = out[login] || []).push({ nick: t, count: s.n, people: s.spk.size, ratio: Math.round(ratio * 10) / 10 });
}
// hand corrections (Data/nickname-overrides.json): wrong matches removed, nicknames the finder misses added, some people skipped
try {
  const ov = JSON.parse(readFileSync(join(here, '..', 'Data', 'nickname-overrides.json'), 'utf8'));
  for (const [login, bad] of Object.entries(ov.remove || {})) if (out[login]) out[login] = out[login].filter(x => !bad.includes(x.nick));
  for (const [login, add] of Object.entries(ov.add || {})) { out[login] = out[login] || []; for (const a of add) if (!out[login].some(x => x.nick === a.nick)) out[login].push({ nick: a.nick, count: a.count || 0, people: a.people || 0, ratio: 0 }); }
  for (const login of ov.skip || []) delete out[login];
} catch { /* no overrides */ }
for (const k of Object.keys(out)) { out[k] = out[k].sort((a, b) => b.count - a.count).slice(0, 4); if (!out[k].length) delete out[k]; }
mkdirSync(appData, { recursive: true });
writeFileSync(join(appData, 'chat_nicknames.json'), JSON.stringify(out, null, 1));
console.log(`${Object.keys(out).length} chatters have community nicknames (from ${total} lines). Written to ${join(appData, 'chat_nicknames.json')}`);
for (const [k, v] of Object.entries(out).sort((a, b) => b[1][0].count - a[1][0].count).slice(0, 60)) console.log('  ' + k.padEnd(24) + v.map(c => `${c.nick} (${c.count}x, ${c.people} people, x${c.ratio})`).join('   '));
