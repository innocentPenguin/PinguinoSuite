"""Live active subs (paged Helix list, audit of profiles, ended subs), avatars (by login, by id for renamed, alias fallback, last good url kept), bots list.
Usage: python Tools/test-host-profilesync.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8981; HX = 8982; B = 'http://127.0.0.1:%d' % PORT
SUBS = [{'user_id': 'u1', 'user_login': 'ana', 'user_name': 'Ana', 'tier': '1000', 'is_gift': False, 'gifter_login': '', 'plan_name': 'Channel Subscription'},
        {'user_id': 'u2', 'user_login': 'ben', 'user_name': 'Ben', 'tier': '2000', 'is_gift': True, 'gifter_login': 'ana', 'plan_name': 'x'},
        {'user_id': 'u3', 'user_login': 'cara', 'user_name': 'Cara', 'tier': '1000', 'is_gift': False, 'gifter_login': '', 'plan_name': 'Channel Subscription (Prime)'},
        {'user_id': 'u4', 'user_login': 'dan', 'user_name': 'Dan', 'tier': '3000', 'is_gift': False, 'gifter_login': '', 'plan_name': 'x'},
        {'user_id': 'streamer1', 'user_login': 'innocentpenguin_', 'user_name': 'IP', 'tier': '1000', 'is_gift': False, 'gifter_login': '', 'plan_name': 'x'}]
USERS = {'ana': ('u1', 'Ana'), 'ben': ('u2', 'Ben'), 'cara': ('u3', 'Cara'), 'dan': ('u4', 'Dan'), 'neweve': ('u6', 'NewEve')}
state = {'users_fail': False, 'subs': list(SUBS)}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self): self.rfile.read(int(self.headers.get('Content-Length', 0))); self._send({'data': []})
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.endswith('/subscriptions'):
            if state['subs'] is None: return self._send({'message': 'boom'}, 500)   # the 'failing sub list' scenario: answer an error instead of crashing the handler
            subs = state['subs']; off = int(q.get('after', ['0'])[0]); page = subs[off:off + 2]
            return self._send({'data': page, 'pagination': {'cursor': str(off + 2)} if off + 2 < len(subs) else {}})
        if u.path.endswith('/users'):
            if state['users_fail']: return self._send({'message': 'boom'}, 500)
            out = []
            for l in q.get('login', []):
                if l in USERS: out.append({'id': USERS[l][0], 'login': l, 'display_name': USERS[l][1], 'profile_image_url': 'https://static-cdn.jtvnw.net/%s.png' % l})
            for i in q.get('id', []):
                if i == 'u5': out.append({'id': 'u5', 'login': 'neweve', 'display_name': 'NewEve', 'profile_image_url': 'https://static-cdn.jtvnw.net/neweve.png'})
            return self._send({'data': out})
        self._send({'data': []})
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgps_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'boards')); json.dump({'aliases': {'cyfi': 'ana'}}, open(os.path.join(d, 'boards', 'aliases.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
def prof(l, **roles): json.dump({'login': l, 'name': l, 'nicknames': (['cyfi'] if l == 'ana' else []), 'roles': roles}, open(os.path.join(d, 'profiles', l + '.json'), 'w'))
prof('ana', sub=True, subTier=1); prof('ben', sub=False, lapsed=True); prof('dan'); prof('eve', sub=True, subTier=1); prof('ghost'); prof('cyfi'); prof('mybot')
os.makedirs(os.path.join(d, 'subs'))
json.dump({'eve': {'url': 'https://static-cdn.jtvnw.net/old-eve.png', 'id': 'u5', 'status': 'ok', 'checkedAt': 1}}, open(os.path.join(d, 'avatars.json'), 'w'))
def start():
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8984', 'PINGUINO_PROFILESYNC_FAST': '1'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
def J(*p): return json.load(open(os.path.join(d, *p), encoding='utf-8'))
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra)
host = start()
try:
    time.sleep(2.5)
    live = J('subs', 'live_subs.json')
    chk('active subs read across pages (streamer left out)', live['count'] == 4 and set(live['users']) == {'ana', 'ben', 'cara', 'dan'}, live)
    chk('tier, gift, gifter and prime are kept', live['users']['dan']['tier'] == 3 and live['users']['ben']['isGift'] and live['users']['ben']['gifter'] == 'ana' and live['users']['cara']['prime'], live['users'])
    au = J('subs', 'sub_audit.json')
    chk('audit counts: twitch 4, profiles say 2, missing = ben (marked lapsed), cara (no profile), dan (not subbed)', au['twitch'] == 4 and au['profiles'] == 2 and au['missing'] == 3 and {m['login'] for m in au['missingLogins']} == {'ben', 'cara', 'dan'}, au)
    chk('a profile that still says subbed without a Twitch sub is listed', au['profilesSubbedButNotOnTwitch'] == ['eve'], au)
    ava = J('avatars.json')
    chk('avatars by login', ava['ana']['url'].endswith('ana.png') and ava['dan']['status'] == 'ok', ava.get('ana'))
    chk('renamed account found by id', ava['eve']['status'] == 'ok' and ava['eve']['renamedTo'] == 'neweve' and ava['eve']['url'].endswith('neweve.png'), ava.get('eve'))
    chk('alias with no picture of its own borrows the main account', ava['cyfi']['url'].endswith('ana.png') and ava['cyfi']['status'] == 'via', ava.get('cyfi'))
    rep = J('avatar_report.json'); miss = {m['login']: m['reason'] for m in rep['missing']}
    chk('report lists what is still missing and why', 'ghost' in miss and 'not found' in miss['ghost'] and rep['withAvatar'] + rep['stillMissing'] == rep['profilesTotal'], rep)
    bots = J('profile_bots.json')['bots']
    chk('bots list carries known bots and *bot accounts, not the streamer', 'mybot' in bots and 'nightbot' in bots and 'innocentpenguin_' not in bots, bots)
    # last good url survives a failing lookup
    state['users_fail'] = True; api('/api/profile-sync', {}); ava2 = J('avatars.json')
    chk('a failed lookup keeps the last good picture', ava2['ana']['url'].endswith('ana.png'), ava2.get('ana'))
    state['users_fail'] = False
    # an event refreshes the list quickly: a new sub appears
    state['subs'].append({'user_id': 'u9', 'user_login': 'newsub', 'user_name': 'NewSub', 'tier': '1000', 'is_gift': False, 'gifter_login': '', 'plan_name': 'x'})
    host.stdin.write(b'event TwitchSub newsub 1\n'); host.stdin.flush(); time.sleep(3.0)
    chk('a sub event refreshes the active list', 'newsub' in J('subs', 'live_subs.json')['users'])
    # sub list failure keeps the last good file
    before = J('subs', 'live_subs.json')['count']; state['subs'] = None
    try: api('/api/profile-sync', {'avatars': False})
    except Exception: pass
    chk('a failing sub list keeps the last good file and says so', 'kept the last good list' in api('/api/profile-sync')['subs'] and J('subs', 'live_subs.json')['count'] == before, api('/api/profile-sync')['subs'])
    state['subs'] = list(SUBS); api('/api/profile-sync', {'avatars': False}); chk('status endpoint reports counts', 'active subs per Twitch 4' in api('/api/profile-sync')['subs'], api('/api/profile-sync')['subs'])
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
