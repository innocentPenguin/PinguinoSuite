"""Lifetime baseline for the "all" and current-year boards: Data/boards/totals.json holds lifetime figures, the event log only started later, so "all" used to equal the month.
The first time both exist Data/boards/period_baseline.json is written (total minus what the buckets already hold) and every later "all"/year figure is baseline + events, never counted twice;
a reload and a restart give the same numbers; month/week/day stay events only. Usage: python Tools/test-host-periodbase.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSPORT = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgpb_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); os.makedirs(os.path.join(d, 'boards'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
def U(n, w, m, g, b, p): return {'name': n, 'gifts': g, 'bits': b, 'messages': m, 'points': p, 'watchMinutes': w}
TOT = {'ok': True, 'users': {'amy': U('amy', 5000, 900, 4, 100, 300), 'bob': U('bob', 200, 50, 0, 0, 10), 'cy': U('cy', 30, 0, 0, 0, 0), 'dee': U('dee', 100, 10, 0, 0, 5), 'deeold': U('deeold', 40, 7, 0, 0, 3)}}
json.dump({'aliases': {'deeold': 'dee'}}, open(os.path.join(d, 'boards', 'aliases.json'), 'w'))   # two raw rows of one person in the snapshot
json.dump(TOT, open(os.path.join(d, 'boards', 'totals.json'), 'w'))
open(os.path.join(d, 'boards', 'metric_events.jsonl'), 'w').write(json.dumps({'ts': int(time.time()) - 60, 'user': 'cy', 'metric': 'watchtime', 'amount': 10, 'id': 'old1'}) + chr(10))   # already in the log (and in cy's total) when the baseline is made
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_ECONOMY_TESTHOOK': '1', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p):
    try: return json.load(urllib.request.urlopen(B + p, timeout=10))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def post(p, o):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=10))
def val(metric, period, user, key=''):
    r = [x for x in get('/api/boards?metric=%s&period=%s&key=%s' % (metric, period, key))['rows'] if x['login'] == user]; return r[0]['value'] if r else 0
def start():
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2); return h
host = start()
try:
    now = int(time.time())
    # events that come AFTER the snapshot add on top of it
    post('/api/boards/event', {'user': 'amy', 'metric': 'watchtime', 'amount': 100, 'ts': now, 'id': 'e1'})
    post('/api/boards/event', {'user': 'bob', 'metric': 'watchtime', 'amount': 20, 'ts': now, 'id': 'e2'})
    post('/api/boards/event', {'user': 'amy', 'metric': 'messages', 'amount': 10, 'ts': now, 'id': 'e3'})
    bp = os.path.join(d, 'boards', 'period_baseline.json')
    for _ in range(10):
        if os.path.exists(bp): break
        get('/api/boards?metric=watchtime&period=all'); time.sleep(0.5)
    chk('baseline file written', os.path.exists(bp))
    bm = json.load(open(bp))['metrics']
    chk('two raw alias rows of one person SUM in the baseline (watchtime 100+40, messages 10+7, points 5+3), not last-row-wins', bm['watchtime'].get('dee') == 140 and bm['messages'].get('dee') == 17 and bm['points'].get('dee') == 8 and 'deeold' not in bm['watchtime'], bm['watchtime'])
    tot = json.load(open(os.path.join(d, 'boards', 'totals.json')))['users']
    a, m = val('watchtime', 'all', 'amy'), val('watchtime', 'month', 'amy')
    chk('month is events only, all time is far above it', m == 100 and a > m, (a, m))
    chk('all time = lifetime total (5000) + the events after it; cy: the 10 min already in the log are not counted twice', a == 5000 + 100 and val('watchtime', 'all', 'cy') == 30, (a, val('watchtime', 'all', 'cy')))
    ykey = get('/api/boards?metric=watchtime&period=year')['key']
    chk('the current year gets the baseline too', val('watchtime', 'year', 'amy', ykey) == a, (ykey, val('watchtime', 'year', 'amy', ykey), a))
    chk('week and day stay events only', val('watchtime', 'week', 'amy') == 100 and val('watchtime', 'day', 'amy') == 100)
    chk('messages baseline', val('messages', 'all', 'amy') == 910 and val('messages', 'month', 'amy') == 10, (val('messages', 'all', 'amy'), tot['amy']['messages']))
    chk('gifts and bits baseline', val('gifts', 'all', 'amy') == 4 and val('bits', 'all', 'amy') == 100, (val('gifts', 'all', 'amy'), val('bits', 'all', 'amy')))
    rows = get('/api/boards?metric=watchtime&period=all&login=bob')
    chk('ranking and the me row use the lifetime figures', rows['rows'][0]['login'] == 'amy' and rows['me']['rank'] == 2 and rows['me']['value'] == 220 and rows['total'] == 4, rows)
    post('/api/boards/event', {'user': 'amy', 'metric': 'watchtime', 'amount': 5, 'ts': now, 'id': 'e4'}); a2 = val('watchtime', 'all', 'amy')
    chk('a later event adds on top, once', a2 == a + 5, (a, a2))
    post('/api/boards/event', {'user': 'amy', 'metric': 'watchtime', 'amount': 5, 'ts': now, 'id': 'e4'}); chk('same id counts once', val('watchtime', 'all', 'amy') == a2)
    try: post('/api/boards/reload', {})
    except Exception: pass
    chk('reload gives the same numbers', val('watchtime', 'all', 'amy') == a2, val('watchtime', 'all', 'amy'))
    host.kill(); host.wait(); host = start()
    chk('restart gives the same numbers', val('watchtime', 'all', 'amy') == a2, val('watchtime', 'all', 'amy'))
    chk('baseline file is the kept snapshot', json.load(open(bp))['metrics']['watchtime']['amy'] > 0)
finally:
    host.kill(); time.sleep(0.5); print(open(out, 'rb').read().decode('utf-8', 'replace')[-1200:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS periodbase'); sys.exit(1 if fails else 0)
