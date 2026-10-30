#!/usr/bin/env python
"""Read-only: rebuild channel-point redemption baselines and emit one seed JSON.

Usage:  python -I Tools/redeem-seed.py [--cutoff 2026-10-30T23:00:00Z] [--out PATH] [--root D:/PinguinoSuite]

Writes JSON to stdout (or --out; never inside Data/). Reads only:
  Data/chat_logs/2026/*/*.txt, _original-downloads/10-*.txt, live/*.jsonl  (SoundAlerts chat lines)
  Archive/streamerbot-2026-10-19/logs.zip                                  (Streamer.bot-bound redeems)
  Data/runtime/console/host.jsonl(.1)                                      (Host-era song request / skip song)
Method and double-count notes: Docs/qa/redeems-history-2026-10-30.md.

--cutoff C: drop events newer than C so the Host's live counter (which starts at the
restart) does not double count. Default: no cut, baselineThrough = newest event seen.
"""
import re, glob, json, collections, zipfile, argparse, sys, datetime as dt

ap = argparse.ArgumentParser()
ap.add_argument('--root', default='D:/PinguinoSuite')
ap.add_argument('--cutoff')
ap.add_argument('--out')
ap.add_argument('--no-feed', action='store_true', help='skip folding in the Host site_activity feed gap')
a = ap.parse_args()
ROOT = a.root.rstrip('/') + '/'
CHAT = ROOT + 'Data/chat_logs/'
BROADCASTER = 'innocentpenguin_'
UTC = dt.timezone.utc

def parse_iso(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(UTC)

CUT = parse_iso(a.cutoff) if a.cutoff else None
def epoch(ts):
    return dt.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC).timestamp()
def keep(ts):
    return CUT is None or epoch(ts) <= CUT.timestamp()


# ---- stream day = America/Chicago calendar date (same as PinguinoHost/HostPeriods.cs: Tz Chicago, DayShiftHours 0)
# No tzdata on this box, so the US DST rule is coded: CDT (UTC-5) from the 2nd Sunday of March 08:00 UTC to the
# 1st Sunday of November 07:00 UTC, else CST (UTC-6).
def _nth_sunday(y, mo, n):
    d = dt.datetime(y, mo, 1, tzinfo=UTC)
    d += dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    return d
def chicago_day(utc_ts):
    u = dt.datetime.strptime(utc_ts[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
    start = _nth_sunday(u.year, 3, 2).replace(hour=8); end = _nth_sunday(u.year, 11, 1).replace(hour=7)
    off = -5 if start <= u < end else -6
    return (u + dt.timedelta(hours=off)).strftime('%Y-%m-%d')

# ---- 1. SoundAlerts chat lines, three overlapping sources, deduped ------------------------
LINE = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] #\S+ soundalerts: (.*)$')
def parse_txt(f):
    for l in open(f, encoding='utf-8', errors='replace'):
        m = LINE.match(l.rstrip('\n'))
        if m:
            yield m.group(1), m.group(2)

allv = []
for f in sorted(glob.glob(CHAT + '2026/*/*.txt')):
    seen = set()
    for ts, s in parse_txt(f):
        if (ts, s) in seen:           # the public log repeats a few lines inside one file
            continue
        seen.add((ts, s)); allv.append((ts, s, 'public'))
for f in sorted(glob.glob(CHAT + '_original-downloads/10-*.txt')):
    for ts, s in parse_txt(f):
        allv.append((ts, s, 'orig'))
for f in sorted(glob.glob(CHAT + 'live/*.jsonl')):
    for l in open(f, encoding='utf-8'):
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get('u') == 'soundalerts':
            ts = dt.datetime.fromtimestamp(d['t'] / 1000, UTC).strftime('%Y-%m-%d %H:%M:%S')
            allv.append((ts, d['m'], 'live'))
allv.sort(key=lambda x: epoch(x[0]))
events, byt = [], collections.defaultdict(list)
for ts, s, src in allv:           # same text within 5 s from a different source = same event
    e = epoch(ts); hit = None
    for ev in byt[s][-5:]:
        if abs(ev['e'] - e) <= 5 and src not in ev['src']:
            hit = ev; break
    if hit:
        hit['src'].add(src); continue
    ev = {'ts': ts, 'e': e, 'm': s, 'src': {src}}
    events.append(ev); byt[s].append(ev)

RULES = [
    ('pushups', 'Pushups', r'^\S+ says DO PUSHUPS!!!$'),
    ('hydrate', 'Hydrate', r'^\S+ (redeemed "Hydrate"|wants everyone to hydrate!)'),
    ('mimimimi', 'Mimimimi', r'^\S+ redeemed "Mimimimi"'),
    ('crab_rave', 'Crab Rave', r"^\S+ redeemed \"Crab Rave\"|^\S+ is crab ravin'"),
    ('posture_check', 'Posture Check', r'^\S+ redeemed "Posture Check"|wants you to check your posture|posture check$'),
    ('lizard', 'Lizard', r'^LIZARD$|^\S+ redeemed "Lizard"'),
    ('hello_there', 'Hello There', r'^\S+ says hi!$'),
    ('yippeeee', 'yippeeee', r'^\S+ redeemed "yippeeee"'),
    ('eat', 'Eat!', r'remind you to eat|reminding you to eat'),
    ('video_share', 'Short Video Share', r'^\S+ redeemed "(Long|Short) Video Share"'),
    ('tts', 'Text-to-Speech', r'^\S+ redeemed "Text-to-Speech"'),
    ('cat', 'cat (unmapped)', r'^cat$'),
]
RX = [(g, t, re.compile(p)) for g, t, p in RULES]

groups = collections.OrderedDict()
def grp(gid, title, source, note=''):
    return groups.setdefault(gid, {'id': gid, 'title': title, 'source': source, 'note': note,
                                   'raw': 0, 'baseline': 0, 'broadcasterTests': 0,
                                   'days': collections.Counter(), 'local': False, 'ev': [], 'first': None, 'last': None})
def add(g, ts, viewer=True, user=''):
    g['ev'].append((ts, user))
    g['raw'] += 1
    if not viewer:
        g['broadcasterTests'] += 1
    else:
        g['baseline'] += 1
        g['days'][g['local'] and ts[:10] or chicago_day(ts)] += 1
    g['first'] = ts if g['first'] is None or ts < g['first'] else g['first']
    g['last'] = ts if g['last'] is None or ts > g['last'] else g['last']

for gid, title, _ in RULES:      # fixed order, pushups first
    grp(gid, title, 'soundalerts-chat', 'UTC. baseline excludes lines typed by %s (sound tests).' % BROADCASTER)
for e in events:
    if not keep(e['ts']):
        continue
    for gid, title, rx in RX:
        if rx.search(e['m']):
            user = e['m'].split()[0].lower() if not e['m'].startswith(('LIZARD', 'cat')) else ''
            add(groups[gid], e['ts'], viewer=(user != BROADCASTER), user=user)
            break

# ---- 2. Streamer.bot-bound rewards (logs.zip) ----------------------------------------------
SB = {'Suggestion Box': ('suggestion', 'Suggestion'), 'Vol': ('max_volume', 'Max Volume'),
      'Crossbar': ('crossbar', 'Add Crossbar Sound'), 'Timeout 60 sec': ('timeout_someone', 'Timeout Someone')}
pat = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+ \w+\] ActionDispatcher :: Queueing '([^']*)' \(([0-9a-f-]+), TwitchRewardRedemption\) .*initiated by (\S+)")
for gid, title in SB.values():
    grp(gid, title, 'streamerbot-logs', 'Streamer.bot local time (not UTC). Archive ends 2026-10-19. All users incl. broadcaster tests.')
z = zipfile.ZipFile(ROOT + 'Archive/streamerbot-2026-10-19/logs.zip')
for name in sorted(z.namelist()):
    for raw in z.open(name):
        if b'TwitchRewardRedemption' not in raw:
            continue
        m = pat.match(raw.decode('utf-8', 'replace'))
        if m and m.group(2) in SB and keep(m.group(1)):
            groups[SB[m.group(2)][0]]['local'] = True
            add(groups[SB[m.group(2)][0]], m.group(1))

# ---- 3. Host era: song request / skip song from the Host console --------------------------
grp('song_request', 'Song Request', 'host-console',
    'UTC. Host console only: "ran Spotify: channel point song request (redeem" + "song request redeem left to Songify". Starts 2026-10-23.')
grp('skip_song', 'Skip Song', 'host-console', 'UTC. "ran Spotify: channel point skip song (redeem". Starts 2026-10-24.')
for f in (ROOT + 'Data/runtime/console/host.jsonl.1', ROOT + 'Data/runtime/console/host.jsonl'):
    try:
        fh = open(f, encoding='utf-8', errors='replace')
    except OSError:
        continue
    for l in fh:
        if 'song' not in l:
            continue
        try:
            d = json.loads(l)
        except ValueError:
            continue
        msg = d.get('msg', '')
        ts = d.get('ts', '')[:19].replace('T', ' ')
        if not keep(ts):
            continue
        if "ran 'Spotify: channel point song request' (redeem" in msg or 'song request redeem left to Songify' in msg:
            add(groups['song_request'], ts)
        elif "ran 'Spotify: channel point skip song' (redeem" in msg:
            add(groups['skip_song'], ts)


# ---- 4. Host feed gap: redemptions the logs have not caught up with ------------------------
FEED = {'pushups': 'pushups', 'hydrate': 'hydrate', 'mimimimi': 'mimimimi', 'crab rave': 'crab_rave',
        'posture check': 'posture_check', 'lizard': 'lizard', 'hello there': 'hello_there',
        'yippeeee': 'yippeeee', 'song request': 'song_request', 'skip song': 'skip_song',
        'timeout someone': 'timeout_someone', 'text-to-speech': 'tts', 'long video share': 'video_share',
        'short video share': 'video_share', 'video share': 'video_share', 'suggestion': 'suggestion'}
console_new = max([groups[x]['last'] for x in ('song_request', 'skip_song') if groups[x]['last']], default='')
gap = collections.Counter(); gap_unmapped = collections.Counter()
if not a.no_feed:
    try:
        feed = json.load(open(ROOT + 'Data/runtime/runtime/site_activity.json', encoding='utf-8-sig'))
    except (OSError, ValueError):
        feed = []
    for f in feed:
        if f.get('type') != 'redemption':
            continue
        ts = dt.datetime.fromtimestamp(f['at'], UTC).strftime('%Y-%m-%d %H:%M:%S')
        if not keep(ts):
            continue
        title = (f.get('extra') or '').strip()
        gid = FEED.get(title.lower())
        if not gid:
            gap_unmapped[title] += 1; continue
        g = groups[gid]; user = (f.get('user') or '').lower()
        if g['source'] == 'soundalerts-chat':      # already in the chat log if same user within 20 s
            if any(u == user and abs(epoch(t) - f['at']) <= 20 for t, u in g['ev']):
                continue
            viewer = user != BROADCASTER
        elif g['source'] == 'host-console':
            if ts <= console_new:
                continue
            viewer = True
        else:                                        # streamerbot-logs group: archive ends 2026-10-19
            viewer = True
        gap[gid] += 1
        if viewer:
            g['baseline'] += 1; g['days'][chicago_day(ts)] += 1
        g['raw'] += 1
        g['last'] = ts if not g['last'] or ts > g['last'] else g['last']

def permonth(g):
    pm = collections.Counter()
    for d, n in g['days'].items():
        pm[d[:7]] += n
    return dict(sorted(pm.items()))
RECORD_START = {'soundalerts-chat': chicago_day(allv[0][0]), 'host-console': '2026-10-19', 'streamerbot-logs': '2026-02-04'}

# ---- output --------------------------------------------------------------------------------
newest = max((g['last'] for g in groups.values() if g['last'] and g['source'] != 'streamerbot-logs'), default=None)
out = {
    'generatedAt': dt.datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'cutoff': CUT.strftime('%Y-%m-%dT%H:%M:%SZ') if CUT else None,
    'baselineThrough': (CUT.strftime('%Y-%m-%dT%H:%M:%SZ') if CUT else (newest.replace(' ', 'T') + 'Z' if newest else None)),
    'baselineThroughNote': 'newest UTC event time across chat/console sources (or the --cutoff). Host live counter must count only redeems AFTER this.',
    'sourcesNewest': {src: max((g['last'] for g in groups.values() if g['source'] == src and g['last']), default=None)
                      for src in ('soundalerts-chat', 'host-console', 'streamerbot-logs')},
    'recordStart': min(RECORD_START.values()),
    'recordStartNote': 'No per-event record before this stream day (2026-02-04, Streamer.bot logs; SoundAlerts chat text starts per group recordStart). Dec 2025-Feb 3 is unknown, not zero.',
    'dayDefinition': 'Stream day = America/Chicago calendar date of the event (PinguinoHost/HostPeriods.cs: Tz America/Chicago, DayShiftHours 0). UTC chat/console/feed times are converted with the US DST rule; Streamer.bot log times are already Chicago local. baseline = sum(days); perMonth = sum of days by Chicago month.',
    'estimatedDays': {'pushups': {'2026-02-04..2026-02-14': 10}},
    'estimated': {'pushups': {'count': 10, 'range': [5, 16], 'window': '2026-02-04..2026-02-14',
                              'note': 'NOT in baseline. Keep separate; shown as "~N before 2026-02-16". Dec 2025-Feb 3 unknown.'}},
    'feedGapNote': 'baseline INCLUDES feedGapAdded: Host site_activity redemptions the logs lacked (chat groups: no same-user chat line within 20 s; console groups: newer than the console). Do not --add these again. Feed only reaches back to its rolling 100 events; unmapped feed titles are in feedUnmapped.',
    'feedUnmapped': dict(gap_unmapped),
    'groups': [],
}
for g in groups.values():
    out['groups'].append({
        'id': g['id'], 'title': g['title'], 'source': g['source'], 'note': g['note'],
        'baseline': g['baseline'], 'feedGapAdded': gap.get(g['id'], 0), 'baselineRaw': g['raw'], 'broadcasterTests': g['broadcasterTests'],
        'days': dict(sorted(g['days'].items())), 'perMonth': permonth(g), 'recordStart': RECORD_START[g['source']], 'firstAt': g['first'], 'lastAt': g['last'],
    })
txt = json.dumps(out, indent=2)
if a.out:
    if '/Data/' in a.out.replace('\\', '/'):
        sys.exit('refusing to write under Data/ (read-only tool)')
    open(a.out, 'w', encoding='utf-8').write(txt)
else:
    print(txt)
