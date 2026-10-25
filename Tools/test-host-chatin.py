"""Platform-only replies: POST /api/chat-in (YouTube chat) -> an Actions & Events command answers through Multi /api/send {platform:youtube, text, reply_to} ONCE and never to Twitch;
namespaced identity, own-bot loop guard, tiktok skipped quietly, Multi 400/502 not retried and no Twitch fallback, duplicate guard keyed on platform+text (same text on twitch still allowed),
module token + role forced to viewer, /api/say with platform for Chatty/Helper. A fake Multi on a local port stands in: no real chat, no live ports.
Usage: python Tools/test-host-chatin.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8981, 8982, 'test-module-token'
sends = []; mode = {'code': 200}
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append((self.path, b, self.headers.get('Authorization', '')))
        c = mode['code']; o = {'ok': True, 'id': 'm1'} if c == 200 else {'detail': 'tiktok is read-only' if c == 400 else 'boom'}
        r = json.dumps(o).encode(); self.send_response(c); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgci_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
def act(i, name, text, perm='everyone'):
    return {'id': i, 'name': i, 'enabled': True, 'triggers': [{'type': 'command', 'names': [name], 'permission': perm}], 'steps': [{'type': 'say', 'as': 'core', 'text': text}]}
json.dump({'actions': [act('hi', '!hi', '@{user} hello from the Host'), act('modonly', '!modonly', 'mods only line', 'mod'), act('bc', '!bc', '{user} uses bc')], 'seeded': ['spotify-redeem']}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '30'})
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
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    c, j = cin('Viewer', '!hi', tok=None) if False else (post('/api/chat-in', {'platform': 'youtube', 'user': 'x', 'text': '!hi'}, None))
    chk('no token -> 401', c == 401, c)
    c, j = cin('Viewer', '!hi'); time.sleep(2.5)
    chk('chat-in ok + consumed', c == 200 and j.get('ok') and j.get('consumed'), j)
    chk('exactly one send, to youtube, with reply_to, @sender dropped, no yt: key leaked', len(sends) == 1 and sends[0][0] == '/api/send' and sends[0][1] == {'platform': 'youtube', 'text': 'hello from the Host', 'reply_to': 'yt-msg-1'}, sends)
    chk('Multi called with the bearer token', sends and sends[0][2] == 'Bearer multi-test', sends[:1])
    n = len(sends); cin('Viewer2', '!hi', mid='yt-msg-2'); time.sleep(2)
    chk('same text again for another viewer within 30 s: duplicate guard (platform+text) holds it back', len(sends) == n, sends[n:])
    cin('Viewer3', '!bc', mid='yt-msg-3'); time.sleep(2)
    chk('text with the viewer name shows the plain name, not yt:viewer3', sends[-1][1]['text'] == 'Viewer3 uses bc' or sends[-1][1]['text'].lower() == 'viewer3 uses bc', sends[-1:])
    n = len(sends); cin('Viewer', '!modonly', mid='yt-msg-4'); time.sleep(1.5)
    chk('role is forced to viewer: mod-only command stays silent even if the body claims mod', len(sends) == n, sends[n:])
    post('/api/chat-in', {'platform': 'youtube', 'user': 'Mod', 'text': '!modonly', 'msgId': 'x', 'role': 4, 'isMod': True}); time.sleep(1.5)
    chk('body role/isMod ignored', len(sends) == n, sends[n:])
    cin('PinguinoB0t', '!hi', mid='yt-msg-5'); cin('Anyone', '!hi', mid='yt-msg-6', isBot=True); time.sleep(1.5)
    chk('own bot account / isBot: ignored, no reply (loop guard)', len(sends) == n, sends[n:])
    c, j = cin('Viewer', '!hi', plat='tiktok', mid='tt-1'); time.sleep(1.5)
    chk('tiktok: accepted, nothing sent', c == 200 and len(sends) == n, (j, sends[n:]))
    c, j = cin('Viewer', '!hi', plat='nonsense'); chk('unknown platform refused', j.get('ok') is False, j)
    # Multi refuses: 502 -> logged, not retried, no twitch
    mode['code'] = 502; n = len(sends); cin('Viewer9', '!bc', mid='yt-msg-9'); time.sleep(2)
    chk('Multi 502: one attempt only (no retry)', len(sends) == n + 1, sends[n:])
    mode['code'] = 200
    # /api/say with platform (Chatty / Helper answering a YouTube viewer)
    n = len(sends); c, j = post('/api/say', {'text': 'Chatty says hi', 'bot': 'chat', 'platform': 'youtube', 'reply_to': 'yt-msg-7'})
    chk('/api/say platform=youtube -> Multi youtube reply, ok', c == 200 and j.get('ok') and sends[n:] and sends[n][1] == {'platform': 'youtube', 'text': 'Chatty says hi', 'reply_to': 'yt-msg-7'}, (j, sends[n:]))
    n = len(sends); c, j = post('/api/say', {'text': 'Chatty says hi', 'bot': 'chat', 'platform': 'youtube', 'reply_to': 'yt-msg-8'})
    chk('/api/say same text again on youtube: duplicate', j.get('duplicate') is True and len(sends) == n, j)
    # same text on twitch is NOT held back by the youtube entry (and never reaches Multi)
    n = len(sends); c, j = post('/api/say', {'text': 'Chatty says hi', 'bot': 'chat'})
    chk('twitch say path never calls Multi /api/send for platform text (key is per platform)', len(sends) == n and 'duplicate' in j and j['duplicate'] is False, (j, sends[n:]))
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS chatin'); sys.exit(1 if fails else 0)
