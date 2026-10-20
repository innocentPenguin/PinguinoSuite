"""On-stream countdown/stopwatch (absolute timestamps, subathon add-time, onZero line, mod commands, restart) and viewer reminders (!remindme, caps, late delivery after a restart).
Usage: python Tools/test-host-streamtimers.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8971; HX = 8972; B = 'http://127.0.0.1:%d' % PORT
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
d = tempfile.mkdtemp(prefix='pgst_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def start():
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8973', 'PINGUINO_TIMERS_FAST': '1', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def chatted(since=0): return [m for t, m in chats if t >= since]
def feed(h, line, wait=0.8): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait)
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra, '| says:', says()[-3:], '| chats:', [m for _, m in chats][-4:])
def tm(r, i=0): return r['timers'][i]
# a reminder that was already due while the Host was down
os.makedirs(d, exist_ok=True)
json.dump({'version': 1, 'seq': 5, 'reminders': [{'id': 'r5', 'login': 'latey', 'display': 'Latey', 'by': 'latey', 'at': int(time.time()) - 3700, 'created': int(time.time()) - 7300, 'text': 'call mom'}]}, open(os.path.join(d, 'reminders.json'), 'w'))
host = start()
try:
    time.sleep(1.5)
    chk('a reminder that fell due while the Host was off is delivered late, with a note', any('@Latey reminder: call mom' in m and 'late' in m for m in chatted()), chatted())
    # ---- durations through the commands ----
    feed(host, '*mod1: !countdown 1h30m big stream')
    r = api('/api/stream-timers'); t = tm(r)
    chk('!countdown 1h30m parses and labels', t['id'] == 'countdown' and t['label'] == 'big stream' and 5390000 < t['remainingMs'] <= 5400000 and t['state'] == 'running', t)
    feed(host, '*mod1: !countdown 10:00'); chk('10:00 means 10 minutes', 590000 < tm(api('/api/stream-timers'))['remainingMs'] <= 600000)
    feed(host, '*mod1: !addtime 2m'); chk('!addtime 2m adds time', 710000 < tm(api('/api/stream-timers'))['remainingMs'] <= 720000)
    feed(host, '*mod1: !addtime -5m'); chk('!addtime -5m takes time off', 410000 < tm(api('/api/stream-timers'))['remainingMs'] <= 420000)
    feed(host, '*mod1: !countdown pause'); a = tm(api('/api/stream-timers')); time.sleep(1.2); b = tm(api('/api/stream-timers'))
    chk('pause freezes the clock', a['state'] == 'paused' and a['remainingMs'] == b['remainingMs'], (a, b))
    feed(host, '*mod1: !countdown resume'); chk('resume starts it again', tm(api('/api/stream-timers'))['state'] == 'running')
    n0 = len(says()); feed(host, 'viewer1: !countdown 5m'); feed(host, 'viewer1: !addtime 5m'); chk('viewers cannot run timers', len(says()) == n0 and tm(api('/api/stream-timers'))['remainingMs'] < 420000)
    # ---- restart keeps absolute time ----
    before = tm(api('/api/stream-timers'))['endsAt']; host.kill(); time.sleep(1.2); host = start()
    after = tm(api('/api/stream-timers'))
    chk('restart: the same end time (absolute timestamps)', after['endsAt'] == before and after['state'] == 'running', after)
    # ---- subathon + onZero ----
    api('/api/stream-timers', {'action': 'countdown', 'id': 'sub', 'seconds': 100, 'label': 'subathon', 'add': {'sub': 30, 'gift': 10, 'bitsPer100': 5}, 'onZero': {'say': 'Subathon over, {label}!'}})
    feed(host, 'event TwitchSub alice 1'); feed(host, 'event TwitchCheer bob 300')
    sub = [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'sub'][0]
    chk('subathon: a sub adds 30 s and 300 bits add 15 s', 140000 < sub['remainingMs'] <= 145000, sub)
    api('/api/stream-timers', {'action': 'countdown', 'id': 'quick', 'seconds': 2, 'label': 'quick', 'onZero': {'say': 'Zero reached for {label}'}})
    s1 = time.time() - t0; time.sleep(3.5)
    chk('onZero: the line is said once when it reaches zero', chatted(s1).count('Zero reached for quick') == 1 and [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'quick'][0]['state'] == 'done', chatted(s1))
    # ---- stopwatch ----
    feed(host, '*mod1: !stopwatch start'); time.sleep(1.3); feed(host, '*mod1: !stopwatch stop')
    sw = [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'stopwatch'][0]; e1 = sw['elapsedMs']; time.sleep(1.0)
    sw2 = [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'stopwatch'][0]
    chk('stopwatch counts while running and stops', sw['state'] == 'stopped' and 1200 <= e1 < 4000 and sw2['elapsedMs'] == e1, (sw, sw2))
    feed(host, '*mod1: !stopwatch start'); time.sleep(0.6); feed(host, '*mod1: !stopwatch stop'); sw3 = [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'stopwatch'][0]
    chk('stopwatch continues where it stopped', sw3['elapsedMs'] > e1 + 400, (e1, sw3))
    feed(host, '*mod1: !stopwatch reset'); chk('reset', [x for x in api('/api/stream-timers')['timers'] if x['id'] == 'stopwatch'][0]['elapsedMs'] == 0)
    feed(host, '*mod1: !stoptimer'); chk('!stoptimer clears everything', api('/api/stream-timers')['timers'] == [])
    # ---- reminders ----
    s2 = time.time() - t0
    feed(host, 'viewer1: !remindme 1s drink water', 2.5)
    chk('!remindme answers and delivers the @mention', any('OK @viewer1' in m for m in says()) and '@viewer1 reminder: drink water' in chatted(s2), (says()[-2:], chatted(s2)))
    for i in range(4): feed(host, 'viewer2: !remindme 30m thing %d' % i)
    chk('at most 3 open reminders per viewer', any('already have 3 reminders' in m for m in says()[-2:]), says()[-2:])
    feed(host, 'viewer2: !reminders'); chk('!reminders lists them', any('your reminders:' in m and 'thing 0' in m for m in says()[-1:]), says()[-1:])
    feed(host, 'viewer2: !cancelreminder 2'); chk('!cancelreminder', len(api('/api/reminders?user=viewer2')['reminders']) == 2 and any('reminder 2 cancelled' in m for m in says()[-1:]))
    feed(host, 'viewer3: !remindme 90000 forever')
    chk('more than 24 hours is refused', any('longest reminder is 24 hours' in m for m in says()[-1:]), says()[-1:])
    s3 = time.time() - t0; feed(host, '*mod1: !remind @viewer4 1s stretch', 2.5)
    chk('mods can remind someone else', any('@viewer4 reminder: stretch' in m and 'from mod1' in m for m in chatted(s3)), chatted(s3))
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
