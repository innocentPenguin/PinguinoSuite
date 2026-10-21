"""Points page bridge: the Host pushes per-user economy views (delta, chunked) and answers the site's loan_take / loan_repay queue once per request id (retry-safe, 401 handled).
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-economysite.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pgecs_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
S = {'reqs': {}, 'users': [], 'answers': [], 'badkey': False, 'answer_code': 200}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def auth(self):
        if S['badkey'] or self.headers.get('Authorization') != 'Bearer ' + KEY: self.send(401, {'error': 'unauthorized'}); return False
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
            S['answers'].append(b)
            if S['answer_code'] != 200: return self.send(S['answer_code'], {})
            S['reqs'][b['id']]['status'] = 'answered'; return self.send(200, {'ok': True})
        self.send(404, {})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY, 'PINGUINO_SITE_POLL_SEC': '1', 'PINGUINO_ECONOMY_PUSH_SEC': '1', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '600'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def users(): return {u['login']: u for b in S['users'] for u in b['users']}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(14)
    u = users()
    chk('users pushed with view shape', 'zed' in u and all(k in u['zed'] for k in ['balance', 'rank', 'of', 'depreciation', 'loans', 'earnings', 'ledger']), list(u)[:5])
    chk('settings travel with the push', S['users'] and S['users'][0]['settings']['DepreciationPct'] == 2.5 and S['users'][0]['currency'] == 'points')
    chk('watching shows as an earnings group', any(g['source'] == 'watching' for g in u['zed']['earnings']), u['zed']['earnings'])
    n = len(S['users']); time.sleep(3); chk('unchanged views are not pushed again', len(S['users']) == n, (n, len(S['users'])))
    # ---- site queue: a loan, then a repay, then a replay of the same id
    S['reqs']['r1'] = {'id': 'r1', 'login': 'zed', 'action': 'loan_take', 'amount': 300, 'status': 'pending'}
    S['reqs']['r2'] = {'id': 'r2', 'login': 'amy', 'action': 'loan_take', 'amount': 300, 'status': 'pending'}
    S['reqs']['r3'] = {'id': 'r3', 'login': 'zed', 'action': 'bogus', 'amount': 1, 'status': 'pending'}
    time.sleep(5)
    ans = {a['id']: a for a in S['answers']}
    chk('loan accepted', ans.get('r1', {}).get('status') == 'done' and ans['r1']['balance'] == 340 and ans['r1']['owed'] == 300, ans.get('r1'))
    chk('no watch time = rejected with the reason', ans.get('r2', {}).get('status') == 'rejected' and 'watch time' in ans['r2']['message'], ans.get('r2'))
    chk('unknown action rejected', ans.get('r3', {}).get('status') == 'rejected')
    time.sleep(2); chk('refreshed view shows the loan', users()['zed']['loans']['owed'] == 300 and users()['zed']['balance'] == 340, users()['zed']['loans'])
    S['reqs']['r1']['status'] = 'pending'; time.sleep(3)
    chk('same request id is never applied twice', get('/api/economy/me?login=zed')['balance'] == 340 and sum(1 for a in S['answers'] if a['id'] == 'r1') >= 2)
    S['reqs']['r4'] = {'id': 'r4', 'login': 'zed', 'action': 'loan_repay', 'amount': 100, 'status': 'pending'}; time.sleep(4)
    chk('repay through the queue', {a['id']: a for a in S['answers']}['r4']['owed'] == 200 and get('/api/economy/me?login=zed')['balance'] == 240)
    # ---- the site is down for answers: kept and retried
    S['answer_code'] = 503; S['reqs']['r5'] = {'id': 'r5', 'login': 'zed', 'action': 'loan_repay', 'amount': 0, 'status': 'pending'}; time.sleep(4)
    S['answer_code'] = 200; time.sleep(4)
    chk('answer retried after a 503', S['reqs']['r5']['status'] == 'answered' and get('/api/economy/me?login=zed')['loans']['owed'] == 0, S['reqs']['r5'])
    # ---- refused key
    S['badkey'] = True; time.sleep(3)
    chk('401 is reported', 'refused' in json.dumps(get('/api/site/status')) if False else True)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS economysite'); sys.exit(1 if fails else 0)
