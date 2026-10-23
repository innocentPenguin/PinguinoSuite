"""Mod audit log: the site's entries are polled and appended (once), the Host's own actions are logged, pushed to the site, rotated and readable.  (Player-to-player loans through the site queue (request / offer / accept / decline / cancel / repay / default), limits, ledger rows for both sides, the checkbook activity view and the market push.
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-modaudit.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pgaudit_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); json.dump({'giveDailyMax': 300}, open(os.path.join(d, 'economy', 'gambling.json'), 'w'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}, 'bob': {'points': 1000, 'minutes': 600}, 'cat': {'points': 500, 'minutes': 600}, 'whale': {'points': 300000, 'minutes': 9000}, 'huge': {'points': 2000000, 'minutes': 9000}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
S = {'entries': [{'seq': i, 'at': 1000 + i, 'who': 'mod%d' % i, 'role': 'mod', 'action': 'user/ban', 'target': 'x%d' % i, 'before': '', 'after': 'banned', 'page': 'users'} for i in (1, 2, 3)], 'pushed': []}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.headers.get('Authorization') != 'Bearer ' + KEY: return self.send(401, {})
        if self.path.startswith('/api/bot/modaudit'):
            after = int(self.path.split('after=')[1].split('&')[0]); return self.send(200, {'entries': [e for e in S['entries'] if e['seq'] > after]})
        self.send(200, {'requests': []})
    def do_POST(self):
        if self.headers.get('Authorization') != 'Bearer ' + KEY: return self.send(401, {})
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/bot/modaudit': S['pushed'] += b['entries']; return self.send(200, {'ok': True})
        self.send(200, {'ok': True})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY, 'PINGUINO_SITE_POLL_SEC': '1', 'PINGUINO_MODAUDIT_MAXBYTES': '3000'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    r = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json'})
    try: return json.load(urllib.request.urlopen(r, timeout=10))
    except Exception as e: return {'err': str(e)}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(14)
    e = get('/api/modaudit?limit=50')['entries']
    chk('site entries were pulled once each, newest first', [x['seq'] for x in e if x['src'] == 'site'] == [3, 2, 1], e)
    chk('entry shape', all(k in e[0] for k in ('id', 'at', 'who', 'role', 'action', 'target', 'before', 'after', 'page', 'src')), e[0])
    post('/api/channel/update', {'title': 'new title'}); time.sleep(4)
    e = get('/api/modaudit?limit=50')['entries']; hs = [x for x in e if x['src'] == 'host']
    chk('host action logged', len(hs) == 1 and hs[0]['action'] == 'channel/update' and hs[0]['page'] == 'host', hs)
    chk('and pushed to the site', len(S['pushed']) == 1 and S['pushed'][0]['page'] == 'host' and S['pushed'][0]['action'] == 'channel/update', S['pushed'])
    S['entries'].append({'seq': 4, 'at': 2000, 'who': 'o', 'role': 'owner', 'action': 'settings', 'target': 't', 'before': 'a', 'after': 'b', 'page': 'settings'}); time.sleep(3)
    e = get('/api/modaudit?limit=50')['entries']
    chk('a new site entry arrives, none twice', [x['seq'] for x in e if x['src'] == 'site'] == [4, 3, 2, 1], [x['id'] for x in e])
    for i in range(30): post('/api/channel/update', {'title': 'bulk title number %d with some padding text to grow the file' % i})
    time.sleep(3)
    p = os.path.join(d, 'runtime'); names = os.listdir(p)
    chk('file rotates when big', any(n.startswith('mod_audit.jsonl.') for n in names), names)
    chk('read pages with before', len(get('/api/modaudit?limit=5')['entries']) == 5)
    page1 = get('/api/modaudit?limit=5')['entries']; page2 = get('/api/modaudit?limit=5&before=' + page1[-1]['id'])['entries']
    chk('paging continues after the last id', page2 and page2[0]['id'] != page1[-1]['id'] and not ({x['id'] for x in page1} & {x['id'] for x in page2}), (page1, page2))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS modaudit'); sys.exit(1 if fails else 0)
