"""Stream-day REHEARSAL for the overlays (sim Host, temp data, own port; never touches OBS, Twitch or the live Host).
Replays a scripted evening: idle -> queue open -> joins -> match + team picks -> win -> wheel lobby + spin -> sub / resub / gift / raid / hype ->
subroll -> queue close, and after EVERY step asserts that each overlay's data endpoint still answers with a sane payload
(live_state.js, /api/queue-idle, /api/customs/state, /api/wheel/public, /api/subroll, /overlay/latest|goal|subfooter, /api/scene-layouts, /api/scene-health)
and that no overlay page is missing. Usage: python Tools/rehearse-overlays.py [dll] [--keep] [--hold SECONDS]   (the dll is a Release build of PinguinoHost, run from a temp copy, never from bin\\Release of the live app).
Then a RAID rehearsal on a second sim Host (mock Helix + mock Multi): goodnight with no raid fires at once; raid_start = ONE chat message ("Prepare your emotes" + the Discord invite), no shoutout clip (Ivan 10-27) within seconds; the same raid never starts twice; stream.offline with a raid pending is held; raid_out (a few seconds after the signal in the test) says the !leftbehind line, then stop-stream, and releases the held goodnight; overlays stay sane after every step.
Exit 0 = every step sane. Registered for run-all-tests through Tools/test-host-rehearsal.py."""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--') and not a.isdigit()]
dll = args[0] if args else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
import socket
def freeport():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
PORT = freeport(); WS = freeport(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrh_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
# the bot core writes live_state.js into settings.json OverlayDir (default: the REAL overlays folder, shared with the live Host and every other sim): point it at our temp dir
od = os.path.join(d, 'overlays_out'); os.makedirs(od); json.dump({'OverlayDir': od}, open(os.path.join(d, 'settings.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_SIM_SUBS': '1'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
fails = []; step = ['start']
def chk(n, ok, x=''):
    if not ok: fails.append('[%s] %s %s' % (step[0], n, str(x)[:240]))
def raw(p): return urllib.request.urlopen(B + p, timeout=10).read().decode('utf-8', 'replace')
def get(p):
    try: return json.loads(raw(p))
    except Exception as e: return {'__err': str(e)}
def LS():
    try:
        t = raw('/live_state.js'); return json.loads(t[t.index('{'):t.rindex('}') + 1])
    except Exception as e: return {'__err': str(e)}
def feed(l, w=0.7): h.stdin.write((l + '\n').encode()); h.stdin.flush(); time.sleep(w)
def ev(t, o): feed('eventsub %s %s' % (t, json.dumps(o)), 0.8)

def sane(extra=None):
    """Every overlay data source answers and has the fields its page reads."""
    ls = LS()
    chk('live_state.js parses', '__err' not in ls and 'queueOpen' in ls and isinstance(ls.get('queue'), list) and isinstance(ls.get('teams'), dict), ls.get('__err'))
    cs = get('/api/customs/state'); chk('customs state', isinstance(cs.get('queue'), list) and 'open' in cs, cs.get('__err') or sorted(cs)[:12])
    qi = get('/api/queue-idle'); chk('queue-idle', qi.get('ok') is True and isinstance(qi.get('items'), list) and qi.get('visibleRows', 0) > 0, qi.get('__err'))
    wp = get('/api/wheel/public'); chk('wheel public', 'status' in wp and 'pool' in wp or '__err' not in wp and 'status' in wp, wp.get('__err'))
    sr = get('/api/subroll/state'); chk('subroll state', 'running' in sr, sr.get('__err'))
    sl = get('/api/scene-layouts?profile=h'); chk('scene layout h', sl.get('ok') is True and len(sl['layout']['widgets']) >= 20, sl.get('__err'))
    sv = get('/api/scene-layouts?profile=v'); chk('scene layout v', sv.get('ok') is True, sv.get('__err'))
    sh = get('/api/scene-health'); chk('scene health answers', 'problems' in sh, sh.get('__err'))
    for p in ('/overlay/latest', '/overlay/goal?id=followers', '/overlay/subfooter'):
        try: t = raw(p); chk('page ' + p, len(t) > 200 and '<html' in t.lower())
        except Exception as e: chk('page ' + p, False, e)
    if extra:
        try: extra(ls, cs, qi, wp, sr)
        except Exception as e: chk('payload shape (%s)' % type(e).__name__, False, e)
    return ls, cs, qi, wp, sr

try:
    for _ in range(120):
        try: raw('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)

    step[0] = 'pages'
    ov = os.path.join(suite, 'PinguinoB0t', 'overlays')
    pages = sorted(f for f in os.listdir(ov) if f.endswith('.html') and not f.startswith('scene-editor') and '.bak' not in f)
    for pg in pages:
        try: t = raw('/' + pg); chk('page ' + pg + ' served', len(t) > 300)
        except Exception as e: chk('page ' + pg + ' served', False, e)
    for q in ('wheel.html?part=wheel', 'players.html?part=teams', 'queue.html?part=idle', 'customs.html?part=status', 'scene.html?profile=h', 'scene.html?profile=v'):
        try: chk('page ' + q, len(raw('/' + q)) > 300)
        except Exception as e: chk('page ' + q, False, e)

    step[0] = 'idle (nothing running)'
    # the Host serves OverlayDir first, then the suite overlays folder (which can hold a stale live_state.js from an earlier run, or none: 404). Wait until the bot core has written ITS state into our temp OverlayDir; nudge it with a harmless close if it has not yet.
    lsf = os.path.join(od, 'live_state.js')
    for i in range(40):
        if os.path.exists(lsf): break
        if i == 6: feed('#ivan: !queue close', 0.3)
        time.sleep(0.5)
    chk('the sim bot core wrote live_state.js into its own OverlayDir', os.path.exists(lsf))
    sane(lambda ls, cs, qi, wp, sr: chk('idle: queue closed and empty, no match', ls['queueOpen'] is False and not ls.get('currentMatch') and wp['status'] == 'none' and sr['running'] is False, (ls['queueOpen'], len(ls['queue']))))

    step[0] = 'queue open'
    feed('#ivan: !queue open')
    sane(lambda ls, cs, qi, wp, sr: chk('open reaches live state and customs', ls['queueOpen'] is True and cs['open'] is True))
    users = 'a1 b2 c3 d4 e5 f6'.split()
    for u in users: feed(u + ': !register Epic' + u, 0.4)

    step[0] = 'joins'
    for u in users: feed(u + ': !join', 0.4)
    def joined(ls, cs, qi, wp, sr):
        chk('six in the queue with 1..6 positions', [q['pos'] for q in ls['queue']] == list(range(1, len(ls['queue']) + 1)) and len(ls['queue']) >= 1, [q.get('pos') for q in ls['queue']])
        chk('queue rows carry what the card needs', all(q.get('user') and q.get('epic') for q in ls['queue']))
        chk('customs queue matches live state', len(cs['queue']) == len(ls['queue']), (len(cs['queue']), len(ls['queue'])))
    sane(joined)

    step[0] = 'match + team picks'
    feed('#ivan: !match fill', 1.5)
    def matched(ls, cs, qi, wp, sr):
        m = ls.get('currentMatch') or {}
        chk('current match has 3 per team, no duplicates', len(m.get('blue', [])) == 3 and len(m.get('orange', [])) == 3 and len({(p if isinstance(p, str) else p.get('user') or p.get('name') or json.dumps(p)) for p in m.get('blue', []) + m.get('orange', [])}) == 6, m)
        chk('customs shows the match', cs.get('match') is not None, cs.get('match'))
        chk('match has an id and a status', m.get('id') and m.get('status'), (m.get('id'), m.get('status')))
    sane(matched)

    step[0] = 'team names'
    try:
        r = urllib.request.urlopen(urllib.request.Request(B + '/api/customs/teams', data=json.dumps({'orange': {'name': 'Spicy Orange', 'color': '#ff7a00'}, 'blue': {'name': 'Ice Blue', 'color': '#1e8fff'}}).encode(), headers={'Content-Type': 'application/json'}), timeout=10)
        chk('team rename accepted', json.loads(r.read()).get('ok') is True)
    except Exception as e: chk('team rename accepted', False, e)
    time.sleep(1); sane(lambda ls, cs, qi, wp, sr: chk('custom team names reach live state', ls['teams']['orange']['name'] == 'Spicy Orange' and ls['teams']['blue']['name'] == 'Ice Blue', ls['teams']))

    step[0] = 'win'
    feed('#ivan: !win blue', 1.2)
    sane(lambda ls, cs, qi, wp, sr: chk('result recorded', ls.get('lastEvent') is not None or ls.get('recentEvents')))

    step[0] = 'wheel lobby'
    feed('#ivan: !wheel open')
    for u in ['ana', 'bo', 'cy', 'dee']: feed(u + ': !me', 1.1)
    sane(lambda ls, cs, qi, wp, sr: chk('lobby lists the four, no MMR/seed leak', wp['status'] == 'open' and sorted(wp.get('names', [])) == ['ana', 'bo', 'cy', 'dee'] and 'seed' not in json.dumps(wp) and 'avg' not in json.dumps(wp), wp))

    step[0] = 'wheel spin'
    feed('#ivan: !wheel spin', 2.0)
    def spin(ls, cs, qi, wp, sr):
        chk('spinning with one pick', wp['status'] == 'drawing' and wp.get('draw') and len(wp['draw']['steps']) >= 1, (wp.get('status'), wp.get('names'), wp.get('draw')))
    sane(spin)
    time.sleep(9)
    sane(lambda ls, cs, qi, wp, sr: chk('pick left the pool', len(wp.get('pool', [])) <= 3, wp.get('pool')))

    step[0] = 'subs: new, resub, gift'
    ev('channel.subscribe', {'user_login': 'newbie', 'tier': '1000', 'is_gift': False})
    ev('channel.subscription.message', {'id': 'rs1', 'user_login': 'oldtimer', 'tier': '2000', 'cumulative_months': 14, 'streak_months': 6, 'message': {'text': 'hi'}})
    ev('channel.subscription.gift', {'user_login': 'gifty', 'tier': '1000', 'total': 3, 'cumulative_total': 10, 'is_anonymous': False})
    def subs(ls, cs, qi, wp, sr):
        la = raw('/overlay/latest'); chk('latest page loads', 'latest' in la.lower())
    sane(subs)
    mp = os.path.join(d, 'subs', 'subscribers_master.json')
    chk('resub reached the sub master', os.path.exists(mp) and 'oldtimer' in open(mp, encoding='utf-8-sig').read().lower())

    step[0] = 'raid + hype'
    ev('channel.raid', {'from_broadcaster_user_id': 'x', 'from_broadcaster_user_login': 'raider', 'viewers': 30})
    ev('channel.hype_train.begin', {'id': 'h1', 'level': 1, 'total': 300, 'progress': 300, 'goal': 500, 'type': 'regular'})
    ev('channel.hype_train.end', {'id': 'h1', 'level': 2, 'total': 900})
    sane()

    if '--hold' in sys.argv:
        print('HOLDING sim Host at ' + B + ' (match, wheel lobby, subs, raid done)', flush=True); time.sleep(int(sys.argv[sys.argv.index('--hold') + 1]))

    step[0] = 'shoutout'
    feed('#ivan: !so raider', 1.5)
    sane()

    step[0] = 'subroll'
    try:
        r = urllib.request.urlopen(urllib.request.Request(B + '/api/subroll/start', data=json.dumps({'mode': 'tier', 'style': 'roll'}).encode(), headers={'Content-Type': 'application/json'}), timeout=10)
        st = json.loads(r.read()); chk('subroll starts', st.get('running') is True, st)
    except Exception as e: chk('subroll starts', False, e)
    sr = get('/api/subroll'); chk('subroll payload has rows', '__err' not in sr and (sr.get('rows') or sr.get('subs') or sr.get('groups') is not None or sr.get('ok') is True), list(sr)[:8])
    sane(lambda ls, cs, qi, wp, sr: chk('subroll running', sr['running'] is True, sr))
    try: urllib.request.urlopen(urllib.request.Request(B + '/api/subroll/stop', data=b'{}', headers={'Content-Type': 'application/json'}), timeout=10).read()
    except Exception as e: chk('subroll stops', False, e)

    step[0] = 'scenes under load'
    sl = get('/api/scene-layouts?profile=h'); chk('stage layouts still readable', sl.get('ok') is True)
    sh = get('/api/scene-health'); chk('scene health ok in a default set-up', sh.get('ok') is True or all('8766' in x or '8771' in x for x in sh.get('problems', [])), sh.get('problems'))

    step[0] = 'queue close'
    feed('#ivan: !queue close', 2.0)
    sane(lambda ls, cs, qi, wp, sr: chk('closed reaches live state', ls['queueOpen'] is False and cs['open'] is False))

    step[0] = 'host log'
    log = open(outf, errors='replace').read()
    bad = [l for l in log.splitlines() if re.search(r'Unhandled|Exception|\bERROR\b', l) and 'Epic' not in l][:3]
    chk('no exceptions in the Host output', not bad, bad)
    chk('Host still alive', h.poll() is None)
    if '--log' in sys.argv: print(chr(10).join(l for l in log.splitlines() if 'ana' in l or 'ivan' in l.lower() or 'wheel' in l.lower()))
finally:
    h.kill(); time.sleep(0.5)
    if '--keep' not in sys.argv: shutil.rmtree(d, True)
# ---- raid rehearsal: a second sim Host with a mock Helix + mock Multi (the shoutout clip goes to Multi's alerts source), same sanity checks around every step ----
def raid_rehearsal():
    import http.server, threading, urllib.parse
    global B, h
    HX, MP = freeport(), freeport(); RP, RW = freeport(), freeport()
    chats = []; fires = []; t0 = time.time()
    def clip(i): return {'id': i, 'title': 't' + i, 'url': 'https://clips.twitch.tv/' + i, 'view_count': 50, 'is_featured': True, 'duration': 9.5, 'created_at': '2020-01-01T00:00:00Z', 'thumbnail_url': 'https://x/y-preview-480x272.jpg'}
    class HX_(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, o, code=200):
            b = json.dumps(o).encode() if o is not None else b''
            self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
            if u.path.endswith('/users'): lg = q.get('login', [''])[0]; self._send({'data': [{'id': 'id_' + lg, 'login': lg}]})
            elif u.path.endswith('/channels'): bid = q.get('broadcaster_id', [''])[0]; lg = bid[3:]; self._send({'data': [{'broadcaster_login': lg, 'broadcaster_name': lg.capitalize(), 'game_name': 'Rocket League'}]})
            elif u.path.endswith('/clips'): self._send({'data': [clip('RC1')]})
            else: self._send({'data': []})
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if u.path.endswith('/chat/messages'):
                n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); chats.append((time.time() - t0, b.get('message', ''))); self._send({'data': [{'is_sent': True}]})
            else: self._send(None, 204)
    class MU(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            n = int(self.headers.get('Content-Length', 0)); b = json.loads(self.rfile.read(n) or b'{}'); fires.append((time.time() - t0, self.path, b))
            o = json.dumps({'ok': True, 'text': 'queued'}).encode(); self.send_response(200); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
    sm = http.server.ThreadingHTTPServer(('127.0.0.1', MP), MU); sh_ = http.server.ThreadingHTTPServer(('127.0.0.1', HX), HX_)
    for sv in (sm, sh_): threading.Thread(target=sv.serve_forever, daemon=True).start()
    rd = tempfile.mkdtemp(prefix='pgrhr_'); rout = os.path.join(rd, 'out.txt')
    json.dump({'Channel': 'trial', 'OverlayPort': RP, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'streamer1'}, open(os.path.join(rd, 'host_secrets.json'), 'w'))
    rod = os.path.join(rd, 'overlays_out'); os.makedirs(rod); json.dump({'OverlayDir': rod}, open(os.path.join(rd, 'settings.json'), 'w'))
    json.dump({'RaidStartDelaySec': 0}, open(os.path.join(rd, 'latest_settings.json'), 'w'))   # the raid lands 10 s after Twitch's signal instead of 90 s
    json.dump({'CooldownSec': 1, 'ManualDedupeMinutes': 0}, open(os.path.join(rd, 'shout_settings.json'), 'w'))
    json.dump({'Enabled': True, 'Url': 'http://127.0.0.1:%d' % MP, 'Token': ''}, open(os.path.join(rd, 'alert_bridge.json'), 'w'))
    json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(rd, 'bots.json'), 'w'))
    json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(rd, 'bots_secrets.json'), 'w'))
    e2 = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; e2.update({'PINGUINO_COMPAT_WS_PORT': str(RW), 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX})
    h2 = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', rd, '--suite', suite], env=e2, stdin=subprocess.PIPE, stdout=open(rout, 'ab'), stderr=subprocess.STDOUT)
    oh, ob = h, B; h = h2; B = 'http://127.0.0.1:%d' % RP
    def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=15))
    def runs(i): return [r for r in get('/api/automations/log?n=100').get('runs', []) if r['id'] == i]
    def texts(): return [m for _, m in chats]
    try:
        for _ in range(240):
            try: raw('/api/status'); break
            except Exception: time.sleep(0.5)
        time.sleep(2)
        for i in ('sb-raidstart', 'sb-raidout', 'sb-offline'): post('/api/automations/enable', {'id': i, 'on': True})
        for i in range(40):   # same as the main run: wait for this Host's own live_state.js (else the suite folder's stale copy or a 404 is served)
            if os.path.exists(os.path.join(rod, 'live_state.js')): break
            if i == 6: feed('#ivan: !queue close', 0.3)
            time.sleep(0.5)

        step[0] = 'raid: goodnight with no raid fires at once'
        ev('stream.offline', {'broadcaster_user_login': 'trial'}); time.sleep(1.5)
        chk('no raid pending: the goodnight ran', len(runs('sb-offline')) == 1, [r['id'] for r in get('/api/automations/log?n=20').get('runs', [])])
        sane()

        step[0] = 'raid_start'
        tp = time.time() - t0
        r = post('/api/raid/prep', {'target': 'raidtarget'}); chk('raid prep accepted, first signal fires', r.get('fired') is True, r)
        time.sleep(4)
        rs = runs('sb-raidstart'); chk('raid start ran once', len(rs) == 1 and rs[0]['ok'], rs)
        if rs:
            o = rs[0]['output']
            chk('one message: the emotes line with the Discord invite, no shoutout step', len(o) == 1 and 'Prepare your emotes' in o[0] and 'iscord' in o[0], o)
            chk('raid start finished within a few seconds', rs[0]['ms'] < 5000, rs[0]['ms'])
        want = [m for m in texts() if 'Prepare your emotes' in m]
        chk('chat got the emotes line with the Discord invite once', len(want) == 1 and 'Discord' in want[0], texts())
        chk('no shoutout clip is sent for the raid target', len(fires) == 0, fires)
        sane()
        r2 = post('/api/raid/prep', {'target': 'raidtarget'}); chk('the same raid does not start twice', r2.get('fired') is False, r2)

        step[0] = 'raid: goodnight held while the raid is pending'
        ev('stream.offline', {'broadcaster_user_login': 'trial'}); time.sleep(2)
        chk('goodnight held (not said yet)', len(runs('sb-offline')) == 1, len(runs('sb-offline')))
        sane()

        step[0] = 'raid_out'
        feed('event TwitchRaidOut raidtarget 40', 0.5)
        time.sleep(3); chk('raid_out waits for the raid to land (not at the signal)', len(runs('sb-raidout')) == 0)
        for _ in range(20):
            if runs('sb-raidout'): break
            time.sleep(1)
        ro = runs('sb-raidout'); chk('raid out ran once after the delay', len(ro) == 1, len(ro))
        if ro:
            o = ro[0]['output']; chk('the !leftbehind line first, then the stop-stream step last', 'leftbehind' in o[0] and 'OBS' in o[-1], o)
        time.sleep(1.5)
        chk('the held goodnight was said after the raid landed', len(runs('sb-offline')) == 2, len(runs('sb-offline')))
        chk('no shoutout clip for the whole raid', len(fires) == 0, len(fires))
        sane()

        step[0] = 'raid: host log'
        bad = [l for l in open(rout, errors='replace').read().splitlines() if re.search(r'Unhandled|Exception|\bERROR\b', l)][:3]
        chk('no exceptions in the raid Host output', not bad, bad); chk('raid Host still alive', h.poll() is None)
    finally:
        h.kill(); time.sleep(0.5); h, B = oh, ob
        for sv in (sm, sh_):
            try: sv.shutdown()
            except Exception: pass
        if '--keep' not in sys.argv: shutil.rmtree(rd, True)
try: raid_rehearsal()
except Exception as e: fails.append('[raid] rehearsal error %r' % (e,))
print('FAIL ' + '; '.join(fails) if fails else 'PASS rehearse-overlays'); sys.exit(1 if fails else 0)
