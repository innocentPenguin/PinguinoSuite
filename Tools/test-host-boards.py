"""Leaderboard totals: gifts (bomb counted once), bits, messages, watch streaks; bots/practice/anonymous left out; pushed to the site. Usage: python Tools/test-host-boards.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8961; FAKE = 8962; B = 'http://127.0.0.1:%d' % PORT
got = []; asked = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        import urllib.parse
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); asked.extend(q.get('login', []))
        disp = {'generous': 'GeNeRoUs', 'cyfirl': 'CyFiRL', 'sg_yen': 'SG_Yen', 'bitty': 'bitty'}
        body = json.dumps({'data': [{'login': l, 'display_name': disp[l]} for l in q.get('login', []) if l in disp]}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        got.append((self.path, self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
srv = HTTPServer(('127.0.0.1', FAKE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgboards_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'faketoken', 'ClientId': 'cid', 'BroadcasterId': '99'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'ForwardToSite': False, 'SiteSupportersUrl': 'http://127.0.0.1:%d/api/bot/supporters' % FAKE, 'SiteBoardsUrl': 'http://127.0.0.1:%d/api/bot/boards' % FAKE, 'SiteEventsUrl': 'http://127.0.0.1:%d/api/bot/events' % FAKE}, open(os.path.join(d, 'latest_settings.json'), 'w'))
t0 = 1771300000
ev = [{'At': t0, 'Type': 'gift', 'User': 'generous', 'Amount': 5, 'To': ''}] + [{'At': t0 + 1, 'Type': 'gift', 'User': 'generous', 'Amount': 1, 'To': 'r%d' % i} for i in range(5)] + \
     [{'At': t0 + 500, 'Type': 'gift', 'User': 'generous', 'Amount': 1, 'To': 'solo1'}, {'At': t0 + 900, 'Type': 'gift', 'User': 'anonymous', 'Amount': 9, 'To': ''},
      {'At': t0 + 10, 'Type': 'cheer', 'User': 'bitty', 'Amount': 100, 'To': ''}, {'At': t0 + 99, 'Type': 'cheer', 'User': 'bitty', 'Amount': 250, 'To': ''}, {'At': t0 + 20, 'Type': 'cheer', 'User': 'nightbot', 'Amount': 5000, 'To': ''},
      {'At': t0 + 30, 'Type': 'sub', 'User': 'subber', 'Amount': 1, 'To': ''},
      {'At': t0 + 2000, 'Type': 'gift', 'User': 'cyfirl', 'Amount': 3, 'To': ''}, {'At': t0 + 3000, 'Type': 'gift', 'User': 'sg_yen', 'Amount': 2, 'To': ''}, {'At': t0 + 3100, 'Type': 'cheer', 'User': 'sg_yen', 'Amount': 1500, 'To': ''}, {'At': t0 + 3200, 'Type': 'cheer', 'User': 'cyfirl', 'Amount': 100, 'To': ''}]
json.dump(ev, open(os.path.join(d, 'chat_events.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
for u, n in (('talker', 500), ('generous', 20), ('nightbot', 99999), ('trial', 4000), ('practice01', 5), ('silent', 0), ('bitty', 10), ('cyfirl', 600), ('sg_yen', 60)):
    json.dump({'login': u, 'name': (u if u in ('generous', 'cyfirl') else u.capitalize()), 'activity': {'messages': n}, 'roles': ({'mod': True, 'sub': True, 'subTier': 2} if u == 'bitty' else {})}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
os.makedirs(os.path.join(d, 'streaks'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8963'; env['BOT_API_KEY'] = 'testkey'; env['PINGUINO_HELIX_BASE'] = 'http://127.0.0.1:%d/helix' % FAKE
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=15))
def post(p, body=b'{}'):
    rq = urllib.request.Request(B + p, data=body, headers={'Content-Type': 'application/json', 'Origin': B}); return json.load(urllib.request.urlopen(rq, timeout=30))
def say(line): host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(0.4)
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    say('@msg-id=viewermilestone;msg-param-category=watch-streak;msg-param-id=s1;msg-param-value=33;login=talker;display-name=Talker;tmi-sent-ts=1792500000000 :tmi.twitch.tv USERNOTICE #trial :x')
    say('event TwitchCheer talker 40')
    a = post('/api/boards/refresh'); u = a['users']
    chk('gift bomb counted once (5 + 1 standalone), recipient lines not added again', u['generous']['gifts'] == 6)
    chk('anonymous gifter left out', 'anonymous' not in u)
    chk('bits summed per person', u['bitty']['bits'] == 350)
    chk('bots and practice players are left out', 'nightbot' not in u and 'practice01' not in u)
    chk('messages come from the profiles; zero-message people are not listed', u['talker']['messages'] == 500 and 'silent' not in u)
    chk('watch streak data included', u['talker']['streakBest'] == 33 and u['talker']['streakCurrent'] == 33 and u['talker']['streakAt'].startswith('2026-10-'))
    chk('the streamer is flagged and kept out of the top lists', u['trial'].get('streamer') is True and all(x['login'] != 'trial' for x in a['top']['messages']))
    chk('top lists ranked', a['top']['messages'][0]['login'] == 'cyfirl' and a['top']['bits'][0]['login'] == 'cyfirl' and a['top']['gifts'][0]['login'] == 'generous')
    time.sleep(1); pushed = [g for g in got if g[0] == '/api/bot/supporters']
    chk('gifts and bits pushed to /api/bot/supporters with the key', len(pushed) >= 1 and pushed[-1][1] == 'Bearer testkey' and pushed[-1][2]['gifts'] == {'generous': 6, 'cyfirl': 5} and pushed[-1][2]['bits'].get('bitty') == 350 and pushed[-1][2]['bits'].get('cyfirl') == 1600 and 'sg_yen' not in pushed[-1][2]['gifts'])
    chk('bots, practice players and the streamer are not in the push', all(k not in pushed[-1][2]['gifts'] and k not in pushed[-1][2]['bits'] for k in ('nightbot', 'practice01', 'trial')))
    bp = [g for g in got if g[0] == '/api/bot/boards']
    chk('the full board is pushed too, with streaks and messages, without the streamer', len(bp) >= 1 and bp[-1][1] == 'Bearer testkey' and bp[-1][2]['users']['talker']['streakBest'] == 33 and bp[-1][2]['users']['talker']['messages'] == 500 and 'trial' not in bp[-1][2]['users'] and 'nightbot' not in bp[-1][2]['users'])
    n = len(pushed); post('/api/boards/refresh'); time.sleep(1)
    chk('unchanged totals are not pushed again', len([g for g in got if g[0] == '/api/bot/supporters']) == n and len([g for g in got if g[0] == '/api/bot/boards']) == len(bp))
    pb = json.load(open(os.path.join(d, 'profiles', 'bitty.json')))['roles']
    chk('bits badge tier written next to the mod and sub roles (350 bits -> 100)', pb['bitsBadge'] == 100 and pb['bitsTotal'] == 350 and pb['mod'] is True and pb['sub'] is True and pb['subTier'] == 2)
    chk('people without bits get no bits role', 'bitsBadge' not in json.load(open(os.path.join(d, 'profiles', 'generous.json')))['roles'])
    chk('/api/boards shows the push result', get('/api/boards')['push']['note'] != 'not pushed yet' and get('/api/boards')['users']['bitty']['bitsBadge'] == 100)
    time.sleep(1.5); a2 = get('/api/boards'); u2 = a2['users']
    chk('sg_yen is folded into cyfirl: gifts, bits and messages combined, alias hidden', 'sg_yen' not in u2 and u2['cyfirl']['gifts'] == 5 and u2['cyfirl']['bits'] == 1600 and u2['cyfirl']['messages'] == 660 and u2['cyfirl']['aka'] == ['sg_yen'])
    chk('the merged person carries the combined bits badge (1600 -> 1000)', u2['cyfirl']['bitsBadge'] == 1000)
    chk('real Twitch capitalisation is used from Helix (and cached, one ask per login)', u2['generous']['name'] == 'GeNeRoUs' and u2['cyfirl']['name'] == 'CyFiRL' and asked.count('generous') == 1 and 'talker' not in asked)
    chk('aliases.json and names.json are written', os.path.exists(os.path.join(d, 'boards', 'aliases.json')) and os.path.exists(os.path.join(d, 'boards', 'names.json')))
    chk('the same totals are served on /api/boards', get('/api/boards')['users']['bitty']['bits'] == 350)
finally:
    host.kill(); srv.shutdown(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
