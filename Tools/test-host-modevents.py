"""ban/unban/mod/unmod events carry the moderator into /api/activity.  Usage: python Tools/test-host-modevents.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8991; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgmodev_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8990'
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
fails = []
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    for ln in ('event TwitchBan troll 1 modjoe', 'event TwitchUnban troll 1 modjoe', 'event TwitchMod newmod 1 innocentpenguin_', 'event TwitchUnmod newmod 1 innocentpenguin_', 'event TwitchFollow ann', 'event TwitchFollow ann'):
        h.stdin.write((ln + '\n').encode()); h.stdin.flush(); time.sleep(0.4)
    items = json.load(urllib.request.urlopen(B + '/api/activity?since=0', timeout=5))['items']
    got = {i['kind']: i for i in items}
    for k, u, m in (('ban', 'troll', 'modjoe'), ('unban', 'troll', 'modjoe'), ('mod', 'newmod', 'innocentpenguin_'), ('unmod', 'newmod', 'innocentpenguin_')):
        i = got.get(k)
        if not i or i.get('user') != u or i.get('moderator') != m: fails.append('%s item wrong: %s' % (k, i))
    fo = [i for i in items if i['kind'] == 'follow' and i.get('user') == 'ann']
    if len(fo) != 2 or fo[0].get('refollow') is not False or fo[1].get('refollow') is not True: fails.append('refollow flags wrong: %s' % [i.get('refollow') for i in fo])
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS ban/unban/mod/unmod carry user + moderator')
sys.exit(1 if fails else 0)
