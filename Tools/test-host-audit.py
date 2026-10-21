"""Audit of the viewer/mod commands in the Host (sim mode, temp data): one command = at most ONE reply line, cooldowns hold (same user and same command inside 20 s,
anyone inside 8 s), mod-only and broadcaster-only commands are silent for everybody else, and nothing a viewer types changes points.
Usage: python Tools/test-host-audit.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8988; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgaud_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'adjust': {'alice': 500, 'bob': 300}}, open(os.path.join(eco, 'points.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8989'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.7):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
def bal(u): return json.load(urllib.request.urlopen(B + '/api/economy/user?login=' + u, timeout=5))['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    # 1) one command, one reply (a fresh user every time so cooldowns do not hide anything)
    viewer = ['!points', '!watchtime', '!toppoints', '!topwatch', '!topgifters', '!topbits', '!topyappers', '!topstreaks', '!rank', '!uptime', '!downtime',
              '!commands', '!leaderboards', '!bits', '!gifted', '!sub', '!founders', '!pm']
    for i, c in enumerate(viewer):
        r = ask('viewer%d: %s' % (i, c), 0.9)
        chk('one reply for ' + c, len(r) <= 1, r)
    # 2) cooldowns: the same user + command again inside 20 s is silent; another user inside 8 s is silent; another command is fine
    ask('cd1: !uptime', 0.9)
    r = ask('cd1: !uptime'); chk('same user, same command: silent', r == [], r)
    r = ask('cd2: !uptime'); chk('another user, same command inside the global gap: silent', r == [], r)
    r = ask('cd1: !downtime', 0.9); chk('another command is answered', len(r) == 1, r)
    # 3) mod-only commands are silent for viewers (the word may belong to another bot); the broadcaster-only ones too, and they never move points
    before = (bal('alice'), bal('bob'))
    for c in ['!removepoints @alice 100', '!economy status', '!setrank alice gold', '!alias a b', '!boards', '!subs', '!streaks', '!names', '!lookup alice', '!addpoints alice 1000', '!editpoints alice 0', '!pgrant alice 5']:
        r = ask('rando: ' + c, 0.5); chk('viewer gets nothing for ' + c, r == [], r)
    chk('a viewer typing point commands changes nothing', (bal('alice'), bal('bob')) == before, (before, bal('alice'), bal('bob')))
    r = ask('modman: !addpoints alice 1000', 0.5); chk('a mod is not the broadcaster: hidden grant refused', bal('alice') == before[0], bal('alice'))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS audit'); sys.exit(1 if fails else 0)
