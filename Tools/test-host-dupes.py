"""Never the same line twice: identical chat lines (any module) inside 30 s are sent once; different lines still go out; PINGUINO_DUP_SECONDS=0 turns it off.
Usage: python Tools/test-host-dupes.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8981; HX = 8982; B = 'http://127.0.0.1:%d' % PORT
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
d = tempfile.mkdtemp(prefix='pgdup_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def start(dup):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8983', 'PINGUINO_TIMERS_FAST': '1', 'PINGUINO_TIMERS_LIVE': '1'})
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
host = start(None)
try:
    api('/api/timers', {'globalGapSec': 0})
    api('/api/timers', {'timer': {'id': 'one', 'name': 'One', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': ['Same  Line!']}})
    api('/api/timers', {'timer': {'id': 'two', 'name': 'Two', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': ['same line!']}})
    time.sleep(5)
    chk('two timers + repeats of the same line (case/spacing differ) -> said once', len([m for m in chats if m.lower().replace(' ', '') == 'sameline!']) == 1, chats)
    api('/api/timers', {'id': 'one', 'enabled': False}); api('/api/timers', {'id': 'two', 'enabled': False})
    api('/api/timers', {'timer': {'id': 'three', 'name': 'Three', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': ['other line']}})
    time.sleep(2.5)
    chk('a different line still goes out', 'other line' in chats, chats)
    api('/api/timers', {'id': 'three', 'enabled': False})
    # ---- the newer send paths (Master View customs/mod, wheel POSTs, Suite !run) go through the same guard
    chats.clear()
    for _ in range(3): api('/api/customs/mod', {'action': 'queue', 'value': 'close'})
    time.sleep(1.5)
    closes = [m for m in chats if 'queue' in m.lower() and ('clos' in m.lower())]
    print('   customs/mod x3 chat lines:', closes)
    chk('customs/mod "queue close" x3 sends no repeated chat line (this harness has no Core, so it proves the endpoint adds none of its own)', len(closes) <= 1, closes)
    chats.clear()
    for _ in range(3): api('/api/wheel/new', {})
    time.sleep(1.5)
    chk('wheel/new x3 sends no repeated chat line (same limit: the Host adds none of its own)', len(chats) == len(set(m.lower().replace(' ', '') for m in chats)), chats)
    host.kill(); time.sleep(1); chats.clear()
    host = start('0')
    api('/api/timers', {'globalGapSec': 0})
    api('/api/timers', {'timer': {'id': 'four', 'name': 'Four', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': ['again']}})
    time.sleep(4.5)
    chk('PINGUINO_DUP_SECONDS=0 switches the guard off (test mode)', chats.count('again') >= 2, chats)
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
