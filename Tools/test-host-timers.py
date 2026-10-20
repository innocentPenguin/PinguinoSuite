"""Chat timers: persisted state, rotate/random/all, live-only, min chat messages, global gap, !timer mod commands, /api/timers.
Usage: python Tools/test-host-timers.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8997; HX = 8998; B = 'http://127.0.0.1:%d' % PORT
chats = []; t0 = time.time()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}')
        if self.path.endswith('/chat/messages'): chats.append((time.time() - t0, b.get('message', '')))
        self._send({'data': [{'is_sent': True}]})
    def do_GET(self): self._send({'data': []})
srv = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgtim_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
def start(live):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8999', 'PINGUINO_TIMERS_FAST': '1', 'PINGUINO_TIMERS_LIVE': live, 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def feed(h, line): h.stdin.write((line + '\n').encode()); h.stdin.flush()
def says(): return [l[6:] for l in open(os.path.join(d, 'out.txt'), encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def texts(since=0): return [m for t, m in chats if t >= since]
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra, 'chats:', [m for _, m in chats][-8:])
host = start('1')
try:
    r = api('/api/timers')
    chk('three disabled sample timers are seeded', r['ok'] and len(r['timers']) == 3 and all(not t['enabled'] for t in r['timers']), r)
    time.sleep(2.5); chk('disabled timers never fire', texts() == [])
    api('/api/timers', {'globalGapSec': 0})
    r = api('/api/timers', {'timer': {'id': 'rot', 'name': 'Rotate', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'mode': 'rotate', 'messages': ['A one', 'B two', 'C three']}})
    s0 = time.time() - t0; time.sleep(6.5)
    got = texts(s0)
    chk('rotate: the messages go out in order and wrap around', len(got) >= 4 and got[:4] == ['A one', 'B two', 'C three', 'A one'], got)
    api('/api/timers', {'id': 'rot', 'enabled': False})
    def saved():
        for _ in range(10):
            try: x = json.load(open(os.path.join(d, 'timers.json')))['timers']; return [i for i in x if i['id'] == 'rot'][0]['lastRun'] > 0
            except Exception: time.sleep(0.2)
        return False
    chk('persisted state: lastRun is in timers.json', saved())
    # min chat messages
    api('/api/timers', {'timer': {'id': 'gate', 'name': 'Gate', 'enabled': True, 'everySec': 1, 'minChatMessages': 3, 'messages': ['gated']}})
    s1 = time.time() - t0; time.sleep(2.5)
    chk('minChatMessages: nothing without chat', 'gated' not in texts(s1))
    for i in range(3): feed(host, 'viewer%d: hello there' % i)
    time.sleep(2.0)
    chk('minChatMessages: fires once enough chat came', 'gated' in texts(s1))
    api('/api/timers', {'id': 'gate', 'enabled': False})
    # all mode
    s2 = time.time() - t0
    api('/api/timers', {'timer': {'id': 'allm', 'name': 'All', 'enabled': True, 'everySec': 1, 'mode': 'all', 'minChatMessages': 0, 'messages': ['all-1', 'all-2']}})
    time.sleep(3.5); g = texts(s2)
    chk('mode all: every message goes out', 'all-1' in g and 'all-2' in g, g)
    api('/api/timers', {'id': 'allm', 'enabled': False})
    # global gap
    api('/api/timers', {'globalGapSec': 3})
    s3 = time.time() - t0
    for nm in ('g1', 'g2'): api('/api/timers', {'timer': {'id': nm, 'name': nm, 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': [nm + '-msg']}})
    time.sleep(9); gs = [(t, m) for t, m in chats if t >= s3 and m.endswith('-msg')]
    gaps = [b[0] - a[0] for a, b in zip(gs, gs[1:])]
    chk('global gap: two due timers never fire closer than the gap', len(gs) >= 3 and all(g >= 2.7 for g in gaps), gaps)
    for nm in ('g1', 'g2'): api('/api/timers', {'id': nm, 'enabled': False})
    api('/api/timers', {'globalGapSec': 0})
    # mod commands
    n0 = len(chats)
    def say(line, wait=0.8): feed(host, line); time.sleep(wait)
    s0n = len(says()); say('viewer1: !timer list'); chk('viewers get nothing from !timer', len(says()) == s0n)
    say('*mod1: !timer add 60 hydrate or die'); say('*mod1: !timer list')
    msgs = says()
    chk('!timer add / list', any("added: every 60 min" in m for m in msgs) and any('hydrate' in m for m in msgs), msgs[-3:])
    tid = [t for t in api('/api/timers')['timers'] if t['messages'] == ['hydrate or die']][0]['id']
    say('*mod1: !timer now ' + tid); chk('!timer now sends it immediately', 'hydrate or die' in texts(0))
    say('*mod1: !timer off ' + tid); chk('!timer off', [t for t in api('/api/timers')['timers'] if t['id'] == tid][0]['enabled'] is False)
    say('*mod1: !timer gap 90'); chk('!timer gap', api('/api/timers')['globalGapSec'] == 90)
    say('*mod1: !timer remove ' + tid); chk('!timer remove', all(t['id'] != tid for t in api('/api/timers')['timers']))
    api('/api/timers', {'globalGapSec': 0})
    # restart: persisted state, nothing fires at once, offline gate
    api('/api/timers', {'timer': {'id': 'keep', 'name': 'Keep', 'enabled': True, 'everySec': 1, 'minChatMessages': 0, 'messages': ['kept']}})
    time.sleep(1.5); host.kill(); time.sleep(1.0)
    host = start('0'); s4 = time.time() - t0; time.sleep(3.0)
    chk('restart keeps the timers; offline (onlineOnly) fires nothing', any(t['id'] == 'keep' for t in api('/api/timers')['timers']) and 'kept' not in texts(s4), texts(s4))
    api('/api/timers', {'timer': {'id': 'keep', 'onlineOnly': False}}); time.sleep(2.5)
    chk('onlineOnly=false fires even offline', 'kept' in texts(s4))
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
