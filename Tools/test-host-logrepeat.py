"""A site that answers 404 to every push must not flood the log: the same warning is written once per window (with a count of repeats later), and the command-list push backs off.
Usage: python Tools/test-host-logrepeat.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
HITS = {'commands': 0}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _any(self):
        n = int(self.headers.get('Content-Length', 0)); self.rfile.read(n)
        if 'commands-all' in self.path: HITS['commands'] += 1
        self.send_response(404); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
    do_GET = do_POST = _any
srv = ThreadingHTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pglr_')
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': 'k', 'PINGUINO_SITE_POLL_SEC': '1'})
fails = []
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(45)
    log = open(os.path.join(d, 'console', 'host.jsonl'), encoding='utf-8').read().splitlines() if os.path.exists(os.path.join(d, 'console', 'host.jsonl')) else []
    n = sum(1 for l in log if 'command list push failed' in l)
    if HITS['commands'] < 1: fails.append('the command-list push never reached the fake site')
    if n != 1: fails.append('command-list failure logged %d times in 45 s (want exactly 1)' % n)
    if HITS['commands'] > 6: fails.append('command-list push did not back off (%d tries in 45 s)' % HITS['commands'])
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS logrepeat'); sys.exit(1 if fails else 0)
