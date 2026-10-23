"""GET /api/clips-dump against a fake Helix: cursor paging, per-year windows, dedupe, saved file shape.  Usage: python Tools/test-host-clips.py [dll]"""
import urllib.error, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX = 8984, 8985; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgclips_')
json.dump({'Channel': 'clipt', 'OverlayPort': PORT, 'ClientId': 'cid', 'UserToken': 'tok', 'BroadcasterId': '111'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
reqs = []; ownq = []
FEAT = [{'id': 'F%d' % i, 'title': 'f%d' % i, 'url': 'https://clips.twitch.tv/F%d' % i, 'view_count': 10 * i, 'created_at': '2026-10-20T00:00:00Z', 'is_featured': True} for i in (1, 2, 3, 4)] + [{'id': 'N1', 'title': 'n', 'url': 'https://clips.twitch.tv/N1', 'view_count': 999, 'created_at': '2026-10-20T00:00:00Z', 'is_featured': False}]
def clip(i, year): return {'id': 'c%d' % i, 'title': 't%d' % i, 'url': 'u%d' % i, 'view_count': i, 'created_at': '%d-05-01T00:00:00Z' % year, 'duration': 10.0, 'creator_name': 'x', 'game_id': '1', 'is_featured': False, 'extra': 1}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); reqs.append(q); yr = int(q['started_at'][0][:4]); after = q.get('after', [''])[0]
        if 'ended_at' not in q: data, cur = FEAT, None; ownq.append(q['started_at'][0])
        elif yr == 2024: data = [clip(i, 2024) for i in range(1, 101)] if not after else [clip(i, 2024) for i in range(101, 131)]; cur = 'p2' if not after else None
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
    for _ in range(240):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = json.load(urllib.request.urlopen(B + '/api/clips-dump', timeout=120)); chk('ok', r['ok'] and r['count'] == 130, r)
    rows = json.load(open(os.path.join(d, 'clips', 'clips.json'), encoding='utf-8'))
    chk('saved rows', len(rows) == 130 and set(rows[0].keys()) == {'id', 'title', 'url', 'view_count', 'created_at', 'duration', 'creator_name', 'game_id', 'is_featured'}, rows[:1])
    chk('broadcaster id used', all(q['broadcaster_id'] == ['111'] and q['first'] == ['100'] for q in reqs))
    chk('paged with cursor', any(q.get('after') == ['p2'] for q in reqs))
    chk('sorted by date', [x['created_at'] for x in rows] == sorted(x['created_at'] for x in rows))
    def jget(p): return json.load(urllib.request.urlopen(B + p, timeout=20))
    def jpost(p, b): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(b).encode(), headers={'Content-Type': 'application/json'}), timeout=20))
    ownq.clear(); r = jget('/api/clips-pick?own=1'); chk('pick: featured only, most viewed first (F4, never the 999-view non-featured)', r['ok'] and r['clip']['id'] == 'F4', r)
    chk('pick asks Helix for the last 14 days', len(ownq) == 1 and 12.9 < (time.time() - time.mktime(time.strptime(ownq[0], '%Y-%m-%dT%H:%M:%SZ')) + time.timezone) / 86400 < 14.1, ownq)
    chk('pick is read only (same answer twice)', jget('/api/clips-pick?own=1')['clip']['id'] == 'F4')
    chk('Helix list is cached: three picks made one Helix request', len(ownq) == 1, ownq)
    chk('sent: marks it', jpost('/api/clips-sent', {'url': 'https://clips.twitch.tv/F4', 'by': 'chatty'})['ok'])
    chk('sent twice in a row is idempotent', jpost('/api/clips-sent', {'url': 'https://clips.twitch.tv/F4', 'by': 'chatty'}).get('already') is True)
    chk('next pick skips the one just sent', jget('/api/clips-pick?own=1')['clip']['id'] == 'F3')
    jpost('/api/clips-sent', {'url': 'https://clips.twitch.tv/F3', 'by': 'lore'}); jpost('/api/clips-sent', {'url': 'F2?x=1', 'by': 'helper'})
    r = jget('/api/clips-pick?own=1'); chk('never one of the last 3 sent by any bot -> F1', r['clip']['id'] == 'F1' and r['recent'] == ['f4', 'f3', 'f2'], r)
    jpost('/api/clips-sent', {'url': 'F1', 'by': 'x'}); chk('after 4 sends the oldest (F4) is free again', jget('/api/clips-pick?own=1')['clip']['id'] == 'F4')
    rec = json.load(open(os.path.join(d, 'clips_recent.json'))); chk('shared file holds the sends with who sent them', [x['by'] for x in rec] == ['chatty', 'lore', 'helper', 'x'], rec)
    # reserve=1: pick + mark in one step so two bots asking together get different clips
    a1 = jget('/api/clips-pick?own=1&reserve=1&by=helper')['clip']['id']; a2 = jget('/api/clips-pick?own=1&reserve=1&by=lore')['clip']['id']
    chk('two reserved picks in a row are different clips (%s %s)' % (a1, a2), a1 == 'F4' and a2 == 'F3')
    chk('confirming a reserved clip keeps it', jpost('/api/clips-sent', {'url': a2, 'by': 'lore'}).get('already') is True)
    chk('giving a reserved clip back (post timed out)', jpost('/api/clips-sent', {'url': a2, 'release': True}).get('released') is False)   # F3 was confirmed above, so it cannot be released
    a3 = jget('/api/clips-pick?own=1&reserve=1&by=chatty')['clip']['id']; chk('third bot gets a different clip again (' + a3 + ')', a3 not in (a1, a2))
    chk('release hands it back', jpost('/api/clips-sent', {'url': a3, 'release': True}).get('released') is True and jget('/api/clips-pick?own=1')['clip']['id'] == a3)
    # a web page (Origin header) is refused on both routes
    def code(rq):
        try: return urllib.request.urlopen(rq, timeout=10).status
        except urllib.error.HTTPError as e: return e.code
    chk('clips-pick with an Origin header is refused', code(urllib.request.Request(B + '/api/clips-pick?own=1', headers={'Origin': 'https://evil.example'})) == 403)
    chk('clips-sent with an Origin header is refused', code(urllib.request.Request(B + '/api/clips-sent', data=b'{"url":"zz"}', headers={'Origin': 'https://evil.example', 'Content-Type': 'application/json'})) == 403 and 'zz' not in json.load(open(os.path.join(d, 'clips_recent.json')))[-1]['id'])
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS clips dump + pick'); sys.exit(1 if fails else 0)
