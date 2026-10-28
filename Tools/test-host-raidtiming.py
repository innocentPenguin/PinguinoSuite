"""Raid timing (sim Host + fake Helix + fake OBS; the real OBS is never touched). Twitch sends channel.raid when the raid EXECUTES (48-137 s after it was picked), so:
 - Sery_Bot's goodbye line (the moment the raid is picked) fires the raid line + Discord line at once; the later channel.raid event repeats nothing and supplies the target (!leftbehind)
 - the event lands the raid by default (no RaidStartDelaySec): goodnight, !leftbehind line, StopStream a few seconds after it, once; Ivan's by-hand offline afterwards repeats nothing
 - without the Sery line the event does it all in order: emotes, Discord, goodnight, !leftbehind, StopStream
 - another chatter's words, and a Sery line while the stream is known offline, do nothing
Usage: python Tools/test-host-raidtiming.py [dll]"""
import asyncio, base64, hashlib, http.server, json, os, shutil, struct, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, OBSP, WSP, HX, MX, TOK = 9171, 9172, 9173, 9174, 9175, 'test-module-token'; B = 'http://127.0.0.1:%d' % PORT
CRLF = chr(13) + chr(10)
OBS = {'streaming': True, 'ignore_first': False, 'reqs': [], 'stops': 0}
chats = []; sends = []; chatters = {'n': 40}

class WS:
    def __init__(self, r, w): self.r, self.w = r, w
    async def send(self, text):
        b = text.encode(); n = len(b)
        hdr = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack('>H', n)
        self.w.write(hdr + b); await self.w.drain()
    async def recv(self):
        while True:
            h = await self.r.readexactly(2); op, n = h[0] & 15, h[1] & 127
            if n == 126: n = struct.unpack('>H', await self.r.readexactly(2))[0]
            mask = await self.r.readexactly(4) if h[1] & 128 else b''
            data = await self.r.readexactly(n)
            if mask: data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if op == 8: raise EOFError()
            if op == 1: return data.decode()
async def conn(r, w):
    try:
        head = (await r.readuntil((CRLF + CRLF).encode())).decode()
        key = [l.split(':', 1)[1].strip() for l in head.split(CRLF) if l.lower().startswith('sec-websocket-key')][0]
        acc = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        proto = 'Sec-WebSocket-Protocol: obswebsocket.json' + CRLF if 'obswebsocket.json' in head else ''
        w.write(('HTTP/1.1 101 Switching Protocols' + CRLF + 'Upgrade: websocket' + CRLF + 'Connection: Upgrade' + CRLF + 'Sec-WebSocket-Accept: ' + acc + CRLF + proto + CRLF).encode()); await w.drain()
        ws = WS(r, w)
        await ws.send(json.dumps({'op': 0, 'd': {'obsWebSocketVersion': '5.0.0', 'rpcVersion': 1}}))
        await ws.recv(); await ws.send(json.dumps({'op': 2, 'd': {'negotiatedRpcVersion': 1}}))
        while True:
            m = json.loads(await ws.recv())
            if m['op'] != 6: continue
            d = m['d']; t = d['requestType']; data = {}
            OBS['reqs'].append((time.time(), t))
            if t == 'GetStreamStatus': data = {'outputActive': OBS['streaming'], 'outputReconnecting': False}
            elif t == 'StopStream':
                OBS['stops'] += 1
                if not (OBS['ignore_first'] and OBS['stops'] == 1): OBS['streaming'] = False
            await ws.send(json.dumps({'op': 7, 'd': {'requestType': t, 'requestId': d['requestId'], 'requestStatus': {'result': True, 'code': 100}, 'responseData': data}}))
    except Exception: pass
    finally: w.close()
def run_obs():
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.start_server(conn, '127.0.0.1', OBSP)); loop.run_forever()
threading.Thread(target=run_obs, daemon=True).start()

def reply(h, o, code=200):
    b = json.dumps(o).encode(); h.send_response(code); h.send_header('Content-Type', 'application/json'); h.send_header('Content-Length', str(len(b))); h.end_headers(); h.wfile.write(b)
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path.endswith('/chat/messages'): chats.append((time.time(), b.get('message', '')))
        reply(self, {'data': [{'is_sent': True}]})
    def do_GET(self):
        if '/chat/chatters' in self.path: return reply(self, {'data': [{'user_login': 'u%d' % i} for i in range(chatters['n'])]})
        reply(self, {'data': []})
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self): reply(self, {'connectors': [{'platform': 'youtube', 'status': 'connected'}]})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append(b); reply(self, {'ok': True, 'id': 'm1'})
for port, hh in ((HX, Hx), (MX, Mx)): threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', port), hh).serve_forever, daemon=True).start()

fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
    if not ok: fails.append(n)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=8))
def texts(): return [c[1] for c in chats]
def n_of(s): return sum(1 for c in texts() if s in c)

OLD_ACTIONS = [
    {'id': 'sb-raidstart', 'name': 'Raid scheduled', 'enabled': True, 'triggers': [{'type': 'raid_start'}], 'conditions': [], 'steps': [
        {'type': 'shoutout_queue', 'user': '{target}', 'by': 'raid', 'auto': True},
        {'type': 'say', 'as': 'core', 'text': 'EMOTES line'}, {'type': 'delay', 'ms': 700}, {'type': 'say', 'as': 'core', 'text': 'DISCORD {link:discord}'}]},
    {'id': 'sb-raidout', 'name': 'Raid out', 'enabled': True, 'triggers': [{'type': 'raid_out'}], 'conditions': [], 'steps': [
        {'type': 'say', 'as': 'core', 'text': 'DISCORD {link:discord}'}, {'type': 'delay', 'ms': 1500}, {'type': 'obs_request', 'request': 'StopStream'}]},
    {'id': 'sb-offline', 'name': 'Stream offline', 'enabled': True, 'triggers': [{'type': 'stream_offline'}], 'conditions': [], 'steps': [{'type': 'say', 'as': 'core', 'text': 'GOODNIGHT'}]}]

LIVEV = {'v': '1'}   # PINGUINO_LIVE: the Host's live flag (forced)
class H:
    def __init__(self, obs_port, delay_sec):
        self.d = tempfile.mkdtemp(prefix='pgrc_'); self.out = os.path.join(self.d, 'out.txt'); d = self.d
        json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': obs_port, 'ObsPassword': '', 'UserToken': 't', 'ClientId': 'c', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
        json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
        json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
        json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
        delay_sec is None or json.dump({'RaidStartDelaySec': delay_sec}, open(os.path.join(d, 'latest_settings.json'), 'w'))
        json.dump({'seeded': ['spotify', 'spotify2', 'musicoff1', 'songhelper1', 'raidshort1', 'raidflow2'], 'actions': OLD_ACTIONS}, open(os.path.join(d, 'automations.json'), 'w'))
        env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
        env.update({'PINGUINO_COMPAT_WS_PORT': str(WSP), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_OBS': '1', 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_LIVE': LIVEV['v']})
        self.p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(self.out, 'wb'), stderr=subprocess.STDOUT)
        for _ in range(80):
            try: get('/api/status'); break
            except Exception: time.sleep(0.5)
        time.sleep(4)
    def feed(self, l): self.p.stdin.write((l + chr(10)).encode()); self.p.stdin.flush()
    def text(self): return open(self.out, encoding='utf-8', errors='replace').read()
    def log(self):
        f = os.path.join(self.d, 'console', 'host.jsonl')
        return open(f, encoding='utf-8', errors='replace').read() if os.path.exists(f) else ''
    def yt(self, text, uid='UCleft1'):
        rq = urllib.request.Request(B + '/api/chat-in', data=json.dumps({'platform': 'youtube', 'user': 'Yt Viewer', 'userId': uid, 'text': text, 'msgId': 'm' + str(time.time())}).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK})
        urllib.request.urlopen(rq, timeout=20)
    def stop(self):
        self.p.kill(); time.sleep(0.7); shutil.rmtree(self.d, True)
def reset(streaming=True, ignore_first=False, n=40): OBS.update(streaming=streaming, ignore_first=ignore_first, reqs=[], stops=0); chats.clear(); sends.clear(); chatters['n'] = n
def stops(): return [t for t in OBS['reqs'] if t[1] == 'StopStream']
def waitfor(f, secs):
    t = time.time()
    while time.time() - t < secs:
        if f(): return True
        time.sleep(0.4)
    return False


def irc(nick, text, h): h.p.stdin.write(('@id=m-%s-%s;display-name=%s;user-id=900 :%s!%s@%s.tmi.twitch.tv PRIVMSG #trial :%s\n' % (nick, time.time(), nick, nick, nick, nick, text)).encode()); h.p.stdin.flush()
SERY = "Have a great rest of your day! seryboLove Don't forget to stay hydrated and take care of yourself! seryboArrive"
fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
    if not ok: fails.append(n)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=8))
def texts(): return [c[1] for c in chats]
def n_of(s): return sum(1 for c in texts() if s in c)

# ---- 1. Sery line first, then the event
reset(); h = H(OBSP, None)
try:
    waitfor(lambda: 'OBS connected' in h.text(), 8)
    irc('viewer9', SERY, h); time.sleep(2.5)
    chk('another chatter saying the same words: nothing', texts() == [], texts())
    t0 = time.time(); irc('sery_bot', SERY, h); ok = waitfor(lambda: len(chats) >= 2, 6); t1 = time.time()
    t = texts()
    chk('Sery line: emotes + Discord line out within seconds, nothing else', ok and len(t) == 2 and 'EMOTES' in t[0] and 'DISCORD' in t[1] and t1 - t0 < 6, (t, t1 - t0))
    time.sleep(2); irc('sery_bot', SERY, h); time.sleep(2)
    chk('a second Sery line repeats nothing', len(texts()) == 2, texts())
    time.sleep(3); chatters['n'] = 40
    tev = time.time(); h.feed('raidpick evuto_ 12')   # = the channel.raid event: execution
    chk('event lands the raid within seconds: StopStream reached OBS', waitfor(lambda: len(stops()) >= 1, 12), OBS['reqs'][-5:])
    lag = stops()[0][0] - tev if stops() else 99
    time.sleep(1); t = texts()
    chk('order: emotes, Discord, goodnight, !leftbehind line; each once', [x[:7] for x in t] == ['EMOTES ', 'DISCORD', 'GOODNIG', "Didn't "] and n_of('DISCORD') == 1, t)
    chk('landed on the event, not the 90 s countdown (StopStream < 10 s after it)', lag < 10 and 'raid landed (the raid event' in h.log(), (lag, [l for l in h.log().splitlines() if 'raid landed' in l]))
    n0 = len(chats); h.feed('viewer3: !leftbehind'); time.sleep(2)
    chk('!leftbehind has the target from the event', texts()[n0:] == ['https://twitch.tv/evuto_'], texts()[n0:])
    OBS['streaming'] = False; h.feed('event StreamOffline streamer'); time.sleep(3)
    chk('Ivan ending it by hand afterwards repeats nothing', n_of('GOODNIGHT') == 1 and len(stops()) == 1 and n_of('DISCORD') == 1, (texts(), len(stops())))
finally: h.stop()

# ---- 2. no Sery line: the event does it all, in order
reset(); h = H(OBSP, None)
try:
    waitfor(lambda: 'OBS connected' in h.text(), 8)
    h.feed('raidpick evuto_ 12')
    chk('event alone: StopStream reached OBS', waitfor(lambda: len(stops()) >= 1, 15), (texts(), OBS['reqs'][-5:]))
    time.sleep(1); t = texts()
    chk('event alone: emotes, Discord, goodnight, !leftbehind in that order', [x[:7] for x in t] == ['EMOTES ', 'DISCORD', 'GOODNIG', "Didn't "], t)
    gap = [c[0] for c in chats]
    chk('goodnight comes after the Discord line (>= 2 s)', len(gap) >= 3 and gap[2] - gap[1] >= 2, gap)
finally: h.stop()

# ---- 3. Sery line while the stream is known offline: nothing
LIVEV['v'] = '0'; reset(); h = H(OBSP, None)
try:
    waitfor(lambda: 'OBS connected' in h.text(), 8); time.sleep(8); n0 = len(chats)
    irc('sery_bot', SERY, h); time.sleep(3)
    chk('Sery line while offline: nothing said', len(chats) == n0 and 'raid start signal' not in h.log(), (texts()[n0:], ))
finally: h.stop()
print('FAILS: %d' % len(fails)); sys.exit(1 if fails else 0)
