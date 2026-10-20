"""Hype train + channel goal announcements (start/finish only, once each, switchable).
Usage: python Tools/test-host-announce.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8985; HX = 8986; B = 'http://127.0.0.1:%d' % PORT
chats = []
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}')
        if self.path.endswith('/chat/messages'): chats.append(b.get('message', ''))
        self._send({'data': [{'is_sent': True}]})
    def do_GET(self): self._send({'data': []})
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgann_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def start(dup):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8987', 'PINGUINO_TIMERS_FAST': '1', 'PINGUINO_TIMERS_LIVE': '1'})
    if dup is not None: env['PINGUINO_DUP_SECONDS'] = dup
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra, chats[-6:])
def ev(t, o, wait=0.7): host.stdin.write(('eventsub ' + t + ' ' + json.dumps(o) + chr(10)).encode()); host.stdin.flush(); time.sleep(wait)
host = start(None)
try:
    time.sleep(1)
    ev('channel.hype_train.begin', {'id': 'h1', 'level': 1, 'total': 300, 'goal': 500})
    ev('channel.hype_train.progress', {'id': 'h1', 'level': 2, 'total': 900, 'goal': 1500})
    chk('hype begin is announced once, progress is silent', len(chats) == 1 and 'Hype train started' in chats[0], chats)
    ev('channel.hype_train.end', {'id': 'h1', 'level': 3, 'total': 2500, 'top_contributions': [{'user_login': 'small', 'user_name': 'Small', 'type': 'bits', 'total': 100}, {'user_login': 'big', 'user_name': 'BigGifter', 'type': 'subscription', 'total': 900}]})
    chk('hype end names the level and the top contributor', len(chats) == 2 and 'level 3' in chats[1] and '@BigGifter' in chats[1], chats)
    ev('channel.hype_train.end', {'id': 'h1', 'level': 3, 'total': 2500, 'top_contributions': []})
    chk('the same hype train is not announced twice', len(chats) == 2, chats)
    ev('channel.goal.begin', {'id': 'g1', 'type': 'follow', 'description': '1000 followers', 'current_amount': 900, 'target_amount': 1000, 'is_achieved': False})
    ev('channel.goal.progress', {'id': 'g1', 'type': 'follow', 'description': '1000 followers', 'current_amount': 990, 'target_amount': 1000, 'is_achieved': False})
    chk('goal start and progress are silent', len(chats) == 2, chats)
    ev('channel.goal.end', {'id': 'g1', 'type': 'follow', 'description': '1000 followers', 'current_amount': 1000, 'target_amount': 1000, 'is_achieved': True})
    chk('a reached goal is announced with its description', len(chats) == 3 and 'goal reached' in chats[2].lower() and '1000 followers' in chats[2], chats)
    ev('channel.goal.end', {'id': 'g2', 'type': 'sub', 'description': '50 subs', 'current_amount': 20, 'target_amount': 50, 'is_achieved': False})
    chk('an unreached goal gets the ended line', len(chats) == 4 and '20/50' in chats[3], chats)
    st = json.load(open(os.path.join(d, 'announce.json'))); st['HypeOn'] = False; json.dump(st, open(os.path.join(d, 'announce.json'), 'w'))
    ev('channel.hype_train.begin', {'id': 'h2', 'level': 1, 'total': 300, 'goal': 500})
    chk('HypeOn=false silences hype train lines', len(chats) == 4, chats)
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
