"""OBS replay buffer auto-start (Tools/mock-obs.py): already active -> no Start call; inactive -> exactly one StartReplayBuffer on connect / stream start / recording start; never ToggleReplayBuffer;
setting off -> nothing; replay buffer disabled in OBS -> replayBufferEnabled=false, no Start spam.  Usage: python Tools/test-host-replaybuffer.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, OBS = 8996, 8997; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrb_'); os.makedirs(os.path.join(d, 'config')); out = os.path.join(d, 'out.txt'); ctrl = os.path.join(d, 'ctrl.txt'); mlog = os.path.join(d, 'mock.log')
open(ctrl, 'w').write('')
json.dump({'Channel': 'rbt', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': OBS, 'ObsPassword': 'pw-test'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8998', 'PINGUINO_LIVE': '0', 'PINGUINO_OBS': '1'})
fails = []; host = None; mock = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B}), timeout=10))
def send(c): open(ctrl, 'w').write(c); time.sleep(1.0)
def reqs(): return [l.split()[1] for l in open(mlog, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('REQ ')]
def n(t): return reqs().count(t)
def st(): return get('/api/obs/status')
def waitfor(f, secs=25):
    for _ in range(secs * 2):
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.5)
    return False
try:
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    mock = subprocess.Popen([sys.executable, os.path.join(here, 'mock-obs.py'), str(OBS), 'pw-test', ctrl], stdout=open(mlog, 'wb'), stderr=subprocess.STDOUT, env=dict(os.environ, RB_ACTIVE='1'))
    chk('connects', waitfor(lambda: st()['connected']), st())
    chk('already active: status read', waitfor(lambda: n('GetReplayBufferStatus') >= 1 and st()['replayBuffer']['active']), reqs())
    chk('already active: no Start', n('StartReplayBuffer') == 0, reqs())
    r = st(); chk('status shape', r['autoStartReplayBuffer'] is True and r['replayBufferEnabled'] is True and set(r['replayBuffer']) >= {'active', 'lastAutoStart', 'lastError'} and r['replayBuffer']['lastAutoStart'] == 0, r)
    # stream started, buffer off -> exactly one Start
    send('rboff'); send('streamstart'); time.sleep(1.5)
    chk('stream start -> one Start', n('StartReplayBuffer') == 1, reqs()); r = st(); chk('active + lastAutoStart', r['replayBuffer']['active'] and r['replayBuffer']['lastAutoStart'] > 0 and r['replayBuffer']['lastError'] == '', r)
    send('streamstart'); time.sleep(1.5); chk('already active again: still one Start', n('StartReplayBuffer') == 1, reqs())
    # recording started
    send('rboff'); send('start'); time.sleep(1.5); chk('recording start -> second Start', n('StartReplayBuffer') == 2, reqs())
    # setting off
    r = post('/api/tune', {'area': 'obs', 'values': {'autoStartReplayBuffer': False}}); chk('tune off', r['ok'] and r['applied']['autoStartReplayBuffer'] is False, r)
    chk('tune lists obs area', any(a['id'] == 'obs' for a in get('/api/tune')['areas']) and st()['autoStartReplayBuffer'] is False)
    send('rboff'); send('streamstart'); time.sleep(1.5); chk('setting off: no Start', n('StartReplayBuffer') == 2, reqs())
    post('/api/tune', {'area': 'obs', 'values': {'autoStartReplayBuffer': True}})
    # replay buffer not enabled in OBS
    send('rboff'); send('rbdisable'); send('streamstart'); chk('disabled: flagged', waitfor(lambda: st()['replayBufferEnabled'] is False and st()['replayBuffer']['lastError'] != '', 30), st())
    r = st(); chk('disabled: error surfaced', r['replayBuffer']['lastError'] != '' and r['replayBuffer']['active'] is False, r)
    chk('disabled: no Start spam', n('StartReplayBuffer') == 2, reqs())
    send('rbenable'); send('streamstart'); chk('re-enabled in OBS: started', waitfor(lambda: n('StartReplayBuffer') == 3, 20) and waitfor(lambda: st()['replayBufferEnabled'] and st()['replayBuffer']['active'], 10), st())
    # disconnect/reconnect -> start again when inactive
    send('rboff'); send('drop'); chk('reconnect -> Start', waitfor(lambda: n('StartReplayBuffer') == 4, 40), reqs())
    chk('never toggled', n('ToggleReplayBuffer') == 0, reqs())
    log = ''
    for root, _, fs in os.walk(d):
        for f in fs:
            if f.endswith('.jsonl'): log += open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
    chk('auto-start logged', 'replay buffer auto-started' in log, log[-300:])
    chk('disabled warned once', log.count('replay buffer not started') == 1, log.count('replay buffer not started'))
finally:
    if host: host.kill()
    if mock: mock.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS replaybuffer'); sys.exit(1 if fails else 0)
