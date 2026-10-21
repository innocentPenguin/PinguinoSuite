"""Replays: GET /api/replays, /api/replays/{id} (public-safe), /api/replays/proposals (roster-matched winner for a match with no winner) and POST /api/replays/apply (runs !matchwin).
Usage: python Tools/test-host-replays.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8982; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrep_'); lite = os.path.join(d, 'lite'); res = os.path.join(lite, 'replays', 'results'); os.makedirs(res)
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def pl(n, tw, **k): return dict({'name': n, 'platform': 'epic', 'twitch': tw, 'score': 100, 'goals': 1, 'assists': 0, 'saves': 1, 'shots': 2, 'bot': False, 'account_id': 'SECRET-ID', 'path': 'C:/secret'}, **k)
def rep(i, when, blue, orange, win, attributed=True):
    r = {'schema': 1, 'match_id': i, 'played_at': when, 'status': 'complete', 'team_size': len(blue), 'map': 'Stadium_P', 'duration_s': 300, 'blue': {'score': 3, 'players': blue}, 'orange': {'score': 1, 'players': orange},
         'winner': win if attributed else None, 'attributed': attributed, 'mvp': blue[0]['name'], 'source': 'lite-replay-v1', 'file': 'C:/Users/x/Demos/a.replay'}
    if not attributed: r['winner_detected'] = win
    json.dump(r, open(os.path.join(res, i + '.json'), 'w'))
rep('AAA111', '2026-10-21T15:00:00', [pl('Ann', 'ann'), pl('Ben', 'ben')], [pl('Cat', 'cat'), pl('Dan', 'dan')], 'blue')          # roster == match 7
rep('BBB222', '2026-10-21T16:00:00', [pl('Cat', 'cat'), pl('Dan', 'dan')], [pl('Ann', 'ann'), pl('Ben', 'ben')], 'blue', False)   # sides swapped, gate closed -> winner_detected
rep('CCC333', '2026-10-21T17:00:00', [pl('Ann', 'ann'), pl('Zed', None)], [pl('Cat', 'cat'), pl('Dan', 'dan')], 'blue')         # unknown twitch name: never proposed
rep('DDD444', '2026-10-21T18:00:00', [pl('Eve', 'eve'), pl('Fay', 'fay')], [pl('Gus', 'gus'), pl('Hal', 'hal')], 'orange')       # no such match
now = int(time.time())
def match(i, w): return {'Id': i, 'Format': '2v2', 'Mode': 'random', 'CreatedAt': now - 3600, 'FinishedAt': now - 3000, 'Winner': w, 'Blue': [{'Username': 'ann'}, {'Username': 'ben'}], 'Orange': [{'Username': 'cat'}, {'Username': 'dan'}]}
for sub in ('', 'runtime'):
    os.makedirs(os.path.join(d, sub), exist_ok=True); json.dump([match(7, None), match(8, 'Blue')], open(os.path.join(d, sub, 'matches.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983', 'PINGUINO_LITE_DIR': lite})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=10))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    r = get('/api/replays'); chk('list', r['ok'] and r['count'] == 4 and [i['id'] for i in r['items']][0] == 'DDD444', r)
    txt = json.dumps(r); chk('no paths or account ids leak', 'SECRET' not in txt and 'Demos' not in txt and 'C:/' not in txt, txt[:200])
    chk('limit', get('/api/replays?limit=2')['count'] == 2)
    o = get('/api/replays/AAA111'); chk('one replay', o['ok'] and o['replay']['blue']['players'][0]['twitch'] == 'ann' and o['replay']['winner'] == 'blue' and 'SECRET' not in json.dumps(o), o)
    chk('unknown id', get('/api/replays/nope')['ok'] is False); chk('bad id rejected', get('/api/replays/..%5Cx')['ok'] is False)
    pr = get('/api/replays/proposals')['proposals']; ids = sorted((p['replayId'], p['matchId'], p['winner']) for p in pr)
    chk('proposals: exact roster only, sides mapped, unknown-name replay skipped', ids == [('AAA111', 7, 'blue'), ('BBB222', 7, 'orange')], ids)
    bad = post('/api/replays/apply', {'matchId': 8, 'replayId': 'AAA111'}); chk('apply rejects a match that is not proposed', bad['ok'] is False, bad)
    chk('nothing applied by itself', all(m['Winner'] in (None, 'Blue') for m in json.load(open(os.path.join(d, 'runtime', 'matches.json')))))
    ok = post('/api/replays/apply', {'matchId': 7, 'replayId': 'AAA111', 'by': 'ivan'}); chk('apply ok', ok['ok'] and ok['winner'] == 'blue', ok); time.sleep(2)
    got = {}
    for sub in ('', 'runtime'):
        try: got[sub] = [m for m in json.load(open(os.path.join(d, sub, 'matches.json'))) if m['Id'] == 7][0]['Winner']
        except Exception as e: got[sub] = str(e)
    chk('winner written to matches.json', any(str(v).lower() == 'blue' for v in got.values()), got)
    chk('no longer proposed', not any(p['matchId'] == 7 for p in get('/api/replays/proposals')['proposals']))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS replays'); sys.exit(1 if fails else 0)
