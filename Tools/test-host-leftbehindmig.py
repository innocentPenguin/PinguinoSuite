"""One-time migration 'leftbehind1': an automations.json seeded before !leftbehind existed gets sb-leftbehind (enabled, command !leftbehind), once (no duplicate on the next start,
deleting it afterwards sticks), a dated backup is made, and the old sb-session-cmd / sb-goal-cmd / sb-recap seeds are NOT re-added.
Usage: python Tools/test-host-leftbehindmig.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 9191; B = 'http://127.0.0.1:%d' % PORT
SEEDED = ['spotify', 'spotify-redeem', 'sbreplace1', 'sbreplace2', 'alertsound1', 'raidstart1', 'raidout2', 'spotify2', 'speak', 'popupasync1', 'raidflow2', 'popuphold1', 'musicoff1', 'songhelper1', 'rules1', 'rules2', 'raidshout1', 'raidshort1', 'raidorder1']
d = tempfile.mkdtemp(prefix='pglb_'); res = []
def chk(n, ok, x=''):
    res.append((n, ok)); print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=8))
def start():
    json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '9192', 'PINGUINO_DUP_SECONDS': '0'})
    p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3); return p
def stop(p): p.kill(); time.sleep(0.8)
def doc(): return json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8-sig'))
def ids(): return [a['id'] for a in doc()['actions']]
try:
    json.dump({'seeded': SEEDED, 'actions': [{'id': 'sb-latest-cmd', 'name': 'Command: !latest', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!latest']}], 'conditions': [], 'steps': []}]}, open(os.path.join(d, 'automations.json'), 'w'))
    p = start(); a = doc(); stop(p)
    lb = [x for x in a['actions'] if x['id'] == 'sb-leftbehind']
    chk('added once, enabled, command !leftbehind', len(lb) == 1 and lb[0]['enabled'] and lb[0]['triggers'][0]['names'] == ['!leftbehind'], lb)
    chk('has the raid_target + if-notempty steps', lb and [s['type'] for s in lb[0]['steps']] == ['raid_target', 'if'], lb)
    chk('old session/goal/recap seeds not re-added', not any(i in ids() for i in ('sb-session-cmd', 'sb-goal-cmd', 'sb-recap')), ids())
    chk('marker + dated backup', 'leftbehind1' in a['seeded'] and any(f.startswith('automations.json.before-leftbehind-') for f in os.listdir(d)))
    p = start(); n = ids().count('sb-leftbehind'); stop(p); chk('second start: no duplicate', n == 1, n)
    a = doc(); a['actions'] = [x for x in a['actions'] if x['id'] != 'sb-leftbehind']; json.dump(a, open(os.path.join(d, 'automations.json'), 'w'))
    p = start(); n = ids().count('sb-leftbehind'); stop(p); chk('deleting it afterwards sticks', n == 0, n)
finally:
    shutil.rmtree(d, True)
bad = [n for n, ok in res if not ok]; print('FAILS: %d' % len(bad)); sys.exit(1 if bad else 0)
