"""Act live while recording: OBS RecordStateChanged / GetRecordStatus (Tools/mock-obs.py) drive LiveState.Active; paused still counts; OBS dropped = false; toggle persists (default ON) without clobbering offline mode;
!uptime says recording-only; host.jsonl gets a state-change line.  Usage: python Tools/test-host-recording.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, OBS = 8984, 8985; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrec_'); os.makedirs(os.path.join(d, 'config')); out = os.path.join(d, 'out.txt'); ctrl = os.path.join(d, 'ctrl.txt'); open(ctrl, 'w').write('')
json.dump({'Channel': 'rect', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': OBS, 'ObsPassword': 'pw-test'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8986', 'PINGUINO_LIVE': '0', 'PINGUINO_OBS': '1'})
fails = []; host = None; mock = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B}), timeout=10))
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def send(c): open(ctrl, 'w').write(c); time.sleep(1.2)
def st(): return get('/api/offline-mode')
def waitfor(f, secs=25):
    for _ in range(secs * 2):
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.5)
    return False
def start_host():
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
try:
    host = start_host(); time.sleep(1)
    r = st(); chk('default: toggle ON, nothing recording, OBS not up', r['actLiveWhileRecording'] is True and r['recording'] is False and r['behavesLive'] is False and r['source'] == 'idle', r)
    mock = subprocess.Popen([sys.executable, os.path.join(here, 'mock-obs.py'), str(OBS), 'pw-test', ctrl], stdout=open(os.path.join(d, 'mock.log'), 'wb'), stderr=subprocess.STDOUT)
    chk('OBS connects, not recording', waitfor(lambda: get('/api/obs/tree')['connected']) and st()['recording'] is False and st()['behavesLive'] is False)
    send('start'); r = st(); chk('recording starts -> acts live', r['recording'] and r['behavesLive'] and r['source'] == 'recording' and r['live'] is not True, r)
    chk('timers follow', get('/api/timers')['live'] is True)
    host.stdin.write(b'viewer: !uptime\n'); host.stdin.flush(); time.sleep(1.5)
    chk('uptime says recording', any('recording' in s.lower() and 'twitch' in s.lower() for s in says()), says())
    send('pause'); r = st(); chk('paused still active', r['recording'] and r['behavesLive'], r)
    send('resume'); chk('resumed active', st()['behavesLive'])
    send('stop'); r = st(); chk('stop -> idle', not r['recording'] and not r['behavesLive'] and r['source'] == 'idle', r)
    send('start'); r = post('/api/offline-mode', {'actLiveWhileRecording': False}); chk('toggle off reply', r['ok'] and r['actLiveWhileRecording'] is False and r['recording'] is True and r['behavesLive'] is False, r)
    chk('persisted in file, enabled untouched', json.load(open(os.path.join(d, 'config', 'offline_mode.json'))) .get('actLiveWhileRecording') is False)
    r = post('/api/offline-mode', {'enabled': True}); chk('offline mode on, recording ignored', r['enabled'] and r['behavesLive'] and r['source'] == 'offline-mode' and r['actLiveWhileRecording'] is False, r)
    r = post('/api/offline-mode', {'enabled': False, 'actLiveWhileRecording': True}); chk('both fields in one call', r['ok'] and r['enabled'] is False and r['actLiveWhileRecording'] and r['behavesLive'] and r['source'] == 'recording', r)
    r = post('/api/offline-mode', {}); chk('empty refused', r['ok'] is False, r)
    send('drop'); chk('OBS drop -> not recording', waitfor(lambda: st()['recording'] is False and st()['behavesLive'] is False, 10), st())
    chk('OBS reconnects', waitfor(lambda: get('/api/obs/tree')['connected'], 30) and st()['recording'] is False)
    send('start'); chk('record again after reconnect', st()['behavesLive'])
    # restart: GetRecordStatus after identify picks up an already running recording
    host.kill(); time.sleep(1); host = start_host()
    chk('restart mid-recording picked up', waitfor(lambda: st()['recording'] is True, 30) and st()['behavesLive'], st())
    log = ''
    for root, _, fs in os.walk(d):
        for f in fs:
            if f.endswith('.jsonl'): log += open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
    chk('state-change logged', 'OBS recording STARTED' in log and 'OBS recording stopped' in log, log[-300:])
finally:
    if host: host.kill()
    if mock: mock.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS recording'); sys.exit(1 if fails else 0)
