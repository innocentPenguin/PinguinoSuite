"""Points rules: match awards at the v2 rate (7 minutes of the player's own watch rate x2 to play, x3 to win; one payment per match id), the points-settings API
(ranges, dry run, hot save) and POST /api/economy/event answering paid / already / refused.  Usage: python Tools/test-host-points.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT = _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgpts_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'runtime')); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0, 'DepreciationTiers': []}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
now = int(time.time())
def P(*n): return [{'Username': x} for x in n]
json.dump([{'Id': 1, 'Format': '2v2', 'Activity': 'competitive', 'Blue': P('ann', 'ben'), 'Orange': P('cat', 'nightbot'), 'Winner': 'Blue', 'FinishedAt': now - 99},
           {'Id': 2, 'Format': '2v2', 'Activity': 'casual', 'Blue': P('ann', 'dan'), 'Orange': P('eve', 'fay'), 'Winner': 'Orange', 'FinishedAt': now - 90}], open(os.path.join(d, 'runtime', 'matches.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(_free()), 'PINGUINO_ECONOMY_TESTHOOK': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '1', 'PINGUINO_ECONOMY_AWARD_FROM': '0', 'PINGUINO_ECONOMY_GRACE_SEC': '0', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1'})   # v2 stays on
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    try: return json.load(urllib.request.urlopen(rq, timeout=10))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def bal(u): return get('/api/economy/me?login=' + u)['balance']
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(240):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
    # viewer rate 10 per 5 min = 2/min; 7 min x2 = 28 to play, x3 = 42 to win
    chk('comp play + win at the v2 rate', bal('ann') == 98 and bal('ben') == 70 and bal('cat') == 28, (bal('ann'), bal('ben'), bal('cat')))
    chk('casual: loser plays, winners win', bal('eve') == 70 and bal('fay') == 70 and bal('dan') == 28, (bal('eve'), bal('fay'), bal('dan')))
    chk('bots earn nothing', bal('nightbot') == 0)
    time.sleep(3); chk('rescan pays nothing twice', bal('ann') == 98, bal('ann'))
    # ---- settings API
    s = get('/api/economy/points-settings'); chk('GET lists the keys', s['ok'] and s['values']['MatchMinutes'] == 7 and s['values']['MatchPlayMult'] == 2 and 'examples' in s, s.get('values'))
    for k, v in [('MatchMinutes', 0), ('MatchMinutes', 500), ('MatchWinMult', -1), ('WatchIntervalMin', 'x'), ('Bogus', 1), ('WatchV2', 1), ('TipCurve', [[5, 100], [1, 50]]), ('TipCurve', 'no')]:
        r = post('/api/economy/points-settings', {'values': {k: v}}); chk('rejects %s=%r' % (k, v), r.get('ok') is False and r.get('error'), r)
    r = post('/api/economy/points-settings', {'values': {'MatchMinutes': 14}, 'dry': True}); chk('dry run saves nothing', r['ok'] and get('/api/economy/points-settings')['values']['MatchMinutes'] == 7, r)
    r = post('/api/economy/points-settings', {'values': {'MatchMinutes': 14, 'MatchWinMult': 4, 'TipCurve': [[1, 1000], [10, 15000]]}}); chk('valid save', r['ok'] and r['values']['MatchMinutes'] == 14 and r['values']['MatchWinMult'] == 4, r)
    chk('saved settings are read back', get('/api/economy/points-settings')['values']['MatchMinutes'] == 14)
    # ---- event route answers
    r = post('/api/economy/event', {'type': 'tip', 'login': 'zoe', 'amount': 1, 'id': 'pt-t1'}); chk('tip paid', r['ok'] and r['paid'] and not r['already'], r)
    r = post('/api/economy/event', {'type': 'tip', 'login': 'zoe', 'amount': 1, 'id': 'pt-t1'}); chk('same tip id: ok, not paid again', r['ok'] and not r['paid'] and r['already'], r)
    r = post('/api/economy/event', {'type': 'resub', 'login': 'zoe', 'tier': '1', 'amount': 1, 'id': 'pt-r1'}); chk('resub paid', r['ok'] and r['paid'], r)
    r = post('/api/economy/event', {'type': 'gift', 'login': 'ananonymousgifter', 'amount': 5, 'id': 'pt-g1'}); chk('system account: ok false, not paid', r['ok'] is False and r['paid'] is False and r['error'], r)
    r = post('/api/economy/event', {'type': 'cheer', 'login': 'nightbot', 'amount': 100, 'id': 'pt-c1'}); chk('bot: ok false', r['ok'] is False and r['paid'] is False, r)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS points'); sys.exit(1 if fails else 0)
