"""Suite tuning API: GET/POST /api/tune (validate, clamp, unknown key, null clears maxBet), /api/gamble/simulate (no points move), /api/economy/grant (silent, audited, negative takes, idempotent id).
Usage: python Tools/test-host-tune.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8996; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgtn_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'adjust': {'alice': 1000, 'bob': 500}}, open(os.path.join(eco, 'points.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8998'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    r = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(r, timeout=10))
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def bal(u): return get('/api/economy/user?login=' + u)['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    t = get('/api/tune'); ids = [a['id'] for a in t['areas']]
    chk('areas', ids == ['wheel', 'queue', 'gambling', 'economy', 'alias'], ids)
    f = {a['id']: {x['key']: x for x in a['fields']} for a in t['areas']}
    chk('wheel field shape', f['wheel']['spinSpeed']['type'] == 'number' and f['wheel']['spinSpeed']['min'] == 1500 and f['wheel']['mode']['options'] == ['random', 'balanced'], f['wheel']['spinSpeed'])
    chk('maxBet optional + empty', f['gambling']['maxBet'].get('optional') and f['gambling']['maxBet']['value'] is None, f['gambling']['maxBet'])
    r = post('/api/tune', {'area': 'gambling', 'values': {'winChance': 5, 'payout': 3, 'cooldownSec': 7}})
    chk('clamped', r['ok'] and r['applied']['winChance'] == 1 and r['applied']['payout'] == 3, r)
    r = post('/api/tune', {'area': 'gambling', 'values': {'maxBet': 250}}); chk('max bet set', r['ok'], r)
    chk('read back', {x['key']: x['value'] for x in get('/api/tune')['areas'][2]['fields']}['maxBet'] == 250)
    r = post('/api/tune', {'area': 'gambling', 'values': {'maxBet': None}}); chk('null clears maxBet', r['ok'] and get('/api/tune')['areas'][2]['fields'][7]['value'] is None, r)
    r = post('/api/tune', {'area': 'gambling', 'values': {'nope': 1, 'winChance': 'abc', 'minBet': None}})
    chk('errors', not r['ok'] and set(r['errors']) == {'nope', 'winChance', 'minBet'}, r)
    r = post('/api/tune', {'area': 'nothing', 'values': {}}); chk('unknown area', not r['ok'], r)
    r = post('/api/tune', {'area': 'economy', 'values': {'PointsPerMinute': 2.5, 'OnlyWhileLive': False}}); chk('economy applied', r['ok'] and get('/api/economy')['settings']['PointsPerMinute'] == 2.5, r)
    r = post('/api/tune', {'area': 'alias', 'values': {'didYouMean': False}}); chk('alias', r['ok'] and not {x['key']: x['value'] for x in get('/api/tune')['areas'][4]['fields']}['didYouMean'], r)
    r = post('/api/tune', {'area': 'wheel', 'values': {'spinSpeed': 99999, 'mode': 'weird', 'joinFeedSec': 1.5}})
    chk('wheel validation', set(r['errors']) == {'mode'} and r['applied']['spinSpeed'] == 30000 and r['applied']['joinFeedSec'] == 1.5, r)
    r = post('/api/gamble/simulate', {'game': 'gamble', 'bet': 100, 'rounds': 500}); b0 = bal('alice')
    chk('simulate', r['ok'] and r['wins'] + r['losses'] == 500 and len(r['sample']) == 10 and 'avgPayout' in r and bal('alice') == b0, r)
    r = post('/api/gamble/simulate', {'game': 'dice'}); chk('simulate bad game', not r['ok'], r)
    n0 = len(says())
    r = post('/api/economy/grant', {'target': 'user', 'login': 'alice', 'amount': 50, 'reason': 'test', 'silent': True, 'id': 'g1'})
    chk('grant user', r['ok'] and r['affected'] == 1 and bal('alice') == 1050, (r, bal('alice')))
    post('/api/economy/grant', {'target': 'user', 'login': 'alice', 'amount': 50, 'id': 'g1'}); chk('grant id idempotent', bal('alice') == 1050, bal('alice'))
    r = post('/api/economy/grant', {'target': 'user', 'login': 'bob', 'amount': -100, 'reason': 'take'}); chk('grant negative takes', bal('bob') == 400, bal('bob'))
    r = post('/api/economy/grant', {'target': 'everyone', 'amount': 10, 'reason': 'all'}); chk('grant everyone', r['ok'] and r['affected'] >= 2 and bal('alice') == 1060 and bal('bob') == 410, (r, bal('alice'), bal('bob')))
    chk('grant silent in chat', len(says()) == n0, says()[n0:])
    log = open(os.path.join(eco, 'grants.log'), encoding='utf-8').read(); chk('audit log', 'test' in log and 'take' in log and 'everyone' in log, log)
    chk('bad amount', not post('/api/economy/grant', {'target': 'user', 'login': 'alice', 'amount': 0})['ok'])
    h.stdin.write(b'*mod1: !pgrant @alice 5 hidden\n'); h.stdin.flush(); time.sleep(1.2)
    chk('hidden command works, says nothing', bal('alice') == 1065 and len(says()) == n0, (bal('alice'), says()[n0:]))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS tune'); sys.exit(1 if fails else 0)
