// Builds the community's LORE from the chat logs: running jokes, catchphrases and inside references ("ur replaced", "L community", "sybau"...).
// Writes Data\lore.json:  [ { phrase, count, people, days, first:{date,user,text}, last, samples:[{date,user,text}] }, ... ]
// The bot looks a viewer's message up in it, so a reference to something that started months ago comes with where it came from and how it was used.
//
//   node Pipeline\build-lore.mjs            (about a minute; run it again after importing new logs)
//   options: --logs D:\PinguinoSuite\Data\chat_logs   --out D:\PinguinoSuite\Data\lore.json   --min-count 20   --min-people 6
//
// A phrase counts as lore when it is used 20+ times by 6+ different chatters on 5+ different days, is not a command / link / @mention / emote, and is
// either (A) made of at least one UNUSUAL word (not in the everyday word list, not a swear, not someone's name or nickname) that is not simply present
// every single day, or (B) made only of everyday words but then it must be a real running joke: clustered in time (half of its uses inside one
// two-week stretch) . Everyday phrases that are simply spread
// over every day ("i think", "don't know") are just how people talk and are left out.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dayFiles, dayOf } from './lib-logs.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : process.argv[i + 1]; };
const logsDir = arg('logs', 'D:\\PinguinoSuite\\Data\\chat_logs');
const outFile = arg('out', 'D:\\PinguinoSuite\\Data\\lore.json');
const MIN_COUNT = Number(arg('min-count', 20)), MIN_PEOPLE = Number(arg('min-people', 6)), MIN_DAYS = 5;
const here = dirname(fileURLToPath(import.meta.url));
const appData = join(process.env.APPDATA || '', 'BVQ');
const roleInfo = JSON.parse(readFileSync(join(appData, 'chat_profiles.json'), 'utf8')).users;
const common = readFileSync(join(here, '..', 'Data', 'common-words.txt'), 'utf8').split(/\r?\n/).map(w => w.trim().toLowerCase()).filter(Boolean);
const top1000 = new Set(common.slice(0, 1000)), commonAll = new Set(common);
const isBot = u => !!roleInfo[u]?.bot || /bot$/.test(u) || ['nightbot', 'streamelements', 'soundalerts', 'streamlabs', 'moobot', 'fossabot', 'synchrabot', 'pinguinob0t', 'potatbotat', 'sery_bot'].includes(u);
const logins = new Set(Object.keys(roleInfo));

const files = dayFiles(logsDir);
const tokens = text => {
  if (/^!/.test(text) || /https?:\/\//i.test(text)) return null;
  const t = text.toLowerCase().replace(/[\u2018\u2019`]/g, "'").replace(/@\w+/g, ' ').split(/[^a-z0-9']+/).filter(w => w.length >= 1 && w.length <= 20);
  return t.length ? t : null;
};
const isEmote = (raw, w) => /^[a-z0-9]{3,10}[A-Z]\w+$/.test(raw);

// ---- pass 1: word counts ----
const uni = new Map(); let total = 0;
function* messages() {
  for (const f of files) {
    const day = dayOf(f);
    for (const l of readFileSync(join(logsDir, f), 'utf8').split('\n')) {
      const m = /^\[[^\]]+\] #\S+ (\S+): (.*)$/.exec(l); if (!m || isBot(m[1])) continue;
      const tk = tokens(m[2]); if (!tk) continue;
      yield { day, u: m[1], tk, text: m[2] };
    }
  }
}
for (const { tk } of messages()) for (const w of new Set(tk)) { uni.set(w, (uni.get(w) || 0) + 1); total++; }
// ---- pass 2: bigrams / trigrams among words that are used enough ----
const big = new Map(), tri = new Map();
const OK = w => (uni.get(w) || 0) >= MIN_COUNT && !/^\d+$/.test(w);
for (const { u, day, tk } of messages()) {
  const seen = new Set();
  for (let i = 0; i + 1 < tk.length; i++) {
    if (!OK(tk[i]) || !OK(tk[i + 1])) continue;
    const b = tk[i] + ' ' + tk[i + 1];
    if (!seen.has(b)) { seen.add(b); let e = big.get(b); if (!e) { e = { n: 0, sp: new Set(), days: new Set(), dc: new Map() }; big.set(b, e); } e.n++; e.sp.add(u); e.days.add(day); e.dc.set(day, (e.dc.get(day) || 0) + 1); }
    if (i + 2 < tk.length && OK(tk[i + 2])) {
      const t3 = b + ' ' + tk[i + 2];
      if (!seen.has(t3)) { seen.add(t3); let e = tri.get(t3); if (!e) { e = { n: 0, sp: new Set(), days: new Set(), dc: new Map() }; tri.set(t3, e); } e.n++; e.sp.add(u); e.days.add(day); e.dc.set(day, (e.dc.get(day) || 0) + 1); }
    }
  }
}
const dayIndex = new Map(files.map((f, i) => [dayOf(f), i]));
const peakShare = e => { const arr = new Array(files.length).fill(0); for (const [d, n] of e.dc) arr[dayIndex.get(d)] += n; let best = 0, w = 0; for (let i = 0; i < arr.length; i++) { w += arr[i]; if (i >= 14) w -= arr[i - 14]; best = Math.max(best, w); } return best / e.n; };
const SWEAR = new Set('shit fuck fucking fucked damn bitch bitches ass asses dick pussy crap hell wtf stfu lmao lmfao bruh dude yall gotta imma lemme gimme gonna wanna aint legit alright'.split(' '));
let nickTokens = new Set(); try { for (const v of Object.values(JSON.parse(readFileSync(join(appData, 'chat_nicknames.json'), 'utf8')))) for (const n of v) nickTokens.add(n.nick); } catch { /* none */ }
const nameLike = w => logins.has(w) || nickTokens.has(w) || [...logins].some(l => l.length >= 6 && (l.startsWith(w) && w.length >= 4));
const unusual = w => !commonAll.has(w) && !SWEAR.has(w) && !nameLike(w) && w.length >= 4 && !/^[0-9']+$/.test(w) && !/'/.test(w);
const keepPhrase = (words, e, s) => {
  const daysShare = e.days.size / files.length;
  if (words.some(unusual)) return daysShare <= 0.8 || e.n < 400;
  if (words.some(w => SWEAR.has(w))) return false;
  return peakShare(e) >= 0.5;   // everyday words: only a real burst (a joke of its time) counts, never plain speech
};
const stick = (c, words, grams) => c / Math.min(...words.map(w => uni.get(w) || 1));
const everyday = words => words.every(w => top1000.has(w));
const lore = new Map();   // phrase -> {kind,n,people,days}
for (const [p, e] of big) {
  if (e.n < MIN_COUNT || e.sp.size < MIN_PEOPLE || e.days.size < MIN_DAYS) continue;
  const w = p.split(' ');
  const s = stick(e.n, w);
  if (s < 0.2 || !keepPhrase(w, e, s)) continue;
  lore.set(p, { n: e.n, people: e.sp.size, days: e.days.size, s });
}
for (const [p, e] of tri) {
  if (e.n < MIN_COUNT || e.sp.size < MIN_PEOPLE || e.days.size < MIN_DAYS) continue;
  const w = p.split(' ');
  const b1 = big.get(w[0] + ' ' + w[1])?.n || 1, b2 = big.get(w[1] + ' ' + w[2])?.n || 1;
  const s = e.n / Math.min(b1, b2);
  if (s < 0.3 || !keepPhrase(w, e, s)) continue;
  lore.set(p, { n: e.n, people: e.sp.size, days: e.days.size, s });
  for (const sub of [w[0] + ' ' + w[1], w[1] + ' ' + w[2]]) { const b = lore.get(sub); if (b && e.n >= 0.6 * b.n) lore.delete(sub); }   // the longer phrase is the joke, not its parts
}
// rare single words many people use (made-up words, names of things): not in the everyday word list, not a login
const uniSp = new Map(), uniDays = new Map();
for (const { u, day, tk } of messages()) for (const w of new Set(tk)) { if (!commonAll.has(w) && (uni.get(w) || 0) >= 30 && w.length >= 4 && !logins.has(w)) { (uniSp.get(w) || uniSp.set(w, new Set()).get(w)).add(u); (uniDays.get(w) || uniDays.set(w, new Set()).get(w)).add(day); } }
for (const [w, sp] of uniSp) if (sp.size >= 8 && uniDays.get(w).size >= MIN_DAYS && !lore.has(w) && unusual(w) && uniDays.get(w).size / files.length <= 0.8) lore.set(w, { n: uni.get(w), people: sp.size, days: uniDays.get(w).size, s: 1 });

// ---- pass 3: first / last use and a few sample lines for every lore phrase ----
const info = new Map([...lore.keys()].map(p => [p, { first: null, last: null, samples: [] }]));
const ngrams = tk => { const out = new Set(); for (let i = 0; i < tk.length; i++) { out.add(tk[i]); if (i + 1 < tk.length) out.add(tk[i] + ' ' + tk[i + 1]); if (i + 2 < tk.length) out.add(tk[i] + ' ' + tk[i + 1] + ' ' + tk[i + 2]); } return out; };
let seq = 0;
for (const { day, u, tk, text } of messages()) {
  for (const g of ngrams(tk)) {
    const e = info.get(g); if (!e) continue;
    const rec = { date: day, user: u, text: text.slice(0, 140) };
    if (!e.first) e.first = rec;
    e.last = rec;
    e.n = (e.n || 0) + 1;
    // reservoir of 5 samples, spread over time
    if (e.samples.length < 5) e.samples.push(rec); else { const j = Math.floor(Math.random() * e.n); if (j < 5) e.samples[j] = rec; }
  }
}
const out = [...lore].map(([p, v]) => {
  const e = info.get(p);
  const samples = e.samples.sort((a, b) => a.date.localeCompare(b.date)).filter((s, i, a) => a.findIndex(x => x.user === s.user) === i).slice(0, 4);
  return { phrase: p, count: v.n, people: v.people, days: v.days, first: e.first, last: e.last?.date, samples };
}).filter(x => x.first).sort((a, b) => b.count - a.count).slice(0, 3500);
writeFileSync(outFile, JSON.stringify(out));
console.log(`${out.length} lore phrases written to ${outFile} (from ${total} word uses, ${files.length} days).`);
console.log('top 60: ' + out.slice(0, 60).map(x => `${x.phrase} (${x.count}x, ${x.people} people, since ${x.first.date})`).join(' | '));
