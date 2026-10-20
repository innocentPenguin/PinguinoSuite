"""Host lore stays silent on terms ChattyPinguino's canned file owns (no double reply); lore-only terms still answer; aliases covered; enabled:false not owned; file edits picked up.
Usage: python Tools/test-host-loreowned.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pglo_'); outf = os.path.join(d, 'out.txt'); canned = os.path.join(d, 'canned.json')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'CannedFile': canned}, open(os.path.join(d, 'chat_settings.json'), 'w'))
def entry(i, t, al, txt): return {'id': i, 'triggers': [t], 'aliases': al, 'response': txt, 'enabled': True}
json.dump({'entries': [entry('own1', '!ownedone', ['!ownedalias'], 'LORE-OWNED'), entry('free1', '!freeone', [], 'LORE-FREE'), entry('off1', '!offone', [], 'LORE-OFF')], 'settings': {'globalCooldownSec': 0, 'userCooldownSec': 0, 'entryCooldownSec': 0}}, open(os.path.join(d, 'channel_lore.json'), 'w'))
def wc(cmds): json.dump({'cooldownSec': 0, 'commands': cmds}, open(canned, 'w'))
wc([{'name': 'ownedone', 'aliases': ['ownedalias'], 'text': 'CHATTY-A', 'enabled': True}, {'name': 'offone', 'text': 'x', 'enabled': False}])
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8995'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(0.8); return says()[n:]
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('v1: !ownedone'); chk('owned term answered once, by Chatty only', r == ['CHATTY-A'], r)
    r = ask('v1: !ownedalias'); chk('owned alias: Host never answers (Chatty dup guard may swallow the repeat)', 'LORE-OWNED' not in r and len(r) <= 1, r)
    r = ask('v1: !freeone'); chk('lore-only term answered', r == ['LORE-FREE'], r)
    r = ask('v1: !offone'); chk('disabled canned entry is not owned', r == ['LORE-OFF'], r)
    time.sleep(1.1); wc([{'name': 'freeone', 'text': 'CHATTY-B', 'enabled': True}])
    r = ask('v2: !freeone'); chk('file edit picked up (now owned, once)', r == ['CHATTY-B'], r)
    r = ask('v2: !ownedone'); chk('no longer owned after edit', r == ['LORE-OWNED'], r)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS lore owned')
sys.exit(1 if fails else 0)
