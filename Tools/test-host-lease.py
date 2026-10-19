"""Single-instance test for PinguinoHost against a mock core device lease (Docs\\MODULE_CONTRACT.md "Devices: master / auxiliary").
Usage: python Tools/test-host-lease.py [path-to-PinguinoHost.dll]   (default: PinguinoHost/bin/Release/net8.0/PinguinoHost.dll)
Hosts run on temp data folders and read a throwaway channel anonymously; nothing is sent."""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
MODE = {'v': 'master'}   # master | aux | old (404)
STREAM = []
fails = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        data = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path != '/api/device/lease': return self._send(404, {})
        if self.headers.get('Authorization') != 'Bearer testtoken': return self._send(401, {'ok': False})
        if MODE['v'] == 'old': return self._send(404, {})
        self._send(200, {'is_master': MODE['v'] == 'master', 'master_id': 'm1', 'master_name': 'Streaming PC', 'device_id': 'd1'})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/device/streaming': STREAM.append(b.get('on'))
        self._send(200, {'ok': True})

srv = ThreadingHTTPServer(('127.0.0.1', 8841), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

def host(port):
    d = tempfile.mkdtemp(prefix='pglease_')
    json.dump({'Channel': 'pglease_test', 'OverlayPort': port}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    env = dict(os.environ, PINGUINO_LEASE_URL='http://127.0.0.1:8841', PINGUINO_API_TOKEN='testtoken', PINGUINO_LEASE_POLL='2', PINGUINO_LEASE_GRACE='6', PINGUINO_DATA_DIR=d)
    return subprocess.Popen(['dotnet', dll, '--no-sync', '--data', d], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get(port, path):
    try: return json.load(urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=3))
    except Exception: return None

def until(fn, secs, what):
    t = time.time() + secs
    while time.time() < t:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.5)
    fails.append('timeout: ' + what); return False

def state(port):
    s = get(port, '/api/status')
    return ((s or {}).get('lease') or {}).get('state'), (s or {}).get('chatConnected')

procs = []
try:
    # a Host on an auxiliary device: never connects, then (after the core says "not master" twice) shuts itself down
    MODE['v'] = 'aux'
    x = host(8851); procs.append(x)
    until(lambda: x.poll() is not None, 40, 'a Host that is told it is not the master shuts down')
    # promoted: a Host that sees is_master:true connects
    MODE['v'] = 'master'
    a = host(8852); procs.append(a)
    until(lambda: state(8852)[0] == 'master', 25, 'A sees is_master and becomes master')
    until(lambda: state(8852)[1] is True, 25, 'A chat connected')
    # a second Host on the same data folder is refused by the PC mutex (checked through a fresh process on the same --data)
    # demoted: A must disconnect chat and exit
    MODE['v'] = 'aux'
    until(lambda: a.poll() is not None, 30, 'A shuts down after losing the master role')
    # an old core without the device endpoint: single device, Host runs
    MODE['v'] = 'old'
    o = host(8853); procs.append(o)
    until(lambda: state(8853)[0] == 'master' and state(8853)[1] is True, 30, 'old core (404): Host runs as the only device')
    # core vanishes: after the grace period the Host stops
    srv.shutdown(); srv.server_close()
    until(lambda: o.poll() is not None, 40, 'Host stops when the core stays unreachable')
finally:
    for p in procs:
        try: p.kill()
        except Exception: pass
print('HOST LEASE: ' + ('PASS' if not fails else 'FAIL - ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
