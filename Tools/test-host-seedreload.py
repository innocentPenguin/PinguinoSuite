"""Seeds written while the Host runs: pushups.json and runtime/redeem_counts.json that are NEWER than the Host's own last read/write are read again (the next Save never overwrites a fresh seed),
and POST /api/seeds/reload reads both now (no restart). Usage: python Tools/test-host-seedreload.py [dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8997; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgseed_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'runtime'), exist_ok=True)
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8998'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n)
    if not ok: fails.append('%s %s' % (n, x))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    chk('pushups start empty', api('/api/pushup')['allTime'] == 0)
    api('/api/pushup', {'action': 'add', 'value': 3})
    chk('a mod add counts', api('/api/pushup')['allTime'] == 3)
    time.sleep(1.1)
    # a seed written while the Host runs: seen without a reload, and the next Save keeps it
    json.dump({'enabled': True, 'count': 0, 'baseline': 825, 'baselineNote': 'test', 'baselineApplied': False}, open(os.path.join(d, 'pushups.json'), 'w'))
    s = api('/api/pushup'); chk('a pushups.json newer than the Host\'s own write is read again (allTime 825 + 0)', s['allTime'] == 825 and s.get('baselineApplied') is True, s)
    s = api('/api/pushup', {'action': 'add', 'value': 2}); chk('the next write builds on the seed, not on the old memory', s['allTime'] == 827, s)
    # redeem counts
    time.sleep(1.1)
    json.dump({'groups': {'pushups': {'title': 'Pushups', 'baseline': 165, 'baselineThrough': '2026-10-31T02:53:00Z', 'perMonth': {'2026-10': 165}, 'live': 0, 'livePerMonth': {}, 'days': {}, 'liveDays': {}}}, 'seen': []}, open(os.path.join(d, 'runtime', 'redeem_counts.json'), 'w'))
    json.dump({'pushups': {'title': 'Pushups', 'ids': [], 'aliases': ['pushups']}}, open(os.path.join(d, 'runtime', 'redeem_groups.json'), 'w'))
    r = api('/api/seeds/reload', {}); chk('POST /api/seeds/reload answers ok with both states', r.get('ok') is True and r['pushup']['allTime'] == 827 and 'redeems' in r, str(r)[:300])
    rd = api('/api/redeems'); txt = json.dumps(rd); chk('/api/redeems holds the reloaded pushups group (165)', '165' in txt, txt[:300])
    time.sleep(1.1)
    json.dump({'enabled': True, 'count': 0, 'baseline': 900, 'baselineNote': 'again', 'baselineApplied': False}, open(os.path.join(d, 'pushups.json'), 'w'))
    r = api('/api/seeds/reload', {}); chk('reload reads a newer pushups.json (900)', r['pushup']['allTime'] == 900, r['pushup'])
finally:
    try: host.stdin.write(b'quit\n'); host.stdin.flush(); host.wait(timeout=10)
    except Exception: host.kill()
if fails: print('\n'.join(fails)); sys.exit(1)
print('ALL PASS')
