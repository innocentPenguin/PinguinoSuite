"""Host-supplied live state: WasLive in settings.json and the strike-off on a new stream, no website key. Usage: python Tools/test-host-live.py [dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8903; d = tempfile.mkdtemp(prefix='pglive_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'WasLive': False, 'LastLiveSeen': 1}, open(os.path.join(d, 'settings.json'), 'w'))
json.dump({'bob': {'Username': 'bob', 'Platform': 'epic', 'GameId': 'x', 'TwitchId': '1', 'Strikes': 2, 'StrikeDecayAt': int(time.time()) - 90000, 'Wins': 0, 'Losses': 0, 'Points': 0}}, open(os.path.join(d, 'players.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8904'; env['PINGUINO_LIVE'] = '1'
host = subprocess.Popen(['dotnet', dll, '--sim', '--data', d], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
res = []
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(14)
    live = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/live' % PORT, timeout=5))
    res.append(('/api/live says live (forced)', live['live'] is True))
    st = json.load(open(os.path.join(d, 'settings.json')))
    res.append(('settings.json WasLive became true without a website key', st.get('WasLive') is True))
    pl = json.load(open(os.path.join(d, 'players.json')))
    res.append(('one temporary strike expired after a full day (decay is per day, not per stream)', pl['bob']['Strikes'] == 1))
finally:
    host.kill(); print(d)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
