"""Customs: !pm private match name (mods set, everyone reads, cleared when the activity ends, in /api/customs/state AND live_state.json as pmName), team labels Grey/Orange (ids stay blue/orange;
teams + teamNames in the state; a saved default Blue becomes Grey once, a custom name stays), and innocentpenguin_ is never put on the blue/Grey side by balance / reroll (manual !in still can).
Usage: python Tools/test-host-pmteams.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
class H:
    def __init__(self, port, settings=None):
        self.port = port; self.B = 'http://127.0.0.1:%d' % port; self.d = tempfile.mkdtemp(prefix='pgpm_'); self.outp = os.path.join(self.d, 'out.txt')
        json.dump({'Channel': 'trial', 'OverlayPort': port}, open(os.path.join(self.d, 'host_secrets.json'), 'w'))
        if settings: json.dump(settings, open(os.path.join(self.d, 'settings.json'), 'w'))
        env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(port + 1), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
        self.p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', self.d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(self.outp, 'wb'), stderr=subprocess.STDOUT)
        for _ in range(80):
            try: self.api('/api/status'); break
            except Exception: time.sleep(0.5)
        time.sleep(4)
    def api(self, path, body=None):
        rq = urllib.request.Request(self.B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(rq, timeout=20))
    def feed(self, l, w=1.3): self.p.stdin.write((l + '\n').encode()); self.p.stdin.flush(); time.sleep(w)
    def out(self): return open(self.outp, 'rb').read().decode('utf-8', 'replace')
    def stop(self): self.p.kill(); time.sleep(0.5); shutil.rmtree(self.d, True)
def mod(h, a, v=''): return h.api('/api/customs/mod', {'action': a, 'value': v})
h = H(8991)
try:
    st = h.api('/api/customs/state')
    chk('default labels: blue side is Grey, orange stays Orange', st['teams']['blue']['name'] == 'Grey' and st['teams']['orange']['name'] == 'Orange' and st['teamNames'] == {'blue': 'Grey', 'orange': 'Orange'}, (st['teams'], st.get('teamNames')))
    chk('pmName is "" when unset (state)', st.get('pmName') == '', st.get('pmName'))
    o0 = len(h.out()); h.feed('viewer1: !pm'); o = h.out()[o0:]
    chk('nobody set it: "No private match name set yet."', 'viewer1 No private match name set yet.' in o, o[-300:])
    o0 = len(h.out()); h.feed('viewer1: !pm peng999'); o = h.out()[o0:]
    chk('a viewer cannot set it', h.api('/api/customs/state')['pmName'] == '', o[-300:])
    o0 = len(h.out()); h.feed('#trial: !pm peng472', 3); o = h.out()[o0:]
    chk('a mod sets it', h.api('/api/customs/state')['pmName'] == 'peng472' and 'Private match: peng472' in o, o[-300:])
    o0 = len(h.out()); h.feed('viewer1: !pm'); o = h.out()[o0:]
    chk('anyone reads it with one line', 'viewer1 Private match: peng472' in o, o[-300:])
    h.feed('viewer1: !pm hacked'); chk('a viewer typing a name only reads', h.api('/api/customs/state')['pmName'] == 'peng472')
    h.feed('#trial: !pm PengABC extra words'); chk('one token, kept as typed', h.api('/api/customs/state')['pmName'] == 'PengABC', h.api('/api/customs/state')['pmName'])
    h.feed('#trial: !pm ' + 'x' * 25); chk('over 20 characters refused', h.api('/api/customs/state')['pmName'] == 'PengABC')
    h.feed('#trial: !pm peng472')
    live = None
    for f in (os.path.join(h.d, 'live_state.json'), os.path.join(h.d, 'runtime', 'live_state.json')):
        if os.path.exists(f): live = json.load(open(f, encoding='utf-8-sig')); break
    chk('live_state.json (/api/customs for overlays and the site) carries pmName and teamNames', live and live.get('pmName') == 'peng472' and live.get('teamNames') == {'blue': 'Grey', 'orange': 'Orange'}, live and (live.get('pmName'), live.get('teamNames')))
    mod(h, 'activity', 'rl competitive')
    names = ['innocentpenguin_', 'p2', 'p3', 'p4', 'p5', 'p6']
    for n in names: h.feed('%s: !register %sEpic' % (n, n), 0.5); h.feed('%s: !join' % n, 0.5)
    seen = 0
    for i in range(7):
        r = mod(h, 'balance' if i == 0 else 'reroll'); time.sleep(0.8)
        m = h.api('/api/customs/state').get('match') or {}
        if m.get('blue') or m.get('orange'):
            seen += 1
            chk('round %d: innocentpenguin_ is on orange, never blue' % i, 'innocentpenguin_' in m['orange'] and 'innocentpenguin_' not in m['blue'], (m['blue'], m['orange']))
    chk('the balancer produced teams in the rounds', seen >= 5, seen)
    m0 = h.api('/api/customs/state').get('match') or {}
    if m0.get('blue'): h.feed('#trial: !out ' + m0['blue'][0], 1.5)   # blue is full: free a slot first
    h.feed('#trial: !in innocentpenguin_ blue', 1.5); m = h.api('/api/customs/state').get('match') or {}
    chk('a manual move to blue is still allowed', 'innocentpenguin_' in (m.get('blue') or []), (m.get('blue'), m.get('orange')))
    mod(h, 'activity', 'rl end')
    chk('ending the activity clears pmName', h.api('/api/customs/state')['pmName'] == '', h.api('/api/customs/state')['pmName'])
    h.feed('#trial: !pm', 1.2); chk('a mod with no name just reads (nothing set)', 'No private match name set yet.' in h.out()[-600:])
    h.feed('#trial: !teamname blue Ice', 1.2); h.feed('#trial: !teamname blue reset', 1.2)
    st = h.api('/api/customs/state'); chk('!teamname blue reset restores Grey', st['teams']['blue']['name'] == 'Grey' and st['teamNames']['blue'] == 'Grey', st['teams'])
finally:
    h.stop()
h = H(8993, {'BlueName': 'Blue', 'BlueHex': '#1e8fff'})
try:
    mod(h, 'activity', 'rl competitive'); mod(h, 'activity', 'rl end'); time.sleep(1)   # make the bots publish their state
    st = h.api('/api/customs/state'); chk('a saved default Blue / #1e8fff becomes Grey once', st['teams']['blue']['name'] == 'Grey' and st['teams']['blue']['color'] == '#9aa0a6', st['teams'])
finally:
    h.stop()
h = H(8995, {'BlueName': 'Ice', 'BlueHex': '#00ffff'})
try:
    mod(h, 'activity', 'rl competitive'); mod(h, 'activity', 'rl end'); time.sleep(1)
    st = h.api('/api/customs/state'); chk('a custom team name and colour are left alone', st['teams']['blue']['name'] == 'Ice' and st['teams']['blue']['color'] == '#00ffff', st['teams'])
finally:
    h.stop()
print('FAIL ' + '; '.join(fails) if fails else 'PASS pmteams'); sys.exit(1 if fails else 0)
