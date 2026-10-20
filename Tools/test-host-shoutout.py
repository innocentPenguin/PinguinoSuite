"""Shoutout queue: temp chat line right away, native Twitch card after a random 1-5 s delay and the 2-minute gap, same target once per hour.
Usage: python Tools/test-host-shoutout.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8985; HX = 8986; B = 'http://127.0.0.1:%d' % PORT
posts = []; chats = []; t0 = time.time()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode() if o is not None else b''
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.endswith('/users'):
            lg = q.get('login', [''])[0]; self._send({'data': [{'id': 'id_' + lg, 'login': lg}]})
        elif u.path.endswith('/channels'):
            bid = q.get('broadcaster_id', [''])[0]; lg = bid[3:]; self._send({'data': [{'broadcaster_login': lg, 'broadcaster_name': lg.capitalize(), 'game_name': 'Rocket League'}]})
        else: self._send({'data': []})
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.endswith('/chats/shoutouts'):
            q = urllib.parse.parse_qs(u.query); posts.append((time.time() - t0, q.get('to_broadcaster_id', [''])[0], q.get('moderator_id', [''])[0], q.get('from_broadcaster_id', [''])[0])); self._send(None, 204)
        elif u.path.endswith('/chat/messages'):
            n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); chats.append((time.time() - t0, b.get('message', ''))); self._send({'data': [{'is_sent': True}]})
        else: self._send({'data': []})
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgshout_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'NativeGapSec': 3, 'NativeDelayMinSec': 1, 'NativeDelayMaxSec': 2}, open(os.path.join(d, 'shout_settings.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_HELIX_BASE'] = 'http://127.0.0.1:%d' % HX; env['PINGUINO_COMPAT_WS_PORT'] = '8987'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def says(): return [m for _, m in chats]
res = []
def chk(n, ok):
    res.append((n, bool(ok)))
    if not ok: print('   says:', says(), 'posts:', posts)
try:
    for _ in range(60):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    ts = time.time() - t0
    r = api('/api/shoutouts', {'user': 'alpha', 'by': 'mod'}); chk('queued', r.get('result') == 'queued')
    time.sleep(0.6); s1 = says()
    chk('temp line posted immediately, before any card', any('Shoutout queued, in the meantime please check out Alpha at https://twitch.tv/alpha. Last playing Rocket League' in x for x in s1) and not posts)
    time.sleep(2.2)
    chk('the card went out after the 1-2 s delay, from the streamer account', len(posts) == 1 and posts[0][1] == 'id_alpha' and posts[0][2] == 'streamer1' and posts[0][3] == 'streamer1' and posts[0][0] - ts >= 0.9)
    chk('no second chat line after a successful card', len([x for x in says() if 'alpha' in x.lower()]) == 1)
    r = api('/api/shoutouts', {'user': 'beta', 'by': 'mod'}); time.sleep(0.6)
    chk('the second temp line is also immediate', any('check out Beta' in x for x in says()))
    time.sleep(6.5)
    chk('the second card waits for the gap (>= 3 s after the first)', len(posts) == 2 and posts[1][0] - posts[0][0] >= 3.0, )
    api('/api/shoutouts', {'user': 'alpha', 'by': 'raid'})   # manual window is 2 min: duplicate
    chk('same streamer inside the dedupe window is a duplicate', len(posts) == 2)
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
