// Nightly Phase 1 (lore): node Tools/lore-mining/nightly-phase1.mjs [YYYY-MM-DD] [--min 150] [--out path]
// Reads Data/chat_logs/2026/MM/<date>.txt, reports its size, and ONLY when there are enough human messages
// (default 150) does it "learn": candidate new terms, new people without a card, pairs that talk a lot, and
// stat shifts. Writes Docs/nightly/lore-phase1-<date>.md (git-ignored). Read-only on Data/lore: it never edits
// lore or cards; Phase 1 findings are proposals for a human/lore worker to fold in with notes.mjs + build.mjs.
// Privacy: skips Privacy anon/forget users, bots, and writes no message text (only terms and counts).
import fs from 'fs'; import path from 'path';
const SUITE = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1')), '..', '..');
const a = process.argv.slice(2);
const opt = (n, d) => { const i = a.indexOf(n); return i >= 0 ? a[i + 1] : d; };
const pos = a.filter((x, i) => !x.startsWith('--') && !(i > 0 && a[i - 1].startsWith('--')));
const day = pos[0] || new Date().toISOString().slice(0, 10);
const MIN = +opt('--min', 150);
const out = opt('--out', path.join(SUITE, 'Docs', 'nightly', 'lore-phase1-' + day + '.md'));
const BOTS = new Set(['pinguinob0t', 'pinguinohelper', 'chattypinguino', 'nightbot', 'streamelements', 'soundalerts', 'rocketrankbot', 'streamlabs', 'streamerbot', 'moobot', 'fossabot']);
const rj = (f, d) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return d; } };

const logf = path.join(SUITE, 'Data', 'chat_logs', day.slice(0, 4), day.slice(5, 7), day + '.txt');
let head = ['# Lore Phase 1 - ' + day, ''];
if (!fs.existsSync(logf)) { fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, head.concat('No chat log at `' + path.relative(SUITE, logf) + '`. Nothing to learn.', '').join('\n')); console.log('no log for ' + day); process.exit(0); }

const raw = fs.readFileSync(logf, 'utf8');
const rows = [];
for (const l of raw.split(/\r?\n/)) { const r = /^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\] #\S+ (\S+?): (.*)$/.exec(l); if (r) rows.push({ t: r[2], u: r[3].toLowerCase(), x: r[4] }); }
const mem = rj(path.join(SUITE, 'Data', 'runtime', 'chat_memory.json'), rj(path.join(SUITE, 'Data', 'chat_memory.json'), {}));
const optout = new Set();
for (const [u, v] of Object.entries(mem.Users || mem)) if (v && typeof v === 'object' && /^(anon|forget)$/i.test(String(v.Privacy || ''))) { optout.add(u.toLowerCase()); if (v.Login) optout.add(String(v.Login).toLowerCase()); for (const x of v.Aliases || []) optout.add(String(x).toLowerCase()); }
const aliases = (rj(path.join(SUITE, 'Data', 'boards', 'aliases.json'), {}).aliases) || {};
const main = u => aliases[u] || u;
const isBot = u => BOTS.has(u) || /bot$/.test(u);
const human = rows.filter(r => !isBot(r.u) && !r.x.startsWith('!')).map(r => ({ ...r, u: main(r.u) })).filter(r => !optout.has(r.u));
const kb = (raw.length / 1024).toFixed(1);
const L = head.concat(`Log: \`${path.relative(SUITE, logf).replace(/\\/g, '/')}\` - ${kb} KB, ${rows.length} lines, ${human.length} human chat messages (commands, bots and opted-out users excluded). Threshold to learn: ${MIN}.`, '');

if (human.length < MIN) {
  L.push('**Too small to learn from.** No lore changes proposed; the log will be folded into the next day that clears the threshold.', '');
  fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, L.join('\n'));
  console.log(`${day}: ${human.length} msgs < ${MIN}, no learning -> ${out}`); process.exit(0);
}

// known vocabulary: lore items, person-card lore tags, stoplist
const lore = rj(path.join(SUITE, 'Data', 'lore', 'channel_lore.json'), {});
const known = new Set((lore.items || []).flatMap(i => String(i.term || '').toLowerCase().split(/[\s/,]+/)).filter(Boolean));
const graph = rj(path.join(SUITE, 'Data', 'lore', 'people_graph.json'), { nodes: [], edges: [] });
const nodes = new Set((graph.nodes || []).map(n => String(n.id || n.login || n).toLowerCase()));
const STOP = new Set('the a an and or but is are was were be been to of in on at for with it its it\'s this that these those i you he she they we me my your his her them us not no yes yeah ok okay so if as do does did done have has had just like get got can could would should will what when why how who where there here then than too very really im i\'m dont don\'t its lol lmao lmfao haha hahaha pog gg w l one two out up down all any some more most from into about over what\'s that\'s you\'re they\'re can\'t didn\'t doesn\'t isnt isn\'t wasnt wasn\'t u ur yo oh uh um hi hey hello bro man dude gonna wanna also still now good bad nice well back much many even ever never always going go went come came see saw look looked think thought know knew want need make made take took give gave say said tell told let lets let\'s aint ain\'t lil yea nah mb gm don him better long today game play stream live bot bots today much'.split(/\s+/));
const words = {}, who = {};
for (const r of human) {
  const txt = r.x.toLowerCase().replace(/https?:\S+/g, ' ').replace(/@\w+/g, ' ');
  const seen = new Set();
  for (const w of txt.match(/[a-z][a-z0-9']{2,}/g) || []) {
    if (STOP.has(w) || known.has(w) || w.length > 20 || seen.has(w)) continue; seen.add(w);
    words[w] = (words[w] || 0) + 1; (who[w] ??= new Set()).add(r.u);
  }
}
const terms = Object.entries(words).filter(([w, n]) => n >= 4 && who[w].size >= 2).sort((x, y) => y[1] - x[1]).slice(0, 25);

const per = {}; for (const r of human) per[r.u] = (per[r.u] || 0) + 1;
const top = Object.entries(per).sort((x, y) => y[1] - x[1]);
const cards = new Set(fs.existsSync(path.join(SUITE, 'Data', 'lore', 'person_cards')) ? fs.readdirSync(path.join(SUITE, 'Data', 'lore', 'person_cards')).map(f => f.replace(/\.\w+$/, '').toLowerCase()) : []);
const newPeople = top.filter(([u, n]) => n >= 5 && !nodes.has(u) && !cards.has(u));

// pairs: @mentions between people
const pairs = {};
for (const r of human) for (const m of r.x.toLowerCase().matchAll(/@(\w{3,25})/g)) {
  const t = main(m[1]); if (t === r.u || isBot(t) || optout.has(t)) continue;
  const k = [r.u, t].sort().join(' + '); pairs[k] = (pairs[k] || 0) + 1;
}
const topPairs = Object.entries(pairs).filter(([, n]) => n >= 3).sort((x, y) => y[1] - x[1]).slice(0, 10);
const edgeKey = new Set((graph.edges || []).map(e => [e.a || e.source, e.b || e.target].map(s => String(s).toLowerCase()).sort().join(' + ')));
const clips = [...raw.matchAll(/(?:twitch\.tv\/[^\/\s]+\/clip\/|clips\.twitch\.tv\/)([A-Za-z0-9_-]+)/g)].length;

L.push('## Who talked', '', top.slice(0, 10).map(([u, n]) => `- ${u}: ${n}${nodes.has(u) ? '' : ' (not in people graph)'}`).join('\n'), '');
L.push('## Candidate new terms (not yet in channel_lore; 4+ uses by 2+ people)', '', terms.length ? terms.map(([w, n]) => `- \`${w}\` x${n} (${who[w].size} people)`).join('\n') : '_none_', '');
L.push('Proposal only: read them in context (`ctx.mjs`) before any goes into notes.mjs. Words are not meanings.', '');
L.push('## People without a graph node or card (5+ messages)', '', newPeople.length ? newPeople.map(([u, n]) => `- ${u}: ${n}`).join('\n') : '_none_', '');
L.push('## Pairs that @ each other 3+ times', '', topPairs.length ? topPairs.map(([k, n]) => `- ${k}: ${n}${edgeKey.has(k) ? ' (edge exists)' : ' (**no edge yet**)'}`).join('\n') : '_none_', '');
L.push(`## Misc`, '', `- clip links shared: ${clips}`, `- opted-out users in the sources are skipped (${optout.size} on the list)`, '');
fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, L.join('\n'));
console.log(`${day}: ${human.length} msgs, learned: ${terms.length} terms, ${newPeople.length} new people, ${topPairs.length} pairs -> ${out}`);
