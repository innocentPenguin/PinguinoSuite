"""Core side of the strike check-in: it removes TEMPORARY strikes the Host queued, never permanent ones, and writes the done file the Host turns into mod-audit entries. Usage: python Tools/test-host-strikecheckin-core.py [dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8905; d = tempfile.mkdtemp(prefix='pgchk_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'WasLive': False, 'LastLiveSeen': 1}, open(os.path.join(d, 'settings.json'), 'w'))
now = int(time.time())
def pl(n, s, p): return {'Username': n, 'Platform': 'epic', 'GameId': 'x', 'TwitchId': n, 'Strikes': s, 'PermaStrikes': p, 'StrikeDecayAt': now, 'Wins': 0, 'Losses': 0, 'Points': 0}
json.dump({'tmp': pl('tmp', 2, 0), 'mix': pl('mix', 1, 1), 'perm': pl('perm', 0, 2)}, open(os.path.join(d, 'players.json'), 'w'))
os.makedirs(os.path.join(d, 'runtime'), exist_ok=True)
json.dump({'items': [{'login': 'tmp', 'n': 1, 'at': now}, {'login': 'mix', 'n': 1, 'at': now}, {'login': 'perm', 'n': 1, 'at': now}, {'login': 'nobody', 'n': 1, 'at': now}]}, open(os.path.join(d, 'runtime', 'strike_checkin_queue.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8906'; env['PINGUINO_LIVE'] = '1'
host = subprocess.Popen(['dotnet', dll, '--sim', '--data', d], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
res = []
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(16)
    p = json.load(open(os.path.join(d, 'players.json')))
    res.append(('temporary strike removed (2 -> 1)', p['tmp']['Strikes'] == 1))
    res.append(('permanent strike untouched, temporary one removed (1+1 -> 0+1)', p['mix']['Strikes'] == 0 and p['mix']['PermaStrikes'] == 1))
    res.append(('only permanent strikes: nothing changes', p['perm']['Strikes'] == 0 and p['perm']['PermaStrikes'] == 2))
    res.append(('queue file consumed', not os.path.exists(os.path.join(d, 'runtime', 'strike_checkin_queue.json'))))
    out = open(os.path.join(d, 'out.txt'), encoding='utf-8', errors='replace').read()
    res.append(('nothing said in chat', '[say]' not in out))
    time.sleep(22)
    ma = ''
    for root, _, fs in os.walk(d):
        for f in fs:
            if 'audit' in f.lower(): ma += open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
    res.append(('mod audit has the system entries', ma.count('strike check-in') >= 2))
finally:
    host.kill(); print(d)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
