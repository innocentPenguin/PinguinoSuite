"""Simulated players: /api/sim/* (start/add/remove/join/leave/tick/clear/config/status), names from the site pool (cached), sim players on the wheel + queue (join/leave feed), separate sim ledger + gambling,
silent in chat, sim:true on what Core pushes to the site, sendSimToSite OFF leaves them out, refuses to start / stops when the real stream is live, and the LEAK test: real ledger + saved files unchanged.
Usage: python Tools/test-host-sim.py [dll]"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, SITE = 8976, 8977; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsim_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'simt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'WebSyncUrl': 'http://127.0.0.1:%d' % SITE, 'WebSyncKey': 'k'}, open(os.path.join(d, 'settings.json'), 'w'))
SITE_NAMES = ['Aurora1', 'Borealis2', 'Cinder3', 'Drift4', 'Eclipse5', 'Fjord6', 'Glacier7', 'Harbor8', 'Iris9', 'Jade10', 'Kelp11', 'Lagoon12', 'Mesa13', 'Nimbus14', 'Opal15', 'Pebble16']
POSTS = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/api/bot/names'): return self._send({'names': SITE_NAMES})
        if self.path.startswith('/api/bot/commands'): return self._send({'commands': []})
        self._send({})
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0); body = self.rfile.read(n).decode('utf-8', 'replace')
        try: POSTS.append((self.path, json.loads(body)))
        except Exception: POSTS.append((self.path, None))
        self._send({'ok': True})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8978', 'PINGUINO_LIVE': '0', 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': 'testkey'})
fails = []; h = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=15))
def post(p, o=None): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o or {}).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=30))
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def start(extra=None):
    e = dict(env); e.update(extra or {})
    p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=e, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2); return p
def feed(l, w=1.0): h.stdin.write((l + '\n').encode()); h.stdin.flush(); time.sleep(w)
def files():
    r = {}
    for root, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in ('logs', 'console', 'sim')]
        for f in fs:
            if f in ('out.txt',) or f.endswith('.tmp') or f.endswith('.log') or f.endswith('.jsonl'): continue
            p = os.path.join(root, f); rel = os.path.relpath(p, d)
            try: r[rel] = hashlib.md5(open(p, 'rb').read()).hexdigest()
            except OSError: pass
    return r
def runtime(name):
    for root in (d, os.path.join(d, 'runtime')):
        p = os.path.join(root, name)
        if os.path.exists(p): return json.load(open(p, encoding='utf-8-sig'))
    return None
def waitfor(f, secs=20):
    for _ in range(secs * 2):
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.5)
    return False
def last_post(path, since=0):
    xs = [b for (p, b) in POSTS[since:] if p == path and b is not None]; return xs[-1] if xs else None
try:
    h = start(); time.sleep(1)
    feed('#ivan: !queue open'); feed('viewer1: !register vone'); feed('viewer2: !register vtwo'); feed('viewer1: !join'); feed('#ivan: !wheel open'); feed('viewer1: !me')
    time.sleep(6)   # let the real sign-ups reach disk and the first pushes settle
    real_before = files(); says_before = len(says())
    st = get('/api/sim/status'); chk('off by default', st['on'] is False and st['simulation'] is False and st['count'] == 0, st)
    chk('flag in /api/live + /api/status', get('/api/live')['simulation'] is False and get('/api/status')['simulation'] is False)
    r = post('/api/sim/add', {'n': 2}); chk('add while off refused', r['ok'] is False, r)
    r = post('/api/sim/start', {'count': 10, 'mode': 'both'}); chk('start', r['ok'] and r['on'] and r['count'] == 10 and r['namesSource'] == 'site', r)
    names = [p['name'] for p in r['players']]; chk('names come from the site pool', all(n in SITE_NAMES for n in names), names)
    chk('names cached', os.path.exists(os.path.join(d, 'sim', 'names.json')) and len(json.load(open(os.path.join(d, 'sim', 'names.json')))['names']) == 16)
    chk('flag on', get('/api/live')['simulation'] is True and get('/api/status')['simulation'] is True)
    chk('queue got the sim players', waitfor(lambda: get('/api/sim/status')['queueSim'] == 10), get('/api/sim/status'))
    chk('wheel got them (+1 real)', waitfor(lambda: get('/api/sim/status')['wheelSignedUp'] == 11), get('/api/sim/status'))
    chk('start twice refused', post('/api/sim/start', {'count': 3})['ok'] is False)
    chk('silent in chat', len(says()) == says_before, says()[says_before:])
    # join / leave with the wheel feed
    r = post('/api/sim/join', {'names': ['Quartz17', 'Raven18']}); chk('join names', r['ok'] and r['count'] == 12, r)
    r = post('/api/sim/leave', {'names': ['Quartz17']}); chk('leave name', r['ok'] and r['count'] == 11, r)
    time.sleep(2); wp = runtime('wheel_public.json'); kinds = [(f['name'], f['kind']) for f in wp.get('feed', [])]
    chk('join/leave feed', ('Quartz17', 'join') in kinds and ('Quartz17', 'leave') in kinds and wp['signedUp'] == 12, kinds)
    r = post('/api/sim/add', {'n': 2}); chk('add', r['ok'] and r['count'] == 13, r); r = post('/api/sim/remove', {'n': 3}); chk('remove', r['ok'] and r['count'] == 10, r)
    # sim ledger + gambling: the real ledger never moves
    r = post('/api/sim/config', {'startBalance': 500, 'earnPerMin': 60, 'gambling': True}); chk('config', r['ok'] and r['startBalance'] == 500, r)
    for _ in range(40): post('/api/sim/tick')
    st = get('/api/sim/status'); chk('sim bets happened', st['stats']['bets'] >= 5, st['stats'])
    chk('balances moved on the sim ledger only', any(p['points'] != 1000 for p in st['players']), [p['points'] for p in st['players']])
    chk('gamble output stayed out of chat', len(says()) == says_before, says()[says_before:])
    chk('real viewers unaffected', True)
    for bad in [{'churnPerMin': -1}, {'sendSimToSite': 'x'}, {'nope': 1}]: chk('config refused %s' % list(bad), post('/api/sim/config', bad)['ok'] is False)
    # what Core pushes to the site: tagged sim:true, then left out
    n0 = len(POSTS); time.sleep(2); feed('viewer2: !join', 3); post('/api/sim/join', {'names': ['Slate19']}); time.sleep(4)
    stp = last_post('/api/bot/state', n0); whp = last_post('/api/bot/wheel', n0)
    chk('state push tagged', stp and stp.get('sim') is True and any(q.get('sim') is True for q in stp['queue']) and any(not q.get('sim') for q in stp['queue']), json.dumps([stp.get('sim'), stp['queue'][:3]]) if stp else None)
    chk('wheel push tagged', whp and whp.get('sim') is True and any(q.get('sim') for q in whp['queue']), json.dumps(whp)[:200] if whp else None)
    r = post('/api/sim/config', {'sendSimToSite': False}); chk('site off', r['ok'] and r['sendSimToSite'] is False, r)
    n1 = len(POSTS); time.sleep(5); stp = last_post('/api/bot/state', n1); whp = last_post('/api/bot/wheel', n1)
    chk('site off: state without sim', stp and not stp.get('sim') and not any(q.get('sim') for q in stp['queue']) and 'Slate19' not in json.dumps(stp) and any(q['user'] == 'viewer1' for q in stp['queue']), json.dumps([stp.get('sim'), stp['queue'][:3]]) if stp else None)
    chk('site off: wheel hidden', whp and whp['status'] == 'none' and not whp.get('sim'), json.dumps(whp)[:200] if whp else None)
    chk('local overlay still shows them', runtime('wheel_public.json')['signedUp'] >= 10)
    post('/api/sim/config', {'sendSimToSite': True}); n2 = len(POSTS); time.sleep(5); whp = last_post('/api/bot/wheel', n2)
    chk('site back on', whp and whp.get('sim') is True and whp['status'] != 'none', json.dumps(whp)[:200] if whp else None)
    # spin the wheel with sim players: team lines for sim players never reach chat
    feed('#ivan: !wheel speed 1500'); feed('#ivan: !wheel mode random'); feed('#ivan: !wheel size 2')
    for _ in range(12): feed('#ivan: !wheel spin', 1.9)
    time.sleep(4); wp = runtime('wheel_public.json')
    chk('wheel drew', wp['status'] in ('drawing', 'final'), wp['status'])
    chk('no team lines in chat', not any(__import__('re').match(r'Team \d+:', s) or 'TOURNAMENT TEAMS' in s for s in says()), [s for s in says() if 'Team' in s])
    # clear: everything back
    n3 = len(POSTS); r = post('/api/sim/clear'); chk('clear', r['ok'] and r['on'] is False and r['count'] == 0, r)
    time.sleep(6); stp = last_post('/api/bot/state', n3)
    chk('site state is clean after clear', stp and not stp.get('sim') and not any(q.get('sim') for q in stp['queue']) and not stp.get('practice'), json.dumps(stp)[:300] if stp else None)
    chk('flag off', get('/api/live')['simulation'] is False)
    chk('sim ledger gone', post('/api/sim/tick')['ok'] is False)
    # leak test: nothing real changed (apart from files the REAL viewers legitimately touched)
    real_after = files()
    leaked = [k for k, v in real_after.items() if 'sim_' in open(os.path.join(d, k), encoding='utf-8-sig', errors='replace').read() and not k.endswith('names.json')]
    chk('no sim_ in any saved file', not leaked, leaked)
    chk('real ledger unchanged', real_after.get(os.path.join('economy', 'points.json')) == real_before.get(os.path.join('economy', 'points.json')) and real_after.get(os.path.join('runtime', 'economy', 'points.json')) == real_before.get(os.path.join('runtime', 'economy', 'points.json')))
    for f in ['players.json', 'matches.json', 'queue.json']:
        a = real_before.get(f) or real_before.get(os.path.join('runtime', f)); b = real_after.get(f) or real_after.get(os.path.join('runtime', f))
        txt = open(os.path.join(d, f if f in real_after else os.path.join('runtime', f)), encoding='utf-8-sig').read() if (f in real_after or os.path.join('runtime', f) in real_after) else ''
        chk('%s has no sim players' % f, 'sim' not in txt.lower())
    chk('viewer1 still queued and signed up', any(q['user'] == 'viewer1' for q in runtime('live_state.json')['queue']))
    # churn loop
    r = post('/api/sim/start', {'count': 4}); chk('restart sim', r['ok'] and r['count'] == 4, r)
    post('/api/sim/config', {'churnPerMin': 120}); chk('churn changes the crowd by itself', waitfor(lambda: get('/api/sim/status')['stats']['joins'] + get('/api/sim/status')['stats']['leaves'] > 6, 40), get('/api/sim/status')['stats'])
    h.kill(); time.sleep(1)
    # the real stream is live: refuses to start
    h = start({'PINGUINO_LIVE': '1'}); time.sleep(8)
    r = post('/api/sim/start', {'count': 5}); chk('refuses while the real stream is live', r['ok'] is False and 'live' in r['error'], r)
    feed('viewer3: !queue', 3)   # Core starts on the first message and writes the real state over any leftover sim files
    chk('nothing queued', get('/api/sim/status')['queueSim'] == 0 and get('/api/sim/status')['on'] is False)
finally:
    if h: h.kill()
    srv.shutdown(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS sim'); sys.exit(1 if fails else 0)
