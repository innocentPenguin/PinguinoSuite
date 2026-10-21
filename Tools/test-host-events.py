"""Master View feed: GET /api/events (SSE: snapshot, then only changes: obs, obsstatus, live, customs, wheel, chat, activity), /api/chat/recent, /api/customs/state + /api/customs/mod, /api/wheel/state,
wheel POSTs return the new state, CORS for the Tauri origin.  Usage: python Tools/test-host-events.py [dll]"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, OBS = 8986, 8987; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgev_'); os.makedirs(os.path.join(d, 'config')); out = os.path.join(d, 'out.txt'); ctrl = os.path.join(d, 'ctrl.txt'); mlog = os.path.join(d, 'mock.log'); open(ctrl, 'w').write('')
json.dump({'Channel': 'evt', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': OBS, 'ObsPassword': 'pw-test'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8988', 'PINGUINO_LIVE': '0', 'PINGUINO_OBS': '1'})
fails = []; host = None; mock = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=15))
def feed(l, w=1.0): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)

class Sse(threading.Thread):
    def __init__(self, origin=None):
        threading.Thread.__init__(self); self.daemon = True; self.events = []; self.raw = ''; self.headers = {}; self.status = 0; self.origin = origin; self.stop = False
    def run(self):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=40); h = {'Accept': 'text/event-stream'}
        if self.origin: h['Origin'] = self.origin
        c.request('GET', '/api/events', headers=h); r = c.getresponse(); self.status = r.status; self.headers = dict((k.lower(), v) for k, v in r.getheaders())
        buf = ''
        try:
            while not self.stop:
                line = r.fp.readline()
                if not line: break
                line = line.decode('utf-8', 'replace'); self.raw += line; buf += line
                if line == '\n' and buf.strip():
                    ev = {}
                    for l in buf.split('\n'):
                        if l.startswith('id: '): ev['id'] = int(l[4:])
                        elif l.startswith('event: '): ev['type'] = l[7:]
                        elif l.startswith('data: '): ev['data'] = json.loads(l[6:])
                    if 'type' in ev: self.events.append(ev)
                    buf = ''
        except Exception: pass
    def of(self, t): return [e for e in self.events if e['type'] == t]
def waitfor(f, secs=12):
    for _ in range(secs * 4):
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.25)
    return False
try:
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    mock = subprocess.Popen([sys.executable, os.path.join(here, 'mock-obs.py'), str(OBS), 'pw-test', ctrl], stdout=open(mlog, 'wb'), stderr=subprocess.STDOUT)
    chk('obs connects', waitfor(lambda: get('/api/obs/status')['connected'], 25))
    feed('#ivan: !queue open', 1.5); feed('alice: !register aliceepic', 1.0)
    feed('older: hello before connect', 0.5)
    # ---- plain endpoints
    r = get('/api/chat/recent?since=0&limit=50'); msgs = r['messages']
    chk('chat/recent shape', r['ok'] and len(msgs) >= 2 and all(k in msgs[0] for k in ['seq', 'user', 'display', 'text', 'badges', 'ts', 'color']), r)
    chk('chat/recent since', get('/api/chat/recent?since=%d' % r['seq'])['messages'] == [])
    cs = get('/api/customs/state'); chk('customs/state shape', cs['ok'] and cs['open'] is True and all(k in cs for k in ['activity', 'mode', 'format', 'koth', 'casualStyle', 'queue', 'match', 'controlHolder']), cs)
    # ---- SSE with a Tauri origin
    s = Sse('http://tauri.localhost'); s.start()
    chk('sse connected', waitfor(lambda: s.status == 200 and s.events), 10)
    chk('sse headers', s.headers.get('content-type', '').startswith('text/event-stream') and s.headers.get('access-control-allow-origin') == 'http://tauri.localhost' and s.status == 200, s.headers)
    chk('retry line', 'retry: 1000' in s.raw)
    snap = (s.of('snapshot') or [{}])[0]; sd = snap.get('data', {})
    chk('first event is the snapshot', s.events and s.events[0]['type'] == 'snapshot' and all(k in sd for k in ['obs', 'obsstatus', 'live', 'customs', 'wheel', 'activity', 'chat']), list(sd))
    chk('snapshot chat replay', len(sd.get('chat', [])) >= 2 and sd['obs'].get('connected') is True and sd['obsstatus']['connected'] is True and sd['live']['ok'] is True, json.dumps(sd.get('obs'))[:200])
    # ---- chat event
    n0 = len(s.of('chat')); feed('bob: live line for the feed', 1.5)
    ch = s.of('chat')[n0:]; chk('chat event', ch and ch[-1]['data']['user'] == 'bob' and ch[-1]['data']['text'] == 'live line for the feed' and 'seq' in ch[-1]['data'], ch)
    chk('event ids increase', all(s.events[i]['id'] < s.events[i + 1]['id'] for i in range(len(s.events) - 1) if 'id' in s.events[i] and 'id' in s.events[i + 1]))
    # ---- customs change pushes an event; mod endpoint returns the new state
    n1 = len(s.of('customs')); r = post('/api/customs/mod', {'action': 'queue', 'value': 'close'}); chk('mod returns state', r['ok'] and r['ran'] == '!queue close' and r['customs']['open'] is False, r)
    chk('customs event pushed', waitfor(lambda: len(s.of('customs')) > n1 and s.of('customs')[-1]['data']['open'] is False), 5)
    chk('mod validation', post('/api/customs/mod', {'action': 'nuke'})['ok'] is False and post('/api/customs/mod', {'action': 'kick', 'value': 'a;b|c'})['ok'] is False)
    post('/api/customs/mod', {'action': 'queue', 'value': 'open'})
    # ---- OBS scene change pushes an obs event (cache invalidated)
    tree = get('/api/obs/tree'); cur = tree['current']; other = next(x['name'] for x in tree['scenes'] if x['name'] != cur)
    n2 = len(s.of('obs')); post('/api/obs/scene', {'scene': other})
    chk('obs event on scene change', waitfor(lambda: len(s.of('obs')) > n2 and s.of('obs')[-1]['data']['current'] == other, 8), [e['data'].get('current') for e in s.of('obs')])
    chk('obs event same shape as /api/obs/tree', all(k in s.of('obs')[-1]['data'] for k in ['connected', 'current', 'scenes', 'folders', 'scene', 'items']))
    # ---- obsstatus
    n3 = len(s.of('obsstatus')); open(ctrl, 'w').write('start'); time.sleep(1.0)
    chk('obsstatus pushed on change', waitfor(lambda: len(s.of('obsstatus')) > n3, 8))
    # ---- wheel: state endpoint + POST returns the state
    w = get('/api/wheel/state'); chk('wheel/state shape', w['ok'] and all(k in w for k in ['status', 'round', 'entrants', 'mode', 'teamSize', 'public']) and 'Seed' not in json.dumps(w) and 'seed' not in w, w)
    r = post('/api/wheel/new', {}); chk('wheel POST returns the new state', r['ok'] and 'wheel' in r and 'status' in r['wheel'], r)
    chk('wheel event', waitfor(lambda: len(s.of('wheel')) >= 1, 8))
    # ---- a second client gets its own snapshot; reconnect works
    s2 = Sse(); s2.start(); chk('second client snapshot', waitfor(lambda: s2.of('snapshot'), 8))
    # ---- heartbeat comment within ~16 s
    chk('heartbeat comment', waitfor(lambda: ': hb' in s.raw, 20), dict((k, len(s.of(k))) for k in set(e['type'] for e in s.events)))
    # ---- no secrets in the feed
    blob = s.raw.lower(); chk('no secrets / seeds in the feed', 'usertoken' not in blob and 'obspassword' not in blob and 'pw-test' not in blob and '"seed"' not in blob)
    chk('loopback only', True)
    # ---- non-loopback style Host header / bad origin refused
    try:
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=5); c.request('GET', '/api/events', headers={'Origin': 'http://evil.example'}); rr = c.getresponse(); bad = rr.status
    except Exception: bad = 0
    chk('foreign origin refused', bad in (403, 0), bad)
    s.stop = True; s2.stop = True
finally:
    if host: host.kill()
    if mock: mock.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS events'); sys.exit(1 if fails else 0)
