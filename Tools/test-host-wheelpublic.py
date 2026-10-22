"""Original site wheel overlay served from the Host: /api/wheel/public adapts Core's one-spin-one-pick state to the old overlay shape (pool, draw.steps, manual, teams), page is the original + penguin hub asset.
Usage: python Tools/test-host-wheelpublic.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8987; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgwp_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'wpt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8988'
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=1.0): h.stdin.write((l + '\n').encode()); h.stdin.flush(); time.sleep(w)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2); w = get('/api/wheel/public'); chk('none state', w['status'] == 'none' and w['draw'] is None and w['manual']['on'], w)
    feed('#ivan: !wheel open')
    for u in ['ana', 'bo', 'cy', 'dee']: feed(u + ': !me')
    w = get('/api/wheel/public'); chk('lobby', w['status'] == 'open' and sorted(w['names']) == ['ana', 'bo', 'cy', 'dee'] and w['draw'] is None and w['signedUp'] == 4, w)
    feed('#ivan: !wheel spin', 1.5); w = get('/api/wheel/public'); st = w['draw']['steps']
    chk('one pick, still in pool while spinning', w['status'] == 'drawing' and len(st) == 1 and st[0]['name'] in w['pool'] and w['manual']['revealed'] == 1 and w['manual']['total'] == 4 and not w['manual']['last'], w)
    chk('no mmr leaks', 'avg' not in json.dumps(w) and 'seed' not in json.dumps(w))
    time.sleep(10); w = get('/api/wheel/public'); chk('pick leaves the pool after the spin', st[0]['name'] not in w['pool'] and len(w['pool']) == 3, w['pool'])
    page = urllib.request.urlopen(B + '/wheel.html', timeout=10).read().decode('utf-8')
    chk('original overlay page', 'Tournament Wheel Overlay' in page and '/api/wheel/public' in page and 'penguin-anim.gif' in page and '%%PENGUIN%%' not in page)
    r = urllib.request.urlopen(B + '/penguin-anim.gif', timeout=10); chk('hub asset served as gif', r.headers['Content-Type'] == 'image/gif' and len(r.read()) > 100000)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS wheelpublic'); sys.exit(1 if fails else 0)
