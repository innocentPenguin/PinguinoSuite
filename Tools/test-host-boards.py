"""Leaderboard totals: gifts (bomb counted once), bits, messages, watch streaks; bots/practice/anonymous left out; pushed to the site. Usage: python Tools/test-host-boards.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8961; FAKE = 8962; B = 'http://127.0.0.1:%d' % PORT
got = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        got.append((self.path, self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
srv = HTTPServer(('127.0.0.1', FAKE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgboards_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'ForwardToSite': True, 'SiteSupportersUrl': 'http://127.0.0.1:%d/api/bot/supporters' % FAKE, 'SiteEventsUrl': 'http://127.0.0.1:%d/api/bot/events' % FAKE}, open(os.path.join(d, 'latest_settings.json'), 'w'))
t0 = 1771300000
ev = [{'At': t0, 'Type': 'gift', 'User': 'generous', 'Amount': 5, 'To': ''}] + [{'At': t0 + 1, 'Type': 'gift', 'User': 'generous', 'Amount': 1, 'To': 'r%d' % i} for i in range(5)] + \
     [{'At': t0 + 500, 'Type': 'gift', 'User': 'generous', 'Amount': 1, 'To': 'solo1'}, {'At': t0 + 900, 'Type': 'gift', 'User': 'anonymous', 'Amount': 9, 'To': ''},
      {'At': t0 + 10, 'Type': 'cheer', 'User': 'bitty', 'Amount': 100, 'To': ''}, {'At': t0 + 99, 'Type': 'cheer', 'User': 'bitty', 'Amount': 250, 'To': ''}, {'At': t0 + 20, 'Type': 'cheer', 'User': 'nightbot', 'Amount': 5000, 'To': ''},
      {'At': t0 + 30, 'Type': 'sub', 'User': 'subber', 'Amount': 1, 'To': ''}]
json.dump(ev, open(os.path.join(d, 'chat_events.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
for u, n in (('talker', 500), ('generous', 20), ('nightbot', 99999), ('trial', 4000), ('practice01', 5), ('silent', 0)):
    json.dump({'login': u, 'name': u.capitalize(), 'activity': {'messages': n}, 'roles': {}}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
os.makedirs(os.path.join(d, 'streaks'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8963'; env['BOT_API_KEY'] = 'testkey'
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
    chk('top lists ranked', a['top']['messages'][0]['login'] == 'talker' and a['top']['bits'][0]['login'] == 'bitty' and a['top']['gifts'][0]['login'] == 'generous')
    time.sleep(1); pushed = [g for g in got if g[0] == '/api/bot/supporters']
    chk('gifts and bits pushed to /api/bot/supporters with the key', len(pushed) >= 1 and pushed[-1][1] == 'Bearer testkey' and pushed[-1][2]['gifts'] == {'generous': 6} and pushed[-1][2]['bits'].get('bitty') == 350)
    chk('bots, practice players and the streamer are not in the push', all(k not in pushed[-1][2]['gifts'] and k not in pushed[-1][2]['bits'] for k in ('nightbot', 'practice01', 'trial')))
    n = len(pushed); post('/api/boards/refresh'); time.sleep(1)
    chk('unchanged totals are not pushed again', len([g for g in got if g[0] == '/api/bot/supporters']) == n)
    chk('the same totals are served on /api/boards', get('/api/boards')['users']['bitty']['bits'] == 350)
finally:
    host.kill(); srv.shutdown(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
