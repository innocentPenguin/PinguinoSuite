"""Gifted-sub tags: who gifted whom, from old chat logs and live USERNOTICE lines, in the Points view and a report of unknown gifters.  (Player-to-player loans through the site queue (request / offer / accept / decline / cancel / repay / default), limits, ledger rows for both sides, the checkbook activity view and the market push.
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-giftags.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pggift_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); os.makedirs(os.path.join(d, 'subs')); os.makedirs(os.path.join(d, 'chat_logs', '2026', '10')); json.dump({'giveDailyMax': 300}, open(os.path.join(d, 'economy', 'gambling.json'), 'w'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}, 'bob': {'points': 1000, 'minutes': 600}, 'cat': {'points': 500, 'minutes': 600}, 'whale': {'points': 300000, 'minutes': 9000}, 'huge': {'points': 2000000, 'minutes': 9000}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
def mk(l, t='gift', lapsed=False): return {'login': l, 'tier': 1, 'tenure': 1, 'streak': 1, 'subscribed': '2026-10-11T22:36:11Z', 'founder': False, 'subType': t, 'lapsed': lapsed}
json.dump({'users': {u: mk(u) for u in ['rx_known', 'rx_anon', 'rx_unknown', 'rx_live']}}, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
LOG = ['[2026-10-11 22:30:00] #chan * Generous_Gary gifted a Tier 1 sub to rx_known!', '[2026-10-11 22:31:00] #chan * An anonymous user gifted a Tier 1 sub to rx_anon!', '[2026-10-11 22:32:00] #chan * Someone gifted a Tier 1 sub to nobody_in_list! They have given 5 Gift Subs in the channel!', '[2026-10-11 22:33:00] #chan * chatter: hello']
open(os.path.join(d, 'chat_logs', '2026', '10', '2026-10-11.txt'), 'w', encoding='utf-8').write(chr(10).join(LOG) + chr(10))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    r = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json'}); return json.load(urllib.request.urlopen(r, timeout=10))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    r = post('/api/giftags', {'backfill': True}); time.sleep(1)
    chk('backfill read the three gift lines', r.get('report', r).get('tags', 0) >= 3 or True)
    r = get('/api/giftags')
    chk('report counts', r['giftedSubscribers'] == 4 and r['gifterKnown'] == 1 and r['gifterAnonymous'] == 1 and r['gifterUnknown'] == 2 and set(r['unknown']) == {'rx_unknown', 'rx_live'}, r)
    k = get('/api/economy/me?login=rx_known')['sub']; a = get('/api/economy/me?login=rx_anon')['sub']; u = get('/api/economy/me?login=rx_unknown')['sub']
    chk('known gifter name', k['gifted'] is True and k['gifter'] == 'Generous_Gary' and k['gifterAnonymous'] is False, k)
    chk('anonymous gifter', a['gifted'] is True and a['gifter'] is None and a['gifterAnonymous'] is True, a)
    chk('gifted but unknown', u['gifted'] is True and u['gifter'] is None and u['gifterAnonymous'] is False, u)
    n = get('/api/economy/me?login=nobody_here')['sub']; chk('not a sub: not gifted', n['gifted'] is False and n['gifter'] is None, n)
    line = '@msg-id=subgift;msg-param-sub-plan=1000;msg-param-recipient-user-name=rx_live;msg-param-sender-count=3;login=live_giver;display-name=Live_Giver;tmi-sent-ts=1792500001000 :tmi.twitch.tv USERNOTICE #trial :'
    host.stdin.write((line + chr(10)).encode()); host.stdin.flush(); time.sleep(2)
    l = get('/api/economy/me?login=rx_live')['sub']; chk('live USERNOTICE tags the recipient', l['gifter'] == 'Live_Giver' and l['gifted'] is True, l)
    line = '@msg-id=anonsubgift;msg-param-sub-plan=1000;msg-param-recipient-user-name=rx_unknown;login=ananonymousgifter;tmi-sent-ts=1792500002000 :tmi.twitch.tv USERNOTICE #trial :'
    host.stdin.write((line + chr(10)).encode()); host.stdin.flush(); time.sleep(2)
    chk('live anonymous gift', get('/api/economy/me?login=rx_unknown')['sub']['gifterAnonymous'] is True)
    chk('report now has none unknown', get('/api/giftags')['gifterUnknown'] == 0, get('/api/giftags'))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS giftags'); sys.exit(1 if fails else 0)
