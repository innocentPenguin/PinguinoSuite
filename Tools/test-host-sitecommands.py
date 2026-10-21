"""Command list push: POST /api/bot/commands-all with the bot key {commands:[...]} (unfiltered, archived included), pushed on change and re-pushed within ~60 s.
Usage: python Tools/test-host-sitecommands.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, SITE = 8963, 8964; B = 'http://127.0.0.1:%d' % PORT; KEY = 'site-KEY-cmds'
d = tempfile.mkdtemp(prefix='pgsc_'); json.dump({'Channel': 'x', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w')); json.dump({'WebSyncKey': KEY}, open(os.path.join(d, 'settings.json'), 'w'))
got = []
class S(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length']))); got.append((self.path, self.headers.get('Authorization'), b)); self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', SITE), S).serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8965', 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def mine(): return [g for g in got if g[0] == '/api/bot/commands-all']
def wait(n, s=25):
    for _ in range(s * 2):
        if len(mine()) >= n: return True
        time.sleep(0.5)
    return False
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=10))
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(60):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    chk('pushed at start', wait(1), len(got)); g = mine()[0] if mine() else ('', '', {})
    cs = g[2].get('commands', []); chk('bot key + shape', g[1] == 'Bearer ' + KEY and len(cs) > 20 and all(k in cs[0] for k in ['id', 'name', 'permission', 'enabled', 'archived', 'uses']) and 'createdBy' not in cs[0], cs[:1])
    time.sleep(12); chk('not pushed again without a change', len(mine()) == 1, len(mine()))
    post('/api/commands/profile', {'id': '!mmr', 'enabled': False, 'by': 'test'}); post('/api/commands/archive', {'id': '!mmr', 'by': 'test'})
    chk('change pushed, archived command still in the list', wait(2, 20) and any(c['id'] == '!mmr' and c['archived'] for c in mine()[-1][2]['commands']), len(mine()))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS site commands'); sys.exit(1 if fails else 0)
