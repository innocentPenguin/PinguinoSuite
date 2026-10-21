"""Welcome bonus: a first-ever chatter ("^name:" in --sim) gets 100 points AFTER the welcome, in its own line, once per login; bots, the streamer and
sim players never. Usage: python Tools/test-host-welcome.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8996; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgwel_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8997', 'PINGUINO_WELCOME_DELAY_SEC': '2'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def say(): return [l for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say]') and 'points' in l and 'gamble' in l]
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=0.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    feed('^newbie: hi everyone', 0.5)
    chk('no bonus line in the same breath as the welcome', not say(), say())
    time.sleep(3.0)
    s = say(); chk('bonus line comes later, once, with the right words', len(s) == 1 and '@newbie' in s[0] and '100 points' in s[0] and '!shop' in s[0] and 'compete' in s[0], s)
    chk('100 points landed', get('/api/economy/user?login=newbie').get('points', get('/api/economy/user?login=newbie').get('balance')) in (100, 100.0), get('/api/economy/user?login=newbie'))
    feed('^newbie: hello again', 0.3); time.sleep(3.0)
    chk('a repeat first-message flag does not pay twice', len(say()) == 1 and get('/api/economy/user?login=newbie').get('points', 100) == 100, say())
    feed('^pinguinob0t: hi', 0.3); feed('^streamer1: hi', 0.3); feed('plain: hi', 0.3); time.sleep(3.0)
    chk('bots, the streamer and non-first chatters get nothing', len(say()) == 1, say())
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS welcome'); sys.exit(1 if fails else 0)
