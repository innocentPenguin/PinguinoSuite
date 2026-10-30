#!/usr/bin/env python3
"""Runs Tools/post-restart-check.py against a sim Host (temp data, free port, never the live Host). Usage: python Tools/test-host-postrestart.py [dll]
PASS = the check exits 0 on a healthy sim Host (WARN rows allowed, e.g. chat/OBS not connected in sim), prints a summary and the route probe ran."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dll = args[0] if args else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def freeport():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
PORT, WS = freeport(), freeport()
d = tempfile.mkdtemp(prefix='pgpr_')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
od = os.path.join(d, 'overlays_out'); os.makedirs(od); json.dump({'OverlayDir': od}, open(os.path.join(d, 'settings.json'), 'w'))
open(os.path.join(od, 'live_state.js'), 'w').write('window.LIVE_STATE = {};')   # a fresh sim data dir has no live_state yet: seed the minimal file so the /live_state.js asset check has something to serve
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = str(WS)
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
rc = 1; out = ''
try:
    for _ in range(120):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3).read(); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    p = subprocess.run([sys.executable, os.path.join(here, 'post-restart-check.py'), '--base', 'http://127.0.0.1:%d' % PORT, '--since', 'edb1e54^', '--lenient'], capture_output=True, text=True, timeout=240)
    out = p.stdout + p.stderr; rc = p.returncode
finally:
    try: h.kill()
    except Exception: pass
print(out)
ok = rc == 0 and 'SUMMARY:' in out and 'new route /api/scene-health' in out
print('PASS postrestart' if ok else 'FAIL postrestart (exit %s)' % rc)
sys.exit(0 if ok else 1)
