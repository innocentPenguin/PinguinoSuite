"""Host-owned channel point rewards: GET /api/rewards says which rewards the Host owns, POST /api/rewards/create makes its own (title clash with another app's reward is refused,
cost/prompt copied, song request automation pointed at it, idempotent), a 403 "Client-Id must match" refund is warned once and never retried, and a trigger with a rewardId only fires for that reward.
Usage: python Tools/test-host-rewards.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, MOD = 8986, 8987, 8988
patches = []; posts = []
rewards = [{'id': 'rw1', 'title': 'Song Request', 'cost': 500, 'prompt': 'Say the song', 'is_enabled': True, 'is_user_input_required': True}]
ours = set()
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        rows = [r for r in rewards if q.get('only_manageable_rewards') != ['true'] or r['id'] in ours]
        self._j(200, {'data': rows})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); posts.append(b)
        if any(r['title'].lower() == b['title'].lower() for r in rewards): return self._j(400, {'message': 'CREATE_CUSTOM_REWARD_DUPLICATE_REWARD'})
        r = dict(b, id='rwNEW', is_enabled=True); rewards.append(r); ours.add('rwNEW'); self._j(200, {'data': [r]})
    def do_PATCH(self):
        n = int(self.headers.get('Content-Length', 0)); self.rfile.read(n); patches.append(self.path)
        if 'reward_id=rw1' in self.path: return self._j(403, {'message': 'The Client-Id header must match the client ID used to create the custom reward'})
        self._j(200, {'data': [{}]})
class Mod(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0))); b = json.dumps({'ok': False, 'refund': True, 'say': 'nope'}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
for port, h in ((HX, Hx), (MOD, Mod)): threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', port), h).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgrw_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'actions': [{'id': 'spotify-redeem', 'name': 'SR', 'enabled': True, 'triggers': [{'type': 'redeem', 'title': 'Song Request'}], 'steps': [{'type': 'module_command', 'url': 'http://127.0.0.1:%d/api/chat-command' % MOD, 'command': 'sr', 'redeem': True}]}], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8989', 'PINGUINO_REFUND_POLL_SEC': '300'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def api(p, body=None):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=20))
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    # a refund of a foreign reward: 403 once, then the Host stops asking
    feed('event TwitchRedeem alice bad_song', 2.0); feed('event TwitchRedeem bob bad_song', 2.0)
    chk('foreign reward: one PATCH only (second skipped, no more 403s)', len(patches) == 1, patches)
    time.sleep(0.5); import glob; txt = ''.join(open(f, 'rb').read().decode('utf-8', 'replace') for f in glob.glob(os.path.join(d, '**', 'host.jsonl'), recursive=True)); chk('one warning naming the fix', txt.count('created by another app') == 1, txt.count('created by another app'))
    r = api('/api/rewards'); chk('list', r['ok'] and len(r['rewards']) == 1 and r['rewards'][0]['owned'] is False, r)
    r = api('/api/rewards/create', {}); chk('title clash with the other app refused with the way out', r['ok'] is False and 'another app' in r['error'] and 'rename or delete' in r['error'], r)
    chk('nothing was posted to Twitch for the clash', len(posts) == 0, posts)
    rewards[0]['title'] = 'Song Request (old)'
    r = api('/api/rewards/create', {}); chk('no cost known: asks for it instead of guessing', r['ok'] is False and 'cost' in r['error'], r)
    r = api('/api/rewards/create', {'cost': 500, 'prompt': 'Type the song'}); chk('created', r.get('ok') and r.get('created') and r['id'] == 'rwNEW' and r['cost'] == 500 and r['automationSwitched'] is True, r)
    chk('Twitch got title/cost/prompt/input flag', posts and posts[-1] == {'title': 'Song Request', 'cost': 500, 'prompt': 'Type the song', 'is_user_input_required': True}, posts)
    n = len(posts); r = api('/api/rewards/create', {'cost': 500}); chk('second call is idempotent', r.get('ok') and r.get('already') and r['id'] == 'rwNEW' and len(posts) == n, r)
    a = [x for x in api('/api/automations')['doc']['actions'] if x['id'] == 'spotify-redeem'][0]; tr = a['triggers'][0]
    chk('automation points at the new reward', tr['title'] == 'Song Request' and tr['rewardId'] == 'rwNEW', tr)
    rows = {x['id']: x for x in api('/api/rewards')['rewards']}; chk('list: new one is ours, old is not', rows['rwNEW']['owned'] and not rows['rw1']['owned'], rows)
    # a trigger with a rewardId only fires for that reward (sim redeems always carry rw1)
    ran0 = len(api('/api/automations/log?n=100')['runs']); feed('event TwitchRedeem carol hello', 2.0)
    chk('redeem of another reward id does not run the automation', len(api('/api/automations/log?n=100')['runs']) == ran0)
finally:
    host.kill(); time.sleep(0.5); print(open(out,"rb").read().decode("utf-8","replace")[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS rewards'); sys.exit(1 if fails else 0)
