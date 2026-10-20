"""Offline mode switch: default off, GET/POST /api/offline-mode (Origin gated), shown in /api/live-state, timers behave live while ON, persists over a restart, !offlinemode for mods only.
Usage: python Tools/test-host-offline.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8979; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgoff_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'offt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8978', 'PINGUINO_LIVE': '0'})
fails = []; host = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body, origin=B):
    h = {'Content-Type': 'application/json'}
    if origin: h['Origin'] = origin
    return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(body).encode(), headers=h), timeout=10))
def start():
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3); return h
def feed(h, line): h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(1.5)
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
try:
    host = start()
    r = get('/api/offline-mode'); chk('default off', r['ok'] and r['enabled'] is False and r['live'] is not True and r['behavesLive'] is False, r)
    chk('live-state shows it', get('/api/live-state')['offlineMode'] is False)
    chk('timers see offline', get('/api/timers')['live'] is False)
    try: post('/api/offline-mode', {'enabled': True}, origin='http://evil.example'); chk('foreign origin refused', False)
    except urllib.error.HTTPError as e: chk('foreign origin refused', e.code in (401, 403), e.code)
    r = post('/api/offline-mode', {}); chk('enabled required', r['ok'] is False, r)
    r = post('/api/offline-mode', {'enabled': True}); chk('POST on', r['ok'] and r['enabled'] and r['behavesLive'] and r['live'] is not True, r)
    chk('live-state shows on', get('/api/live-state')['offlineMode'] is True)
    chk('timers behave live', get('/api/timers')['live'] is True)
    chk('file written', json.load(open(os.path.join(d, 'config', 'offline_mode.json')))['enabled'] is True)
    host.kill(); host.wait(); host = start()
    chk('persisted over restart', get('/api/offline-mode')['enabled'] is True)
    n = len(says()); feed(host, 'viewer: !offlinemode off'); chk('viewer ignored', get('/api/offline-mode')['enabled'] is True and len(says()) == n, says()[n:])
    feed(host, '*modguy: !offlinemode status'); chk('mod status', any('Offline mode is ON' in s for s in says()), says())
    feed(host, '*modguy: !offlinemode off'); chk('mod off', get('/api/offline-mode')['enabled'] is False and any('OFF' in s for s in says()), says())
    chk('timers back to offline', get('/api/timers')['live'] is False)
    feed(host, '#ivan: !offlinemode on'); chk('streamer on', get('/api/offline-mode')['enabled'] is True)
    feed(host, '*modguy: !offlinemode bogus'); chk('usage line', any('Use: !offlinemode' in s for s in says()), says())
    post('/api/offline-mode', {'enabled': False}); chk('POST off', get('/api/offline-mode')['enabled'] is False)
    log = open(os.path.join(d, 'runtime', 'mod_audit.log'), encoding='utf-8', errors='replace').read(); chk('audited', 'offline-mode' in log, log[-200:])
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS offline mode'); sys.exit(1 if fails else 0)
