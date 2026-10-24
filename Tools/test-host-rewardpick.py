"""Reward picker: POST /api/rewards/use (Host-owned reward -> automation pointed at it; foreign -> needsTakeover) and /api/rewards/takeover
(Host copy with the same cost/prompt/colour/cooldown/limits; old one renamed "(old)" + disabled when Twitch lets it, else copy titled "(Host)" + manualStep and one rename try only;
"(old)" title already used -> "(old 2)"; missing scope -> needsScope message instead of a raw failure; a reward the Host already owns is just used).
Usage: python Tools/test-host-rewardpick.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX = 8976, 8977
patches = []; posts = []; mode = {'scope': False, 'wscope': False}
def rw(i, t, c):
    return {'id': i, 'title': t, 'cost': c, 'prompt': 'p-' + i, 'is_enabled': True, 'is_user_input_required': True, 'background_color': '#FF8800', 'should_redemptions_skip_request_queue': False,
            'max_per_stream_setting': {'is_enabled': True, 'max_per_stream': 5}, 'max_per_user_per_stream_setting': {'is_enabled': True, 'max_per_user_per_stream': 2},
            'global_cooldown_setting': {'is_enabled': True, 'global_cooldown_seconds': 60}}
rewards = [rw('mine', 'Hydrate', 100), rw('fsr', 'Song Request', 500), rw('fx', 'Shout', 200), rw('fx2', 'Shout (old)', 1)]
ours = {'mine'}; canrename = {'fx'}
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if mode['scope']: return self._j(401, {'message': 'Missing scope: channel:manage:redemptions'})
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self._j(200, {'data': [r for r in rewards if q.get('only_manageable_rewards') != ['true'] or r['id'] in ours]})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); posts.append(b)
        if mode['scope'] or mode['wscope']: return self._j(401, {'message': 'Missing scope: channel:manage:redemptions'})
        if any(r['title'].lower() == b['title'].lower() for r in rewards): return self._j(400, {'message': 'CREATE_CUSTOM_REWARD_DUPLICATE_REWARD'})
        n = 'new%d' % len(posts); r = dict(b, id=n, is_enabled=True); rewards.append(r); ours.add(n); self._j(200, {'data': [r]})
    def do_PATCH(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); i = q['id'][0]; patches.append((i, b))
        if mode['scope'] or mode['wscope']: return self._j(401, {'message': 'Missing scope: channel:manage:redemptions'})
        if i not in canrename: return self._j(403, {'message': 'The Client-Id header must match the client ID used to create the custom reward'})
        r = [x for x in rewards if x['id'] == i][0]; r['title'] = b['title']; r['is_enabled'] = b['is_enabled']; self._j(200, {'data': [r]})
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', HX), Hx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgrp_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def act(i, t): return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'redeem', 'title': t}], 'steps': [{'type': 'log', 'text': 'x'}]}
json.dump({'actions': [act('spotify-redeem', 'Song Request'), act('a-hyd', 'x'), act('a-shout', 'Shout'), act('a-sc', 'z')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8979', 'PINGUINO_REFUND_POLL_SEC': '300'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def api(p, body=None):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=20))
def trig(i): return [x for x in api('/api/automations')['doc']['actions'] if x['id'] == i][0]['triggers'][0]
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    r = api('/api/rewards'); chk('list has owned flags', {x['id']: x['owned'] for x in r['rewards']} == {'mine': True, 'fsr': False, 'fx': False, 'fx2': False}, r)
    r = api('/api/rewards/use', {'rewardId': 'mine', 'automation': 'a-hyd'}); t = trig('a-hyd')
    chk('use: Host-owned reward points the automation at it (any automation, not only songs)', r['ok'] and r['owned'] and t['rewardId'] == 'mine' and t['title'] == 'Hydrate', (r, t))
    r = api('/api/rewards/use', {'rewardId': 'fsr'}); chk('use: foreign reward asks for takeover, nothing changed', r['ok'] is False and r['needsTakeover'] and 'Streamer.bot' in r['error'] and 'rewardId' not in trig('spotify-redeem'), r)
    r = api('/api/rewards/use', {'rewardId': 'nope'}); chk('use: unknown id', r['ok'] is False, r)
    # take over a reward that cannot be renamed (the normal case)
    r = api('/api/rewards/takeover', {'rewardId': 'fsr'}); t = trig('spotify-redeem')
    chk('takeover (rename refused): copy made, titled (Host), manual step said clearly', r['ok'] and r['created'] and r['oldRenamed'] is False and r['title'] == 'Song Request (Host)' and r['manualStep'] and 'Twitch dashboard' in r['message'], r)
    chk('takeover: automation points at the copy', t['rewardId'] == r['id'] and t['title'] == 'Song Request (Host)', t)
    b = posts[-1]
    chk('copy has same cost/prompt/colour/queue flag/cooldown/limits', b['cost'] == 500 and b['prompt'] == 'p-fsr' and b['background_color'] == '#FF8800' and b['is_user_input_required'] is True and b['is_max_per_stream_enabled'] and b['max_per_stream'] == 5
        and b['is_max_per_user_per_stream_enabled'] and b['max_per_user_per_stream'] == 2 and b['is_global_cooldown_enabled'] and b['global_cooldown_seconds'] == 60 and b['should_redemptions_skip_request_queue'] is False, b)
    chk('rename tried exactly once, no spam', [p for p in patches if p[0] == 'fsr'] == [('fsr', {'title': 'Song Request (old)', 'is_enabled': False})], patches)
    # a rename that Twitch allows, with "(old)" already taken -> "(old 2)"
    n = len(patches); r = api('/api/rewards/takeover', {'rewardId': 'fx', 'automation': 'a-shout'}); t = trig('a-shout')
    chk('takeover (rename allowed): old renamed "(old 2)" because "(old)" exists, disabled; copy keeps the title', r['ok'] and r['oldRenamed'] and r['oldNewTitle'] == 'Shout (old 2)' and r['title'] == 'Shout' and 'manualStep' not in r and patches[n] == ('fx', {'title': 'Shout (old 2)', 'is_enabled': False}), (r, patches[n:]))
    chk('takeover: a-shout follows the copy', t['rewardId'] == r['id'] and t['title'] == 'Shout', t)
    # a reward the Host already owns: takeover just uses it
    np_ = len(posts); r = api('/api/rewards/takeover', {'rewardId': 'mine', 'automation': 'a-hyd'}); chk('takeover of an owned reward = use', r['ok'] and r.get('already') and len(posts) == np_, r)
    # missing scope
    mode['scope'] = True; np_, nq = len(posts), len(patches)
    for path in ('/api/rewards/use', '/api/rewards/takeover'):
        r = api(path, {'rewardId': 'fsr', 'automation': 'a-sc'}); chk(path + ' missing scope: friendly message, no crash', r['ok'] is False and r.get('needsScope') and 'sign in as streamer again' in r['error'] and 'HTTP' not in r['error'], r)
    mode['scope'] = False
    chk('missing scope: nothing written', len(posts) == np_ and len(patches) == nq)
    # scope missing only for writing (reads fine, the rename/create answers 401)
    mode['wscope'] = True; r = api('/api/rewards/takeover', {'rewardId': 'fsr', 'automation': 'a-sc'})
    chk('write-only missing scope: friendly message, nothing created', r['ok'] is False and r.get('needsScope') and 'HTTP' not in r['error'] and len(posts) == np_, r)
finally:
    host.kill(); time.sleep(0.5); print(open(out, "rb").read().decode("utf-8", "replace")[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS rewardpick'); sys.exit(1 if fails else 0)
