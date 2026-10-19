"""Streamer-account API (Suite Accounts page): sim Host, no real token. Usage: python Tools/test-host-account.py [dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8895; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgacct_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'ClientId': 'testclientid', 'UserToken': 'fake'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8898'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def call(p, body=None):
    rq = urllib.request.Request(B + p, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=20))
res = []
try:
    for _ in range(60):
        try: call('/api/status'); break
        except Exception: time.sleep(0.5)
    a = call('/api/account/streamer')
    res.append(('GET shape (no token ever returned)', 'required' in a and 'scopes' in a and 'fake' not in json.dumps(a)))
    res.append(('required list has clips:edit + channel:moderate', {'clips:edit', 'channel:moderate'} <= {r['scope'] for r in a['required']}))
    s = call('/api/account/streamer/signin', {'open': False})
    res.append(('signin returns url with every scope', s['ok'] and 'clips%3Aedit' in s['url'] and 'channel%3Amoderate' in s['url'] and not s['opened']))
    o = call('/api/account/streamer/signout', {})
    res.append(('signout ok', o['ok']))
    res.append(('token cleared on disk', json.load(open(os.path.join(d, 'host_secrets.json'))).get('UserToken') == ''))
finally:
    host.kill()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
