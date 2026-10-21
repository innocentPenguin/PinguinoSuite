"""GET /api/commands/all: unfiltered command list (archived + disabled included) with raw usage and a ranked `top`.  Usage: python Tools/test-host-cmdall.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8982; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcall_'); json.dump({'Channel': 't', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8983'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'o.txt'), 'wb'), stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=10))
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    for _ in range(3): host.stdin.write(b'alice: !mmr\n'); host.stdin.flush(); time.sleep(0.8)
    a = get('/api/commands/all'); n0 = a['count']
    chk('shape', a['ok'] and a['unfiltered'] and a['count'] == len(a['commands']) == len(a['top']) and all('uses' in c and 'archived' in c for c in a['commands']), list(a))
    chk('top sorted', all(a['top'][i]['uses'] >= a['top'][i + 1]['uses'] for i in range(len(a['top']) - 1)))
    post('/api/commands/profile', {'id': '!mmr', 'enabled': False, 'by': 'test'}); post('/api/commands/archive', {'id': '!mmr', 'by': 'test'})
    b = get('/api/commands/all'); m = [c for c in b['commands'] if c['id'] == '!mmr']
    chk('archived + disabled command still listed', b['count'] == n0 and len(m) == 1 and m[0]['archived'] is True, m)
    chk('not in the filtered list', all(c['id'] != '!mmr' for c in get('/api/commands/profiles')['commands']))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS cmdall'); sys.exit(1 if fails else 0)
