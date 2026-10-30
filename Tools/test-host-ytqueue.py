"""YouTube sends go through one paced queue (min spacing, FIFO, one retry after a 403 too-many-messages, never a duplicate, bounded).
Usage: python Tools/test-host-ytqueue.py [dll]
Template docstring: New YouTube / TikTok viewers (first line ever seen) are welcomed once, a few seconds after the answer to that line, as their own @name message with the WelcomeBonus paid then; logged in platform_users.json;
a second line, a known viewer, a spam first line and ForeignGreeting=false get nothing. A fake Multi stands in: no real chat.
Usage: python Tools/test-host-foreignwelcome.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8994, 8995, 'test-module-token'
sends = []; mode = {'code': 200, 'arm': 0}; att = []; lastok = [0.0]
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); now = time.time(); att.append((now, b.get('text', '')))
        if mode['arm'] > 0: mode['arm'] -= 1; c = 502; o = {'detail': 'send failed 403 The user has posted too many chat messages'}
        elif now - lastok[0] < 1.2: c = 502; o = {'detail': 'send failed 403 The user has posted too many chat messages'}
        else: c = 200; o = {'ok': True, 'id': 'm1'}; lastok[0] = now; sends.append((self.path, b, now))
        r = json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgyq_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def act(i, name, text, perm='everyone'):
    return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'command', 'names': [name], 'permission': perm}], 'steps': [{'type': 'say', 'as': 'core', 'text': text}]}
json.dump({'actions': [act('hi', '!hi', '@{user} hello from the Host'), act('modonly', '!modonly', 'mods only line', 'mod'), act('bc', '!bc', '{user} uses bc')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8996', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '30', 'PINGUINO_FOREIGN_WELCOME_DELAY_MS': '300', 'PINGUINO_YT_SPACING_MS': '1500', 'PINGUINO_YT_BACKOFF_MS': '600'})
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
    # two commands at once from two YouTube viewers: both answers must arrive, spaced, none refused
    cin('Ann', '!hi', mid='a1', userId='UCann'); time.sleep(0.4); cin('Bob', '!hi', mid='a2', userId='UCbob'); time.sleep(8)
    hi = [s for s in sends if 'hello from the Host' in s[1]['text']]
    chk('both answers arrived', len(hi) == 2, [s[1]['text'] for s in sends])
    chk('no send was refused by the 1.2 s fake limit', all(a[0] in [s[2] for s in sends] for a in att), att)
    if len(sends) >= 2: chk('sends are spaced at least 1.4 s apart', all(sends[i + 1][2] - sends[i][2] >= 1.4 for i in range(len(sends) - 1)), [round(s[2] - sends[0][2], 2) for s in sends])
    chk('order kept: Ann before Bob', len(hi) == 2 and '@Ann' in hi[0][1]['text'] and '@Bob' in hi[1][1]['text'], [s[1]['text'] for s in hi])
    # a forced 403 on the next send: one retry, the line still arrives, once
    n0 = len(att); sends[:] = []; mode['arm'] = 1
    cin('Cat', '!bc', mid='c1', userId='UCcat'); time.sleep(6)
    bc = [s for s in sends if 'uses bc' in s[1]['text']]
    chk('after a 403 the line was retried and arrived exactly once', len(bc) == 1, [s[1]['text'] for s in sends])
    # the same line is not queued twice
    n1 = len(sends); cin('Cat', '!bc', mid='c2', userId='UCcat'); time.sleep(3)
    chk('a repeat of the same line within the dup window is not sent again', len([s for s in sends if 'uses bc' in s[1]['text']]) == 1, [s[1]['text'] for s in sends])
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS ytqueue'); sys.exit(1 if fails else 0)
