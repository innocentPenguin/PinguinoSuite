"""Seeds the Host's redeem counters (Data/runtime/redeem_groups.json + redeem_counts.json).

DRY RUN by default: prints the baseline per group and writes nothing. --write applies it, after copying any existing file to
<file>.before-seed-YYYYMMDD-HHMMSS.bak. Cut-off C (--through, UTC ISO) = the moment of the Host restart: the baseline must hold everything up
to C and the Host counts only redemptions after it. Run it only when the stream is off and 100 has said the restart is on.

  python Tools/seed-redeems.py --data D:/PinguinoSuite/Data/runtime                       # dry run, values from the 2026-10-30 history doc
  python Tools/seed-redeems.py --data ... --classified groups.json --through 2026-10-30T14:00:00Z   # dry run from 14's fresh extraction
  python -I Tools/redeem-seed.py --cutoff 2026-10-30T14:00:00Z --out seed.json      # 14's extraction (read-only)
  python Tools/seed-redeems.py --data ... --seed-json seed.json                    # dry run from it (cut-off = its baselineThrough)
  python Tools/seed-redeems.py --data ... --seed-json seed.json --write
  python Tools/seed-redeems.py --data ... --through 2026-10-30T14:00:00Z --write   # values from the doc

--seed-json is the output of Tools/redeem-seed.py (14); groups it does not know (or maps differently) keep the doc values. It also carries the per stream-day history
(group "days" {YYYY-MM-DD: n}, Chicago day), the group's "recordStart" and the separate "estimatedDays" series: the Host stores them per group (days, recordStart, estimatedDays), answers today / week / month / all
from them and never lets the estimate into a total. Seeded days only ever count toward the days they name (a seed never writes today or this week by itself: it holds nothing newer than its cut-off).
--classified is 14's groups.json (group name -> ["YYYY-MM-DD HH:MM:SS|chat text"]); lines after --through are left out and broadcaster lines
(innocentpenguin_) are not counted. Groups that come from Streamer.bot logs (suggestion, max_volume, add_crossbar_sound, timeout_someone) always keep the doc values;
--add group=N adds N to a group (e.g. timeout_someone=3 for the Host-era redemptions the logs never counted). The Pushups estimate for Feb 4-15 is stored apart ("estimated") and never enters a total.
"""
import argparse, datetime as dt, json, os, shutil, sys

GROUPS = {
    'pushups': ('Pushups', ['b618f97f', '5567e401', '09c78a1c'], ['Pushups', 'Do Pushups Now!']),
    'hydrate': ('Hydrate', ['7d9b5951', '4627369b', '4ef5ade3'], ['Hydrate', 'Hydrate!']),
    'mimimimi': ('Mimimimi', ['306cb8f8', '9f5b9098'], ['Mimimimi', 'Mimimimi - Sound']),
    'hello_there': ('Hello There', ['fc9d5c74'], ['Hello There']),
    'crab_rave': ('Crab Rave', ['0b6a9b59', '51774805'], ['Crab Rave', 'Crab Rave - Sound']),
    'posture_check': ('Posture Check', ['bcfdab37', '7843108f'], ['Posture Check', 'Posture Fix!']),
    'lizard': ('Lizard', ['f4aed617'], ['Lizard']),
    'yippeeee': ('yippeeee', ['14d7d1dc'], ['yippeeee']),
    'video_share': ('Video Share', ['0d3c25b6'], ['Video Share', 'Long Video Share', 'Short Video Share']),
    'text_to_speech': ('Text-to-Speech', ['c4683ea4'], ['Text-to-Speech']),
    'suggestion': ('Suggestion', ['65467951'], ['Suggestion']),
    'max_volume': ('Max Volume', ['47d16fc5'], ['Max Volume', 'Max Volume (10 Seconds)']),
    'add_crossbar_sound': ('Add Crossbar Sound', ['96c5e96f'], ['Add Crossbar Sound']),
    'timeout_someone': ('Timeout Someone', ['2d1e8090'], ['Timeout Someone']),
    'song_request': ('Song Request', ['e086b229'], ['Song Request']),
    'skip_song': ('Skip Song', ['ba75b1c3'], ['Skip Song']),
}
# viewer lines through 2026-10-30 ~01:00 UTC, per UTC month (Docs/qa/redeems-history-2026-10-30.md)
DOC = {
    'pushups': {'2026-02': 14, '2026-03': 25, '2026-04': 38, '2026-05': 25, '2026-06': 14, '2026-07': 10, '2026-08': 8, '2026-09': 1, '2026-10': 26},
    'hydrate': {'2026-02': 107, '2026-03': 150, '2026-04': 75, '2026-05': 129, '2026-06': 95, '2026-07': 89, '2026-08': 70, '2026-09': 107, '2026-10': 102},
    'mimimimi': {'2026-02': 39, '2026-03': 91, '2026-04': 86, '2026-05': 54, '2026-06': 22, '2026-07': 30, '2026-08': 37, '2026-09': 23, '2026-10': 9},
    'hello_there': {'2026-02': 12, '2026-03': 29, '2026-04': 51, '2026-05': 72, '2026-06': 49, '2026-07': 43, '2026-08': 37, '2026-09': 29, '2026-10': 28},
    'crab_rave': {'2026-03': 46, '2026-04': 98, '2026-05': 38, '2026-07': 9, '2026-08': 33, '2026-09': 19, '2026-10': 42},
    'posture_check': {'2026-07': 13, '2026-08': 58, '2026-09': 51, '2026-10': 46},
    'lizard': {'2026-07': 16, '2026-08': 68, '2026-09': 41, '2026-10': 10},
    'yippeeee': {'2026-10': 44},
    'video_share': {'2026-03': 15, '2026-04': 12, '2026-05': 3, '2026-06': 9, '2026-07': 10},
    'text_to_speech': {'2026-07': 36},
    'suggestion': {'2026-02': 33, '2026-03': 78, '2026-04': 118, '2026-05': 125, '2026-06': 3},
    'max_volume': {'2026-02': 32, '2026-03': 7},
    'add_crossbar_sound': {'2026-03': 5},
    'timeout_someone': {'2026-04': 5, '2026-07': 1},
    'song_request': {'2026-10': 224},   # Host console only, from 2026-10-23
    'skip_song': {'2026-10': 25},       # Host console only, from 2026-10-24
}
ESTIMATED = {'pushups': {'count': 10, 'range': '2026-02-04..2026-02-15', 'note': 'SoundAlerts posted 134 lines then, text never saved; a ratio, not a count. Not in baseline or total.'}}
FROM_LOGS = {'suggestion', 'max_volume', 'add_crossbar_sound', 'timeout_someone'}
NAMES = {'Pushups': 'pushups', 'Hydrate': 'hydrate', 'Mimimimi': 'mimimimi', 'Hello There': 'hello_there', 'Crab Rave': 'crab_rave', 'Posture Check': 'posture_check',
         'Lizard': 'lizard', 'yippeeee': 'yippeeee', 'Video Share (Long/Short)': 'video_share', 'Text-to-Speech': 'text_to_speech'}
BROADCASTER = 'innocentpenguin_'
SEED_IDS = {'tts': 'text_to_speech', 'crossbar': 'add_crossbar_sound'}   # 14's Tools/redeem-seed.py group ids that differ from the Host's keys


def from_classified(path, through):
    raw = json.load(open(path, encoding='utf-8')); out = {}
    for name, lines in raw.items():
        key = NAMES.get(name)
        if not key: continue
        pm = {}
        for l in lines:
            ts, msg = l.split('|', 1)
            if msg.lower().startswith(BROADCASTER + ' '): continue
            t = dt.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc)
            if through and t > through: continue
            pm[ts[:7]] = pm.get(ts[:7], 0) + 1
        out[key] = pm
    return out


def from_seed_json(path):
    j = json.load(open(path, encoding='utf-8')); out = {}; hist = {}
    for g in j.get('groups', []):
        k = SEED_IDS.get(g['id'], g['id'])
        if k not in GROUPS: continue
        days = {d: int(n) for d, n in (g.get('days') or {}).items() if int(n) > 0}
        pm = dict(g.get('perMonth') or {})
        if days:
            pm = {}
            for d, n in days.items(): pm[d[:7]] = pm.get(d[:7], 0) + n
            hist[k] = {'days': dict(sorted(days.items())), 'recordStart': g.get('recordStart')}
        out[k] = pm
    est = j.get('estimatedDays') or {}
    for k, v in est.items():
        if k in GROUPS: hist.setdefault(k, {})['estimatedDays'] = v
    return out, j.get('baselineThrough'), hist


def build(a):
    through = dt.datetime.strptime(a.through, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc) if a.through else None
    base = {k: dict(v) for k, v in DOC.items()}
    a.hist = {}
    if a.seed_json:
        sj, thr, a.hist = from_seed_json(a.seed_json); base.update(sj)
        if not a.through and thr:
            a.through = thr; through = dt.datetime.strptime(thr, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    if a.classified:
        for k, pm in from_classified(a.classified, through).items(): base[k] = pm; a.hist.pop(k, None)   # a re-extraction by month replaces the day series of that group
    for x in a.add or []:
        k, n = x.split('=', 1)
        if k not in GROUPS: sys.exit('unknown group ' + k)
        cur = base.setdefault(k, {}); m = (through or dt.datetime.now(dt.timezone.utc)).strftime('%Y-%m'); cur[m] = cur.get(m, 0) + int(n)
        a.hist.pop(k, None)   # a manual add has no day: the group falls back to its months
    return base, through


def stamp_copy(p):
    if os.path.exists(p):
        b = p + '.before-seed-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak'; shutil.copy2(p, b); return b


DEFAULT_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'runtime')
HOST_MARKERS = ('host_secrets.json', 'automations.json', 'bots.json', 'chat_settings.json')   # files only the Host's real data folder has
def host_data(d):
    """The Host's real data dir (Data/runtime = HostApi.DataDir) is the default; a folder without any host file is refused (a typo or the parent Data/ folder would seed files the Host never reads)."""
    d = os.path.abspath(d)
    if not any(os.path.exists(os.path.join(d, m)) for m in HOST_MARKERS):
        sys.exit('refused: %s has none of %s, so it is not the Host data folder (the default is %s)' % (d, '/'.join(HOST_MARKERS), DEFAULT_DATA))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', default=DEFAULT_DATA)
    ap.add_argument('--through'); ap.add_argument('--classified'); ap.add_argument('--seed-json'); ap.add_argument('--add', action='append'); ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    a.data = host_data(a.data)
    base, through = build(a)
    rt = os.path.join(a.data, 'runtime'); gp = os.path.join(rt, 'redeem_groups.json'); cp = os.path.join(rt, 'redeem_counts.json')
    print('target files:'); print('  ' + gp); print('  ' + cp)
    print('%-20s %9s  %-10s %s' % ('group', 'baseline', 'days', 'per month'))
    for k in GROUPS:
        h = a.hist.get(k, {}); dsum = sum((h.get('days') or {}).values()); b = sum(base.get(k, {}).values())
        ds = ('%d%s' % (len(h['days']), '' if dsum == b else ' MISMATCH')) if h.get('days') else '-'
        print('%-20s %9d  %-10s %s' % (k, b, ds, json.dumps(base.get(k, {}), sort_keys=True)))
        if h.get('days') and dsum != b: sys.exit('group %s: sum of days %d != baseline %d' % (k, dsum, b))
    print('cut-off C: %s   (estimated, not in totals: %s)' % (a.through or 'NOT SET', json.dumps(ESTIMATED)))
    old = json.load(open(cp, encoding='utf-8')) if os.path.exists(cp) else {}
    live = sum((g.get('live') or 0) for g in (old.get('groups') or {}).values())
    if old: print('existing %s: %d live counts are kept (seen ids too)' % (cp, live))
    if not a.write: print('DRY RUN: nothing written. Add --write --through <UTC ISO> to apply.'); return
    if not through: sys.exit('--write needs --through YYYY-MM-DDTHH:MM:SSZ (the restart moment)')
    os.makedirs(rt, exist_ok=True)
    for p in (gp, cp):
        b = stamp_copy(p)
        if b: print('backup:', b)
    groups = json.load(open(gp, encoding='utf-8')) if os.path.exists(gp) else {}
    for k, (title, ids, aliases) in GROUPS.items(): groups[k] = {'title': title, 'ids': ids, 'aliases': aliases}
    counts = old if old else {}
    counts.setdefault('groups', {}); counts.setdefault('seen', [])
    for k, (title, ids, aliases) in GROUPS.items():
        e = counts['groups'].get(k) or {}
        e.update({'title': title, 'baseline': sum(base.get(k, {}).values()), 'baselineThrough': a.through, 'perMonth': dict(sorted(base.get(k, {}).items()))})
        e.setdefault('live', 0); e.setdefault('livePerMonth', {}); e.setdefault('lastRedeemAt', None)
        if k in ESTIMATED: e['estimated'] = ESTIMATED[k]
        h = a.hist.get(k, {})
        if h.get('days'): e['days'] = h['days']; e['recordStart'] = h.get('recordStart')
        else: e.pop('days', None)
        if h.get('estimatedDays'): e['estimatedDays'] = h['estimatedDays']
        counts['groups'][k] = e
    json.dump(groups, open(gp, 'w', encoding='utf-8'), indent=2); json.dump(counts, open(cp, 'w', encoding='utf-8'), indent=2)
    print('written:', gp, cp)


main()
