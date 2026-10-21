"""Backfill the period event log (Data\\boards\\metric_events.jsonl) from what the Host already stored, then ask a running Host to rebuild its buckets.
Safe to run any number of times: every line carries a stable id and an id that is already in the file is never written again.
What it can recover (and how exactly):
  gifts, bits    Data\\boards\\events.json (every event has its own timestamp: counts in the exact day / week)
  points         Data\\economy\\points.json ledger (exact timestamps; loans and depreciation are not income/spending)
  watchtime, points from watching   points.json "months" (only the MONTH is known: grain "month", counts for that month, its year and all time, never a day or week)
  messages       Data\\profiles\\*.json activity.perMonth (month grain)
  Months at or after the first live (non-backfill) event of a metric are skipped, so nothing is counted twice.
What has no history to recover: follows, refollows, commands, wins (they start counting from the Host update on).
Usage: python Tools/rebuild-buckets.py [--data D:\\PinguinoSuite\\Data] [--dry-run] [--reload http://127.0.0.1:8770]"""
import argparse, calendar, glob, json, os, sys, urllib.request

ap = argparse.ArgumentParser()
here = os.path.dirname(os.path.abspath(__file__))
ap.add_argument('--data', default=os.path.join(os.path.dirname(here), 'Data'))
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--reload', default='')
a = ap.parse_args()
data = a.data
if os.path.basename(data.rstrip('\\/')).lower() == 'runtime': data = os.path.dirname(data.rstrip('\\/'))
boards = os.path.join(data, 'boards'); target = os.path.join(boards, 'metric_events.jsonl')

def jload(p, default):
    try:
        with open(p, encoding='utf-8-sig') as f: return json.load(f)
    except Exception: return default

have, live_first = set(), {}
if os.path.exists(target):
    for line in open(target, encoding='utf-8'):
        line = line.strip()
        if not line: continue
        try: o = json.loads(line)
        except Exception: continue
        if o.get('id'): have.add(o['id'])
        if not str(o.get('id', '')).startswith('bf:') and not o.get('grain'):
            m = o.get('metric'); t = int(o.get('ts', 0))
            if t and (m not in live_first or t < live_first[m]): live_first[m] = t

def month_of(ts): return __import__('time').strftime('%Y-%m', __import__('time').gmtime(ts))
def skip_month(metric, month): return metric in live_first and month >= month_of(live_first[metric])
def mid_month(month):
    y, m = int(month[:4]), int(month[5:7]); return calendar.timegm((y, m, 15, 18, 0, 0))   # 12:00 Chicago, safely inside the month in any zone

new, counts = [], {}
def emit(user, metric, amount, ts, id, grain=None):
    if not user or amount <= 0 or ts <= 0 or id in have: return
    have.add(id); o = {'ts': int(ts), 'user': user.lower(), 'metric': metric, 'amount': amount, 'id': id}
    if grain: o['grain'] = grain
    new.append(json.dumps(o, separators=(',', ':'))); counts[metric] = counts.get(metric, 0) + 1

# gifts and bits: same ids the Host uses live (type:user:to:at)
for e in jload(os.path.join(boards, 'events.json'), []):
    t = e.get('type'); u = (e.get('user') or '').strip().lstrip('@').lower(); to = (e.get('to') or '').strip().lower()
    if t not in ('gift', 'cheer') or u in ('', 'anonymous'): continue
    emit(u, 'gifts' if t == 'gift' else 'bits', e.get('amount', 0), e.get('at', 0), '%s:%s:%s:%s' % (t, u, to, e.get('at', 0)))

# economy ledger: same ids the Host uses live ("ap:" + ledger id)
pts = jload(os.path.join(data, 'economy', 'points.json'), {})
for lid, e in (pts.get('ledger') or {}).items():
    src = e.get('source') or ''
    if src in ('loan', 'loan_repay', 'depreciation'): continue
    d = e.get('delta', 0)
    if d: emit(e.get('login', ''), 'points' if d > 0 else 'points_spent', abs(d), e.get('at', 0), 'ap:' + lid)
# watching, per month (month grain)
for month, users in (pts.get('months') or {}).items():
    for login, v in users.items():
        if not skip_month('watchtime', month): emit(login, 'watchtime', round(v.get('minutes', 0)), mid_month(month), 'bf:wt:%s:%s' % (month, login), 'month')
        if not skip_month('points', month): emit(login, 'points', round(v.get('points', 0)), mid_month(month), 'bf:pt:%s:%s' % (month, login), 'month')
# messages per month from the viewer profiles
for f in glob.glob(os.path.join(data, 'profiles', '*.json')):
    login = os.path.splitext(os.path.basename(f))[0].lower()
    if login == 'index': continue
    pm = ((jload(f, {}).get('activity') or {}).get('perMonth')) or {}
    for month, n in pm.items():
        if isinstance(n, (int, float)) and len(month) == 7 and not skip_month('messages', month): emit(login, 'messages', n, mid_month(month), 'bf:msg:%s:%s' % (month, login), 'month')

print('%s %d new event lines %s' % ('would write' if a.dry_run else 'writing', len(new), json.dumps(counts, sort_keys=True)))
if new and not a.dry_run:
    os.makedirs(boards, exist_ok=True)
    with open(target, 'a', encoding='utf-8', newline='\n') as f: f.write('\n'.join(new) + '\n')
if a.reload and not a.dry_run:
    try:
        rq = urllib.request.Request(a.reload.rstrip('/') + '/api/boards/reload', b'{}', {'Content-Type': 'application/json', 'Origin': a.reload.rstrip('/')})
        print('Host rebuilt its buckets:', urllib.request.urlopen(rq, timeout=15).read().decode())
    except Exception as ex: print('Host not reloaded (%s): it reads the file at its next start, or POST /api/boards/reload' % ex)
