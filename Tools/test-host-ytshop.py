"""The chat shop for YouTube viewers (yt: identities): !shop is ONE line that says how to buy, !shop guess <stake> takes points and runs the round, !guess pays 2x, the sub item is refused kindly.
Usage: python Tools/test-host-ytshop.py [dll]
Template docstring: New YouTube / TikTok viewers (first line ever seen) are welcomed once, a few seconds after the answer to that line, as their own @name message with the WelcomeBonus paid then; logged in platform_users.json;
a second line, a known viewer, a spam first line and ForeignGreeting=false get nothing. A fake Multi stands in: no real chat.
Usage: python Tools/test-host-foreignwelcome.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8997, 8998, 'test-module-token'
sends = []; mode = {'code': 200}
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append((self.path, b, self.headers.get('Authorization', '')))
        c = mode['code']; o = {'ok': True, 'id': 'm1'} if c == 200 else {'detail': 'tiktok is read-only' if c == 400 else 'boom'}
        r = json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgys_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def act(i, name, text, perm='everyone'):
    return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'command', 'names': [name], 'permission': perm}], 'steps': [{'type': 'say', 'as': 'core', 'text': text}]}
json.dump({'actions': [act('hi', '!hi', '@{user} hello from the Host'), act('modonly', '!modonly', 'mods only line', 'mod'), act('bc', '!bc', '{user} uses bc')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
os.makedirs(os.path.join(d, 'chat_logs', 'live'), exist_ok=True)
GOOD = ['honestly the new update makes the whole lobby feel so much smoother', 'i never thought a penguin could be this funny on a monday morning', 'my cat just knocked the whole coffee over, what a start to the day']
open(os.path.join(d, 'chat_logs', 'live', time.strftime('%Y-%m-%d', time.gmtime()) + '.jsonl'), 'w').write(chr(10).join(json.dumps({'t': 1, 'u': 'chattera', 'i': '11', 'm': g, 'c': 0}) for g in GOOD) + chr(10))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8999', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '30', 'PINGUINO_FOREIGN_WELCOME_DELAY_MS': '300', 'PINGUINO_YT_SPACING_MS': '200'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def post(p, body, tok=TOK):
    h = {'Content-Type': 'application/json'}
    if tok: h['Authorization'] = 'Bearer ' + tok
    try: r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=json.dumps(body).encode(), headers=h), timeout=20); return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, {}
def cin(user, text, plat='youtube', mid='yt-msg-1', **kw):
    b = {'platform': plat, 'user': user, 'userId': 'UC123', 'text': text, 'msgId': mid}; b.update(kw); return post('/api/chat-in', b)
def pts(user):
    sends[:] = []; cin(user, '!points', mid='p-' + user, userId='UC' + user.lower()); time.sleep(1.5)
    return ' '.join(s[1]['text'] for s in sends)
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    def say_(user, uid, text, mid, wait=1.6):
        sends[:] = []; cin(user, text, mid=mid, userId=uid); time.sleep(wait); return [s[1]['text'] for s in sends if 'text' in s[1]]
    say_('Dana', 'UCdana', 'hello', 'd0', 2.5)   # the welcome gives 100 points
    r = say_('Dana', 'UCdana', '!shop', 'd1')
    chk('!shop on YouTube is ONE line, names the viewer, says how to buy', len(r) == 1 and r[0].startswith('@Dana ') and '!shop <item>' in r[0] and '!shop guess' in r[0] and 'yt:' not in r[0] and len(r[0]) <= 200, r)
    chk('the YouTube shop line does not offer the Twitch sub gift', len(r) == 1 and 'sub' not in r[0].lower().replace('subscri', ''), r)
    r = say_('Dana', 'UCdana', '!shop sub', 'd2')
    chk('!shop sub on YouTube is refused kindly, one line, display name', len(r) == 1 and r[0].startswith('@Dana ') and 'Twitch' in r[0] and 'yt:' not in r[0], r)
    r = say_('Dana', 'UCdana', '!points', 'd3'); b0 = r[0] if r else ''
    chk('Dana has the welcome 100', len(r) == 1 and 'balance: 100' in r[0].replace(',', ''), r)
    # from here the Helper bot is up and speaks game / points answers itself; the Host's own record of them is the log (pggame event, points-lookup)
    say_('Dana', 'UCdana', '!shop guess 100', 'd4'); say_('Dana', 'UCdana', '!points', 'd5'); say_('Dana', 'UCdana', '!guess chattera', 'd6'); say_('Dana', 'UCdana', '!points', 'd7')
    log = open(outp, 'rb').read().decode('utf-8', 'replace')
    chk('!shop guess 100 starts a round for the YouTube viewer, named by display name', '"outcome":"start","user":"yt:ucdana","display":"Dana","amount":"100"' in log, log[-600:])
    chk('the stake was taken (balance 0)', 'yt:ucdana = 0|' in log)
    chk('the right guess pays 2x to the YouTube viewer', '"outcome":"win","user":"yt:ucdana","display":"Dana","amount":"100","payout":"200","balance":"200"' in log)
    chk('balance is 200 after the win', 'yt:ucdana = 200|' in log)
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS ytshop'); sys.exit(1 if fails else 0)
