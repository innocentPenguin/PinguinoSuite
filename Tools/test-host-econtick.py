"""Economy tick: log line + lastTick/paidLastTick on /api/economy, chat-activity bonus, one-time import announcement. Usage: python Tools/test-host-econtick.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8994; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pget_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'baseline': {'at': 'x', 'source': 'streamelements', 'users': {'zed': {'points': 50, 'minutes': 5, 'lifetime': 50}}}}, open(os.path.join(eco, 'points.json'), 'w'))
json.dump({'ActivityLinesPerPoint': 2, 'ActivityCapPer10Min': 3, 'PointsPerMinute': 1.0}, open(os.path.join(eco, 'settings.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8996', 'PINGUINO_ECONOMY_LIVE': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '8'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    for i in range(6): h.stdin.write(('viewer%d: hello number %d\n' % (1, i)).encode()); h.stdin.flush(); time.sleep(0.2)
    time.sleep(14)
    e = json.load(urllib.request.urlopen(B + '/api/economy', timeout=5))['earning']
    chk('tick fields', e.get('lastTick') and 'paidLastTick' in e and e.get('lastTickResult') == 'paid', e)
    u = json.load(urllib.request.urlopen(B + '/api/economy/user?login=viewer1', timeout=5))
    chk('activity bonus capped', u['points'] >= 3, u)
    chk('announced once', sum('StreamElements' in s for s in says()) == 1, says())
    cl = open(os.path.join(d, 'console', 'host.jsonl'), encoding='utf-8', errors='replace').read()
    chk('tick log line', 'tick: paid' in cl, cl[-300:])
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS econtick'); sys.exit(1 if fails else 0)
