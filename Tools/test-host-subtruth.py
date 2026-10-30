"""Twitch is the truth for subs: after each live Helix pull the master and the profiles are set to the active list (tier, subType, giftedBy), missing profiles are created for gift recipients,
everything Twitch does not list is lapsed (master rows AND profiles that only had the old sticky log-scraper flag), an empty list changes nothing, a second pass changes nothing.
Usage: python Tools/test-host-subtruth.py [dll]"""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, HX, WS = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
def sub(i, login, tier='1000', gift=False, gifter='', plan='Channel Subscription'): return {'user_id': i, 'user_login': login, 'user_name': login.capitalize(), 'tier': tier, 'is_gift': gift, 'gifter_login': gifter, 'plan_name': plan}
state = {'subs': [sub('u1', 'ana'), sub('u2', 'ben', '2000', True, 'ana'), sub('u3', 'cara', gift=True, gifter='ana'), sub('u4', 'dan', plan='Prime'), sub('streamer1', 'innocentpenguin_')]}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.endswith('/subscriptions'):
            subs = state['subs']; off = int(q.get('after', ['0'])[0]); page = subs[off:off + 2]
            return self._send({'data': page, 'pagination': {'cursor': str(off + 2)} if off + 2 < len(subs) else {}})
        self._send({'data': []})
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', HX), H).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgst_'); outf = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'profiles')); os.makedirs(os.path.join(d, 'subs'))
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def prof(l, **roles): json.dump({'login': l, 'name': l, 'roles': roles}, open(os.path.join(d, 'profiles', l + '.json'), 'w'))
prof('ana', sub=True, subTier=1, subType='recurring', subMonths=7); prof('ben', sub=False, lapsed=True); prof('scraped', sub=True, subMonths=3); prof('expired', sub=True, subTier=1, subType='gift'); prof('plain')
M = lambda l, **k: dict({'login': l, 'tier': 1, 'tenure': 5, 'streak': 2, 'subscribed': '2026-01-01T00:00:00Z', 'founder': False, 'subType': 'gift', 'lapsed': False}, **k)
json.dump({'version': 1, 'lastExportAt': '2026-10-20T00:00:00Z', 'users': {'ana': M('ana', tenure=7, subType='recurring'), 'ben': M('ben', lapsed=True), 'expired': M('expired'), 'innocentpenguin_': M('innocentpenguin_', founder=True)}, 'processed': {}, 'resubSeen': []}, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_PROFILESYNC_FAST': '1'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'wb'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
def J(*p): return json.load(open(os.path.join(d, *p), encoding='utf-8'))
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', n, extra)
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2.5); api('/api/profile-sync', {'avatars': False}); time.sleep(0.5)
    m = J('subs', 'subscribers_master.json')['users']; P = lambda l: J('profiles', l + '.json')['roles'] if os.path.exists(os.path.join(d, 'profiles', l + '.json')) else None
    chk('the 4 active subs are active in the master (streamer is not one of them)', all(m[l]['lapsed'] is False for l in ('ana', 'ben', 'cara', 'dan')), m)
    chk('tier and subType follow Twitch: ben T2 gift by ana, dan prime, ana recurring', m['ben']['tier'] == 2 and m['ben']['subType'] == 'gift' and m['ben']['giftedBy'] == 'ana' and m['dan']['subType'] == 'prime' and m['ana']['subType'] == 'recurring', m)
    chk('existing tenure is kept (Helix has none)', m['ana']['tenure'] == 7, m['ana'])
    chk('a gift recipient with no row gets one (source helix)', m['cara']['source'] == 'helix' and m['cara']['subType'] == 'gift' and m['cara']['giftedBy'] == 'ana', m.get('cara'))
    chk('a master row Twitch does not list is lapsed (expired, streamer)', m['expired']['lapsed'] is True and m['innocentpenguin_']['lapsed'] is True, (m['expired'], m['innocentpenguin_']))
    chk('profiles of the active follow: ben was lapsed, is subbed again with tier and giftedBy', P('ben')['sub'] is True and P('ben')['lapsed'] is False and P('ben')['subTier'] == 2 and P('ben')['giftedBy'] == 'ana', P('ben'))
    chk('missing profiles are created (cara, dan) as subbed', P('cara') is not None and P('cara')['sub'] is True and P('cara')['subType'] == 'gift' and P('dan')['sub'] is True and P('dan')['subType'] == 'prime', (P('cara'), P('dan')))
    chk('profile of an expired master row is lapsed', P('expired')['sub'] is False and P('expired')['lapsed'] is True, P('expired'))
    chk('a sticky scraper flag without master row is cleared', P('scraped')['sub'] is False and P('scraped')['lapsed'] is True, P('scraped'))
    chk('an unrelated profile is untouched', P('plain') == {}, P('plain'))
    snap = (json.dumps(J('subs', 'subscribers_master.json')['users'], sort_keys=True), {l: json.dumps(P(l), sort_keys=True) for l in ('ana', 'ben', 'cara', 'dan', 'scraped', 'expired')})
    api('/api/profile-sync', {'avatars': False}); time.sleep(0.5)
    now = (json.dumps(J('subs', 'subscribers_master.json')['users'], sort_keys=True), {l: json.dumps(P(l), sort_keys=True) for l in ('ana', 'ben', 'cara', 'dan', 'scraped', 'expired')})
    a, b = json.loads(snap[0]), json.loads(now[0])
    for v in list(a.values()) + list(b.values()): v.pop('importedAt', None)
    chk('a second pass changes nothing', a == b and snap[1] == now[1], (a, b))
    state['subs'] = []; api('/api/profile-sync', {'avatars': False}); time.sleep(0.5)
    chk('an empty Twitch list lapses nobody', J('subs', 'subscribers_master.json')['users']['ana']['lapsed'] is False and P('ana')['sub'] is True)
    state['subs'] = [sub('u1', 'ana'), sub('streamer1', 'innocentpenguin_')]; api('/api/profile-sync', {'avatars': False}); time.sleep(0.5)
    chk('a later pass lapses those who ended (ben, cara, dan)', all(J('subs', 'subscribers_master.json')['users'][l]['lapsed'] is True for l in ('ben', 'cara', 'dan')) and P('cara')['sub'] is False and P('ana')['sub'] is True)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
