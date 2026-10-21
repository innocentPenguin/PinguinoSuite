"""Website bridge long poll: Core asks GET /api/bot/commands?wait=20 (not every few seconds), runs a command the moment it comes back, posts the result.
Usage: python Tools/test-host-longpoll.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, SITE = 8961, 8962; B = 'http://127.0.0.1:%d' % PORT; KEY = 'site-KEY-lp'
d = tempfile.mkdtemp(prefix='pglp2_'); json.dump({'Channel': 'x', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'WebSyncKey': KEY, 'WebSyncUrl': 'http://127.0.0.1:%d' % SITE}, open(os.path.join(d, 'settings.json'), 'w'))
polls = []; results = []; state = {'send': False}
class S(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/api/bot/commands'):
            polls.append((time.time(), self.path))
            for _ in range(40):   # hold up to 4 s like a (shortened) long poll
                if state['send']: break
                time.sleep(0.1)
            if state['send']: state['send'] = False; return self._j({'commands': [{'id': 'c1', 'command': '!queue', 'input': 'status', 'user': 'alice', 'privileged': False, 'quiet': True}]})
            return self._j({'commands': []})
        self._j({})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length']) or 0) or b'{}')
        if self.path == '/api/bot/results': results.append((time.time(), b))
        self._j({})
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', SITE), S).serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8960'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(60):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    host.stdin.write(b'alice: !queue'+chr(10).encode()); host.stdin.flush(); time.sleep(12)   # the first command wakes Core, which starts the website loop
    chk('long poll asked with wait=20', len(polls) >= 1 and all('wait=20' in p[1] for p in polls), polls[:2])
    chk('few requests (held open, not every 1-3 s)', len(polls) <= 5, len(polls))
    t0 = time.time(); state['send'] = True
    for _ in range(60):
        if results: break
        time.sleep(0.25)
    chk('command ran and result posted quickly', results and results[0][0] - t0 < 3.5 and results[0][1]['results'][0]['id'] == 'c1', results)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS long poll'); sys.exit(1 if fails else 0)
