"""Mod activity feed: channel events become feed items pushed (whole window, newest first) to POST /api/bot/activity.  (Player-to-player loans through the site queue (request / offer / accept / decline / cancel / repay / default), limits, ledger rows for both sides, the checkbook activity view and the market push.
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-activity.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pgact_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); json.dump({'giveDailyMax': 300}, open(os.path.join(d, 'economy', 'gambling.json'), 'w'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}, 'bob': {'points': 1000, 'minutes': 600}, 'cat': {'points': 500, 'minutes': 600}, 'whale': {'points': 300000, 'minutes': 9000}, 'huge': {'points': 2000000, 'minutes': 9000}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
S = {'pushes': []}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self.send(200, {'requests': [], 'entries': []})
    def do_POST(self):
        if self.headers.get('Authorization') != 'Bearer ' + KEY: return self.send(401, {})
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/bot/activity': S['pushes'].append(b)
        self.send(200, {'ok': True})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY, 'PINGUINO_SITE_POLL_SEC': '1', 'PINGUINO_ACTIVITY_PUSH_SEC': '1', 'PINGUINO_ACTIVITY_SIM': '1'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def ev(t, j):
    host.stdin.write(('eventsub ' + t + ' ' + json.dumps(j) + chr(10)).encode()); host.stdin.flush()
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(12)
    ev('channel.follow', {'user_login': 'newfollower'}); time.sleep(1.2)
    ev('channel.subscription.message', {'user_login': 'bob', 'tier': '2000', 'cumulative_months': 14, 'streak_months': 6, 'message': {'text': 'hi'}}); time.sleep(1.2)
    ev('channel.subscription.gift', {'user_login': 'gifty', 'tier': '1000', 'total': 5, 'is_anonymous': False}); time.sleep(1.2)
    ev('channel.cheer', {'user_login': 'cheerer', 'bits': 500}); time.sleep(1.2)
    ev('channel.raid', {'from_broadcaster_user_login': 'bigstreamer', 'to_broadcaster_user_id': '1', 'viewers': 42}); time.sleep(1.2)
    ev('channel.channel_points_custom_reward_redemption.add', {'user_login': 'redeemer', 'id': 'rd1', 'reward': {'title': 'Hydrate', 'cost': 100, 'id': 'r1'}}); time.sleep(1.2)
    ev('channel.hype_train.end', {'level': 3, 'id': 'h1', 'total': 900}); time.sleep(6)
    p = S['pushes']; chk('feed pushed', len(p) >= 1, p)
    items = p[-1]['items']
    types = [x['type'] for x in items]
    chk('newest first, all types', types[:7] == ['hype', 'redemption', 'raid_in', 'bits', 'gift', 'resub', 'follow'], types)
    by = {x['type']: x for x in items}
    chk('resub label + tier + months', by['resub']['label'] == 'bob resubbed (14 months)' and by['resub']['tier'] == '2000' and by['resub']['amount'] == 14, by['resub'])
    chk('gift count', by['gift']['amount'] == 5 and 'gifted 5 subs' in by['gift']['label'], by['gift'])
    chk('bits, raid, redemption, hype', by['bits']['amount'] == 500 and by['raid_in']['amount'] == 42 and by['redemption']['extra'] == 'Hydrate' and by['hype']['amount'] == 3, [by['bits'], by['raid_in'], by['redemption'], by['hype']])
    chk('ids unique and stable', len({x['id'] for x in items}) == len(items) and all(x['id'] for x in items))
    chk('no personal data fields', all(set(x) <= {'id', 'at', 'type', 'user', 'label', 'amount', 'tier', 'extra'} for x in items), items[0])
    n = len(p); time.sleep(4); chk('nothing new, nothing pushed (until the 2 minute refresh)', len(S['pushes']) == n, (n, len(S['pushes'])))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS activity'); sys.exit(1 if fails else 0)
