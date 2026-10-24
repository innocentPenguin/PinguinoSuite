"""!vanish / !disappear: a 1 s "poof" timeout for whoever typed it (fake timeout in --sim), per-user cooldown, never for mods / the broadcaster / bots, at most one reply line, free.
Usage: python Tools/test-host-vanish.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8935; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgvan_'); outf = os.path.join(d, 'out.txt'); open(outf, 'wb').close()
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8936'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', os.environ.get('PG_SUITE', suite)], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def lines(): return open(outf, encoding='utf-8', errors='replace').read().splitlines()
def says(): return [l[6:] for l in lines() if l.startswith('[say] ')]
def dos(): return [l for l in lines() if l.startswith('[timeout-do]')]
def feed(l, w=0.7): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def pts(u):
    try: r = json.load(urllib.request.urlopen(B + '/api/economy/user?login=' + u, timeout=10)); return r.get('points', r.get('balance', 0)) or 0
    except Exception: return 0
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    time.sleep(1)
    feed('viewer1: hello'); p0 = pts('viewer1'); s0 = len(says()); n0 = len(dos())
    feed('viewer1: !vanish')
    t = dos()[n0:]
    chk('one fake timeout, 1 s, reason poof, for the typist', len(t) == 1 and 'user=viewer1' in t[0] and 'secs=1' in t[0] and 'reason=poof' in t[0], t)
    chk('done by PinguinoB0t\'s own sign-in first', len(t) == 1 and 'actor=core' in t[0], t)
    chk('no reply line', len(says()) == s0, says()[s0:])
    chk('costs nothing', pts('viewer1') == p0, (p0, pts('viewer1')))
    feed('viewer1: !vanish'); feed('viewer1: !disappear')
    chk('cooldown: 10 s per user, no second timeout and no reply', len(dos()) == n0 + 1 and len(says()) == s0, (dos()[n0:], says()[s0:]))
    feed('viewer2: !disappear')
    t = dos()[n0 + 1:]
    chk('alias works for another user (own cooldown)', len(t) == 1 and 'user=viewer2' in t[0], t)
    s1 = len(says()); n1 = len(dos())
    feed('*mod1: !vanish'); r = says()[s1:]
    chk('mod: "mods can\'t vanish", no timeout', r == ["mods can't vanish"] and len(dos()) == n1, (r, dos()[n1:]))
    s2 = len(says())
    feed('#streamer1: !vanish'); r = says()[s2:]
    chk('broadcaster: same refusal, no timeout', r == ["mods can't vanish"] and len(dos()) == n1, (r, dos()[n1:]))
    feed('pinguinob0t: !vanish'); chk('bot account: nothing', len(dos()) == n1)
    s3 = len(says()); feed('*mod1: !vanish'); chk('mod refusal also cools down (one line at most)', len(says()) == s3)
finally:
    host.terminate()
    try: host.wait(10)
    except Exception: host.kill()
    shutil.rmtree(d, ignore_errors=True)
print('FAIL: ' + '; '.join(fails) if fails else 'PASS vanish'); sys.exit(1 if fails else 0)
