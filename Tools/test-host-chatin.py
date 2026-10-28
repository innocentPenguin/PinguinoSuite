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
    chk('chat-in ok', c == 200 and j.get('ok'), j)
    chk('exactly one send, to youtube, with reply_to, @sender dropped, no yt: key leaked', len(sends) == 1 and sends[0][0] == '/api/send' and sends[0][1] == {'platform': 'youtube', 'text': '@Viewer hello from the Host', 'reply_to': 'yt-msg-1'}, sends)
    chk('Multi called with the bearer token', sends and sends[0][2] == 'Bearer multi-test', sends[:1])
    rc = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/chat/recent?limit=20' % PORT, timeout=10))['messages']
    yl = [m for m in rc if m.get('platform') == 'youtube' and m.get('text') == '!hi']
    chk('yt chat is a plain Twitch-style line in /api/chat/recent: platform, name, empty colour and badges', yl and yl[0]['name'] == 'Viewer' and yl[0]['display'] == 'Viewer' and yl[0]['color'] == '' and yl[0]['badges'] == [], rc[-3:])
    ll = [json.loads(l) for f in os.listdir(os.path.join(d, 'chat_logs', 'live')) for l in open(os.path.join(d, 'chat_logs', 'live', f), 'rb').read().decode('utf-8').splitlines()] if os.path.isdir(os.path.join(d, 'chat_logs', 'live')) else []
    chk('yt chat is in the live chat log with platform and display name', any(x.get('p') == 'youtube' and x.get('n') == 'Viewer' for x in ll), ll[-2:])
    cin('Viewer', '!gamble 10', mid='yt-g1'); time.sleep(2.5)
    pg = [l for l in open(outp, 'rb').read().decode('utf-8', 'replace').splitlines() if l.startswith('[pggame]')]
    chk('PgGame event for a YouTube viewer says the display name, never the yt: key', pg and '"display":"Viewer"' in pg[-1] and '"display":"yt:' not in pg[-1], pg[-1:])
    n = len(sends); cin('Viewer2', '!hi', mid='yt-msg-2'); time.sleep(2)
    chk('another viewer gets their own @name line (a different line, so no duplicate hold-back)', len(sends) == n + 1 and sends[n][1]['text'] == '@Viewer2 hello from the Host', sends[n:])
    cin('Viewer3', '!bc', mid='yt-msg-3'); time.sleep(2)
    chk('text with the viewer name shows the plain name, not yt:viewer3', sends[-1][1]['text'].lower() in ('viewer3 uses bc', '@viewer3 viewer3 uses bc'), sends[-1:])
    n = len(sends); cin('Viewer', '!modonly', mid='yt-msg-4'); time.sleep(1.5)
    chk('role is forced to viewer: mod-only command stays silent even if the body claims mod', len(sends) == n, sends[n:])
    post('/api/chat-in', {'platform': 'youtube', 'user': 'Mod', 'text': '!modonly', 'msgId': 'x', 'role': 4, 'isMod': True}); time.sleep(1.5)
    chk('body role/isMod ignored', len(sends) == n, sends[n:])
    cin('PinguinoB0t', '!hi', mid='yt-msg-5'); cin('Anyone', '!hi', mid='yt-msg-6', isBot=True); cin('Anyone2', '!hi', mid='yt-msg-6b', ownBot=True, role=1, isSub=False); time.sleep(1.5)
    chk('own bot account / isBot: ignored, no reply (loop guard)', len(sends) == n, sends[n:])
    c, j = cin('Viewer', '!hi', plat='tiktok', mid='tt-1'); time.sleep(1.5)
    chk('tiktok: accepted, nothing sent', c == 200 and len(sends) == n, (j, sends[n:]))
    # TikTok / YouTube viewers register and join customs through the Host: namespaced by the platform id, display name kept, tiktok never answered anywhere
    def cstate(): return json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/customs/state' % PORT, timeout=10))
    host.stdin.write(b'#trial: !queue open' + bytes([10])); host.stdin.flush(); time.sleep(2.5)
    n = len(sends); o0 = len(open(outp, 'rb').read())
    cin('Tik Toker', '!register TikEpic', plat='tiktok', mid='tt-r', userId='7001'); time.sleep(1.5); cin('Tik Toker', '!join', plat='tiktok', mid='tt-j', userId='7001'); time.sleep(2.5)
    q = [e for e in cstate().get('queue', []) if e.get('platform') == 'tiktok']
    chk('tiktok !register + !join: one queue entry tt:7001 with platform tiktok and the display name', len(q) == 1 and q[0]['username'] == 'tt:7001' and q[0]['name'] == 'Tik Toker', cstate().get('queue'))
    chk('tiktok: nothing sent to Multi or Twitch', len(sends) == n, sends[n:])
    printed = open(outp, 'rb').read().decode('utf-8', 'replace')[o0:]
    clog = open(os.path.join(d, 'console', 'host.jsonl'), 'rb').read().decode('utf-8', 'replace')
    chk('tiktok: exactly one log line per handled command, nothing printed as a Twitch say', clog.count('tiktok Tik Toker ran') == 2 and '[say]' not in printed.replace('[say] The queue', ''), (clog[-500:], printed[-300:]))
    cin('Yt Fan', '!register YtEpic', userId='UCabc-1_x', mid='yt-r'); time.sleep(1.5); cin('Yt Fan', '!join', userId='UCabc-1_x', mid='yt-j'); time.sleep(2.5)
    q = [e for e in cstate().get('queue', []) if e.get('platform') == 'youtube']
    chk('youtube viewer joins with the channel id as key, display name kept', len(q) == 1 and q[0]['username'] == 'yt:ucabc-1_x' and q[0]['name'] == 'Yt Fan', cstate().get('queue'))
    chk('youtube replies go to youtube only, with the display name and no yt: key', sends[n:] and all(x[1]['platform'] == 'youtube' and 'yt:' not in x[1]['text'] for x in sends[n:]), sends[n:])
    # "!register <epic> !join" in one line: the epic name stops at the " !", the join runs, ONE message goes back
    n = len(sends); cin('Petar', '!register petar1211 !join', userId='UCpetar', mid='yt-p1'); time.sleep(3)
    q = [e for e in cstate().get('queue', []) if e.get('username') == 'yt:ucpetar']
    chk('register+join in one line: queued', len(q) == 1, cstate().get('queue'))
    chk('register+join: ONE message, @Petar, registered + joined, no second line', len(sends) - n == 1 and sends[n][1]['text'].startswith('@Petar ') and 'Registered as petar1211' in sends[n][1]['text'] and 'joined the queue' in sends[n][1]['text'], sends[n:])
    pl = json.load(open(os.path.join(d, 'players.json'))); chk('the epic name is petar1211 only', pl.get('yt:ucpetar', {}).get('GameId') == 'petar1211', pl.get('yt:ucpetar'))
    # mods remove them by display name (any case) or by key; two players with the same name are refused
    host.stdin.write(b'#trial: !kick tik toker' + bytes([10])); host.stdin.flush(); time.sleep(2)
    chk('!kick by display name removes the tiktok player', not [e for e in cstate().get('queue', []) if e['username'] == 'tt:7001'], cstate().get('queue'))
    cin('Tik Toker', '!join', plat='tiktok', mid='tt-j2', userId='7001'); time.sleep(2)
    host.stdin.write(b'#trial: !kick tt:7001' + bytes([10])); host.stdin.flush(); time.sleep(2)
    chk('!kick by key still works', not [e for e in cstate().get('queue', []) if e['username'] == 'tt:7001'], cstate().get('queue'))
    cin('Tik Toker', '!register OtherEpic', plat='tiktok', mid='tt-r3', userId='7002'); time.sleep(1.5); cin('Tik Toker', '!join', plat='tiktok', mid='tt-j3', userId='7002'); cin('tik toker', '!register Epic3', plat='tiktok', mid='tt-r4', userId='7001'); time.sleep(1.5); cin('Tik Toker', '!join', plat='tiktok', mid='tt-j4', userId='7001'); time.sleep(2)
    n2 = len(cstate().get('queue', [])); host.stdin.write(b'#trial: !kick Tik Toker' + bytes([10])); host.stdin.flush(); time.sleep(2)
    chk('two players called Tik Toker: refused, nobody removed', len(cstate().get('queue', [])) == n2, cstate().get('queue'))
    rc, r = post('/api/customs/mod', {'action': 'kick', 'value': 'tt:7002'}); time.sleep(1.5)
    chk('Master View kick by key', r.get('ok') and not [e for e in cstate().get('queue', []) if e['username'] == 'tt:7002'], r)
    chk('twitch queue entries carry platform twitch too', all(e.get('platform') for e in cstate().get('queue', [])), cstate().get('queue'))
    c, j = cin('Viewer', '!hi', plat='nonsense'); chk('unknown platform refused', j.get('ok') is False, j)
    # Chatty / Helper / B0t answer YouTube viewers too, on YouTube only
    n = len(sends); o0 = len(open(outp, 'rb').read()); cin('Pointsy', '!points', mid='yt-msg-20'); time.sleep(4)
    new = sends[n:]; printed = open(outp, 'rb').read().decode('utf-8', 'replace')[o0:]
    chk('!points from YouTube: Chatty answers once through Multi youtube (no yt: key in the text), reply_to the message', len(new) == 1 and new[0][1]['platform'] == 'youtube' and new[0][1].get('reply_to') == 'yt-msg-20' and 'yt:' not in new[0][1]['text'] and 'points' in new[0][1]['text'].lower(), new)
    chk('...and nothing printed/sent as a Twitch say', '[say]' not in printed, printed[-300:])
    # a Twitch viewer asking the same thing: Twitch only, nothing to Multi
    n = len(sends); o0 = len(open(outp, 'rb').read()); host.stdin.write(b'twviewer: !points\n'); host.stdin.flush(); time.sleep(4)
    printed = open(outp, 'rb').read().decode('utf-8', 'replace')[o0:]
    chk('Twitch !points: answered as a Twitch say, nothing sent to Multi', len(sends) == n and 'points' in printed.lower(), (sends[n:], printed[-300:]))
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
    # ---- counters: every line (accepted and rejected) is counted per platform, a plain chat line produces NO send, a command exactly one
    mode['code'] = 200; time.sleep(31)
    n = len(sends); cin('Chatter', 'hello everyone, nice stream', mid='yt-plain'); time.sleep(2)
    chk('plain youtube chat line: accepted, no send to Multi', len(sends) == n, sends[n:])
    n = len(sends); cin('Chatter', '!hi', mid='yt-hi-2'); time.sleep(2.5)
    chk('a command from youtube: exactly ONE /api/send, platform youtube', len(sends) == n + 1 and sends[n][1]['platform'] == 'youtube' and sends[n][0] == '/api/send', sends[n:])
    post('/api/chat-in', {'platform': 'twitch', 'user': 'x', 'text': 'hi'}); post('/api/chat-in', {'platform': 'youtube', 'user': 'x', 'text': ''})
    st = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=10)).get('chatIn') or {}
    chk('status.chatIn present with yt/tt counts', st.get('yt', 0) >= 8 and st.get('tt', 0) >= 1, st)
    chk('status.chatIn commands/replies/sendErrors counted', st.get('commands', 0) >= 6 and st.get('replies', 0) >= 3 and st.get('sendErrors', 0) >= 1, st)
    rj = st.get('rejects') or {}
    chk('rejects counted by reason: 401 token, platform, empty, own bot', rj.get('401 token', 0) >= 1 and rj.get('platform', 0) >= 1 and rj.get('empty') == 1 and rj.get('own bot', 0) >= 3, st)
    chk('lastReject says who and why', 'empty' in st.get('lastReject', ''), st)
    # a WRONG token (not just a missing one): 401, counted as "401 token", ONE log line with the caller, never the token value, not repeated within a minute
    hl = lambda: [json.loads(l)['msg'] for l in open(os.path.join(d, 'console', 'host.jsonl'), 'rb').read().decode('utf-8', 'replace').splitlines() if '401 on /api/chat-in' in l]
    before = len(hl()); b4 = (json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=10)).get('chatIn') or {}).get('rejects', {}).get('401 token', 0)
    c1, _ = post('/api/chat-in', {'platform': 'youtube', 'user': 'x', 'text': '!hi'}, 'wrong-token-xyz'); c2, _ = post('/api/chat-in', {'platform': 'youtube', 'user': 'x', 'text': '!hi'}, 'wrong-token-xyz'); time.sleep(2)
    af = (json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=10)).get('chatIn') or {}).get('rejects', {}).get('401 token', 0)
    msgs = hl()
    chk('wrong token: 401 twice, both counted', c1 == 401 and c2 == 401 and af == b4 + 2, (c1, c2, b4, af))
    chk('wrong token: exactly one log line this minute, with the caller and which header, never the token', len(msgs) - before == 1 and '127.0.0.1' in msgs[-1] and 'Authorization Bearer' in msgs[-1] and 'wrong-token-xyz' not in msgs[-1], msgs[-2:])
    time.sleep(35)
    lines = [json.loads(l) for l in open(os.path.join(d, 'console', 'host.jsonl'), 'rb').read().decode('utf-8', 'replace').splitlines() if '"chat-in"' in l and 'chat-in: yt' in l]
    chk('a one-line minute summary was logged', lines and 'commands' in lines[-1]['msg'] and 'replies' in lines[-1]['msg'] and 'send errors' in lines[-1]['msg'], lines[-2:])
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS chatin'); sys.exit(1 if fails else 0)
