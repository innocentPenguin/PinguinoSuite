"""Points + watch time: StreamElements import (fake SE API: dry run, confirm, backup, re-run), earning loop (fake Helix chatters, sub multiplier, bots/streamer left out), commands, boards.
Usage: python Tools/test-host-economy.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8961; SE = 8962; HX = 8963; B = 'http://127.0.0.1:%d' % PORT
JWT = 'sekret-jwt-value-123'
state = {'chatters': ['ana', 'cyfirl', 'helperbot', 'innocentpenguin_', 'nobody1'], 'chatters_code': 200, 'points_bonus': 0}
se_log = []
POINTS = [{'username': 'Cyfirl', 'points': 1000}, {'username': 'SG_Yen', 'points': 250}, {'username': 'ana', 'points': 400}, {'username': 'streamelements', 'points': 99999}, {'username': 'NewGuy', 'points': 70}]
MINUTES = [{'username': 'cyfirl', 'minutes': 600}, {'username': 'ana', 'minutes': 1500}, {'username': 'newguy', 'minutes': 30}, {'username': 'sg_yen', 'minutes': 60}]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); self.rfile.read(n); self._send({'data': [{'is_sent': True}]})
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.startswith('/chat/chatters') or u.path.endswith('/chat/chatters'):
            if state['chatters_code'] != 200: return self._send({'message': 'missing scope'}, state['chatters_code'])
            return self._send({'data': [{'user_login': c} for c in state['chatters']]})
        if self.headers.get('Authorization') != 'Bearer ' + JWT: return self._send({'error': 'unauthorized'}, 401)
        se_log.append(u.path)
        if u.path == '/kappa/v2/channels/me': return self._send({'_id': 'chan1', 'username': 'x'})
        rows = None
        if u.path.endswith('/top'): rows = [dict(r, points=r['points'] + state['points_bonus']) for r in POINTS]
        elif u.path.endswith('/alltime'): rows = [dict(r, points=r['points'] * 2) for r in POINTS]
        elif u.path.endswith('/watchtime'): rows = MINUTES
        if rows is None: return self._send({}, 404)
        off = int(q.get('offset', ['0'])[0]); self._send({'_total': len(rows), 'users': rows[off:off + 2]})   # pages of 2 whatever the limit says
srv = http.server.ThreadingHTTPServer(('127.0.0.1', SE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
hx = http.server.ThreadingHTTPServer(('127.0.0.1', HX), H); threading.Thread(target=hx.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgeco_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'boards')); json.dump({'aliases': {'sg_yen': 'cyfirl'}}, open(os.path.join(d, 'boards', 'aliases.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
for u in ('cyfirl', 'ana', 'viewer1'): json.dump({'login': u, 'name': u.capitalize(), 'activity': {'messages': 30, 'perMonth': {}}, 'roles': {}}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
os.makedirs(os.path.join(d, 'subs')); json.dump({'version': 1, 'users': {'ana': {'login': 'ana', 'tier': 1, 'tenure': 3, 'streak': 3, 'founder': False, 'lapsed': False}}}, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
def start(extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_SE_BASE': 'http://127.0.0.1:%d/kappa/v2' % SE, 'PINGUINO_SE_JWT': JWT, 'PINGUINO_SE_DELAY_MS': '0', 'PINGUINO_COMPAT_WS_PORT': '8964',
                'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0', 'PINGUINO_SUBS_DOWNLOADS': '', 'PINGUINO_ECONOMY_LIVE': '0', 'PINGUINO_ECONOMY_MINUTE_SEC': '1', 'PINGUINO_ECONOMY_V2': '0'})
    if extra: env.update(extra)
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=60))
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def feed(h, line, wait=0.8): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait)
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra, '| says:', says()[-2:])
host = start()
try:
    a = api('/api/economy'); chk('starts empty with the SE token set', a['ok'] and a['people'] == 0 and a['seToken'] == 'set' and a['currency'] == 'points', a)
    r = api('/api/economy/import', {'mode': 'dryrun'})
    chk('dry run reads all three SE lists across pages of 2', r['ok'] and r['usersWithPoints'] == 5 and r['usersWithWatchtime'] == 4 and r['usersWithLifetime'] == 5, r)
    chk('dry run: top 10, unmatched people, folded aliases, bots', r['top10Points'][0]['login'] == 'cyfirl' and r['top10Points'][0]['points'] in (1000, 1250) and any(x['name'] == 'newguy' for x in r['unmatched']) and any('sg_yen > cyfirl' in x for x in r['aliasFolded']) and 'streamelements' in r['botsSkipped'], r)
    chk('dry run changes nothing', api('/api/economy')['people'] == 0)
    chk('the JWT is never in the report or the log', JWT not in json.dumps(r) and JWT not in open(outf, encoding='utf-8', errors='replace').read())
    chk('apply with a wrong id is refused', api('/api/economy/import', {'mode': 'apply', 'confirm': 'nope'})['ok'] is False)
    ap = api('/api/economy/import', {'mode': 'apply', 'confirm': r['id']})
    chk('apply writes the baseline (bots skipped) and there is no backup on the first import', ap['ok'] and ap['applied'] == 4 and ap['backup'] == '', ap)
    u = api('/api/economy/user?login=cyfirl')
    chk('aliases fold into the main account (cyfirl + sg_yen)', u['points'] == 1250 and u['minutes'] == 660 and u['pointsRank'] == 1, u)
    feed(host, 'viewer1: !points cyfirl'); chk('!points shows balance and rank', any('cyfirl has 1,250 points (#1 of 3)' in m for m in says()[-1:]), says()[-1:])
    feed(host, 'ana: !points'); chk('!points without a name shows your own', any('@ana you have 400 points (#2 of 3)' in m for m in says()[-1:]), says()[-1:])
    feed(host, 'ana: !watchtime'); chk('!watchtime', any('@ana you have watched 1d 1h (#1 of 3)' in m for m in says()[-1:]), says()[-1:])
    feed(host, 'viewer1: !toppoints'); chk('!toppoints', any(m.startswith('Top points (all time): 1. cyfirl 1,250 | 2. ana 400 | 3. newguy 70') for m in says()[-1:]), says()[-1:])
    feed(host, 'viewer1: !topwatch'); chk('!topwatch', any(m.startswith('Most watch time (all time): 1. ana 1d 1h') for m in says()[-1:]), says()[-1:])
    n0 = len(says()); feed(host, 'viewer1: !addpoints @ana 500'); chk('viewers cannot add points', len(says()) == n0 and api('/api/economy/user?login=ana')['points'] == 400)
    feed(host, '*mod1: !addpoints @ana 500'); chk('mods can NOT add points (broadcaster only)', api('/api/economy/user?login=ana')['points'] == 400, says()[-1:])
    n1 = len(says()); feed(host, '#ivan: !addpoints @ana 500'); chk('the broadcaster can, silently', api('/api/economy/user?login=ana')['points'] == 900 and len(says()) == n1, says()[-1:])
    feed(host, '*mod1: !removepoints @ana 50'); chk('and remove points', api('/api/economy/user?login=ana')['points'] == 850)
    feed(host, '*mod1: !economy status'); chk('!economy status', any(m.startswith('Economy: 4 people') for m in says()[-1:]) or any(m.startswith('Economy:') for m in says()[-1:]), says()[-1:])
    # boards
    bd = api('/api/boards')
    chk('boards carry points and watch minutes, plus the new lists', bd['users']['cyfirl']['points'] == 1250 and bd['users']['cyfirl']['watchMinutes'] == 660 and bd['top']['points'][0]['login'] == 'cyfirl' and bd['top']['watchtime'][0]['login'] == 'ana', {k: bd['users'].get(k) for k in ('cyfirl',)})
    # re-run: new balances, earned stays, backup made
    state['points_bonus'] = 10
    r2 = api('/api/economy/import', {'mode': 'dryrun'}); ap2 = api('/api/economy/import', {'mode': 'apply', 'confirm': r2['id']})
    chk('re-running replaces the baseline and keeps a backup', ap2['ok'] and ap2['backup'].startswith('points-') and os.path.exists(os.path.join(d, 'economy', 'backups', ap2['backup'])), ap2)
    chk('adjustments survive a re-run (ana 410 + 450)', api('/api/economy/user?login=ana')['points'] == 860, api('/api/economy/user?login=ana'))
    # earning: restart live
    host.kill(); time.sleep(1.0); host = start({'PINGUINO_ECONOMY_LIVE': '1'}); before = {k: api('/api/economy/user?login=' + k) for k in ('ana', 'cyfirl')}
    time.sleep(4.5); after = {k: api('/api/economy/user?login=' + k) for k in ('ana', 'cyfirl')}
    ga = after['ana']['points'] - before['ana']['points']; gc = after['cyfirl']['points'] - before['cyfirl']['points']
    chk('live: chatters earn points and minutes every minute', gc >= 2 and after['cyfirl']['minutes'] > before['cyfirl']['minutes'], (before, after))
    chk('a subscriber earns double', ga >= 2 * gc - 2 and ga > gc, (ga, gc))
    chk('bots, the streamer and strangers without a profile: bots/streamer get nothing', api('/api/economy/user?login=helperbot')['points'] == 0 and api('/api/economy/user?login=innocentpenguin_')['points'] == 0)
    chk('someone in the chatroom with no history starts earning too', api('/api/economy/user?login=nobody1')['points'] > 0)
    e = api('/api/economy'); chk('status says where the chatters came from', 'Helix' in e['earning']['source'], e['earning'])
    mo = api('/api/boards')['months']; cur = sorted(mo.keys())[-1]
    chk('the current month has points and watch-time boards', len(mo[cur]['points']) > 0 and len(mo[cur]['watchtime']) > 0, list(mo[cur].keys()))
    # no scope -> fallback
    state['chatters_code'] = 403; time.sleep(2.2)
    e = api('/api/economy'); chk('without the chatters scope it says so and falls back to active chatters', 'moderator:read:chatters' in e['earning']['source'], e['earning'])
    host.kill(); time.sleep(1.0); host = start({'PINGUINO_ECONOMY_LIVE': '0'}); state['chatters_code'] = 200
    b0 = api('/api/economy/user?login=cyfirl')['minutes']; time.sleep(3.0)
    chk('offline: nobody earns', api('/api/economy/user?login=cyfirl')['minutes'] == b0)
    chk('the JWT never reached the log or the files', JWT not in open(outf, encoding='utf-8', errors='replace').read() and all(JWT not in open(os.path.join(dp, f), encoding='utf-8', errors='replace').read() for dp, _, fs in os.walk(d) for f in fs if f.endswith('.json') or f.endswith('.jsonl')))
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); hx.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
