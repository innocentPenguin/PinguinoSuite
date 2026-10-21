"""Typo router: "! queue", !q, !list -> !queue; !jon/!joi/!jpin/!joinm/!rejoin/"! join" -> !join; !unjoin/!quit -> !leave; near misses answer once per user; known commands untouched; no !peng alias.
Usage: python Tools/test-host-cmdfix.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8996; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcf_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8998'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def clog():
    f = os.path.join(d, 'console', 'host.jsonl'); return open(f, encoding='utf-8', errors='replace').read() if os.path.exists(f) else ''
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=1.0):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    for w, want in (('! queue', '! queue -> !queue'), ('!q', '!q -> !queue'), ('!list', '!list -> !queue'), ('!queue.', 'punctuation after !queue'), ('! join', '! join -> !join'), ('!jon', '!jon -> !join'), ('!joi', '!joi -> !join'), ('!jpin', '!jpin -> !join'), ('!joinm', '!joinm -> !join'), ('!joinn', '!joinn -> !join'), ('!rejoin', '!rejoin -> !join'), ("!join'", 'punctuation after !join'), ('!unjoin', '!unjoin -> !leave'), ('!quit', '!quit -> !leave')):
        r = ask('b1: ' + w, 0.5); chk(w + ' rewritten', want in clog() and not any('did you mean' in x for x in r), (want, r))
    r = ask('c1: !queu'); chk('near miss answers', len(r) == 1 and 'did you mean !queue?' in r[0] and r[0].startswith('@c1 '), r)
    r = ask('c1: !queu'); chk('only once per user', r == [], r)
    r = ask('c2: !poinst'); chk('another user gets it too', len(r) == 1 and '!points' in r[0], r)
    r = ask('c3: !joke'); chk('known lore words are not near misses', not any('did you mean' in x for x in r), r)
    r = ask('c4: !peng'); chk('no !peng alias, no did-you-mean', not any('did you mean' in x for x in r), r)
    r = ask('c5: ! hello there'); chk('"! hello" is not rewritten or answered', r == [], r)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS cmdfix'); sys.exit(1 if fails else 0)
