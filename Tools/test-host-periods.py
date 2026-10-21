"""Period leaderboards: append-only event log -> day/ISO-week/month/year/all buckets in America/Chicago.
Checks midnight / week / month / year rollover, the DST edges (fall back 2026-11-01, spring forward 2027-03-14), same id applies once, reload/backfill idempotency,
bots left out, level (value + pct), keys newest-first, me, and the bucket files being rebuildable.  Usage: python Tools/test-host-periods.py [dll]"""
import calendar, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSPORT = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgper_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'amy': {'points': 300, 'minutes': 120}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_ECONOMY_TESTHOOK': '1', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p):
    try: return json.load(urllib.request.urlopen(B + p, timeout=10))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def U(y, mo, da, h=0, mi=0, s=0): return calendar.timegm((y, mo, da, h, mi, s))
def ev(user, metric, amount, ts, id=None, grain=None):
    o = {'user': user, 'metric': metric, 'amount': amount, 'ts': ts}
    if id: o['id'] = id
    if grain: o['grain'] = grain
    return post('/api/boards/event', o)
def board(metric, period, key='', login=''):
    return get('/api/boards?metric=%s&period=%s&key=%s&login=%s' % (metric, period, key, login))
def val(metric, period, key, user):
    r = [x for x in board(metric, period, key)['rows'] if x['login'] == user]; return r[0]['value'] if r else 0
SNAP = (('messages', 'all'), ('bits', 'month'), ('gifts', 'year'), ('level', 'all'), ('wins', 'day'))
def snap(): return json.dumps([board(m, p) for m, p in SNAP], sort_keys=True)
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    # ---- midnight: 04:59:59Z is still 21 Oct in Chicago (CDT), 05:00:01Z is 22 Oct
    ev('amy', 'messages', 1, U(2026, 10, 22, 4, 59, 59), 'm1'); ev('amy', 'messages', 1, U(2026, 10, 22, 5, 0, 1), 'm2')
    chk('midnight: before', val('messages', 'day', '2026-10-21', 'amy') == 1, board('messages', 'day', '2026-10-21'))
    chk('midnight: after', val('messages', 'day', '2026-10-22', 'amy') == 1)
    # ---- week: Sunday 25 Oct 23:30 CDT is W43, Monday 26 Oct 00:30 CDT is W44
    ev('bob', 'messages', 5, U(2026, 10, 26, 4, 30), 'w1'); ev('bob', 'messages', 7, U(2026, 10, 26, 5, 30), 'w2')
    chk('week: Sunday night is W43', val('messages', 'week', '2026-W43', 'bob') == 5, board('messages', 'week', '2026-W43'))
    chk('week: Monday is W44', val('messages', 'week', '2026-W44', 'bob') == 7)
    # ---- month + DST fall back (1 Nov 2026 2:00 CDT -> 1:00 CST)
    ev('cat', 'bits', 100, U(2026, 11, 1, 4, 30), 'b1'); ev('cat', 'bits', 200, U(2026, 11, 1, 5, 30), 'b2')
    chk('month: 23:30 on 31 Oct is October', val('bits', 'month', '2026-10', 'cat') == 100, board('bits', 'month', '2026-10'))
    chk('month: 00:30 on 1 Nov is November', val('bits', 'month', '2026-11', 'cat') == 200)
    ev('cat', 'bits', 50, U(2026, 11, 2, 5, 30), 'b3'); ev('cat', 'bits', 25, U(2026, 11, 2, 6, 30), 'b4')
    chk('DST fall back: 23:30 CST is still 1 Nov', val('bits', 'day', '2026-11-01', 'cat') == 250, board('bits', 'day', '2026-11-01'))
    chk('DST fall back: 00:30 CST is 2 Nov', val('bits', 'day', '2026-11-02', 'cat') == 25)
    # ---- year + ISO week 53: 1 Jan 2027 00:30 CST is week 2026-W53
    ev('dan', 'gifts', 3, U(2027, 1, 1, 5, 59, 59), 'y1'); ev('dan', 'gifts', 4, U(2027, 1, 1, 6, 0, 1), 'y2')
    chk('year: 23:59:59 on 31 Dec is 2026', val('gifts', 'year', '2026', 'dan') == 3, board('gifts', 'year', '2026'))
    chk('year: 00:00:01 on 1 Jan is 2027', val('gifts', 'year', '2027', 'dan') == 4)
    chk('week 53 of 2026 holds 31 Dec and 1 Jan', val('gifts', 'week', '2026-W53', 'dan') == 7, board('gifts', 'week', '2026-W53'))
    chk('all time adds up', val('gifts', 'all', '', 'dan') == 7)
    # ---- DST spring forward (14 Mar 2027 2:00 CST -> 3:00 CDT)
    ev('eve', 'wins', 1, U(2027, 3, 14, 5, 59), 's1'); ev('eve', 'wins', 1, U(2027, 3, 14, 6, 1), 's2'); ev('eve', 'wins', 1, U(2027, 3, 15, 4, 59), 's3'); ev('eve', 'wins', 1, U(2027, 3, 15, 5, 1), 's4')
    chk('spring forward: day 13', val('wins', 'day', '2027-03-13', 'eve') == 1, board('wins', 'day', '2027-03-13'))
    chk('spring forward: day 14 holds two', val('wins', 'day', '2027-03-14', 'eve') == 2)
    chk('spring forward: day 15', val('wins', 'day', '2027-03-15', 'eve') == 1)
    # ---- same id applies once
    r1 = ev('amy', 'messages', 10, U(2026, 10, 22, 6), 'dup1'); r2 = ev('amy', 'messages', 10, U(2026, 10, 22, 6), 'dup1')
    chk('same id applies once', r1['applied'] and not r2['applied'] and val('messages', 'day', '2026-10-22', 'amy') == 11, (r1, r2))
    # ---- ranking, keys newest-first, total, me, bots left out
    for u, n in (('amy', 9), ('bob', 3), ('nightbot', 500), ('zed', 4)): ev(u, 'messages', n, U(2026, 10, 27, 17), 'rk-' + u)
    b = board('messages', 'day', '2026-10-27', 'bob')
    chk('ranking order', [x['login'] for x in b['rows']] == ['amy', 'zed', 'bob'], b['rows'])
    chk('bots are not ranked', all(x['login'] != 'nightbot' for x in b['rows']) and b['total'] == 3, b['total'])
    chk('me', b.get('me') == {'rank': 3, 'value': 3}, b.get('me'))
    chk('rows carry name and rank', all('name' in x and x['rank'] > 0 for x in b['rows']))
    ks = board('messages', 'day')['keys']; chk('keys newest first', ks == sorted(ks, reverse=True) and ks[0] == '2026-10-27', ks)
    chk('week keys are ISO', all('-W' in k for k in board('messages', 'week')['keys']))
    # ---- level (xp = 1 per minute watched + 2 per message): 300 minutes -> xp 300 -> level 3 at 40%
    ev('lia', 'watchtime', 300, U(2026, 10, 28, 17), 'lv1')
    lv = [x for x in board('level', 'day', '2026-10-28')['rows'] if x['login'] == 'lia'][0]
    chk('level value and pct', lv['value'] == 3 and lv['pct'] == 40.0, lv)
    # ---- grain: an old monthly total counts for the month and year, never a day or a week
    ev('old', 'watchtime', 600, U(2025, 6, 15, 12), 'g1', 'month')
    chk('grain month: in the month and year', val('watchtime', 'month', '2025-06', 'old') == 600 and val('watchtime', 'year', '2025', 'old') == 600)
    chk('grain month: not in a day', board('watchtime', 'day', '2025-06-15')['rows'] == [])
    # ---- the derived buckets are rebuildable: reload gives the same answers; the same lines written twice (a second backfill run) change nothing
    before = snap(); post('/api/boards/reload', {}); post('/api/boards/reload', {})
    chk('reload gives identical boards', before == snap())
    chk('a replayed id is still refused after a reload', not ev('amy', 'messages', 10, U(2026, 10, 22, 6), 'dup1')['applied'])
    f = os.path.join(d, 'boards', 'metric_events.jsonl'); txt = open(f).read(); open(f, 'a').write(txt); post('/api/boards/reload', {})
    chk('duplicate lines (re-run backfill) change nothing', snap() == before)
    # ---- chat: !top and the one-liners
    now = int(time.time()); ev('amy', 'messages', 4, now, 'c1'); ev('zed', 'messages', 2, now, 'c2'); ev('amy', 'watchtime', 90, now, 'c3'); ev('amy', 'points', 250, now, 'c4')
    def say(t):
        host.stdin.write((t + chr(10)).encode()); host.stdin.flush(); time.sleep(2.5)
    say('viewer1: !top messages day'); say('viewer2: !watchtime amy'); say('viewer3: !points amy')
    txt = open(out, 'rb').read().decode('utf-8', 'replace')
    chk('!top says the day board once', txt.count('Most chat messages today: 1. amy') == 1, txt[-600:])
    chk('!watchtime shows today / week / month', 'today 1h 30m, this week 1h 30m, this month 1h 30m' in txt, txt[-600:])
    chk('!points shows earned today / week / month', 'earned today 250, this week 250, this month 250' in txt, txt[-600:])
    # ---- Tools/rebuild-buckets.py: backfill from the old stores, twice, then a reload
    os.makedirs(os.path.join(d, 'boards'), exist_ok=True); os.makedirs(os.path.join(d, 'profiles'), exist_ok=True)
    json.dump([{'at': U(2025, 3, 3, 18), 'type': 'gift', 'user': 'fay', 'amount': 5, 'to': ''}, {'at': U(2025, 3, 4, 18), 'type': 'cheer', 'user': 'fay', 'amount': 300, 'to': ''}], open(os.path.join(d, 'boards', 'events.json'), 'w'))
    json.dump({'activity': {'perMonth': {'2025-03': 40}}}, open(os.path.join(d, 'profiles', 'fay.json'), 'w'))
    def backfill(): return subprocess.run([sys.executable, os.path.join(here, 'rebuild-buckets.py'), '--data', d, '--reload', B], capture_output=True, text=True).stdout
    o1 = backfill(); o2 = backfill()
    chk('backfill writes lines', 'writing 3 new event lines' in o1, o1)
    chk('backfill second run writes nothing', 'writing 0 new event lines' in o2, o2)
    chk('backfill: gift lands on its exact day', val('gifts', 'day', '2025-03-03', 'fay') == 5 and val('gifts', 'year', '2025', 'fay') == 5, board('gifts', 'day', '2025-03-03'))
    chk('backfill: bits', val('bits', 'month', '2025-03', 'fay') == 300)
    chk('backfill: month-only messages are in the month, not in a day', val('messages', 'month', '2025-03', 'fay') == 40 and board('messages', 'day', '2025-03-15')['rows'] == [])
    # ---- bad input, old shape
    chk('bad metric refused', board('nope', 'day').get('ok') is False)
    chk('bad period refused', get('/api/boards?metric=points&period=hour').get('ok') is False)
    chk('old /api/boards still answers', 'users' in get('/api/boards'))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS periods'); sys.exit(1 if fails else 0)
