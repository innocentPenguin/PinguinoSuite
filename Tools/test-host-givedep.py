"""Give limit (chat and site), tiered depreciation preview, public points pages and hide flag.  (Player-to-player loans through the site queue (request / offer / accept / decline / cancel / repay / default), limits, ledger rows for both sides, the checkbook activity view and the market push.
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-givedep.py [dll]"""
import re, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pggive_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); json.dump({'giveDailyPct': 100, 'giveDailyMax': 300}, open(os.path.join(d, 'economy', 'gambling.json'), 'w'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}, 'bob': {'points': 1000, 'minutes': 600}, 'cat': {'points': 500, 'minutes': 600}, 'whale': {'points': 300000, 'minutes': 9000}, 'huge': {'points': 2000000, 'minutes': 9000}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
S = {'reqs': {}, 'users': [], 'answers': []}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def auth(self):
        if self.headers.get('Authorization') != 'Bearer ' + KEY: self.send(401, {'error': 'unauthorized'}); return False
        return True
    def do_GET(self):
        if not self.auth(): return
        if self.path.startswith('/api/bot/economy/requests'): return self.send(200, {'requests': [r for r in S['reqs'].values() if r['status'] == 'pending']})
        self.send(404, {})
    def do_POST(self):
        if not self.auth(): return
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/bot/economy/users': S['users'].append(b); return self.send(200, {'ok': True})
        if self.path == '/api/bot/economy/answers':
            S['answers'].append(b); S['reqs'][b['id']]['status'] = 'answered'; return self.send(200, {'ok': True})
        self.send(404, {})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY, 'PINGUINO_SITE_POLL_SEC': '1', 'PINGUINO_ECONOMY_PUSH_SEC': '1', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '600'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def bal(u): return get('/api/economy/me?login=' + u)['balance']
def q(i, login, action, **kw):
    r = {'id': i, 'login': login, 'action': action, 'status': 'pending'}; r.update(kw); S['reqs'][i] = r
def ans(i, t=10):
    e = time.time() + t
    while time.time() < e:
        for a in S['answers']:
            if a['id'] == i: return a
        time.sleep(0.3)
    return {}
def post(p, o):
    r = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json'}); return json.load(urllib.request.urlopen(r, timeout=10))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    q('g1', 'bob', 'give', toLogin='zed', amount=100, note='thanks'); a = ans('g1')
    chk('site give works', a.get('status') == 'done' and a['data']['givenToday'] == 100 and a['data']['limit'] == 300 and bal('bob') == 900 and bal('zed') == 140, (a, bal('bob'), bal('zed')))
    q('g2', 'bob', 'give', toLogin='bob', amount=5); chk('no giving to yourself', ans('g2').get('status') == 'rejected', ans('g2'))
    q('g3', 'bob', 'give', toLogin='zed', amount=250); a = ans('g3'); chk('over the daily limit is refused with a clear reply', a.get('status') == 'rejected' and re.fullmatch(r'You can only give \d+% of your points per stream, you have 200 points left', a['message']), a)
    q('g4', 'bob', 'give', toLogin='zed', amount=200); chk('up to the limit is fine', ans('g4').get('status') == 'done' and bal('bob') == 700, ans('g4'))
    q('g5', 'bob', 'give', toLogin='zed', amount=1); a = ans('g5'); chk('then nothing more this stream', a.get('status') == 'rejected' and re.fullmatch(r'You can only give \d+% of your points per stream, you have 0 points left', a['message']), a)
    q('g6', 'amy', 'give', toLogin='zed', amount=50); chk('no giving more than you have', ans('g6').get('status') == 'rejected', ans('g6'))
    q('g7', 'zed', 'give', toLogin='cat', amount=0); chk('minimum 1', ans('g7').get('status') == 'rejected', ans('g7'))
    time.sleep(2)
    v = get('/api/economy/me?login=bob'); chk('view shows given today and the limit', v['giveToday'] == 300 and v['giveLimit'] == 300, (v.get('giveToday'), v.get('giveLimit')))
    z = get('/api/economy/me?login=zed'); chk('receiver activity says Received', any(x['label'].startswith('Received 100 from bob') for x in z['activity']), [x['label'] for x in z['activity']])
    chk('giver activity says Gave', any(x['label'].startswith('Gave 100 to zed') for x in v['activity']), [x['label'] for x in v['activity']])
    # chat !give shares the same limit
    host.stdin.write(('cat: !give zed 400' + chr(10)).encode()); host.stdin.flush(); time.sleep(2)
    chk('chat give over the limit is refused too', bal('cat') == 500, bal('cat'))
    # depreciation tiers (marginal bands)
    p = post('/api/economy/depreciation', {})
    rows = {r['login']: r for r in p['top']}
    chk('whale 300k: 150k at 1% + 50k at 2% = 2500', rows.get('whale', {}).get('loss') == 2500, rows.get('whale'))
    chk('huge 2M: 1500 + 5000 + 20000 + 60000 = 86500', rows.get('huge', {}).get('loss') == 86500, rows.get('huge'))
    chk('dry run stays on', p['dryRun'] is True)
    p = post('/api/economy/depreciation', {'DepreciationTiers': [{'from': 100000, 'to': 0, 'pct': 3}], 'DepreciationCap': 10000})
    rows = {r['login']: r for r in p['top']}
    chk('another table and a cap can be previewed', rows['whale']['loss'] == 6000 and rows['huge']['loss'] == 10000, rows)
    w = get('/api/economy/me?login=whale')['depreciation']
    chk('own projection only, no band table', w['perStream'] == 2500 and abs(w['effectivePct'] - 0.83) < 0.02 and 'tiers' not in w, w)
    # public pages
    pv = get('/api/economy/public?login=bob'); chk('public view has balance and activity, no loans', pv['ok'] and pv['balance'] == 700 and pv['activity'] and 'loans' not in pv and 'p2p' not in pv, list(pv.keys()))
    q('h1', 'bob', 'page_hide', hide=True); ans('h1')   # the hide feature was removed: the request is ignored and the page stays public
    pv = get('/api/economy/public?login=bob'); chk('hide request ignored: page still public', pv.get('ok') is True and 'hidden' not in pv, pv)
    chk('own view has no hidden field', 'hidden' not in get('/api/economy/me?login=bob'))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS givedep'); sys.exit(1 if fails else 0)
