"""!downtime and !uptime: live now, then offline after a Host restart (persisted lastLiveSeen); and !points answers with DEFAULT cooldowns (regression: the viewer-command list once dropped the economy commands).
Usage: python Tools/test-host-downtime.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8953; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgdt_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'dtt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def start(live):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8952', 'PINGUINO_LIVE': live})
    open(out, 'wb').close()
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    time.sleep(9); return h
def feed(h, line): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(1.5)
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
host = None
try:
    host = start('1')
    feed(host, 'viewer: !downtime'); chk('live: downtime says live', any('live right now' in s for s in says()), says())
    feed(host, 'viewer: !uptime'); chk('live: uptime', any('has been live for' in s for s in says()), says())
    feed(host, 'viewer: !points'); chk('!points answers with default cooldowns', any('you have 0 points' in s or 'you have' in s for s in says()), says())
    chk('lastLiveSeen persisted', os.path.exists(os.path.join(d, 'live_last.json')))
    host.kill(); host.wait(); time.sleep(2)
    host = start('0')
    feed(host, 'viewer: !downtime'); chk('offline: ended ago', any('last stream ended' in s and 'ago' in s for s in says()), says())
    feed(host, 'viewer2: !uptime'); chk('offline: uptime', any('offline right now' in s for s in says()), says())
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS downtime'); sys.exit(1 if fails else 0)
