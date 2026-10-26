"""Timers also go out on YouTube: a timer fire sends its line to Twitch AND (stream live + Multi reports YouTube connected) to Multi /api/send {platform:youtube, text} exactly once, no reply_to.
Skipped silently (one log line a minute) when Multi/YouTube is down or the stream is offline; per-timer "platforms" (twitch only -> no YouTube leg; youtube only -> no Twitch leg); TikTok is never sent.
A fake Helix and a fake Multi stand in. Usage: python Tools/test-host-timers-yt.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, MX = 8991, 8992, 8993; B = 'http://127.0.0.1:%d' % PORT
chats = []; sends = []; yt = {'status': 'connected', 'http': 200}
def reply(h, o, code=200):
    b = json.dumps(o).encode(); h.send_response(code); h.send_header('Content-Type', 'application/json'); h.send_header('Content-Length', str(len(b))); h.end_headers(); h.wfile.write(b)
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path.endswith('/chat/messages'): chats.append(b.get('message', ''))
        reply(self, {'data': [{'is_sent': True}]})
    def do_GET(self): reply(self, {'data': []})
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith('/api/status'):
            if yt['http'] != 200: return reply(self, {'detail': 'down'}, yt['http'])
            return reply(self, {'connectors': [{'platform': 'twitch', 'status': 'connected'}, {'platform': 'youtube', 'status': yt['status']}, {'platform': 'tiktok', 'status': 'connected'}]})
        reply(self, {}, 404)
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append((self.path, b)); reply(self, {'ok': True, 'id': 'm1'})
for port, h in ((HX, Hx), (MX, Mx)): threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', port), h).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgtyt_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def start(live):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8994', 'PINGUINO_TIMERS_FAST': '1', 'PINGUINO_TIMERS_LIVE': live, 'PINGUINO_DUP_SECONDS': '0'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
res = []
def chk(n, ok, x=''):
    res.append((n, ok))
    if not ok: print('  FAIL', n, x)
def skiplines():
    f = os.path.join(d, 'console', 'host.jsonl')
    return sum(1 for l in open(f, encoding='utf-8', errors='replace') if 'timer line not sent to YouTube' in l) if os.path.exists(f) else 0
def fire(i):
    chats.clear(); sends.clear(); api('/api/timers', {'now': i}); time.sleep(1.5)
host = start('1')
try:
    api('/api/timers', {'globalGapSec': 0})
    r = api('/api/timers', {'timer': {'id': 'a', 'name': 'A', 'enabled': False, 'everySec': 3600, 'minChatMessages': 0, 'messages': ['Join the Discord']}})
    ta = [t for t in r['timers'] if t['id'] == 'a'][0]
    chk('a new timer defaults to twitch + youtube', ta.get('platforms') == ['twitch', 'youtube'], ta.get('platforms'))
    fire('a')
    chk('connected: one YouTube send, text only, no reply_to', len(sends) == 1 and sends[0][0] == '/api/send' and sends[0][1].get('platform') == 'youtube' and sends[0][1].get('text') == 'Join the Discord' and 'reply_to' not in sends[0][1], sends)
    chk('connected: the Twitch line still goes out', chats == ['Join the Discord'], chats)
    yt['status'] = 'disconnected'; fire('a'); fire('a')
    chk('YouTube disconnected: no YouTube send, Twitch still goes', sends == [] and chats == ['Join the Discord'], (sends, chats))
    chk('disconnected: ONE log line for two fires', skiplines() == 1, skiplines())
    yt['status'] = 'connected'; yt['http'] = 500; fire('a')
    chk('Multi down: no send', sends == [] and chats == ['Join the Discord'], (sends, chats))
    yt['http'] = 200
    api('/api/timers', {'timer': {'id': 'a', 'platforms': ['twitch']}}); fire('a')
    chk('platforms=twitch: Twitch only', sends == [] and chats == ['Join the Discord'], (sends, chats))
    api('/api/timers', {'timer': {'id': 'a', 'platforms': ['youtube', 'tiktok', 'kick']}})
    r = api('/api/timers'); chk('only twitch/youtube are stored (tiktok dropped)', [t for t in r['timers'] if t['id'] == 'a'][0]['platforms'] == ['youtube'], r)
    fire('a')
    chk('platforms=youtube: YouTube only', len(sends) == 1 and sends[0][1]['platform'] == 'youtube' and chats == [], (sends, chats))
    api('/api/timers', {'timer': {'id': 'a', 'platforms': ['twitch', 'youtube'], 'mode': 'all', 'messages': ['one', 'two']}}); fire('a'); time.sleep(0.5)
    chk('mode all: each line once on YouTube, never tiktok', [s[1]['text'] for s in sends] == ['one', 'two'] and all(s[1]['platform'] == 'youtube' for s in sends), sends)
    host.kill(); time.sleep(1)
    host = start('0'); yt['status'] = 'connected'; fire('a')
    chk('stream not live: no YouTube send', sends == [], sends)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
