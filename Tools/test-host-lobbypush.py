"""Private match push: helper_settings.json LobbyName/LobbyPassword -> POST /api/bot/match-private with the bot key; pushed once per change; restart does not re-push; password never in logs.
Usage: python Tools/test-host-lobbypush.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, SITE = 8993, 8994; B = 'http://127.0.0.1:%d' % PORT; KEY = 'site-KEY-lobby'; PW = 'topsecretpw77'
d = tempfile.mkdtemp(prefix='pglp_'); hs = os.path.join(d, 'helper_settings.json')
json.dump({'Channel': 'x', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w')); json.dump({'WebSyncKey': KEY}, open(os.path.join(d, 'settings.json'), 'w'))
def setl(n, p, at): json.dump({'LobbyName': n, 'LobbyPassword': p, 'LobbyUpdatedAt': at}, open(hs, 'w'))
setl('peng3', PW, '2026-10-20T21:00:00Z'); got = []
def mine(): return [g for g in got if g[0] == '/api/bot/match-private']
class S(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length']))); got.append((self.path, self.headers.get('Authorization'), b)); self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', SITE), S).serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8996', 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'PINGUINO_LOBBY_POLL_SEC': '1', 'PINGUINO_SITE_POLL_SEC': '600'})
def start():
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    return h
def wait(n):
    for _ in range(25):
        if len([g for g in got if g[0] == '/api/bot/match-private']) >= n: return True
        time.sleep(0.5)
    return False
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
h = start()
try:
    chk('pushed at start', wait(1), got); g = mine()[0] if mine() else ('', '', {})
    chk('bot key and body', g[1] == 'Bearer ' + KEY and g[2] == {'name': 'peng3', 'password': PW, 'active': True}, g)
    time.sleep(3); chk('not pushed twice', len(mine()) == 1, len(mine()))
    setl('peng4', 'newpw', '2026-10-20T22:00:00Z'); chk('change pushed', wait(2) and mine()[-1][2]['name'] == 'peng4', mine()[-1:])
    setl('', '', '2026-10-20T23:00:00Z'); chk('clear pushed as inactive', wait(3) and mine()[-1][2]['active'] is False, mine()[-1:])
    h.kill(); h.wait(); n = len(mine()); h = start(); time.sleep(6); chk('restart does not re-push', len(mine()) == n, (n, len(mine())))
    logs = ''.join(open(os.path.join(r, f), encoding='utf-8', errors='replace').read() for r, _, fs in os.walk(d) for f in fs if f.endswith(('.log', '.jsonl')) or f == 'lobby_push.json')
    chk('password and key never in logs/state', PW not in logs and 'newpw' not in logs and KEY not in logs)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS lobby push'); sys.exit(1 if fails else 0)
