"""Song-request refunds: a rejected redeem (refund:true) is CANCELED at once; an accepted one is remembered and refunded when the Spotify module's
/api/refunds lists it for that user; lastSeq is persisted and nothing is refunded twice.  Usage: python Tools/test-host-refunds.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, MOD = 8975, 8976, 8977
patches = []; state = {'refunds': [], 'reject': set()}
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_PATCH(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); patches.append((self.path, b))
        o = b'{"data":[{}]}'; self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
class Mod(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); since = int(q.get('since', ['0'])[0])
        self._j({'seq': max([r['seq'] for r in state['refunds']] or [0]), 'refunds': [r for r in state['refunds'] if r['seq'] > since]})
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}')
        if 'bad' in b.get('args', ''): self._j({'ok': False, 'refund': True, 'say': 'nope'})
        else: self._j({'ok': True, 'say': 'queued'})
for port, h in ((HX, Hx), (MOD, Mod)): threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', port), h).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgref_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'actions': [{'id': 'sr', 'name': 'SR', 'enabled': True, 'triggers': [{'type': 'redeem', 'title': 'Song Request'}], 'steps': [{'type': 'module_command', 'url': 'http://127.0.0.1:%d/api/chat-command' % MOD, 'command': 'sr', 'redeem': True}]}]}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_SPOTIFY_URL': 'http://127.0.0.1:%d' % MOD, 'PINGUINO_REFUND_POLL_SEC': '1', 'PINGUINO_COMPAT_WS_PORT': '8978'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def waitfor(f, s=10):
    for _ in range(s * 4):
        if f(): return True
        time.sleep(0.25)
    return False
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    feed('event TwitchRedeem alice bad_song', 2.0)
    chk('rejected redeem canceled at once', len(patches) == 1 and 'id=red-bad_song' in patches[0][0] and 'reward_id=rw1' in patches[0][0] and 'broadcaster_id=streamer1' in patches[0][0] and patches[0][1] == {'status': 'CANCELED'}, patches)
    feed('event TwitchRedeem bob good_song', 2.0)
    chk('accepted redeem not canceled', len(patches) == 1, patches)
    state['refunds'].append({'seq': 1, 'user': 'bob', 'song': 'good_song', 'why': 'skipped', 'ts': 1})
    chk('skipped song refunds bobs redeem', waitfor(lambda: len(patches) == 2) and 'id=red-good_song' in patches[1][0], patches)
    state['refunds'].append({'seq': 2, 'user': 'carol', 'song': 'x', 'why': 'removed', 'ts': 2})
    time.sleep(3)
    chk('unknown user refunds nothing', len(patches) == 2, patches)
    time.sleep(2)
    chk('no double refund', len(patches) == 2, patches)
    st = json.load(open(os.path.join(d, 'refund_state.json'))); chk('lastSeq persisted', st.get('lastSeq') == 2, st)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS refunds'); sys.exit(1 if fails else 0)
