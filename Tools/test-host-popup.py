#!/usr/bin/env python3
"""The 'Latest Group' popup after an alert: (1) its length is PopupSeconds from alerts_settings.json (change it, the show duration follows);
(2) two alerts close together keep it visible until the second one's time is up, without a hide/show flicker in between and without ending the first one's window early.
Sim Host + PINGUINO_OBS=1 against Tools/mock-obs.py (it logs every request; show/hide = SetSceneItemEnabled true/false). Usage: python Tools/test-host-popup.py [dll]  (PASS popup)"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dll = args[0] if args else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def freeport():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
PORT, WS, OBS = freeport(), freeport(), freeport()
d = tempfile.mkdtemp(prefix='pgpop_')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': OBS, 'ObsPassword': 'pw'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
od = os.path.join(d, 'overlays_out'); os.makedirs(od); json.dump({'OverlayDir': od}, open(os.path.join(d, 'settings.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_OBS': '1'})
mock = subprocess.Popen([sys.executable, '-u', os.path.join(here, 'mock-obs.py'), str(OBS), 'pw', ''], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
ev = []   # (time, 'show'|'hide')
def pump():
    for ln in mock.stdout:
        if os.environ.get('PG_DEBUG'): print('MOCK', ln.strip()[:160], flush=True)
        if 'SetSceneItemEnabled' in ln and 'Latest Group' not in ln:
            m = re.search(r'"sceneItemEnabled": (true|false)', ln)
            if m and '"sceneItemId": 7' in ln: ev.append((time.time(), 'show' if m.group(1) == 'true' else 'hide'))
threading.Thread(target=pump, daemon=True).start()
time.sleep(1)
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', os.environ.get('PG_SUITE', suite)], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT, text=True)
fails = []
def api(p, body=None):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def feed(l): host.stdin.write(l + '\n'); host.stdin.flush()
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    for _ in range(40):
        if any(True for _ in ev) or 'OBS connected' in open(os.path.join(d, 'out.txt'), encoding='utf-8', errors='replace').read(): break
        time.sleep(0.5)
    time.sleep(1)
    ap = api('/api/overlay-options/schema').get('alertPopup') or {}
    chk('overlay options schema lists PopupSeconds', ap.get('key') == 'PopupSeconds' and ap.get('min') == 1 and ap.get('max') == 120, ap)
    api('/api/automations/enable', {'id': 'sb-cheer', 'on': True})
    api('/api/alerts-settings', {'PopupSeconds': 3}); ev.clear()
    t0 = time.time(); feed('event TwitchCheer cy 300'); time.sleep(6)
    sh = [t for t, k in ev if k == 'show']; hi = [t for t, k in ev if k == 'hide']
    chk('one alert: shown once and hidden once', len(sh) == 1 and len(hi) == 1, ev)
    if sh and hi: chk('one alert: visible about PopupSeconds (3 s)', 2.6 <= hi[0] - sh[0] <= 4.0, hi[0] - sh[0])
    api('/api/alerts-settings', {'PopupSeconds': 6}); ev.clear()
    feed('event TwitchCheer cy 300'); time.sleep(9)
    sh = [t for t, k in ev if k == 'show']; hi = [t for t, k in ev if k == 'hide']
    if sh and hi: chk('PopupSeconds=6 changes the length (6 s)', 5.6 <= hi[0] - sh[0] <= 7.0, hi[0] - sh[0])
    else: chk('PopupSeconds=6 popup shown and hidden', False, ev)
    api('/api/alerts-settings', {'PopupSeconds': 3}); ev.clear()
    ta = time.time(); feed('event TwitchCheer a 100'); time.sleep(2); tb = time.time(); feed('event TwitchCheer b 100'); time.sleep(9)
    kinds = [k for _, k in ev]; hi = [t for t, k in ev if k == 'hide']
    chk('two alerts: one continuous show/hide, no flicker', kinds == ['show', 'hide'], kinds)
    if hi: chk('two alerts: not hidden before the second alert\'s 3 s are up', hi[0] >= tb + 2.6, 'hide %.1f s after the 2nd alert' % (hi[0] - tb)); chk('two alerts: hidden soon after the second one ends (not 6+ s later)', hi[0] <= tb + 4.5, 'hide %.1f s after the 2nd alert' % (hi[0] - tb))
except Exception as e:
    fails.append('error %r; host output: %s' % (e, open(os.path.join(d, 'out.txt'), encoding='utf-8', errors='replace').read()[-800:]))
finally:
    for p in (host, mock):
        try: p.kill()
        except Exception: pass
    time.sleep(1); (None if os.environ.get('PG_DEBUG') else shutil.rmtree(d, True))
print('FAIL popup: ' + '; '.join(fails) if fails else 'PASS popup'); sys.exit(1 if fails else 0)
