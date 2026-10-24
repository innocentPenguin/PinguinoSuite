"""The Helper owns the music replies: the Host's Spotify presets for !song / !songqueue / !vol / !skip are removed (one-time migration of a saved automations.json with a dated backup,
a marker so they are never re-added; a fresh seed never creates them). Dispatching those commands gives zero Host replies and no module call; !sr / !oops / !blocksong / !srclear stay.
Fake Spotify module + sim Host. Usage: python Tools/test-host-musicoff.py [dll]"""
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
    def load(): return json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8'))
    ids = [a['id'] for a in load()['actions']]
    chk('song / queue / vol / skip presets removed', not [i for i in ids if i in ('spotify-song', 'spotify-queue', 'spotify-vol', 'spotify-skip')], ids)
    chk('oops stays', 'spotify-oops' in ids, ids)
    chk('marker set, dated backup written', 'musicoff1' in load()['seeded'] and [f for f in os.listdir(d) if f.startswith('automations.json.before-musicoff-')], os.listdir(d))
    n = len(bodies); o0 = open(outp, 'rb').read().count(b'[say] ')
    for line in ('viewer1: !song', 'viewer1: !np', 'viewer1: !currentsong', 'viewer1: !songqueue', 'viewer1: !srqueue', 'viewer1: !vol', 'viewer1: !volume', 'viewer1: !skip', '*modguy: !skip', 'viewer1: !voteskip'):
        feed(line, 0.8)
    chk('the Host calls the module for none of them', len(bodies) == n, bodies[n:])
    chk('and says nothing', open(outp, 'rb').read().count(b'[say] ') == o0, open(outp, 'rb').read().decode('utf-8', 'replace')[-400:])
    n = len(bodies); feed('viewer1: !oops', 1.5)
    chk('!oops still goes to the module', len(bodies) == n + 1 and bodies[-1]['command'] == 'oops', bodies[n:])
    host.kill(); time.sleep(0.5); ids0 = ids
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3); chk('after a restart they are not added back', [a['id'] for a in load()['actions']] == ids0, [a['id'] for a in load()['actions']])
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS musicoff'); sys.exit(1 if fails else 0)
