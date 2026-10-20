"""GET /api/clips-dump against a fake Helix: cursor paging, per-year windows, dedupe, saved file shape.  Usage: python Tools/test-host-clips.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX = 8984, 8985; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgclips_')
json.dump({'Channel': 'clipt', 'OverlayPort': PORT, 'ClientId': 'cid', 'UserToken': 'tok', 'BroadcasterId': '111'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
reqs = []
def clip(i, year): return {'id': 'c%d' % i, 'title': 't%d' % i, 'url': 'u%d' % i, 'view_count': i, 'created_at': '%d-05-01T00:00:00Z' % year, 'duration': 10.0, 'creator_name': 'x', 'game_id': '1', 'is_featured': False, 'extra': 1}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); reqs.append(q); yr = int(q['started_at'][0][:4]); after = q.get('after', [''])[0]
        if yr == 2024: data = [clip(i, 2024) for i in range(1, 101)] if not after else [clip(i, 2024) for i in range(101, 131)]; cur = 'p2' if not after else None
        elif yr == 2025: data, cur = [clip(50, 2025), clip(1, 2024)], None   # one new, one duplicate id
        else: data, cur = [], None
        o = json.dumps({'data': data, 'pagination': {'cursor': cur} if cur else {}}).encode(); self.send_response(200); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', HX), H).serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983', 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX})
fails = []; host = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = json.load(urllib.request.urlopen(B + '/api/clips-dump', timeout=120)); chk('ok', r['ok'] and r['count'] == 130, r)
    rows = json.load(open(os.path.join(d, 'clips', 'clips.json'), encoding='utf-8'))
    chk('saved rows', len(rows) == 130 and set(rows[0].keys()) == {'id', 'title', 'url', 'view_count', 'created_at', 'duration', 'creator_name', 'game_id', 'is_featured'}, rows[:1])
    chk('broadcaster id used', all(q['broadcaster_id'] == ['111'] and q['first'] == ['100'] for q in reqs))
    chk('paged with cursor', any(q.get('after') == ['p2'] for q in reqs))
    chk('sorted by date', [x['created_at'] for x in rows] == sorted(x['created_at'] for x in rows))
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS clips dump'); sys.exit(1 if fails else 0)
