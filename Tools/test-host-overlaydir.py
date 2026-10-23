"""A sim / test Host must never write the REAL overlays folder (live_state.js): with no OverlayDir in settings.json it writes under its own data dir; an explicit OverlayDir still wins.
Usage: python Tools/test-host-overlaydir.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = int(os.environ.get('PGTEST_PORT', 8963)); B = 'http://127.0.0.1:%d' % PORT
real = os.path.join(suite, 'PinguinoB0t', 'overlays', 'live_state.js')
def stamp(): return (os.path.getmtime(real), os.path.getsize(real)) if os.path.exists(real) else None
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def run(explicit):
    d = tempfile.mkdtemp(prefix='pgovd_'); outf = os.path.join(d, 'out.txt'); ov = os.path.join(d, 'myov'); os.makedirs(ov)
    json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    if explicit: json.dump({'OverlayDir': ov}, open(os.path.join(d, 'settings.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8964'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            try: urllib.request.urlopen(B + '/api/status', timeout=2); break
            except Exception: time.sleep(0.5)
        time.sleep(3)
        for path, body in (('/api/sim/start', {'count': 3, 'mode': 'both'}), ('/api/sim/clear', {})):
            try: urllib.request.urlopen(urllib.request.Request(B + path, json.dumps(body).encode(), {'Content-Type': 'application/json'}), timeout=10).read()
            except Exception as e: print('post', path, e)
            time.sleep(2)
        time.sleep(2)
        return d, ov
    finally:
        h.kill(); time.sleep(0.5)
before = stamp()
d, ov = run(False)
chk('default sim: the real live_state.js is untouched', stamp() == before, (before, stamp()))
own = os.path.join(d, 'overlays', 'live_state.js')
chk('default sim: live_state.js is written under the data dir instead', os.path.exists(own), os.listdir(d))
shutil.rmtree(d, True)
d, ov = run(True)
chk('explicit OverlayDir still wins', os.path.exists(os.path.join(ov, 'live_state.js')) and stamp() == before, (os.listdir(ov), before, stamp()))
shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS overlaydir'); sys.exit(1 if fails else 0)
