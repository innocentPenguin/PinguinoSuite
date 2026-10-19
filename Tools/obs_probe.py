"""Tiny OBS WebSocket 5 client for checks (no extra packages). Reads host/port/password from the Host's host_secrets.json (never prints the password).
Usage: python Tools/obs_probe.py RequestType [json-data]   e.g.  GetReplayBufferStatus   |   GetGroupSceneItemList '{"sceneName":"Latest Group"}'"""
import base64, hashlib, json, os, socket, struct, sys

def _frame(payload, op=1):
    b = payload.encode() if isinstance(payload, str) else payload
    hdr = bytes([0x80 | op]); n = len(b); mask = os.urandom(4)
    hdr += bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n)
    return hdr + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(b))

def _read(s, n):
    buf = b''
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c: raise EOFError
        buf += c
    return buf

def _recv(s):
    msg = b''
    while True:
        h = _read(s, 2); fin = h[0] & 0x80; ln = h[1] & 0x7f
        if ln == 126: ln = struct.unpack('>H', _read(s, 2))[0]
        elif ln == 127: ln = struct.unpack('>Q', _read(s, 8))[0]
        msg += _read(s, ln)
        if fin: return json.loads(msg)

class Obs:
    def __init__(self, host=None, port=None, password=None):
        sec = {}
        for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Data', 'runtime', 'host_secrets.json'),):
            if os.path.exists(p): sec = json.load(open(p, encoding='utf-8-sig'))
        host = host or sec.get('ObsHost', '127.0.0.1'); port = int(port or sec.get('ObsPort', 4455)); pw = password if password is not None else sec.get('ObsPassword', '')
        self.s = socket.create_connection((host, port), timeout=6)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(('GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n' % (host, port, key)).encode())
        resp = b''
        while b'\r\n\r\n' not in resp: resp += self.s.recv(1)
        hello = _recv(self.s); ident = {'rpcVersion': 1}
        a = hello['d'].get('authentication')
        if a and pw:
            sec1 = base64.b64encode(hashlib.sha256((pw + a['salt']).encode()).digest()).decode()
            ident['authentication'] = base64.b64encode(hashlib.sha256((sec1 + a['challenge']).encode()).digest()).decode()
        self.s.sendall(_frame(json.dumps({'op': 1, 'd': ident}))); self.n = 0
        while _recv(self.s)['op'] != 2: pass
    def call(self, rtype, data=None):
        self.n += 1; rid = 'p%d' % self.n
        self.s.sendall(_frame(json.dumps({'op': 6, 'd': {'requestType': rtype, 'requestId': rid, 'requestData': data or {}}})))
        while True:
            m = _recv(self.s)
            if m['op'] == 7 and m['d']['requestId'] == rid: return m['d']
    def close(self):
        try: self.s.close()
        except Exception: pass

if __name__ == '__main__':
    o = Obs(); r = o.call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(json.dumps({'ok': r['requestStatus']['result'], 'status': r['requestStatus'], 'data': r.get('responseData')}, indent=1, ensure_ascii=False)); o.close()
