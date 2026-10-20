"""Sub footer: Twitch subscriber list (fake Helix, 2 pages) and the chat-seen list, tier order T3/T2/T1, filters, hide, pages. Usage: python Tools/test-host-subfooter.py [dll]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8911; FAKE = 8912; B = 'http://127.0.0.1:%d' % PORT
page1 = {'data': [{'user_id': '99', 'user_name': 'Streamer', 'tier': '1000'}, {'user_id': '1', 'user_name': 'Zed', 'tier': '1000'}, {'user_id': '2', 'user_name': 'amy', 'tier': '2000'}], 'pagination': {'cursor': 'c2'}}
page2 = {'data': [{'user_id': '3', 'user_name': 'Bob', 'tier': '3000'}, {'user_id': '4', 'user_name': 'Cat', 'tier': '1000'}, {'user_id': '5', 'user_name': 'Dan', 'tier': '3000'}], 'pagination': {}}
seen = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        seen.append(self.path); q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        b = json.dumps(page2 if q.get('after') == ['c2'] else page1).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
srv = HTTPServer(('127.0.0.1', FAKE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgfoot_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'faketoken', 'ClientId': 'cid', 'BroadcasterId': '99', 'SenderId': '99'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8913'; env['PINGUINO_HELIX_BASE'] = 'http://127.0.0.1:%d/helix' % FAKE
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body=None):
    rq = urllib.request.Request(B + p, data=json.dumps(body or {}).encode(), headers={'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def say(line): host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(0.3)
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    say('$1carl: hi'); say('$3dia: hi'); say('$2gold: hi'); say('viewer: not a sub')
    post('/api/subfooter/settings', {'Scope': 'chat'}); a = get('/api/subfooter')
    chk('chat scope: subs seen chatting, T3 first then T2 then T1', [(n['name'], n['tier']) for n in a['names']] == [('dia', 3), ('gold', 2), ('carl', 1)])
    post('/api/subfooter/settings', {'Scope': 'all'}); post('/api/subfooter/refresh'); time.sleep(2.5); a = get('/api/subfooter')
    names = [(n['name'], n['tier']) for n in a['names']]
    chk('twitch list: both pages read, broadcaster left out, T3 > T2 > T1, alphabetical inside a tier', names == [('Bob', 3), ('Dan', 3), ('amy', 2), ('Cat', 1), ('Zed', 1)])
    chk('the fake Helix was asked for the second page', any('after=c2' in p for p in seen))
    chk('counts are reported', a['counts'] == {'t1': 2, 't2': 1, 't3': 2})
    post('/api/subfooter/settings', {'ShowT1': False}); chk('tier 1 can be hidden', [n['tier'] for n in get('/api/subfooter')['names']] == [3, 3, 2])
    post('/api/subfooter/settings', {'ShowT1': True, 'MaxNames': 2}); chk('most-names cap', len(get('/api/subfooter')['names']) == 2)
    post('/api/subfooter/settings', {'MaxNames': 300, 'Enabled': False}); chk('hide switch is saved', get('/api/subfooter')['settings']['Enabled'] is False)
    post('/api/subfooter/settings', {'Enabled': True, 'Height': 90, 'FontSize': 40}); s = get('/api/subfooter')['settings']; chk('size is configurable', s['Height'] == 90 and s['FontSize'] == 40)
    chk('overlay and controls pages are served', b'/api/subfooter' in urllib.request.urlopen(B + '/overlay/subfooter', timeout=10).read() and b'Sub footer' in urllib.request.urlopen(B + '/subfooter', timeout=10).read())
finally:
    host.kill(); srv.shutdown()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
