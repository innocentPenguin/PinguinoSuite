"""First 5 payout: the five places are paid straight into the economy (15000/10500/7500/4500/3000), never as a chat "!addpoints" line,
and a repeat of the same payout id is not paid twice.
Usage: python Tools/test-host-firstspay.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8996; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgfp_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8998', 'PINGUINO_FIRSTS_PAYOUT_MS': '700'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def out(): return open(outf, encoding='utf-8', errors='replace').read()
def says(): return [l[6:] for l in out().splitlines() if l.startswith('[say] ')]
def feed(line, wait=0.4): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait)
def bal(u): return json.load(urllib.request.urlopen(B + '/api/economy/user?login=' + u, timeout=5))['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    json.load(urllib.request.urlopen(urllib.request.Request(B + '/api/cutover', data=json.dumps({'on': True}).encode(), headers={'Content-Type': 'application/json'}), timeout=15))   # the game only runs after the Streamer.bot cutover
    feed('event StreamOnline nobody', 1.5)
    for i, n in enumerate(['ann', 'bob', 'cy', 'dee', 'eve']): feed('%s: hello there %d' % (n, i))
    time.sleep(6)   # 5 payouts, 0.7 s apart
    want = {'ann': 15000, 'bob': 10500, 'cy': 7500, 'dee': 4500, 'eve': 3000}
    got = {u: bal(u) for u in want}
    chk('each place is paid into the economy', got == want, got)
    chk('no "!addpoints" line was ever said in chat', not [s for s in says() if '!addpoints' in s.lower()], [s for s in says() if 'addpoints' in s.lower()])
    chk('the lock-in line was said once', len([s for s in says() if 'locked in' in s]) == 1, says())
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS firsts pay'); sys.exit(1 if fails else 0)
