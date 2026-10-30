"""Known bot accounts (BotRix ...) are not viewers: no welcome / bonus, no First 5, no points; the list is Data/runtime/bot_accounts.json, extended with !botaccount.
Usage: python Tools/test-host-botaccounts.py [dll]
Original docstring of the template: New YouTube / TikTok viewers (first line ever seen) are welcomed once, a few seconds after the answer to that line, as their own @name message with the WelcomeBonus paid then; logged in platform_users.json;
a second line, a known viewer, a spam first line and ForeignGreeting=false get nothing. A fake Multi stands in: no real chat.
Usage: python Tools/test-host-foreignwelcome.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8991, 8992, 'test-module-token'
sends = []; mode = {'code': 200}
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append((self.path, b, self.headers.get('Authorization', '')))
        c = mode['code']; o = {'ok': True, 'id': 'm1'} if c == 200 else {'detail': 'tiktok is read-only' if c == 400 else 'boom'}
        r = json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgba_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def act(i, name, text, perm='everyone'):
    return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'command', 'names': [name], 'permission': perm}], 'steps': [{'type': 'say', 'as': 'core', 'text': text}]}
json.dump({'actions': [act('hi', '!hi', '@{user} hello from the Host'), act('modonly', '!modonly', 'mods only line', 'mod'), act('bc', '!bc', '{user} uses bc')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8993', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '30', 'PINGUINO_FOREIGN_WELCOME_DELAY_MS': '300'})
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
    c, _ = cin('BotRix', 'BotRix has successfully joined the channel!', mid='b1', userId='UCtuynlwrjh1sxgkxae6u_8q'); time.sleep(1.8)
    chk('a known bot (yt: key from the seed) gets no welcome', not [s for s in sends if 'Welcome' in s[1]['text']], sends)
    sends[:] = []; cin('BotRix', '!points', mid='b2', userId='UCtuynlwrjh1sxgkxae6u_8q'); time.sleep(1.5)
    chk('the bot has 0 points', not sends or all('balance: 0 ' in s[1]['text'] or 'balance: 0' in s[1]['text'] for s in sends), sends)
    sends[:] = []; cin('Neo', 'hello everyone', mid='n1', userId='UCneo'); time.sleep(1.8)
    chk('a real newcomer is still welcomed', len([s for s in sends if 'Welcome' in s[1]['text']]) == 1, sends)
    f = os.path.join(d, 'bot_accounts.json'); ba = json.load(open(f, encoding='utf-8-sig'))['names']
    chk('the seed file exists with the known bots', 'botrix' in ba and 'sery_bot' in ba and 'nightbot' in ba and 'yt:uctuynlwrjh1sxgkxae6u_8q' in ba, ba)
    # a mod adds another account by name; its first line gets nothing
    sends[:] = []; mx = subprocess.run  # noqa
    host.stdin.write(b'*mod1: !botaccount add SpamBotX'+chr(10).encode()); host.stdin.flush(); time.sleep(1.2)
    ba = json.load(open(f, encoding='utf-8-sig'))['names']; chk('!botaccount add writes the list', 'spambotx' in ba, ba)
    sends[:] = []; cin('SpamBotX', 'hello', mid='x1', userId='UCspambotx'); time.sleep(1.8)
    chk('the added bot gets no welcome', not [s for s in sends if 'Welcome' in s[1]['text']], sends)
    host.stdin.write(b'*mod1: !botaccount remove SpamBotX'+chr(10).encode()); host.stdin.flush(); time.sleep(1.0)
    ba = json.load(open(f, encoding='utf-8-sig'))['names']; chk('!botaccount remove', 'spambotx' not in ba, ba)
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS botaccounts'); sys.exit(1 if fails else 0)
