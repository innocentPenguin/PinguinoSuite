"""Stall watchdog: a stuck step and the dispatchLock holder are named, a chat waiting on the lock is reported and still answered, a skipped tick is logged once.  Usage: python Tools/test-host-watchdog.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
import socket
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSP = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgwd_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = str(WSP)
env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'
outp = os.path.join(d, 'out.txt')
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
fails = []
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    h.stdin.write(b'watchdogtest'+bytes([10])); h.stdin.flush()
    t = ''
    for _ in range(60):
        time.sleep(0.5); t = open(outp, 'rb').read().decode('utf-8', 'replace')
        if '[watchdogtest]' in t: break
    for l in t.splitlines():
        if l.startswith('FAIL '): fails.append(l)
    if 'ALL PASS' not in t: fails.append('no ALL PASS: ' + t[-600:])
finally:
    try: h.stdin.close(); h.kill()
    except Exception: pass
if fails: print('FAIL', fails); sys.exit(1)
print('PASS test-host-watchdog')
