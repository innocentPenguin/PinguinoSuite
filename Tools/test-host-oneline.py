"""One command, at most ONE chat line, for EVERY viewer command in the router table (PinguinoB0t/commands.json: who = everyone, owned by the Host or the Core bot), aliases included.
Each command is typed once by its own fresh viewer, bare (no arguments). Pass 1: all commands, then the total chat lines must not exceed the number of commands. Pass 2: each command again alone, at most one line.
Usage: python Tools/test-host-oneline.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8955; B = 'http://127.0.0.1:%d' % PORT
SKIP = {'!golive', '!first', '!firsts', '!helper', '!ask', '!pinguino', '!helperpack', '!lobbypass'}   # not Host/Core replies (Helper), or the First 5 game (needs the cutover)
d = tempfile.mkdtemp(prefix='pgone_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8956'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def send(line): h.stdin.write((line + '\n').encode()); h.stdin.flush()
j = json.load(open(os.path.join(suite, 'PinguinoB0t', 'commands.json'), encoding='utf-8-sig'))
cmds = []
for e in j['commands']:
    if not str(e.get('who', '')).startswith('everyone') or e.get('action') not in ('PinguinoHost', 'PinguinoBotCore'): continue
    for c in [e['command']] + list(e.get('aliases') or []):
        if c.startswith('!') and c not in SKIP and c not in cmds: cmds.append(c)
fails = []
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    n0 = len(says())
    for i, c in enumerate(cmds):
        send('one%d: %s' % (i, c)); time.sleep(0.35)
    prev = -1
    for _ in range(40):   # settle: wait until no new line has come for 3 s (!rank holds the console for up to 3 s)
        time.sleep(3); cur = len(says())
        if cur == prev: break
        prev = cur
    got = says()[n0:]
    print('%d viewer commands, %d chat lines' % (len(cmds), len(got)))
    for i, c in enumerate(cmds):   # always: each command again alone, with a fresh viewer, so a double reply cannot hide behind a silent command
        n = len(says()); send('again%d: %s' % (i, c)); time.sleep(4.0 if c == '!rank' else 1.2)
        r = says()[n:]
        if len(r) > 1: fails.append('%s answered %d lines: %s' % (c, len(r), r))
    if len(got) > len(cmds):
        if not fails: fails.append('%d lines for %d commands, no single command repeats it on its own (late replies?): %s' % (len(got), len(cmds), got))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS one line per command'); sys.exit(1 if fails else 0)
