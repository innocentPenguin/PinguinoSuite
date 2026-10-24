"""EventSub subscribe: a 409 (the subscription already exists) is not a refusal (no 'check token scopes' warning, prestream check stays green) and no subscription is requested twice
(channel.raid from_broadcaster was listed twice, so every start logged 'channel.raid refused (409)').  Usage: python Tools/test-host-eventsub-409.py [dll]"""
import base64, glob, hashlib, http.server, json, os, shutil, socket, struct, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, WS = 8991, 8992, 8993
seen = set(); posted = []
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if 'type' not in b: b = {'type': 'x', 'condition': {}}
        key = json.dumps([b['type'], b['condition']], sort_keys=True); posted.append(key)
        code = 409 if key in seen else 202; seen.add(key); o = b'{"data":[{}]}'
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
    def do_GET(self):
        o = b'{"data":[{"id":"b1","login":"trial","display_name":"trial"}]}'; self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', HX), Hx).serve_forever, daemon=True).start()
def ws_server():
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('127.0.0.1', WS)); s.listen(5)
    while True:
        c, _ = s.accept(); data = b''
        while b'\r\n\r\n' not in data: data += c.recv(4096)
        key = [l.split(b':', 1)[1].strip() for l in data.split(b'\r\n') if l.lower().startswith(b'sec-websocket-key')][0]
        acc = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
        c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + acc + b'\r\n\r\n')
        m = json.dumps({'metadata': {'message_type': 'session_welcome', 'message_id': 'm1'}, 'payload': {'session': {'id': 'S1', 'keepalive_timeout_seconds': 30}}}).encode()
        c.sendall(b'\x81' + (bytes([len(m)]) if len(m) < 126 else b'\x7e' + struct.pack('>H', len(m))) + m)
        try:
            while c.recv(4096): pass
        except Exception: pass
threading.Thread(target=ws_server, daemon=True).start()
d = tempfile.mkdtemp(prefix='pges_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 'tok', 'ClientId': 'cid', 'BroadcasterId': 'b1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_EVENTSUB_URL': 'ws://127.0.0.1:%d/ws' % WS, 'PINGUINO_COMPAT_WS_PORT': '8994'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(80):
        if len(posted) > 25: break
        time.sleep(0.5)
    time.sleep(1.5)
    chk('subscriptions were requested', len(posted) > 20, len(posted))
    chk('none requested twice', len(posted) == len(set(posted)), [k for k in set(posted) if posted.count(k) > 1])
    txt = ''.join(open(f, 'rb').read().decode('utf-8', 'replace') for f in glob.glob(os.path.join(d, '**', 'host.jsonl'), recursive=True))
    chk('no refusal logged', 'refused' not in txt, [l for l in txt.splitlines() if 'refused' in l][:2])
    # a sub that already exists on the Twitch side (409) is fine too: pre-seed and restart is not needed, replay one request
    r = urllib.request.Request('http://127.0.0.1:%d/x' % HX, data=json.dumps({'type': 'channel.raid', 'condition': {'to_broadcaster_user_id': 'b1'}}).encode(), method='POST')
    try: urllib.request.urlopen(r, timeout=5); chk('fake answers 409 for a repeat', False)
    except urllib.error.HTTPError as e: chk('fake answers 409 for a repeat', e.code == 409)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS eventsub-409'); sys.exit(1 if fails else 0)
