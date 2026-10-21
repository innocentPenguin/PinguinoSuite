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
# duplicate bot replies: the same bot saying the same text twice within 60 s
dups = []; last = {}
for r in bot_lines:
    k = (r['u'].lower(), (r.get('m') or '').strip().lower())
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
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
print('wrote ' + out + ' (%d lines, %d dups, %d unknown commands)' % (len(rows), len(dups), len(unknown)))
