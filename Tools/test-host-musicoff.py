"""Music commands have one voice: the Host's Spotify presets for !song / !songqueue / !vol / !skip speak as the helper account (one-time migration, fresh seed too),
and !skip / !voteskip reach the module as a plain vote from everyone, mods included (no instant skip). Fake Spotify module + sim Host.
Usage: python Tools/test-host-musicvoice.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MOD = 8981, 8982
bodies = []
class Mod(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); bodies.append(json.loads(self.rfile.read(n) or b'{}'))
        o = b'{"ok":true,"say":"ok"}'; self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MOD), Mod).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgmv_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
url = 'http://127.0.0.1:%d/api/chat-command' % MOD
def preset(i, cmd, names): return {'id': 'spotify-' + i, 'name': 'Spotify: !' + names[0].lstrip('!'), 'group': 'Spotify', 'enabled': True, 'triggers': [{'type': 'command', 'names': names, 'permission': 'everyone', 'cooldownSec': 0, 'userCooldownSec': 0, 'consume': True}], 'conditions': [], 'steps': [{'type': 'module_command', 'url': url, 'command': cmd, 'as': 'core'}]}
old = {'actions': [preset('skip', 'skip', ['!skip', '!voteskip']), preset('song', 'song', ['!song', '!np']), preset('queue', 'queue', ['!songqueue']), preset('vol', 'volume', ['!vol']), preset('oops', 'oops', ['!oops'])], 'seeded': ['spotify', 'spotify2']}
json.dump(old, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8983'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    acts = {a['id']: a for a in json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8'))['actions']}
    voice = lambda i: acts[i]['steps'][0]['as']
    chk('song / queue / vol / skip speak as helper', all(voice('spotify-' + i) == 'helper' for i in ('song', 'queue', 'vol', 'skip')), {i: voice('spotify-' + i) for i in ('song', 'queue', 'vol', 'skip')})
    chk('oops keeps its voice (not a duplicate)', voice('spotify-oops') == 'core')
    n = len(bodies); feed('*modguy: !skip', 1.5); b = bodies[n:]
    chk('mod !skip is a plain vote', len(b) == 1 and b[0]['command'] == 'skip' and b[0]['isMod'] is False and str(b[0]['role']) == '1', b)
    n = len(bodies); feed('*modguy: !voteskip', 1.5); b = bodies[n:]
    chk('mod !voteskip is the same plain vote', len(b) == 1 and b[0]['command'] == 'skip' and b[0]['isMod'] is False, b)
    n = len(bodies); feed('viewer1: !skip', 1.5); b = bodies[n:]
    chk('viewer !skip reaches the module the same way', len(b) == 1 and b[0]['command'] == 'skip' and b[0]['isMod'] is False, b)
    n = len(bodies); feed('*modguy: !song', 1.5); b = bodies[n:]
    chk('other commands still carry the mod flag', len(b) == 1 and b[0]['isMod'] is True, b)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS musicvoice'); sys.exit(1 if fails else 0)
