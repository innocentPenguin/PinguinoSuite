"""Outgoing raid chain (sim Host + FAKE Twitch Helix + FAKE Multi + FAKE obs-websocket; the real OBS is never touched):
 - stored 'Raid scheduled' (shoutout first) and 'Raid out' (Discord + StopStream) are migrated: no shoutout of the raid target, raid out = !leftbehind line + StopStream (dated backup, marker)
 - the raid pick says the emotes line then the Discord line at once, no shoutout
 - the raid lands when the chatters list (fake Helix) falls to <=20% on two polls: goodnight, THEN the !leftbehind line, THEN StopStream reaches OBS - each exactly once
 - a second landing signal, Twitch's countdown and Ivan ending the stream by hand afterwards repeat nothing (no 2nd Discord / goodnight / leftbehind line / StopStream)
 - a dip to 30% does not land early (the countdown does); Ivan ending by hand before the landing: goodnight once at the landing, StopStream skipped (OBS says it is off)
 - !leftbehind: the raid target's link (Twitch chat; YouTube via Multi; TikTok nothing), once per user per 30 s, nothing before a raid / after the next stream starts, listed in /api/commands/all
 - OBS ignores the first StopStream: sent again; OBS not connected: loud error
Usage: python Tools/test-host-raidchain.py [dll]"""
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

class H:
    def __init__(self, obs_port, delay_sec):
        self.d = tempfile.mkdtemp(prefix='pgrc_'); self.out = os.path.join(self.d, 'out.txt'); d = self.d
        json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': obs_port, 'ObsPassword': '', 'UserToken': 't', 'ClientId': 'c', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
        json.dump({'Bots': {'core': {'Enabled': True, 'Sender': 'helix', 'Account': 'PinguinoB0t'}}}, open(os.path.join(d, 'bots.json'), 'w'))
        json.dump({'core': {'UserToken': 't', 'ClientId': 'c', 'SenderId': 'bot1', 'BroadcasterId': 'streamer1'}}, open(os.path.join(d, 'bots_secrets.json'), 'w'))
        json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
        json.dump({'RaidStartDelaySec': delay_sec}, open(os.path.join(d, 'latest_settings.json'), 'w'))
        json.dump({'seeded': ['spotify', 'spotify2', 'musicoff1', 'songhelper1', 'raidshort1', 'raidflow2'], 'actions': OLD_ACTIONS}, open(os.path.join(d, 'automations.json'), 'w'))
        env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
        env.update({'PINGUINO_COMPAT_WS_PORT': str(WSP), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_OBS': '1', 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_MODULE_TOKEN': TOK})
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

# ---- 1. migration, order on the pick, early landing, no repeats, !leftbehind
reset(); h = H(OBSP, 5)
try:
    a = json.load(open(os.path.join(h.d, 'automations.json'), encoding='utf-8'))
    rs = [x for x in a['actions'] if x['id'] == 'sb-raidstart'][0]['steps']; ro = [x for x in a['actions'] if x['id'] == 'sb-raidout'][0]['steps']
    chk('migrated: no shoutout step left in Raid scheduled', [s['type'] for s in rs] == ['say', 'delay', 'say'], [s['type'] for s in rs])
    chk('migrated: Raid out = leftbehind line, delay, StopStream (no Discord)', [s['type'] for s in ro] == ['say', 'delay', 'obs_request'] and 'leftbehind' in ro[0]['text'] and 'http' not in ro[0]['text'] and 'DISCORD' not in json.dumps(ro), ro)
    chk('migration marked + dated backup', 'raidorder1' in a['seeded'] and any(f.startswith('automations.json.before-raidorder-') for f in os.listdir(h.d)))
    cmds = json.dumps(get('/api/commands/all'))
    chk('!leftbehind is in /api/commands/all', '!leftbehind' in cmds, cmds[:200])
    chk('fake OBS is connected to the Host', waitfor(lambda: 'OBS connected' in h.text(), 8), h.text()[-300:])
    h.feed('viewer1: !leftbehind'); time.sleep(2)
    chk('!leftbehind before any raid answers nothing', n_of('twitch.tv') == 0, texts())
    h.feed('raidpick evuto_ 12'); time.sleep(3)
    t = texts()
    chk('pick: emotes line then Discord line, nothing else (no shoutout)', len(t) == 2 and 'EMOTES' in t[0] and 'DISCORD' in t[1], t)
    chatters['n'] = 3; t0 = time.time()   # Raid Now: the chat empties
    chk('chat emptied: StopStream reached the (fake) OBS', waitfor(lambda: len(stops()) >= 1, 30), OBS['reqs'][-6:])
    time.sleep(1); t = texts()
    i_g = t.index('GOODNIGHT') if 'GOODNIGHT' in t else -1; i_l = next((i for i, x in enumerate(t) if '!leftbehind' in x), -1)
    chk('order: goodnight, then the !leftbehind line', 0 <= i_g < i_l, t)
    chk('StopStream came after the !leftbehind line', stops() and stops()[0][0] >= [c[0] for c in chats if '!leftbehind' in c[1]][0], (stops(), chats))
    chk('the !leftbehind line carries no link', all('twitch.tv' not in x for x in t if 'Type !leftbehind' in x), t)
    chk('landed on the chat-empty signal, not the countdown', 'raid landed (the chat emptied' in h.log(), [l for l in h.log().splitlines() if 'raid landed' in l])
    h.feed('raidpick evuto_ 12'); h.feed('event StreamOffline streamer'); time.sleep(14)   # a second landing signal, Twitch's countdown (5+10 s), Ivan ending by hand
    t = texts()
    chk('once per raid: one Discord, one goodnight, one leftbehind line, one StopStream', n_of('DISCORD') == 1 and n_of('GOODNIGHT') == 1 and n_of('Type !leftbehind') == 1 and len(stops()) == 1, (t, len(stops())))
    n0 = len(chats); h.feed('viewer3: !leftbehind'); time.sleep(2)
    chk('!leftbehind after the raid: the target link', texts()[n0:] == ['https://twitch.tv/evuto_'], texts()[n0:])
    n0 = len(chats); h.feed('viewer3: !leftbehind'); time.sleep(2)
    chk('same viewer within 30 s: nothing', texts()[n0:] == [], texts()[n0:])
    n0 = len(chats); sends.clear(); h.yt('!leftbehind'); time.sleep(3)
    chk('YouTube viewer: answered via Multi, nothing on Twitch, no raw key', texts()[n0:] == [] and len(sends) >= 1 and all(s.get('platform') == 'youtube' for s in sends) and 'twitch.tv/evuto_' in json.dumps(sends) and 'yt:' not in json.dumps(sends), (texts()[n0:], sends))
    h.feed('event StreamOnline streamer'); time.sleep(2)
    n0 = len(chats); h.feed('viewer2: !leftbehind'); time.sleep(2)
    chk('after the next stream starts: nothing', texts()[n0:] == [], texts()[n0:])
finally: h.stop()

# ---- 2. a dip to 30% is not a landing; Ivan ends by hand before the landing
reset(streaming=True, n=40); h = H(OBSP, 5)
try:
    waitfor(lambda: 'OBS connected' in h.text(), 8)
    h.feed('raidpick evuto_ 5'); time.sleep(1); chatters['n'] = 12
    OBS['streaming'] = False; h.feed('event StreamOffline streamer'); time.sleep(8)
    chk('30% is not a landing; the by-hand offline is held (no goodnight yet)', n_of('GOODNIGHT') == 0 and len(stops()) == 0 and 'raid landed' not in h.log(), (texts(), h.log()[-300:]))
    chk('countdown lands: goodnight once, !leftbehind line once', waitfor(lambda: n_of('GOODNIGHT') == 1 and n_of('Type !leftbehind') == 1, 25), texts())
    time.sleep(2)
    chk('OBS already off: StopStream skipped with a log line, none sent', len(stops()) == 0 and 'StopStream skipped' in h.log(), (stops(), h.log()[-300:]))
    chk('landing reason is the countdown', "countdown ran out" in h.log(), h.log()[-300:])
finally: h.stop()

# ---- 3. OBS ignores the first StopStream
reset(streaming=True, ignore_first=True, n=0); h = H(OBSP, 0)
try:
    waitfor(lambda: 'OBS connected' in h.text(), 8)
    h.feed('raidpick evuto_ 5')
    chk('StopStream ignored once: sent again, stream ends', waitfor(lambda: OBS['stops'] >= 2 and not OBS['streaming'], 45), (OBS['stops'], OBS['streaming']))
    chk('the retry is logged', waitfor(lambda: 'sent it again' in h.log(), 10), h.log()[-500:])
finally: h.stop()

# ---- 4. OBS not connected at the landing: loud error
reset(n=0); h = H(OBSP + 50, 0)
try:
    h.feed('raidpick evuto_ 5')
    chk('no OBS: the failure is logged loudly (error level)', waitfor(lambda: 'NOT STOPPED BY THE HOST' in h.log(), 40), h.log()[-500:])
    chk('no OBS: goodnight still said once', n_of('GOODNIGHT') == 1, texts())
finally: h.stop()
print('FAILS: %d' % len(fails)); sys.exit(1 if fails else 0)
