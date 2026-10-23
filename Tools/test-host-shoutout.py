"""Shoutout queue: temp chat line right away; the shoutout is the target's clip fired to Multi (featured first, then most viewed, never one of the last 3 sent, shared clips_recent.json), 60 s cooldown, raid of <3 skipped;
a target without clips falls back to the native Twitch card after a random 1-5 s delay and the 2-minute gap, same target once per hour.
Usage: python Tools/test-host-shoutout.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8985; HX = 8986; B = 'http://127.0.0.1:%d' % PORT
posts = []; chats = []; fires = []; t0 = time.time()
def clip(i, feat, views): return {'id': i, 'title': 't' + i, 'url': 'https://clips.twitch.tv/' + i, 'view_count': views, 'is_featured': feat, 'duration': 9.5, 'created_at': '2020-01-01T00:00:00Z', 'thumbnail_url': 'https://clips-media-assets2.twitch.tv/%s-preview-480x272.jpg' % i}
CLIPS = {'id_alpha': [clip('M1', False, 100), clip('F1', True, 10), clip('M2', False, 50), clip('F2', True, 5), clip('M3', False, 40)], 'id_gamma': [clip('G1', False, 7)], 'id_slow': [clip('S1', False, 7)]}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode() if o is not None else b''
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.endswith('/users'):
            lg = q.get('login', [''])[0]; self._send({'data': [{'id': 'id_' + lg, 'login': lg}]})
        elif u.path.endswith('/channels'):
            bid = q.get('broadcaster_id', [''])[0]; lg = bid[3:]; self._send({'data': [{'broadcaster_login': lg, 'broadcaster_name': lg.capitalize(), 'game_name': 'Rocket League'}]})
        elif u.path.endswith('/clips'):
            self._send({'data': CLIPS.get(q.get('broadcaster_id', [''])[0], [])})
        else: self._send({'data': []})
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.endswith('/chats/shoutouts'):
            q = urllib.parse.parse_qs(u.query); posts.append((time.time() - t0, q.get('to_broadcaster_id', [''])[0], q.get('moderator_id', [''])[0], q.get('from_broadcaster_id', [''])[0])); self._send(None, 204)
        elif u.path.endswith('/chat/messages'):
            n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); chats.append((time.time() - t0, b.get('message', ''))); self._send({'data': [{'is_sent': True}]})
        else: self._send({'data': []})
class M(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); fires.append((self.path, b))
        if b.get('user') == 'slow': time.sleep(8)   # Multi answers after the Host's 6 s timeout
        o = json.dumps({'ok': True, 'text': 'queued'}).encode(); self.send_response(200); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
MP = 8988; threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MP), M).serve_forever, daemon=True).start()
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgshout_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'NativeGapSec': 3, 'NativeDelayMinSec': 1, 'NativeDelayMaxSec': 2, 'CooldownSec': 4, 'ManualDedupeMinutes': 0}, open(os.path.join(d, 'shout_settings.json'), 'w'))
json.dump({'Enabled': True, 'Url': 'http://127.0.0.1:%d' % MP, 'Token': ''}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
json.dump([{'id': 'f1', 'ts': 1, 'by': 'chatty'}], open(os.path.join(d, 'clips_recent.json'), 'w'))   # another bot sent F1 a moment ago
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_HELIX_BASE'] = 'http://127.0.0.1:%d' % HX; env['PINGUINO_COMPAT_WS_PORT'] = '8987'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def says(): return [m for _, m in chats]
res = []
def chk(n, ok):
    res.append((n, bool(ok)))
    if not ok: print('   says:', says(), 'posts:', posts)
try:
    for _ in range(240):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    ts = time.time() - t0
    def shout(u, by='mod'): return api('/api/shoutouts', {'user': u, 'by': by}).get('result')
    def last_clip(): return fires[-1][1]['clip']['url'].rsplit('/', 1)[-1] if fires else None
    # 1. clip shoutout: featured first, skipping F1 (the shared list says another bot sent it)
    chk('queued', shout('alpha') == 'queued'); time.sleep(1.5)
    chk('temp line posted', any('check out Alpha at https://twitch.tv/alpha' in x for x in says()))
    chk('fired to Multi /api/alerts/fire as a shoutout', len(fires) == 1 and fires[0][0] == '/api/alerts/fire' and fires[0][1]['type'] == 'shoutout' and fires[0][1]['user'] == 'alpha')
    chk('featured clip first, not the one another bot just sent (F2, not F1/M1)', last_clip() == 'F2.mp4')
    chk('direct media url + title + duration', fires[0][1]['clip']['url'] == 'https://clips-media-assets2.twitch.tv/F2.mp4' and fires[0][1]['clip']['title'] == 'tF2' and fires[0][1]['clip']['duration_s'] == 10)
    chk('stable id', fires[0][1]['id'].startswith('shoutout:alpha:F2:'))
    chk('no Twitch card for a clip shoutout', not posts)
    chk('one chat line only', len([x for x in says() if 'alpha' in x.lower()]) == 1)
    # 2. cooldown
    chk('second shoutout inside the cooldown is refused', shout('beta') == 'cooldown'); time.sleep(0.5)
    chk('cooldown line says so', any('cooldown' in x.lower() for x in says())) 
    chk('and does nothing else', len(fires) == 1 and not posts)
    # 3. more picks avoid the last 3 sent (F1 by chatty, F2, then M1, M2); a repeat only after 3 others
    seq = []
    for _ in range(3):
        time.sleep(4.3); shout('alpha'); time.sleep(1.2); seq.append(last_clip())
    chk('never repeats the last 3 (f1 f2 sent -> M1, M2, then F1 is free again, featured first) -> ' + str(seq), seq == ['M1.mp4', 'M2.mp4', 'F1.mp4'])
    rec = json.load(open(os.path.join(d, 'clips_recent.json')))
    chk('shared list has every send, newest last, with who sent it', [r['id'] for r in rec] == ['f1', 'f2', 'm1', 'm2', 'f1'] and rec[-1]['by'] == 'shoutout')
    time.sleep(4.3); shout('alpha'); time.sleep(1.2)
    chk('after 3 others a clip may come round again (recent = M1 M2 F1 -> F2)', last_clip() == 'F2.mp4')
    # 4. a target without clips falls back to the native Twitch card (and nothing is fired)
    n = len(fires); time.sleep(4.3); chk('queued beta', shout('beta') == 'queued'); time.sleep(4.5)
    chk('no clips: Twitch card sent as the fallback, nothing fired', len(posts) == 1 and posts[0][1] == 'id_beta' and len(fires) == n)
    # 5. the no-clip shoutout above did not burn the cooldown; a hammering mod gets ONE cooldown line per window
    chk('a no-clip shoutout does not burn the cooldown (gamma queued right after)', shout('gamma') == 'queued'); time.sleep(1.2)
    c0 = len([x for x in says() if 'cooldown' in x.lower()])
    r1 = [shout('zeta'), shout('eta'), shout('theta')]; time.sleep(0.5)
    chk('inside the window: refused, one cooldown line only -> %s' % r1, r1 == ['cooldown'] * 3 and len([x for x in says() if 'cooldown' in x.lower()]) == c0 + 1)
    # 6. Multi queued the clip but the POST timed out: no Twitch card on top
    time.sleep(4.3); np = len(posts); shout('slow'); time.sleep(8.5); sl = [f for _, f in fires if f.get('user') == 'slow']
    chk('timeout: the clip was sent once and NO Twitch card followed', len(sl) == 1 and len(posts) == np)
    chk('timeout: the clip counts as sent (shared list)', json.load(open(os.path.join(d, 'clips_recent.json')))[-1]['id'] == 's1')
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
