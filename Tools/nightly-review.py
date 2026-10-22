"""Nightly chat-log review: Data/chat_logs/live/<date>.jsonl (+ Host/Core error lines) -> Docs/nightly/<date>.md
Usage: python Tools/nightly-review.py [YYYY-MM-DD] [--out path]      (date = the log file's UTC day; default today UTC)

Aggregates only (counts, command names, bot reply health). No chat text is copied except short bot lines and
unknown !commands, and nothing from people who opted out of memory (Data/chat_memory privacy anon/forget).
Sections: volume, who is talking (counts), commands used / unknown commands, bot health (replies, duplicates,
slow answers), Host + Core warnings and errors. Read-only: it never touches the bots or the Host."""
import collections, datetime, json, os, re, sys

here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
day = args[0] if args else datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else os.path.join(suite, 'Docs', 'nightly', day + '.md')
BOTS = {'pinguinob0t', 'pinguinohelper', 'chattypinguino', 'nightbot', 'streamelements', 'soundalerts', 'rocketrankbot', 'streamlabs'}
OURS = {'pinguinob0t', 'pinguinohelper', 'chattypinguino'}

def load_jsonl(path):
    rows = []
    try:
        for l in open(path, encoding='utf-8', errors='replace'):
            l = l.strip()
            if l:
                try: rows.append(json.loads(l))
                except ValueError: pass
    except OSError: pass
    return rows

def opted_out():
    names = set()
    for f in (os.path.join(suite, 'Data', 'runtime', 'chat_memory.json'), os.path.join(suite, 'Data', 'chat_memory.json')):
        try:
            j = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError): continue
        for u, v in (j.get('Users', j) if isinstance(j, dict) else {}).items():
            if isinstance(v, dict) and str(v.get('Privacy', '')).lower() in ('anon', 'forget'): names.add(u.lower())
    return names

def known_commands():
    cmds = set()
    try:
        for c in json.load(open(os.path.join(suite, 'PinguinoB0t', 'commands.json'), encoding='utf-8')):
            cmds.add(c['command'].lower()); cmds.update(a.lower() for a in c.get('aliases', []))
    except (OSError, ValueError, TypeError, KeyError): pass
    try:
        j = json.load(open(os.path.join(suite, 'Data', 'lore.json'), encoding='utf-8'))
        for c in (j.get('commands', []) if isinstance(j, dict) else []): cmds.add(str(c.get('command', c) if isinstance(c, dict) else c).lower())
    except (OSError, ValueError): pass
    return cmds

rows = load_jsonl(os.path.join(suite, 'Data', 'chat_logs', 'live', day + '.jsonl'))
if not rows:
    print('no chat log for ' + day); sys.exit(1)
skip = opted_out(); known = known_commands()
def clock(ms): return datetime.datetime.fromtimestamp(ms / 1000).strftime('%H:%M')
people = collections.Counter(r['u'].lower() for r in rows if r['u'].lower() not in BOTS and r['u'].lower() not in skip)
human = [r for r in rows if r['u'].lower() not in BOTS]
cmdc = collections.Counter(); unknown = collections.Counter()
for r in human:
    m = (r.get('m') or '').strip()
    if m.startswith('!') and len(m) > 1:
        c = m.split()[0].lower(); cmdc[c] += 1
        if known and c not in known: unknown[c] += 1
bot_lines = [r for r in rows if r['u'].lower() in OURS]
per_bot = collections.Counter(r['u'].lower() for r in bot_lines)
# duplicate bot replies: the same bot saying the same text twice within 60 s with NO viewer line in between
# (a repeat answer to a repeated !command is correct, not a duplicate)
dups = []; last = {}
for r in rows:
    u = r['u'].lower()
    if u not in OURS:
        if u not in BOTS: last.clear()
        continue
    k = (u, (r.get('m') or '').strip().lower())
    if k in last and r['t'] - last[k] < 60000: dups.append((clock(r['t']), k[0], k[1][:80]))
    last[k] = r['t']
# answer speed: a human !command followed by the next bot line, in seconds
lat = []; pending = None
for r in rows:
    u = r['u'].lower()
    if u in BOTS:
        if u in OURS and pending is not None: lat.append((r['t'] - pending) / 1000.0); pending = None
    elif (r.get('m') or '').lstrip().startswith('!'): pending = r['t']
lat.sort(); p50 = lat[len(lat) // 2] if lat else None; p95 = lat[int(len(lat) * 0.95)] if lat else None
unanswered = sum(1 for r in human if (r.get('m') or '').lstrip().startswith('!')) - len(lat)
hours = collections.Counter(datetime.datetime.fromtimestamp(r['t'] / 1000).strftime('%H') for r in human)

def log_lines(name):
    got = collections.Counter(); sample = {}
    start = datetime.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc).timestamp(); end = start + 86400
    for r in load_jsonl(os.path.join(suite, 'Data', 'runtime', 'console', name + '.jsonl')):
        ts = r.get('ts')
        if isinstance(ts, str):
            try: ts = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
            except ValueError: ts = None
        if ts is None or not (start <= ts < end): continue
        if r.get('level') in ('warn', 'warning', 'error'):
            key = (r.get('level'), r.get('source', ''), re.sub(r'\d+', 'N', str(r.get('msg', '')))[:110]); got[key] += 1; sample.setdefault(key, str(r.get('msg', ''))[:160])
    return got

L = []; add = L.append
add('# Nightly review, %s' % day); add('')
add('Generated by Tools\\nightly-review.py from Data\\chat_logs\\live\\%s.jsonl (local times %s to %s). Counts only; opted-out people are left out.' % (day, clock(rows[0]['t']), clock(rows[-1]['t']))); add('')
add('## Volume'); add('- %d lines: %d from viewers/mods, %d from our bots (%s), %d from other bots.' % (len(rows), len(human), len(bot_lines), ', '.join('%s %d' % kv for kv in per_bot.most_common()) or 'none', len(rows) - len(human) - len(bot_lines)))
add('- %d different chatters. Busiest hours (local): %s.' % (len(people), ', '.join('%sh %d' % kv for kv in hours.most_common(3))))
add('- Top chatters: ' + ', '.join('%s %d' % kv for kv in people.most_common(8)))
add('')
add('## Commands'); add('- %d command lines. Most used: %s.' % (sum(cmdc.values()), ', '.join('%s %d' % kv for kv in cmdc.most_common(10)) or 'none'))
add('- Unknown commands people tried (candidates for an answer or an alias): ' + (', '.join('%s %d' % kv for kv in unknown.most_common(12)) or 'none'))
add('')
add('## Bot health')
add('- Time from a viewer !command to the next bot line: median %s, p95 %s (%d measured); %d command lines got no bot line (many commands are silent by design).' % ('%.1fs' % p50 if p50 is not None else 'n/a', '%.1fs' % p95 if p95 is not None else 'n/a', len(lat), max(0, unanswered)))
if dups:
    add('- DUPLICATE bot lines (same bot, same text within 60 s): %d' % len(dups))
    for d in dups[:10]: add('  - %s %s: "%s"' % d)
else: add('- No duplicate bot lines.')
add('')
add('## Host and Core warnings / errors (this UTC day)')
for name in ('host', 'core'):
    g = log_lines(name)
    add('- %s: %d warn/error lines in %d kinds%s' % (name, sum(g.values()), len(g), '' if g else '.'))
    for (lvl, src, msg), n in g.most_common(8): add('  - %dx [%s] %s: %s' % (n, lvl, src, msg))
add('')
# ---- Phase 1b: helper review log, Chatty feedback / mistakes / experience, new in-jokes ----
def day_bounds():
    st = datetime.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc).timestamp() - 12 * 3600
    return st, st + 86400 + 24 * 3600   # chat logs are local-evening: take the UTC day plus a margin so the 19:00 to 01:37 session stays whole
lo, hi = rows[0]['t'] / 1000.0 - 60, rows[-1]['t'] / 1000.0 + 60
trig = [r for r in load_jsonl(os.path.join(suite, 'Data', 'helper', 'review.jsonl')) if r.get('type') == 'trigger' and lo <= r.get('at', 0) <= hi and str(r.get('user', '')).lower() not in skip]
ans = [r for r in trig if r.get('kind') == 'answered']; miss = [r for r in trig if r.get('kind') != 'answered']
add('## Helper unanswered')
add('- Helper saw %d questions in this session: %d answered, %d probably missed (full chat window around each is in the private review browser, Data/helper/review.jsonl).' % (len(trig), len(ans), len(miss)))
for r in miss[:25]: add('  - %s: "%s"%s' % (clock(r['at'] * 1000), str(r.get('text', ''))[:110], (' (' + str(r['reason'])[:60] + ')') if r.get('reason') else ''))
if not miss: add('  - none')
ints = collections.Counter(str(r.get('intent') or '?') for r in ans)
add('- Answered by intent: ' + (', '.join('%s %d' % kv for kv in ints.most_common(8)) or 'none')); add('')

chatty = [r for r in rows if r['u'].lower() == 'chattypinguino']
cl = sorted(r['t'] for r in chatty)
GOOD = re.compile(r'\b(lol|lmao|lmfao|haha+|kek|good bot|love (him|it)|funny|based|w bot|clean)\b', re.I)
BAD = re.compile(r"\b(wrong|bad bot|stop|shut up|cringe|annoying|not funny|spam|huh|make sense|dumb|broken)\b", re.I)
fb_good = fb_bad = 0; bad_ex = []; answered_mentions = 0; mentions = 0
for i, r in enumerate(rows):
    u = r['u'].lower(); m = (r.get('m') or '')
    if u in BOTS: continue
    if re.search(r'chatty', m, re.I): mentions += 1
    prev = next((q for q in reversed(rows[max(0, i - 6):i]) if q['u'].lower() == 'chattypinguino'), None)
    if prev is None or r['t'] - prev['t'] > 45000: continue
    if BAD.search(m): fb_bad += 1; bad_ex.append((clock(r['t']), (prev.get('m') or '')[:70], m[:60]))
    elif GOOD.search(m): fb_good += 1
add('## Chatty feedback, mistakes, experience')
add('- Chatty spoke %d times (first %s, last %s). Viewer reactions within 45 s of a Chatty line: %d positive-looking, %d negative-looking (heuristic word match, not sentiment).' % (len(chatty), clock(cl[0]) if cl else 'n/a', clock(cl[-1]) if cl else 'n/a', fb_good, fb_bad))
for e in bad_ex[:6]: add('  - %s Chatty: "%s" -> viewer: "%s"' % e)
cdup = [d for d in dups if d[1] == 'chattypinguino']
add('- Mistakes: %d duplicate Chatty lines; %d negative reactions above to review.' % (len(cdup), len(bad_ex)))
try:
    mem = json.load(open(os.path.join(suite, 'Data', 'runtime', 'chat_memory.json'), encoding='utf-8'))
    have = sum(1 for v in mem.values() if isinstance(v, dict) and str(v.get('Privacy', '')).lower() not in ('anon', 'forget'))
    add('- Experience: Chatty keeps notes on %d people (opted-out left out); %d messages were addressed to it by name this session.' % (have, mentions))
except (OSError, ValueError): add('- Experience: memory file not readable.')
add('')
# new in-jokes: a word or emote said >= 6 times by >= 3 different people this session, not an ordinary word
common = set()
try: common = set(w.strip().lower() for w in open(os.path.join(suite, 'Data', 'common-words.txt'), encoding='utf-8') if w.strip())
except OSError: pass
lore_txt = ''
try: lore_txt = open(os.path.join(suite, 'Data', 'lore.json'), encoding='utf-8').read().lower()
except OSError: pass
cnt = collections.Counter(); who = collections.defaultdict(set)
for r in human:
    if r['u'].lower() in skip: continue
    for w in set(re.findall(r"[a-z0-9_']{3,20}", (r.get('m') or '').lower())):
        if w in common or w.startswith('!') or w.isdigit(): continue
        cnt[w] += 1; who[w].add(r['u'].lower())
cand = [(w, n, len(who[w])) for w, n in cnt.most_common(200) if n >= 6 and len(who[w]) >= 3 and w not in lore_txt]
add('## New in-joke candidates')
add('- Words/emotes used 6+ times by 3+ different people and not yet in the lore file (Ivan decides what is a real joke): ' + (', '.join('%s %dx/%d people' % c for c in cand[:15]) or 'none'))
add('')
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
print('wrote ' + out + ' (%d lines, %d dups, %d unknown commands)' % (len(rows), len(dups), len(unknown)))
