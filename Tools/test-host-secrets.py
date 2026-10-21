"""No secret ever reaches the console log, the log files, the data files (other than the two secrets files) or the public/read API answers,
including on the error paths (Twitch refusing a send with 401 / 429, a slow Twitch).
Usage: python Tools/test-host-secrets.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8985; HX = 8986; B = 'http://127.0.0.1:%d' % PORT
SECRETS = ['TOKSECRET_u7q2x9', 'CIDSECRET_k3m8w1', 'JWTSECRET_eyJhbGciOiJIUzI1NiJ9', 'BOTTOKSECRET_p5r6t4', 'CLIENTSECRET_z1y2x3']
mode = {'code': 401}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); self.rfile.read(n)
        # the refusal body echoes the request headers, the way a careless proxy might: the Host must still not log the secret values
        self._send({'error': 'refused', 'status': mode['code'], 'echo': self.headers.get('Authorization', '')}, mode['code'])
    def do_GET(self): self._send({'data': []}, 401 if mode['code'] == 401 else 200)
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgsec_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': SECRETS[0], 'ClientId': SECRETS[1], 'SeJwt': SECRETS[2], 'ClientSecret': SECRETS[4], 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': SECRETS[3], 'ClientId': SECRETS[1], 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8987', 'PINGUINO_DUP_SECONDS': '0'})
outp = os.path.join(d, 'out.txt')
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try: return urllib.request.urlopen(rq, timeout=15).read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e: return e.read().decode('utf-8', 'replace')
    except Exception as e: return ''
def feed(line, wait=0.5): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait)
fails = []; bodies = []
def leaks(text, ok=()): return [s for s in SECRETS if s in text and s not in ok]
try:
    for _ in range(100):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    for code in (401, 429, 500):
        mode['code'] = code
        api('/api/timers', {'timer': {'id': 't%d' % code, 'name': 'T', 'enabled': False, 'everySec': 60, 'messages': ['hello %d' % code]}})
        for line in ('alice: !points', 'alice: !uptime', 'alice: !commands', 'bob: !lookup alice', 'bob: !first', 'carl: hello there %d' % code):
            feed(line, 0.4)
        api('/api/bots/test', {'id': 'core'}); api('/api/pg/test', {})
        time.sleep(1.0)
    for p in ('/api/status', '/api/bots', '/api/setup', '/api/account', '/api/economy', '/api/logs', '/api/problems', '/api/commands-doc', '/api/automations', '/api/livelog', '/api/streamtimers', '/api/timers', '/api/tune', '/api/config', '/api/cutover'):
        bodies.append((p, api(p)))
    time.sleep(0.5)
finally:
    h.kill(); time.sleep(0.5)
skip = {'host_secrets.json', 'bots_secrets.json'}
out = open(outp, encoding='utf-8', errors='replace').read()
if leaks(out): fails.append('console output leaks ' + str(leaks(out)))
for p, b in bodies:
    ok = (SECRETS[1],) if p == '/api/config' else ()   # the setup form shows the Client ID on purpose: it is a public identifier, not a secret
    if leaks(b, ok): fails.append('API %s leaks %s' % (p, leaks(b, ok)))
for root, _, files in os.walk(d):
    for f in files:
        if f in skip or f == 'out.txt': continue
        try: t = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
        except Exception: continue
        if leaks(t): fails.append('file %s leaks %s' % (os.path.relpath(os.path.join(root, f), d), leaks(t)))
shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS no secret in the log, files or API answers'); sys.exit(1 if fails else 0)
