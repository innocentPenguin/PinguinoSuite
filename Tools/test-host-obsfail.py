#!/usr/bin/env python3
"""The pre-stream OBS item tells 'OBS closed / not running' apart from 'OBS refused the WebSocket password'. Sim Host + PINGUINO_OBS=1 against
(1) a free port nobody listens on -> "closed or not running", (2) Tools/mock-obs.py with another password -> "refused the WebSocket password".
Usage: python Tools/test-host-obsfail.py [dll]   (PASS obsfail)"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dll = args[0] if args else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def freeport():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
fails = []
def scenario(name, obs_port, want, mock_pw=None):
    PORT, WS = freeport(), freeport()
    d = tempfile.mkdtemp(prefix='pgof_')
    json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': obs_port, 'ObsPassword': 'wrong-pw'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    od = os.path.join(d, 'overlays_out'); os.makedirs(od); json.dump({'OverlayDir': od}, open(os.path.join(d, 'settings.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_OBS': '1'})
    mock = subprocess.Popen([sys.executable, os.path.join(here, 'mock-obs.py'), str(obs_port), mock_pw, ''], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) if mock_pw else None
    time.sleep(1)
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3).read(); break
            except Exception: time.sleep(0.5)
        txt = ''
        for _ in range(20):
            time.sleep(1)
            ps = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/prestream' % PORT, timeout=10))
            it = [i for i in ps['items'] if i['id'] == 'obs']
            txt = (it[0].get('detail') or '') if it else ''
            if want in txt: break
        if want not in txt: fails.append('%s: obs detail is %r, wanted %r' % (name, txt, want))
        if name == 'closed' and 'password' in txt: fails.append('closed case mentions the password: ' + txt)
        if name == 'auth' and 'not running' in txt: fails.append('auth case says not running: ' + txt)
    finally:
        for p in (h, mock):
            try: p and p.kill()
            except Exception: pass
        time.sleep(1); shutil.rmtree(d, ignore_errors=True)
scenario('closed', freeport(), 'OBS is closed or not running')
scenario('auth', freeport(), 'refused the WebSocket password', mock_pw='right-pw')
if fails: print('FAIL obsfail: ' + '; '.join(fails)); sys.exit(1)
print('PASS obsfail')
