"""People who typed !optmeout (Privacy "anon" in chat_memory.json) are never named on the Host public boards / chat lines.
Usage: python Tools/test-host-audit.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8987; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pganon_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'adjust': {'alice': 500, 'bob': 300, 'secretsam': 9000}}, open(os.path.join(eco, 'points.json'), 'w'))
json.dump({'secretsam': {'Login': 'secretsam', 'Name': 'SecretSam', 'Privacy': 'anon'}, 'alice': {'Login': 'alice', 'Name': 'Alice', 'Privacy': ''}}, open(os.path.join(d, 'chat_memory.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8986'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.7):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
def bal(u): return json.load(urllib.request.urlopen(B + '/api/economy/user?login=' + u, timeout=5))['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('v1: !toppoints', 1.2); txt = ' '.join(r)
    chk('top points still lists people', 'lice' in txt, r)
    chk('an !optmeout viewer is not named on the points board', 'ecretsam' not in txt.lower() and 'secretsam' not in txt.lower(), r)
    chk('...and shows as Anonymous Penguin', 'Anonymous Penguin' in txt, r)
    r = ask('v2: !points @secretsam', 1.0); chk('asking about an opted-out viewer does not name them', 'ecretsam' not in ' '.join(r).lower(), r)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS audit'); sys.exit(1 if fails else 0)
