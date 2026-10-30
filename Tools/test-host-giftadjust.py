"""Boards: Data/boards/adjust.json one-off gift corrections are added on top of the ledger (real cyfirl +2 entry is checked), survive a rebuild and are not counted twice.
Usage: python Tools/test-host-giftadjust.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSPORT = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgga_'); outp = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'boards'))
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump([{'at': 1788557489, 'type': 'gift', 'user': 'cyfirl', 'amount': 1, 'to': ''}, {'at': 1788557489, 'type': 'gift', 'user': 'anna', 'amount': 3, 'to': ''}], open(os.path.join(d, 'boards', 'events.json'), 'w'))
shutil.copy(os.path.join(suite, 'Data', 'boards', 'adjust.json'), os.path.join(d, 'boards', 'adjust.json'))
real = json.load(open(os.path.join(d, 'boards', 'adjust.json'), encoding='utf-8-sig'))['adjust']
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT)})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=15))
def post(p): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=b'{}', headers={'Content-Type': 'application/json'}), timeout=30))
def gifts(l):
    j = get('/api/boards'); return ((j.get('users') or {}).get(l) or {}).get('gifts')
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2); post('/api/boards/refresh'); time.sleep(1)
    chk('real file: cyfirl gifts +2 with a why', len(real) == 1 and real[0]['user'] == 'cyfirl' and real[0]['type'] == 'gifts' and real[0]['amount'] == 2 and len(real[0]['why']) > 40, real)
    chk('ledger 1 + adjust 2 = 3', gifts('cyfirl') == 3, gifts('cyfirl'))
    chk('others untouched', gifts('anna') == 3, gifts('anna'))
    post('/api/boards/refresh'); time.sleep(1); post('/api/boards/refresh'); time.sleep(1)
    chk('rebuilds do not count it twice', gifts('cyfirl') == 3, gifts('cyfirl'))
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1200:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS giftadjust'); sys.exit(1 if fails else 0)
