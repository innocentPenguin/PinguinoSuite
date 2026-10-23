"""Sim players who leave a balanced practice lobby are never written to players.json / matches.json (SimDrop kept the row in _players but dropped it from _practice).
A mod starts the game (!next) so the sim queue becomes a balanced practice lobby, then sim players leave / are removed.  Usage: python Tools/test-host-simdrop.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    k = socket.socket(); k.bind(('127.0.0.1', 0)); n = k.getsockname()[1]; k.close(); return n
PORT = _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsimdrop_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'simt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
json.dump({'AutoNextMatch': True}, open(os.path.join(d, 'settings.json'), 'w'))
env.update({'PINGUINO_COMPAT_WS_PORT': str(_free()), 'PINGUINO_LIVE': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=15))
def post(p, o=None): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o or {}).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=30))
def saved():
    r = {}
    for f in ('players.json', 'matches.json'):
        for root in (d, os.path.join(d, 'runtime')):
            p = os.path.join(root, f)
            if os.path.exists(p): r[f] = open(p, encoding='utf-8-sig', errors='replace').read()
    return r
def said(): return open(out, encoding='utf-8', errors='replace').read()
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    for c in ('#ivan: !queue open', 'viewer1: !register vone', 'viewer2: !register vtwo', 'viewer1: !join', 'viewer2: !join'):
        h.stdin.write((c + chr(10)).encode()); h.stdin.flush(); time.sleep(1)
    r = post('/api/sim/start', {'count': 10, 'mode': 'both'}); chk('start', r['ok'], r)
    time.sleep(5); h.stdin.write(('#ivan: !next' + chr(10)).encode()); h.stdin.flush()
    for _ in range(40):
        if '[avg ' in said(): break
        time.sleep(0.5)
    chk('a balanced sim lobby formed (!next)', '[avg ' in said(), [l for l in said().splitlines() if '[say]' in l][-6:])
    import re
    lobby_sims = re.findall(r'sim_([a-z0-9_]+)\(', ' '.join(l for l in said().splitlines() if '[avg ' in l))   # the sim players inside the balanced lobby
    chk('sims are in the lobby', len(lobby_sims) >= 2, lobby_sims)
    names = [p['name'] for p in get('/api/sim/status')['players']]
    waiting = [n for n in names if n.lower() not in lobby_sims]   # sims still waiting in the queue while the lobby plays
    chk('some sims are not in the lobby', len(waiting) >= 2, (names, lobby_sims))
    r = post('/api/sim/leave', {'names': waiting}); chk('leave', r['ok'], r)
    r = post('/api/sim/add', {'n': 2}); chk('add', r['ok'], r)
    r = post('/api/sim/remove', {'n': 3}); chk('remove', r['ok'], r)
    for _ in range(40): post('/api/sim/tick')
    time.sleep(4)
    s = saved()
    chk('players.json has no sim_ rows', 'sim_' not in s.get('players.json', ''), s.get('players.json', '')[:300])
    chk('matches.json has no sim_ rows', 'sim_' not in s.get('matches.json', ''), s.get('matches.json', '')[:300])
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS simdrop'); sys.exit(1 if fails else 0)
