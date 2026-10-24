#!/usr/bin/env python3
"""The Host answers the bot core's SetChannelGame (reflection call), so '!activity fn boxfights' sets the Twitch category instead of reporting
"Could not set the Twitch category". Sim Host (nothing goes to Twitch; HostCPH.SetChannelGame answers true in --sim). Usage: python Tools/test-host-setgame.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dll = args[0] if args else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def freeport():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
PORT, WS = freeport(), freeport()
d = tempfile.mkdtemp(prefix='pgsg_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
od = os.path.join(d, 'overlays_out'); os.makedirs(od); json.dump({'OverlayDir': od}, open(os.path.join(d, 'settings.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = str(WS)
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
fails = []
try:
    for _ in range(120):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3).read(); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    h.stdin.write(b'#ivan: !activity fn boxfights\n'); h.stdin.flush(); time.sleep(3)
    out = open(outf, encoding='utf-8', errors='replace').read()
    if 'Twitch category set to Fortnite' not in out: fails.append('no "Twitch category set to Fortnite." line')
    if 'Could not set the Twitch category' in out: fails.append('core still reports it could not set the category')
finally:
    try: h.kill()
    except Exception: pass
    time.sleep(1)
    if fails: print(open(outf, encoding='utf-8', errors='replace').read()[-1500:])
    shutil.rmtree(d, ignore_errors=True)
if fails:
    print('FAIL setgame: ' + '; '.join(fails)); sys.exit(1)
print('PASS setgame')
