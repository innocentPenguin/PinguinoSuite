"""GET /api/boards/twitch-bits: the Helix bits leaderboard through the Host's streamer token (fake Helix here). Answers {login, score} only, never the token; bad period refused.
Usage: python Tools/test-host-twitchbits.py [dll]"""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSPORT, HX = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
seen = []
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        seen.append((self.path, self.headers.get('Authorization'), self.headers.get('Client-Id')))
        r = json.dumps({'data': [{'user_id': '1', 'user_login': 'ZyloRocketLeague', 'user_name': 'Zylo', 'rank': 1, 'score': 3725}, {'user_id': '2', 'user_login': 'amy', 'user_name': 'Amy', 'rank': 2, 'score': 100}], 'total': 2}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', HX), Hx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgtb_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'SECRETTOKEN123', 'ClientId': 'cid-test'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p):
    try: return urllib.request.urlopen(B + p, timeout=15).read().decode()
    except urllib.error.HTTPError as e: return e.read().decode()
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    t = get('/api/boards/twitch-bits?period=all'); j = json.loads(t)
    chk('rows are login + score only, lowercase', j.get('ok') is True and j['rows'] == [{'login': 'zylorocketleague', 'score': 3725}, {'login': 'amy', 'score': 100}] and j['period'] == 'all', t)
    chk('the token never leaves the Host', 'SECRETTOKEN' not in t)
    chk('Helix was asked with the token, period and count', seen and 'period=all' in seen[-1][0] and 'count=100' in seen[-1][0] and seen[-1][1] == 'Bearer SECRETTOKEN123' and seen[-1][2] == 'cid-test', seen)
    get('/api/boards/twitch-bits?period=week&count=5'); chk('period and count are passed on', 'period=week' in seen[-1][0] and 'count=5' in seen[-1][0], seen[-1])
    chk('bad period refused, Helix not called', json.loads(get('/api/boards/twitch-bits?period=forever')).get('ok') is False and 'forever' not in seen[-1][0])
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-800:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS twitchbits'); sys.exit(1 if fails else 0)
