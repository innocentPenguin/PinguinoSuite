"""Customs with YouTube viewers: the Twitch team announcement (!next / !lobby) never prints a yt: / tt: key (Epic name first, else the platform name), /api/customs/state match entries carry epic + a shown
name (no key), /api/wheel/public rows too, and a YouTube reply to a handle with a space is stripped whole. Usage: python Tools/test-host-customsyt.py [dll]"""
import http.server, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, TOK = 8983, 'test-module-token'; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcy_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_YT_SPACING_MS': '200', 'PINGUINO_COMPAT_WS_PORT': '8984', 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_MODULE_TOKEN': TOK})
json.dump({'Url': 'http://127.0.0.1:8985', 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []; sends = []
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append(b)
        r = json.dumps({'ok': True, 'id': 'm1'}).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', 8985), Mx).serve_forever, daemon=True).start()
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def api(path, body=None):
    h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
    return json.load(urllib.request.urlopen(urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers=h), timeout=20))
def feed(l, w=1.2): host.stdin.write((l + chr(10)).encode()); host.stdin.flush(); time.sleep(w)
def yt(name, uid, text, w=1.2): api('/api/chat-in', {'platform': 'youtube', 'user': name, 'userId': uid, 'text': text, 'msgId': 'm' + str(time.time())}); time.sleep(w)
def log(): return open(outp, 'rb').read().decode('utf-8', 'replace')
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
    feed('#trial: !queue open', 2)
    for n in ('tw1', 'tw2', 'tw3'): feed(n + ': !register Tw' + n.upper()); feed(n + ': !join')
    yt('@Yt One', 'UCa1', '!register YtEpicOne'); yt('@Yt One', 'UCa1', '!join')
    yt('@Yt Two', 'UCa2', '!join', 1.2)   # no Epic registered: the platform name is shown
    yt('@Yt Two', 'UCa2', '!register YtEpicTwo'); yt('@Yt Two', 'UCa2', '!join')
    n0 = len(log()); feed('#trial: !next', 3)
    new = log()[n0:]; say = [l for l in new.splitlines() if l.startswith('[say]')]
    chk('teams were announced', len(say) >= 2, new[-800:])
    chk('no yt: / tt: key in any announcement', not re.search(r'\b(yt|tt):', ' '.join(say), re.I), say)
    chk('Epic names are shown for the YouTube players', 'YtEpicOne' in ' '.join(say) and 'YtEpicTwo' in ' '.join(say), say)
    st = api('/api/customs/state'); m = st.get('match') or {}
    ents = (m.get('players') or []) + (m.get('blueP') or []) + (m.get('orangeP') or [])
    chk('match entries exist', len(ents) >= 8, ents)
    chk('no match entry shows a key as display', all(not re.match(r'(yt|tt):', e.get('display', ''), re.I) for e in ents), ents)
    chk('YouTube entries carry the epic', any(e.get('username') == 'yt:uca1' and e.get('epic') == 'YtEpicOne' and e.get('display') == 'YtEpicOne' for e in ents), [e for e in ents if 'yt:' in e.get('username', '')])
    chk('platform name is still on the entry', any(e.get('username') == 'yt:uca1' and e.get('name') == 'Yt One' for e in ents), ents)
    sends[:] = []; yt('@Yt Two', 'UCa2', '!lobby', 3)
    txt = ' '.join(x.get('text', '') for x in sends)
    chk('!lobby from YouTube: one reply, names, no key', len(sends) >= 1 and not re.search(r'(yt|tt):', txt, re.I) and 'YtEpicTwo' in txt, sends)
    chk('the handle with a space is stripped whole (no stray "Two" before Orange)', txt.startswith('@Yt Two ') and ' Two Orange' not in txt and txt.count('@Yt') == 1, txt)
    # one platform per Epic: an Epic already registered on another account (any platform) is refused with the platform named; a mod forces it, !unregister frees it
    sends[:] = []; yt('@Yt Three', 'UCa3', '!register TwTW1', 2)
    txt = ' '.join(x.get('text', '') for x in sends)
    chk('YouTube viewer registering a Twitch-held Epic is refused, platform named', '@Yt Three That Epic is already registered on Twitch. Use that account, or ask a mod.' in txt and 'Registered' not in txt, sends)
    n0 = len(log()); feed('tw4: !register YtEpicOne', 2); new = log()[n0:]
    chk('Twitch viewer registering a YouTube-held Epic is refused, platform named', '[say] @tw4 That Epic is already registered on YouTube. Use that account, or ask a mod.' in new and 'Registered as' not in new, new[-400:])
    n0 = len(log()); feed('tw5: !register twtw1', 2); new = log()[n0:]
    chk('the check ignores case and also covers another Twitch account', '[say] @tw5 That Epic is already registered on Twitch.' in new, new[-400:])
    n0 = len(log()); feed('*mod1: !register @tw4 YtEpicOne', 2); new = log()[n0:]
    chk('a mod can force it with the @ form', 'Registered tw4 as YtEpicOne' in new, new[-400:])
    n0 = len(log()); feed('*mod1: !unregister tw4', 2); new = log()[n0:]
    chk('!unregister frees it', 'Unregistered tw4' in new, new[-400:])
    n0 = len(log()); feed('tw4: !unregister tw1', 1.5); new = log()[n0:]
    chk('a viewer cannot unregister anyone', 'Ask a mod' in new, new[-400:])
    n0 = len(log()); feed('*mod1: !unregister YtEpicTwo', 2); new = log()[n0:]
    chk('!unregister also takes the Epic name', 'Unregistered Yt Two (YtEpicTwo)' in new, new[-400:])
    sends[:] = []; yt('@Yt Three', 'UCa3', '!register YtEpicTwo', 2)
    txt = ' '.join(x.get('text', '') for x in sends)
    chk('a freed Epic can be registered on another platform', 'Registered as YtEpicTwo' in txt, sends)
finally:
    host.kill(); time.sleep(0.5); print(log()[-1800:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS customsyt'); sys.exit(1 if fails else 0)
