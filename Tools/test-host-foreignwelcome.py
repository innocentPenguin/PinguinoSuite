"""New YouTube / TikTok viewers (first line ever seen) are welcomed once, a few seconds after the answer to that line, as their own @name message with the WelcomeBonus paid then; logged in platform_users.json;
a second line, a known viewer, a spam first line and ForeignGreeting=false get nothing. A fake Multi stands in: no real chat.
Usage: python Tools/test-host-foreignwelcome.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8985, 8986, 'test-module-token'
sends = []; mode = {'code': 200}
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append((self.path, b, self.headers.get('Authorization', '')))
        c = mode['code']; o = {'ok': True, 'id': 'm1'} if c == 200 else {'detail': 'tiktok is read-only' if c == 400 else 'boom'}
        r = json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgfw_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def act(i, name, text, perm='everyone'):
    return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'command', 'names': [name], 'permission': perm}], 'steps': [{'type': 'say', 'as': 'core', 'text': text}]}
json.dump({'actions': [act('hi', '!hi', '@{user} hello from the Host'), act('modonly', '!modonly', 'mods only line', 'mod'), act('bc', '!bc', '{user} uses bc')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8987', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '30', 'PINGUINO_FOREIGN_WELCOME_DELAY_MS': '300'})
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
    c, _ = cin('Neo', 'hello everyone', mid='n1', userId='UCneo'); time.sleep(1.8)
    w = [s[1] for s in sends if 'Welcome' in s[1]['text']]
    chk('new yt viewer: one welcome as its own @name message with the bonus', len(sends) == 1 and len(w) == 1 and w[0]['text'].startswith('@Neo Welcome to the stream!') and '+100' in w[0]['text'], sends)
    chk('the welcome never leaks the yt: key', all('yt:' not in s[1]['text'] for s in sends), sends)
    pu = json.load(open(os.path.join(d, 'platform_users.json'), encoding='utf-8-sig'))
    chk('the newcomer is logged in platform_users.json', pu.get('yt:ucneo', {}).get('name') == 'Neo' and pu['yt:ucneo']['platform'] == 'youtube', pu)
    sends[:] = []; cin('Neo', 'second line', mid='n2', userId='UCneo'); time.sleep(1.2)
    chk('a second line from the same viewer: no second welcome', not sends, sends)
    chk('the bonus was paid once and shows in !points', '100' in pts('Neo').replace('Welcome', ''), sends)
    sends[:] = []; cin('Spammy', 'buy cheap followers viewers promo www.boost.xyz', mid='s1', userId='UCspam'); time.sleep(1.5)
    chk('spam first line: no welcome', not sends, sends)
    sends[:] = []; cin('Tik', 'hi', plat='tiktok', mid='t1', userId='tik1'); time.sleep(1.5)
    chk('tiktok newcomer: nothing sent (read-only)', not sends, sends)
    pu = json.load(open(os.path.join(d, 'platform_users.json'), encoding='utf-8-sig'))
    chk('the tiktok newcomer is logged too', pu.get('tt:tik1', {}).get('platform') == 'tiktok', pu)
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS foreignwelcome'); sys.exit(1 if fails else 0)
