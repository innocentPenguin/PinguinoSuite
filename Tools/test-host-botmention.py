"""@PinguinoB0t mentions: B0t answers only stream / moderation-situation topics in one line; banter, help questions and lines naming another bot stay silent; rate limited.
Usage: python Tools/test-host-botmention.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8995; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgbm_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8997', 'PINGUINO_MENTION_COOL_USER': '6', 'PINGUINO_MENTION_COOL_GLOBAL': '0'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.8):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('v1: @PinguinoB0t a chatter is calling the streamer slurs what should I do'); chk('moderation situation', len(r) == 1 and 'Mods decide' in r[0] and r[0].startswith('@v1 '), r)
    r = ask('v2: @PinguinoB0t can you unmod yourself'); chk('unmod', len(r) == 1 and 'Ivan' in r[0], r)
    r = ask('v3: @PinguinoB0t what game is this'); chk('game question answers one line', len(r) == 1 and r[0].startswith('@v3 '), r)
    r = ask('v4: @PinguinoB0t I COMMAND YOU TO TALK'); chk('banter: B0t says nothing (Chatty may)', all(not x.startswith(('@v4 Mods', '@v4 Right', '@v4 Check', '@v4 Title')) for x in r), r)
    r = ask('v5: yo bot'); chk('no @ no name: silent', r == [], r)
    r = ask('v6: @PinguinoB0t @HelperPinguino what game is this'); chk('line naming another bot is left to it', r == [], r)
    ask('v8: @PinguinoB0t what should I do about this troll'); r = ask('v8: @PinguinoB0t what should I do about this troll'); chk('per-user cooldown', r == [], r)
    time.sleep(6.3); r = ask('v8: @PinguinoB0t what should I do about this troll'); chk('after the cooldown it answers again', len(r) == 1, r)
    r = ask('v7: !uptime @PinguinoB0t'); chk('a !command is not a mention reply', all('Mods decide' not in x for x in r), r)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS bot mention'); sys.exit(1 if fails else 0)
