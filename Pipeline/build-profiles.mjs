// Builds a PROFILE FILE for EVERYONE in the chat logs (everyone who ever wrote a message, plus people who were only @mentioned) from the chat logs (Data\chat_logs\*.txt): one JSON file per person in Data\profiles\<login>.json, plus
// Data\profiles\index.json (one summary line each) and a README. The bot reads a viewer's file whenever that viewer (or someone asked about) is in a reply.
//
//   node Pipeline\build-profiles.mjs                       (about a minute for 600k+ lines; run it again after importing new logs)
//   options: --logs D:\PinguinoSuite\Data\chat_logs   --out D:\PinguinoSuite\Data\profiles   --min-msgs 30
//
// WHAT IS IN A PROFILE (everything comes from the public chat itself, nothing is guessed from outside it):
//   seen         FIRST SEEN (the earliest date known: the logs only start on Feb 15 2026, so for people who were around before that it comes from StreamElements'
//                !followage answers in the chat: "X has been following for 3 months" said on Feb 17 means following since about Nov 2025) and LAST SEEN (exact time, UTC), their FIRST MESSAGE and their last one, longest run of days in a row, busiest day
//   activity     messages, active days, messages per month, typical hours (Central), roles seen (mod / VIP / sub)
//   likes        what they say they like / love / enjoy / are into, their "my favorite X is Y" lines, what they dislike, the games they talk about,
//                their favorite emotes and commands, and the words that are most their own
//   mentioned-only  people who were @mentioned but never wrote anything get a short profile too (who mentioned them, when)
//   nicknames    what the community calls them (chat_nicknames.json from build-nicknames.mjs)
//   pets         "my cat Luna" / "my dog is named Rex" style statements they made
//   hobbies      things they say they do or like (gym, anime, drawing...) and the games they talk about most
//   traits       how they come across, measured against the rest of the community (chatty, short messages, night owl, jokester, loud, emote spammer,
//                asks a lot of questions, compliments others, helps newcomers, ...)
//   friends      who they talk with most (mentions both ways + back-and-forth replies)
//   friction     people they have the most heated exchanges with. In this community most of it is roasting between friends, so it is only a hint
//                ("clash"), never a fact about who dislikes whom
//   notes        free text you (or an assistant) can write; it is kept when the profiles are rebuilt
// Sensitive things are left out on purpose: age, school, health, politics, religion, sexuality, real names, locations, contact details.
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dayFiles, dayOf } from './lib-logs.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : process.argv[i + 1]; };
const logsDir = arg('logs', 'D:\\PinguinoSuite\\Data\\chat_logs');
const outDir = arg('out', 'D:\\PinguinoSuite\\Data\\profiles');
const MIN_MSGS = Number(arg('min-msgs', 1));   // everyone who wrote at least this many messages gets a profile (default: all of them)
const appData = join(process.env.APPDATA || '', 'BVQ');
const here = dirname(fileURLToPath(import.meta.url));
const base = JSON.parse(readFileSync(join(appData, 'chat_profiles.json'), 'utf8'));
const roleInfo = base.users;
let nicks = {}; try { nicks = JSON.parse(readFileSync(join(appData, 'chat_nicknames.json'), 'utf8')); } catch { /* none */ }
const isBot = u => !!roleInfo[u]?.bot || /bot$/.test(u) || ['nightbot', 'streamelements', 'soundalerts', 'streamlabs', 'moobot', 'fossabot', 'synchrabot', 'pinguinob0t', 'potatbotat', 'sery_bot'].includes(u);

// ---------- word lists ----------
const SENSITIVE = /\b(\d{1,2}\s*(y\/?o|yo|yrs?|years?)|age|birthday|minor|underage|school|grade|college|teacher|class|depress\w*|anxiety|suicid\w*|therapy|medic\w*|disease|cancer|adhd|autis\w*|diagnos\w*|politic\w*|trump|biden|religio\w*|church|muslim|christian|jewish|atheist|gay|lesbian|bisexual|trans|queer|sexual|porn|nude|sex|address|phone|email|real name|password|ssn)\b/i;
const PET = /\bmy\s+(cat|kitten|dog|puppy|pup|bird|parrot|hamster|rabbit|bunny|fish|snake|lizard|turtle|horse|guinea pig|ferret|gecko|tortoise|cats|dogs)\b(?:\s+(?:is\s+)?(?:named|called|name is))?\s*([A-Za-z]{2,14})?/gi;
const PET_NOT_NAME = new Set('to in on at for of up out off from with into by be as if or is was just did has had keeps kept hit hits slapped bit bites ate eats doing does got gets will would wont like likes loves love really so too also and but the this that who what when why how not very pooped stepped sat sits jumped jumps scratched sleeping sleeps walked walks died dead alive here there right now again always never still looking looked waiting asked wants want needs need'.split(' '));
// Hobbies only count as an explicit first-person statement ("i love gym", "im into anime", "my guitar"): gaming slang like "cooking", "camping" or "my car" is ignored.
const HOBBY_WORDS = { gym: 'gym|lifting|working out|weights', running: 'running|jogging|cardio', basketball: 'basketball|hooping', football: 'football', soccer: 'soccer', baseball: 'baseball', hockey: 'hockey', anime: 'anime|manga', drawing: 'drawing|painting|sketching', music: 'guitar|piano|drums|singing|rapping|producing music', cooking: 'cooking food|baking|cooking dinner', fishing: 'fishing', hunting: 'hunting', hiking: 'hiking|camping outside', skating: 'skating|skateboarding', coding: 'coding|programming', reading: 'reading|books', boxing: 'boxing|mma|wrestling', gardening: 'gardening', movies: 'movies|watching movies', horror: 'horror (?:games|movies)' };
const HOBBIES = Object.fromEntries(Object.entries(HOBBY_WORDS).map(([k, w]) => [k, new RegExp('\\b(?:i|im|i\'m|i\'ve|ive|we)\\s+(?:also |really |just |usually |always |actually |kinda |sorta )*(?:like|love|enjoy|play|do|go|went|am into|am in|been into|started|got into|am learning|learned)\\s+(?:to |the |a |some |doing |playing |going )?(?:' + w + ')\\b|\\bmy\\s+(?:' + w + ')\\b', 'i')]));
const GAMES = { 'Rocket League': /\b(rocket league|\brl\b|customs|gc[123]|ssl|diamond|champ|mmr|ranked)\b/i, Fortnite: /\b(fortnite|zone wars|boxfights?|\bfn\b)\b/i, Minecraft: /\b(minecraft|hardcore|\bmc\b|smp|nether|ender)\b/i, Roblox: /\b(roblox|murder mystery|rivals)\b/i, Valorant: /\b(valorant|valo)\b/i, 'Call of Duty': /\b(warzone|cod|black ops)\b/i, 'Apex Legends': /\bapex\b/i, Overwatch: /\boverwatch\b/i, 'League of Legends': /\b(league of legends|lol rank|aram)\b/i, GTA: /\b(gta|grand theft)\b/i, 'Elden Ring': /\b(elden ring|dark souls)\b/i, Pokemon: /\bpokemon\b/i, Spotify: /\b(spotify|songspot)\b/i, GeoGuessr: /\bgeoguessr\b/i, Garticphone: /\bgarticphone\b/i };
const HOSTILE = /\b(fuck (you|off|u)|shut (up|the)|stfu|sybau|ur (trash|garbage|bad|annoying|stupid|dumb|cringe)|you suck|you'?re (trash|annoying|stupid)|hate (you|u)|leave me alone|stop (pinging|talking|bothering|spamming)|go away|get lost|ban (him|her|them|this)|block (him|her|you)|ratio|touch grass)\b/i;
const SOFT = /\b(lol|lmao|lmfao|haha|jk|joking|kidding|bro|😭|💀|🤣|😂|:\)|<3)\b|[😭💀🤣😂]/i;
const LAUGH = /\b(lol|lmao|lmfao|haha+|kek|rofl)\b|[😭💀🤣😂]/i;
const SWEAR = /\b(fuck\w*|shit\w*|bitch\w*|damn|ass|wtf|bullshit|dickhead)\b/i;
const NICE = /\b(nice|gg|ggs|wp|congrats|proud|good job|well done|great|love (it|you|this)|goated|the goat|clean|insane|w\b|welcome|gl\b|good luck)\b/i;
const HELP = /\b(you can|just type|type !|do !|use !|you need to|you have to|go to|it'?s in|the code is|try |register|!register|!join|!queue)\b/i;
const CUSTOMS = /!(join|register|queue|leave|rank|mmr|next|pos)\b/i;
const GAMBLE = /!(gamble|slots?|duel|roulette|give|points)\b/i;
const SONGS = /!(song|songqueue|skip|voteskip|songspot)\b/i;

// ---------- likes / favorites / dislikes ----------
const common = new Set(readFileSync(join(here, '..', 'Data', 'common-words.txt'), 'utf8').split(/\r?\n/).map(w => w.trim().toLowerCase()).filter(Boolean));
const loginSet = new Set(Object.keys(roleInfo));
const LIKE_RX = /\b(?:i|im|i'm|ive|i've|we)\s+(?:really |just |also |actually |literally |absolutely |fr |truly |kinda |lowkey |highkey |always |still |totally |genuinely )*(love|like|enjoy|adore|prefer|am a fan of|am into|am obsessed with|main)\s+([^.!?,;:()\n]{2,60})/i;
const DISLIKE_RX = /\b(?:i|im|i'm|ive|i've|we)\s+(?:really |just |also |actually |literally |absolutely |fr |truly |always |still |totally |genuinely )*(hate|dislike|can't stand|cant stand|am sick of|despise)\s+([^.!?,;:()\n]{2,60})/i;
const FAV_RX = /\bmy\s+(?:favou?rite|fav)\s+([a-z][a-z ]{1,18}?)\s+(?:is|are|was)\s+([^.!?,;:()\n]{2,50})/i;
const OBJ_BAD_FIRST = new Set('it that this you u him her them everyone everything nothing how when what why who being getting having doing seeing a lot so much more less too to be not no yes just the'.split(' '));
const OBJ_CUT = /\b(because|but|and i|cuz|cause|bc|so|when|since|though|tho|if|lol|lmao|rn|too|as well|for real|fr|ngl|lowkey|honestly)\b/;
const OBJ_BLOCK = /\b(fuck\w*|shit\w*|bitch\w*|nigg\w*|fag\w*|retard\w*|rape\w*|nazi\w*|hitler|epstein|porn\w*|nude\w*|kill\w*|suicide|dick\w*|cock|pussy|ass|asses|indian|black|white|asian|mexican|jewish|arab|chinese|japanese|korean|latino|muslim|christian|gay|trans|straight|woke|trump|biden|election)\b/i;
const OBJ_GENERIC = new Set('good bad nice great best better worse worst bed sleep sleeping stuff things thing shit way one ones lot lots idea ideas time times day days night nights people guys girls kids man men woman women dude bro life stream streams chat chats vibe vibes sound sounds fun hard easy long short big small little old new same different real fake free'.split(' '));
const common3000 = new Set([...common].slice(0, 3000));
// people's names / nicknames are not things they like ("i love mello" is about a person)
const nickWords = new Set(); for (const v of Object.values(nicks)) for (const n of v) nickWords.add(n.nick);
function objOf(raw) {
  let s = String(raw).toLowerCase().split(OBJ_CUT)[0];
  s = s.replace(/\b(the|a|an|to|my|some|playing|watching|listening|eating|doing|going|it when|that)\b/g, ' ').replace(/[^a-z0-9' &+-]/g, ' ').replace(/\s+/g, ' ').trim();
  const w = s.split(' ');
  if (!s || s.length < 2 || s.length > 38 || w.length > 4 || OBJ_BAD_FIRST.has(w[0]) || /^[0-9 ]+$/.test(s) || loginSet.has(s) || SENSITIVE.test(s) || OBJ_BLOCK.test(s) || /(gay|lesbian|nazi|rape|nigg|fag|porn|slut)/.test(s) || OBJ_GENERIC.has(s) || (w.length === 1 && common3000.has(s)) || w.every(x => OBJ_GENERIC.has(x)) || /\b(you|your|yours|u|ur|him|her|his|their|our|its|them|chat|everyone|people|someone|me|this|these|those|ya)\b/.test(s) || w.some(x => nickWords.has(x))) return '';
  return s;
}
const bump = (map, key, text, w = 1) => { const e = map.get(key) || { n: 0, ex: text.slice(0, 110) }; e.n += w; map.set(key, e); };
const top = (map, n, min = 1) => [...map].filter(([, e]) => e.n >= min).sort((x, y) => y[1].n - x[1].n).slice(0, n).map(([k, e]) => ({ what: k, said: e.n, example: e.ex }));

// ---------- birthdays (month + day only) and US states ----------
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const STATES = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming'];
const BDAY_DATE = /(?:my|it'?s|its|today is my|today'?s my)\s+(?:birthday|bday|b-day)\b(?:\s+(?:is|on|was))?\s*(?:on\s+|the\s+)?(?:(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b|(\d{1,2})\s*[\/-]\s*(\d{1,2})(?:\s*[\/-]\s*\d{2,4})?\b)/i;
const BDAY_TODAY = /\b(?:it'?s|its|today is|today'?s)\s+my\s+(?:birthday|bday|b-day)(?:\s+today)?\s*(?:[.!?,]*$|\s+(?:guys|chat|yall|y'all|everyone|boys|lol|lmao)\b)|\btoday\b[^.!?]{0,25}\bmy\s+(?:birthday|bday)\b|\bmy\s+(?:birthday|bday)\s+(?:is\s+)?today\b/i;
const STATE_RX = new RegExp('\\b(?:i|im|i\'m|we)\\s+(?:am\\s+)?(?:live|living|from|based|born and raised)\\s+(?:in\\s+|near\\s+)?(?:[A-Za-z .\'-]+,\\s*)?(' + STATES.join('|') + ')\\b', 'i');
const NOT_PLACE = /\b(street|ave|avenue|road|apartment|apt|school|zip|\d{5})\b/i;

// ---------- accumulate ----------
const FOLLOW = new Map(), WATCH = new Map();   // login -> [{t, ms}] follow ages seen in !followage answers; login -> longest watch time (ms) seen in !watchtime answers
const durMs = s => { let ms = 0; for (const m of String(s).matchAll(/(\d+)\s*(year|yr|month|week|day|hour|hr|min|sec)/gi)) { const n = +m[1], u = m[2].toLowerCase(); ms += n * ({ year: 365 * 864e5, yr: 365 * 864e5, month: 30.44 * 864e5, week: 7 * 864e5, day: 864e5, hour: 36e5, hr: 36e5, min: 6e4, sec: 1e3 }[u]); } return ms; };
const followingSince = login => { const o = FOLLOW.get(login); if (!o || !o.length) return null; const v = o.map(x => x.t - x.ms).sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; };
const M = new Map();   // every @mentioned login -> { n, first:{t,by,text}, last, by: Map }
const noteMention = (o, by, t, text) => { let e = M.get(o); if (!e) { e = { n: 0, first: { t, by, text: text.slice(0, 140) }, last: t, by: new Map() }; M.set(o, e); } e.n++; e.last = t; e.by.set(by, (e.by.get(by) || 0) + 1); };
const files = dayFiles(logsDir);
const U = new Map();
const acc = u => { let a = U.get(u); if (!a) { a = { msgs: 0, days: new Set(), hours: new Array(24).fill(0), months: {}, wk: 0, we: 0, len: 0, caps: 0, q: 0, laugh: 0, swear: 0, emote: 0, nice: 0, help: 0, customs: 0, gamble: 0, songs: 0, links: 0, short: 0, ment: new Map(), turns: new Map(), hostile: new Map(), pets: new Map(), hob: {}, games: {}, hobEx: {}, own: 0, firstT: 0, firstText: '', lastT: 0, lastText: '', likes: new Map(), dislikes: new Map(), favs: new Map(), words: new Map(), emotes: new Map(), cmds: new Map(), dayMsgs: new Map() }; U.set(u, a); } return a; };
const ctHour = (utcMs, off) => new Date(utcMs + off * 3600e3).getUTCHours();
let total = 0;
for (const f of files) {
  const day = dayOf(f);
  const off = (day >= '2026-03-08' && day < '2026-11-01') ? -5 : -6;   // US Central: daylight time from Mar 8, standard time again from Nov 1
  const lines = [];
  for (const l of readFileSync(join(logsDir, f), 'utf8').split('\n')) {
    const m = /^\[(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\] #\S+ (\S+): (.*)$/.exec(l); if (!m) continue;
    lines.push({ t: Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]), u: m[7], text: m[8] });
  }
  total += lines.length;
  for (let i = 0; i < lines.length; i++) {
    const { t, u, text } = lines[i];
    if (u === 'streamelements') {   // !followage / !watchtime answers: evidence of how long someone has been around, also from before the logs start
      let sm;
      if ((sm = /^@\S+,\s+(\S+) has been following \S+ for\s+(.+)$/i.exec(text))) { const ms = durMs(sm[2]); if (ms > 0) (FOLLOW.get(sm[1].toLowerCase()) || FOLLOW.set(sm[1].toLowerCase(), []).get(sm[1].toLowerCase())).push({ t, ms }); }
      else if ((sm = /^@\S+,\s+(\S+) has spent\s+(.+?)\s+watching/i.exec(text))) { const ms = durMs(sm[2]); if (ms > 0) WATCH.set(sm[1].toLowerCase(), Math.max(WATCH.get(sm[1].toLowerCase()) || 0, ms)); }
      continue;
    }
    if (isBot(u)) continue;
    const a = acc(u);
    a.msgs++; a.days.add(day);
    if (!a.firstT) { a.firstT = t; a.firstText = text.slice(0, 220); }
    a.lastT = t; a.lastText = text.slice(0, 220);
    if (!a.birthday && !text.startsWith('!')) {   // "my birthday is March 14" / "it's my birthday today": month and day only, never the year
      let bm = BDAY_DATE.exec(text), mo = 0, dd = 0;
      if (bm) { if (bm[1]) { mo = MONTHS.findIndex(x => x.toLowerCase().startsWith(bm[1].toLowerCase().slice(0, 3))) + 1; dd = +bm[2]; } else { mo = +bm[3]; dd = +bm[4]; } }
      else if (BDAY_TODAY.test(text)) { const ct = new Date(t + off * 3600e3); mo = ct.getUTCMonth() + 1; dd = ct.getUTCDate(); }
      if (mo >= 1 && mo <= 12 && dd >= 1 && dd <= 31) a.birthday = { text: MONTHS[mo - 1] + ' ' + dd, said: day, example: text.slice(0, 100) };
    }
    if (!a.state && !NOT_PLACE.test(text)) { const sm = STATE_RX.exec(text); if (sm) a.state = { state: STATES.find(s => s.toLowerCase() === sm[1].toLowerCase()), said: day, example: text.slice(0, 100) }; }
    a.dayMsgs.set(day, (a.dayMsgs.get(day) || 0) + 1);
    {   // commands, emotes, own words, likes / favorites / dislikes
      const cm = /^!([a-z0-9_]{2,20})/i.exec(text); if (cm) a.cmds.set(cm[1].toLowerCase(), { n: (a.cmds.get(cm[1].toLowerCase())?.n || 0) + 1, ex: '' });
      for (const em of text.match(/\b[a-z0-9]{3,10}[A-Z][A-Za-z0-9]{2,}\b/g) || []) bump(a.emotes, em, '');
      if (!cm && !/https?:\/\//i.test(text)) {
        for (const w of new Set(text.toLowerCase().replace(/@\w+/g, ' ').split(/[^a-z']+/))) if (w.length >= 4 && !common.has(w) && !loginSet.has(w) && !w.includes("'")) a.words.set(w, (a.words.get(w) || 0) + 1);
        if (!SENSITIVE.test(text) && /\b(love|like|enjoy|adore|prefer|fan of|into|obsessed|main|favou?rite|fav|hate|dislike|stand|sick of|despise)\b/i.test(text)) {
          let lm; if ((lm = LIKE_RX.exec(text))) { const o = objOf(lm[2]); if (o) bump(a.likes, o, text, /^(love|adore|enjoy|am a fan of|am obsessed with)$/i.test(lm[1]) ? 2 : 1); }
          if ((lm = DISLIKE_RX.exec(text))) { const o = objOf(lm[2]); if (o) bump(a.dislikes, o, text, 1); }
          if ((lm = FAV_RX.exec(text))) { const o = objOf(lm[2]); const k = lm[1].trim().toLowerCase(); if (o && !SENSITIVE.test(k)) bump(a.favs, 'favorite ' + k + ': ' + o, text); }
        }
      }
    }
    const ch = ctHour(t, off); a.hours[ch]++;
    const month = day.slice(0, 7); a.months[month] = (a.months[month] || 0) + 1;
    const dow = new Date(t + off * 3600e3).getUTCDay(); if (dow === 0 || dow === 6) a.we++; else a.wk++;
    a.len += text.length;
    const letters = text.replace(/[^A-Za-z]/g, '');
    if (letters.length >= 6 && letters === letters.toUpperCase()) a.caps++;
    if (/\?\s*$/.test(text)) a.q++;
    if (LAUGH.test(text)) a.laugh++;
    if (SWEAR.test(text)) a.swear++;
    if (NICE.test(text)) a.nice++;
    if (HELP.test(text) && /@\w+/.test(text)) a.help++;
    if (CUSTOMS.test(text)) a.customs++;
    if (GAMBLE.test(text)) a.gamble++;
    if (SONGS.test(text)) a.songs++;
    if (/https?:\/\//i.test(text)) a.links++;
    if (text.length <= 12) a.short++;
    a.emote += (text.match(/\b[a-z0-9]{3,10}[A-Z][A-Za-z0-9]{2,}\b/g) || []).length;
    // mentions, hostile mentions
    const ments = [...text.toLowerCase().matchAll(/@([a-z0-9_]{3,25})/g)].map(m => m[1]).filter(x => x !== u && !isBot(x));
    for (const o of new Set(ments)) {
      noteMention(o, u, t, text);
      a.ment.set(o, (a.ment.get(o) || 0) + 1);
      if (HOSTILE.test(text)) {
        let h = a.hostile.get(o); if (!h) { h = { n: 0, soft: 0 }; a.hostile.set(o, h); }
        h.n++; if (SOFT.test(text)) h.soft++;
      }
    }
    // back-and-forth: A speaks within 25 s of B's previous line
    for (let j = i - 1; j >= Math.max(0, i - 3); j--) { const p = lines[j]; if (p.u === u || isBot(p.u)) continue; if (t - p.t <= 25000) a.turns.set(p.u, (a.turns.get(p.u) || 0) + 1); break; }
    // pets / hobbies / games (statements about themselves)
    if (!SENSITIVE.test(text)) {
      for (const pm of text.matchAll(PET)) {
        const kind = pm[1].toLowerCase().replace(/s$/, ''); let name = (pm[2] || '').toLowerCase();
        const named = /named|called|name is/i.test(pm[0]);
        if (name && (PET_NOT_NAME.has(name) || (!named && !/^[A-Z]/.test(pm[2])))) name = '';
        const key = kind + '|' + (name ? name[0].toUpperCase() + name.slice(1) : '');
        const have = /\b(i|we)\s+(have|got|own|adopted)\s+(a|an|two|2|three|my)\s+(cat|kitten|dog|puppy|pup|bird|parrot|hamster|rabbit|bunny|fish|snake|lizard|turtle|horse|guinea pig|ferret|gecko|tortoise)/i.test(text);
        const p = a.pets.get(key) || { kind, name: name ? name[0].toUpperCase() + name.slice(1) : '', n: 0, have: false, ex: text.slice(0, 100) }; p.n++; if (have) p.have = true; a.pets.set(key, p);
      }
      for (const [h, rx] of Object.entries(HOBBIES)) if (rx.test(text)) { a.hob[h] = (a.hob[h] || 0) + 1; if (!a.hobEx[h]) a.hobEx[h] = text.slice(0, 90); }
    }
    for (const [g, rx] of Object.entries(GAMES)) if (rx.test(text)) a.games[g] = (a.games[g] || 0) + 1;
  }
}

// ---------- percentiles among regulars ----------
const regs = [...U.entries()].filter(([, a]) => a.msgs >= 150);
const rate = (a, k) => a[k] / a.msgs;
const pct = (fn, p) => { const v = regs.map(([, a]) => fn(a)).sort((x, y) => x - y); return v[Math.min(v.length - 1, Math.floor(v.length * p))] ?? 0; };
const cut = { perDay: [pct(a => a.msgs / a.days.size, .2), pct(a => a.msgs / a.days.size, .85)], len: [pct(a => a.len / a.msgs, .2), pct(a => a.len / a.msgs, .85)], laugh: pct(a => rate(a, 'laugh'), .8), caps: pct(a => rate(a, 'caps'), .85), emote: pct(a => a.emote / a.msgs, .85), q: pct(a => rate(a, 'q'), .85), swear: pct(a => rate(a, 'swear'), .85), nice: pct(a => rate(a, 'nice'), .8), short: pct(a => rate(a, 'short'), .8) };

const D = ms => new Date(ms).toISOString().slice(0, 10);
const ISO = ms => new Date(ms).toISOString().slice(0, 19) + 'Z';
const df = new Map(); for (const [, a] of U) for (const w of a.words.keys()) df.set(w, (df.get(w) || 0) + 1);
const NUSERS = U.size;
const LOGS_START = files.length ? dayOf(files[0]) : '';
const disp = u => roleInfo[u]?.name || u;
const cap1 = s => s ? s[0].toUpperCase() + s.slice(1) : s;
mkdirSync(outDir, { recursive: true });
const index = {};
let written = 0;
const rows = [];
const buildDate = new Date().toISOString().slice(0, 10);
for (const [u, a] of U) {
  if (a.msgs < MIN_MSGS) continue;
  const r = roleInfo[u] || {};
  const days = a.days.size, perDay = a.msgs / days;
  const hrs = a.hours.map((n, h) => [h, n]);
  const lateShare = (hrs.filter(([h]) => h >= 21 || h < 4).reduce((s, [, n]) => s + n, 0)) / a.msgs;
  const streamShare = (hrs.filter(([h]) => h >= 17 && h < 21).reduce((s, [, n]) => s + n, 0)) / a.msgs;
  const topHours = hrs.sort((x, y) => y[1] - x[1]).slice(0, 3).map(([h]) => `${((h + 11) % 12) + 1}${h < 12 ? 'AM' : 'PM'}`);
  const traits = [];
  if (a.msgs >= 150) {
    if (perDay >= cut.perDay[1]) traits.push('very chatty'); else if (perDay <= cut.perDay[0]) traits.push('drops in now and then');
    const avg = a.len / a.msgs; if (avg >= cut.len[1]) traits.push('writes long messages'); else if (avg <= cut.len[0] || rate(a, 'short') >= cut.short) traits.push('keeps messages short');
    if (rate(a, 'laugh') >= cut.laugh) traits.push('jokester (laughs a lot)');
    if (rate(a, 'caps') >= cut.caps && a.caps >= 15) traits.push('loud, hypes in ALL CAPS');
    if (a.emote / a.msgs >= cut.emote && a.emote >= 40) traits.push('emote spammer');
    if (rate(a, 'q') >= cut.q && a.q >= 30) traits.push('asks a lot of questions');
    if (rate(a, 'swear') >= cut.swear && a.swear >= 25) traits.push('colorful language');
    if (rate(a, 'nice') >= cut.nice && a.nice >= 30) traits.push('compliments and cheers others on');
    if (a.help >= 12) traits.push('helps others (tells them what to do / how to join)');
    if (a.customs >= 40) traits.push('plays customs a lot (!join / !queue)');
    if (a.songs >= 40) traits.push('into the song requests');
    if (a.gamble >= 150) traits.push('plays the points games');
    if (lateShare >= 0.6) traits.push('night owl (most messages after 9 PM Central)'); else if (streamShare >= 0.55) traits.push('chats during the stream hours (5-9 PM Central)');
    if (a.we / a.msgs >= 0.45) traits.push('weekend chatter');
  }
  if (r.first && r.first <= Date.parse('2026-03-01') && days >= 100) traits.push('long-time regular (since the start of the logs)'); else if (r.first && r.first >= Date.parse('2026-09-01')) traits.push('newer chatter');
  // behaviour: how they interact
  const behavior = [];
  const toMe = new Map(); // mentions of this person by others
  for (const [v, b] of U) { const n = b.ment.get(u); if (n) toMe.set(v, n); }
  const mentionedTotal = [...toMe.values()].reduce((s, n) => s + n, 0);
  const mentionsOut = [...a.ment.values()].reduce((s, n) => s + n, 0);
  if (a.msgs >= 150) {
    if (mentionsOut / a.msgs >= 0.25) behavior.push('talks directly to people a lot (many @mentions)');
    if (mentionedTotal >= 150) behavior.push('people often talk to them (mentioned ' + mentionedTotal + ' times)');
    if (rate(a, 'links') >= 0.03) behavior.push('shares links often');
  }
  // friends
  const score = new Map();
  for (const [o, n] of a.ment) { const back = U.get(o)?.ment.get(u) || 0; if (back >= 2 && n >= 2) score.set(o, (score.get(o) || 0) + 2 * (n + back)); }
  for (const [o, n] of a.turns) { const back = U.get(o)?.turns.get(u) || 0; score.set(o, (score.get(o) || 0) + (n + back) / 3); }
  const hostPair = o => { const h1 = a.hostile.get(o), h2 = U.get(o)?.hostile.get(u); return { n: (h1?.n || 0) + (h2?.n || 0), soft: (h1?.soft || 0) + (h2?.soft || 0) }; };
  const friends = [...score].filter(([o, s]) => s >= 12 && !isBot(o) && (U.get(o)?.msgs || 0) >= MIN_MSGS && hostPair(o).n < Math.max(3, s / 10)).sort((x, y) => y[1] - x[1]).slice(0, 8).map(([o, s]) => ({ login: o, name: disp(o), strength: Math.round(s) }));
  // friction ("clash"): heated exchanges, mostly banter between friends here
  const clash = [];
  const opp = new Set([...a.hostile.keys()]); for (const [v, b] of U) if (b.hostile.has(u)) opp.add(v);
  for (const o of opp) {
    const h = hostPair(o); if (h.n < 4) continue;
    const talk = (a.ment.get(o) || 0) + (U.get(o)?.ment.get(u) || 0);
    if (talk < 8 || h.n / talk < 0.22) continue;
    clash.push({ login: o, name: disp(o), heated: h.n, ofMentions: talk, mostlyJokes: h.soft / h.n >= 0.5 });
  }
  clash.sort((x, y) => y.heated - x.heated);
  // pets, hobbies, games
  const pets = [...a.pets.values()].filter(p => p.name || p.have).sort((x, y) => y.n - x.n).slice(0, 4).map(p => ({ kind: p.kind, name: p.name || undefined, said: p.n, example: p.ex }));
  const hobbies = Object.entries(a.hob).filter(([, n]) => n >= 2).sort((x, y) => y[1] - x[1]).slice(0, 5).map(([h, n]) => ({ hobby: h, said: n, example: a.hobEx[h] }));
  const games = Object.entries(a.games).filter(([, n]) => n >= 8 && n / a.msgs >= 0.02).sort((x, y) => y[1] - x[1]).slice(0, 5).map(([g, n]) => ({ game: g, mentions: n }));
  // activity
  const months = Object.entries(a.months).sort();
  const lastTwo = months.slice(-2).map(x => x[1]);
  const trend = months.length >= 3 && lastTwo.length === 2 ? (lastTwo[1] > lastTwo[0] * 1.4 ? 'more active lately' : lastTwo[1] < lastTwo[0] * 0.6 ? 'less active lately' : 'steady') : 'steady';
  const lastSeen = r.last ? D(r.last) : '';
  const daysAgo = lastSeen ? Math.round((Date.parse(buildDate) - Date.parse(lastSeen)) / 86400000) : null;
  // first / last seen, first message, streak, busiest day, likes, own words
  const dlist = [...a.days].sort(); let streak = 1, best = 1;
  for (let i = 1; i < dlist.length; i++) { streak = (Date.parse(dlist[i]) - Date.parse(dlist[i - 1])) === 86400000 ? streak + 1 : 1; best = Math.max(best, streak); }
  const busiest = [...a.dayMsgs].sort((x, y) => y[1] - x[1])[0];
  const fs0 = followingSince(u), watchMs = WATCH.get(u) || 0;
  const earliest = fs0 && fs0 < a.firstT ? fs0 : a.firstT;
  const seen = { firstSeen: ISO(earliest), firstSeenSource: fs0 && fs0 < a.firstT ? 'estimated from their !followage answer in the chat (following since about ' + D(fs0) + '); the logs first saw them on ' + D(a.firstT) : 'first message in the logs', firstSeenInLogs: ISO(a.firstT), followingSince: fs0 ? D(fs0) : undefined, watchTimeHours: watchMs ? Math.round(watchMs / 36e5) : undefined, lastSeen: ISO(a.lastT), firstMessage: { at: ISO(a.firstT), text: a.firstText }, lastMessage: { at: ISO(a.lastT), text: a.lastText }, longestRunOfDaysInARow: best, busiestDay: busiest ? { date: busiest[0], messages: busiest[1] } : null, seenBeforeTheLogsStart: !fs0 && D(a.firstT) <= LOGS_START ? 'maybe: they were already chatting on the first logged day (Feb 15 2026), so the real start may be earlier' : undefined };
  const likes = top(a.likes, 12, 2), dislikes = top(a.dislikes, 6, 2), favorites = top(a.favs, 8, 1);
  const emotesTop = top(a.emotes, 6, 3).map(x => ({ emote: x.what, used: x.said }));
  const commandsTop = [...a.cmds].sort((x, y) => y[1].n - x[1].n).slice(0, 6).map(([k, e]) => ({ command: '!' + k, used: e.n }));
  const ownWords = [...a.words].filter(([w, n]) => n >= 4 && (df.get(w) || 99) <= 40).map(([w, n]) => [w, n * Math.log(NUSERS / df.get(w))]).sort((x, y) => y[1] - x[1]).slice(0, 8).map(([w]) => w);
  const file = join(outDir, u + '.json');
  let notes = ''; try { notes = JSON.parse(readFileSync(file, 'utf8')).notes || ''; } catch { /* new */ }
  const p = {
    login: u, name: r.name || u, built: buildDate,
    roles: { mod: !!r.mod, vip: !!r.vip, sub: !!r.sub, subMonths: r.subMonths || 0 },
    nicknames: (nicks[u] || []).map(x => x.nick),
    seen,
    birthday: a.birthday ? { text: a.birthday.text, note: 'month and day only (said on ' + a.birthday.said + '); the year is never stored', example: a.birthday.example } : undefined,
    state: a.state ? a.state.state : undefined,
    likes, dislikes, favorites, games, emotes: emotesTop, commands: commandsTop, ownWords,
    activity: { messages: a.msgs, activeDays: days, firstSeen: D(earliest), lastSeen: D(a.lastT), daysSinceLastSeen: Math.round((Date.parse(buildDate) - Date.parse(D(a.lastT))) / 86400000), messagesPerActiveDay: Math.round(perDay * 10) / 10, trend, typicalHoursCentral: topHours, perMonth: Object.fromEntries(months) },
    pets, hobbies, traits, behavior, friends, clash, notes,
  };
  writeFileSync(file, JSON.stringify(p, null, 1));
  written++;
  index[u] = [p.name, a.msgs, days, D(earliest), D(a.lastT), likes.slice(0, 3).map(x => x.what).join(', '), traits.slice(0, 3).join('; '), friends.slice(0, 3).map(f => f.name).join(', ')].join(' | ');
  rows.push({ u, name: p.name, msgs: a.msgs, days, estimated: !!(fs0 && fs0 < a.firstT), first: ISO(earliest), last: ISO(a.lastT), firstText: a.firstText, likes: likes.slice(0, 3).map(x => x.what).join(', ') });
}
// people who were only @mentioned (never wrote a message in the logs)
let mentionOnly = 0;
for (const [o, e] of M) {
  if (U.has(o) || isBot(o) || e.n < 2 || !/^[a-z0-9_]{3,25}$/.test(o)) continue;
  const file = join(outDir, o + '.json');
  let notes = ''; try { notes = JSON.parse(readFileSync(file, 'utf8')).notes || ''; } catch { /* new */ }
  writeFileSync(file, JSON.stringify({ login: o, name: o, built: buildDate, mentionedOnly: true, note: 'Never wrote a message in the logs; only other people @mentioned them.', seen: { firstMentioned: { at: ISO(e.first.t), by: e.first.by, text: e.first.text }, lastMentioned: ISO(e.last), timesMentioned: e.n, mentionedMostBy: [...e.by].sort((x, y) => y[1] - x[1]).slice(0, 5).map(([k, n]) => ({ login: k, times: n })) }, nicknames: (nicks[o] || []).map(x => x.nick), notes }, null, 1));
  index[o] = ['(mentioned only)', 0, 0, D(e.first.t), D(e.last), '', '', [...e.by].sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k]) => k).join(', ')].join(' | ');
  mentionOnly++;
}
writeFileSync(join(outDir, 'index.json'), JSON.stringify(index, null, 1));
const esc = s => String(s || '').replace(/\|/g, '/').replace(/\s+/g, ' ').trim();
const idx = ['# Everyone in the chat logs', '', `${rows.length} people who wrote at least one message + ${mentionOnly} who were only @mentioned. Times UTC. Built ${buildDate} from ${files.length} days (${LOGS_START} on; people marked ~ have an estimated first-seen date from their !followage answer, which goes back before the logs start; people marked * were already chatting on the first logged day and have no earlier evidence).`, '', '| Login | First seen | Last seen | Messages | Days | First message | Likes |', '|---|---|---|---|---|---|---|'];
for (const r of rows.sort((x, y) => y.msgs - x.msgs)) idx.push(`| ${r.u}${r.estimated ? ' ~' : r.first.slice(0, 10) <= LOGS_START ? ' *' : ''} | ${r.first.slice(0, r.estimated ? 10 : 16).replace('T', ' ')} | ${r.last.slice(0, 16).replace('T', ' ')} | ${r.msgs} | ${r.days} | ${esc(r.firstText).slice(0, 70)} | ${esc(r.likes).slice(0, 60)} |`);
writeFileSync(join(outDir, 'INDEX.md'), idx.join('\n') + '\n');
writeFileSync(join(outDir, 'README.md'), `# Chatter profiles (for the chat bot)

One JSON file per person (everyone who wrote at least ${MIN_MSGS} message(s) + people only @mentioned), built by \`Pipeline\\build-profiles.mjs\` from \`Data\\chat_logs\` (${files.length} days, ${total} messages, built ${buildDate}).
Fields: activity, nicknames (the community's, from build-nicknames.mjs), pets, hobbies, games, traits, behavior, friends, clash (heated exchanges: mostly banter between friends here, only a hint), and \`notes\` (free text; kept when the profiles are rebuilt: edit it by hand to add what you know).
Only public chat is used. Age, school, health, politics, religion, sexuality, real names and contact details are never stored.
Rebuild: \`node Pipeline\\build-nicknames.mjs\` then \`node Pipeline\\build-profiles.mjs\`. \`index.json\` has one summary line per chatter.
`);
console.log(`${written} profile files + ${mentionOnly} mentioned-only profiles written to ${outDir} (from ${U.size} chatters, ${total} lines). INDEX.md lists everyone.`);
