"""Spotify announcements poller: fake Spotify module on a local port, sim Host. Usage: python Tools/test-host-spotify.py [dll]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8893; FAKE = 8894
lines = [{'seq': 1, 'ts': 1, 'text': 'OLD line must be skipped'}]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        since = int(self.path.split('since=')[-1] or 0) if 'since=' in self.path else 0
        b = json.dumps({'seq': lines[-1]['seq'], 'lines': [l for l in lines if l['seq'] > since]}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
srv = HTTPServer(('127.0.0.1', FAKE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgspot_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Enabled': True, 'Url': 'http://127.0.0.1:%d' % FAKE, 'PollSec': 2, 'Prefix': 'NOW: ', 'MaxPerMinute': 2}, open(os.path.join(d, 'spotify_announce.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8897'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out = []; threading.Thread(target=lambda: [out.append(r.decode('utf-8', 'replace')) for r in iter(host.stdout.readline, b'')], daemon=True).start()
res = []
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/spotify-announce' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(7)
    t = ''.join(out); res.append(('old line skipped', 'OLD line' not in t))
    lines += [{'seq': 2, 'ts': 2, 'text': 'Song A'}, {'seq': 3, 'ts': 3, 'text': 'Song B'}, {'seq': 4, 'ts': 4, 'text': 'Song C'}]
    seen = []
    for _ in range(30):
        seen.append(json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/spotify-announce' % PORT, timeout=5))['status']); time.sleep(0.25)
    st0 = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/spotify-announce' % PORT, timeout=5))
    res.append(('new lines taken up to #4', st0['since'] == 4))
    res.append(('rate limit: 2 posted of 3 (sim has no chat sender, so check the status)', any('2 posted' in x for x in seen)))
    st = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/spotify-announce' % PORT, timeout=5))
    res.append(('status endpoint', st.get('ok') is True and st['settings']['Enabled'] is True))
finally:
    host.kill(); srv.shutdown()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
