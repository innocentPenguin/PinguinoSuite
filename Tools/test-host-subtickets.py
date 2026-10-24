"""Get a sub: buying spends points and makes a pending ticket; limits (one pending, monthly caps, cooldown); mods fulfil (!subdone) or refund (!subrefund / API); ships OFF.
Usage: python Tools/test-host-subtickets.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.environ.get('PGSUITE') or os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8984; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgst_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'adjust': {'alice': 5000, 'bob': 5000, 'carl': 5000, 'dina': 100}}, open(os.path.join(eco, 'points.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(eco, 'settings.json'), 'w'))
json.dump({'Enabled': True, 'ChatReplies': True, 'GameVoice': False}, open(os.path.join(d, 'chat_settings.json'), 'w'))   # Chatty voices game lines when GameVoice is on; this test reads the Host's plain line
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8985'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=1.0):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=10))
def bal(u): return get('/api/economy/user?login=' + u)['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('alice: !shop sub'); chk('off by default', 'not open' in ' '.join(r) and bal('alice') == 5000, r)
    st = get('/api/subtickets'); chk('shipped disabled', st['settings']['enabled'] is False and st['settings']['price'] == 0, st)
    post('/api/subtickets', {'action': 'settings', 'enabled': True, 'price': 2000, 'monthlyCapGlobal': 2})
    r = ask('alice: !shop'); chk('listed in !shop', 'Get a sub' in ' '.join(r) and '2,000' in ' '.join(r), r)
    r = ask('dina: !shop sub'); chk('not enough points', bal('dina') == 100 and len(get('/api/subtickets')['tickets']) == 0, r)
    r = ask('alice: !shop sub'); chk('bought', bal('alice') == 3000 and get('/api/subtickets')['pending'] == 1, (r, bal('alice')))
    chk('ping ivan', any('alice bought a sub' in x for x in says()), says())
    r = ask('alice: !shop sub'); chk('one pending per user', 'waiting' in ' '.join(r) and bal('alice') == 3000, r)
    ask('#ivan: !subdone alice')
    t = [x for x in get('/api/subtickets')['tickets'] if x['buyer'] == 'alice'][0]; chk('fulfilled', t['status'] == 'fulfilled' and t['by'], t)
    r = ask('alice: !shop sub'); chk('monthly cap per user', 'this month' in ' '.join(r) and bal('alice') == 3000, r)
    r = ask('bob: !shop sub'); chk('bob buys', bal('bob') == 3000, r)
    r = ask('carl: !shop sub'); chk('global monthly cap', 'taken' in ' '.join(r) and bal('carl') == 5000, r)
    r = ask('#ivan: !subowed'); chk('list owed', 'bob' in ' '.join(r) and 'alice' not in ' '.join(r), r)
    r = ask('bob: !subdone bob'); chk('viewer cannot fulfil', get('/api/subtickets')['pending'] == 1, r)
    r = post('/api/subtickets', {'action': 'refund', 'login': 'bob', 'by': 'suite'}); chk('refund via api', r['ok'] and bal('bob') == 5000, (r, bal('bob')))
    r = post('/api/subtickets', {'action': 'refund', 'login': 'bob'}); chk('no double refund', not r['ok'] and bal('bob') == 5000, r)
    rows = get('/api/economy/ledger?login=bob') if False else None
    r = ask('carl: !shop sub'); chk('refund frees the month slot', bal('carl') == 3000, (r, bal('carl')))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS subtickets'); sys.exit(1 if fails else 0)
