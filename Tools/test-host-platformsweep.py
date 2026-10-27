"""No YouTube/TikTok viewer is ever answered on Twitch: every core command is sent from a yt: and a tt: chat-in line (POST /api/chat-in), and the fake Twitch sender (Helix) must receive NOTHING
containing "yt:" / "tt:" (raw platform keys) - in fact nothing at all for those lines. YouTube answers go to the fake Multi /api/send addressed by display name, TikTok gets nothing.
Usage: python Tools/test-host-platformsweep.py [dll]"""
import http.server, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, MX, TOK = 8971, 8972, 8973, 'test-module-token'
chats = []; sends = []
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
    def do_GET(self): reply(self, {'connectors': []})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append(b); reply(self, {'ok': True, 'id': 'm1'})
for port, h in ((HX, Hx), (MX, Mx)): threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', port), h).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgsw_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '8974', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '0'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
res = []
def chk(n, ok, x=''):
    res.append((n, ok))
    if not ok: print('  FAIL', n, x)
def post(body):
    h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
    try: r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d/api/chat-in' % PORT, data=json.dumps(body).encode(), headers=h), timeout=20); return r.status
    except urllib.error.HTTPError as e: return e.code
core = open(os.path.join(suite, 'PinguinoB0t', 'PinguinoBotCore.cs'), encoding='utf-8-sig').read()
cmds = set(re.findall(r'case "(![a-z0-9]+)"', core)) - {'!shutdown', '!restart'}
try: cmds |= {'!' + c['name'].lstrip('!') for c in json.load(open(os.path.join(suite, 'PinguinoChat', 'canned_commands.json'), encoding='utf-8-sig'))['commands']}   # the canned/link commands (!tiktok ...) too
except Exception: pass
cmds = sorted(cmds)
try:
    for _ in range(80):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    chk('there are core commands to sweep', len(cmds) > 20, len(cmds))
    for plat, uid, name in (('youtube', 'UCsweepyt1', 'Yt Viewer'), ('tiktok', 'tt7001', 'Tik Toker')):
        for c in cmds:
            for arg in ('', ' something'):
                post({'platform': plat, 'user': name, 'userId': uid, 'text': c + arg, 'msgId': 'm-' + c})
        time.sleep(10)
        bad = [m for m in chats if re.search(r'\b(yt|tt):', m) or 'Viewer' in m or 'Toker' in m]
        chk(plat + ': nothing for this viewer reached the Twitch sender', bad == [], bad[:5])
        if plat == 'youtube':
            chk('youtube: answers went to Multi', len(sends) > 0 and all(s.get('platform') == 'youtube' for s in sends), sends[:2])
            chk('youtube: no raw key in any Multi line', not any(re.search(r'\b(yt|tt):', s.get('text', '')) for s in sends), [s['text'] for s in sends if re.search(r'\b(yt|tt):', s.get('text', ''))][:5])
        else:
            chk('tiktok: nothing was sent to Multi', all(s.get('platform') == 'youtube' for s in sends))
    chk('the Twitch sender got nothing at all from those lines', chats == [], chats[:5])
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
