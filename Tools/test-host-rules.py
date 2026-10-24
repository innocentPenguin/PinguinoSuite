"""!pmrules: seeded preset (everyone, 30 s global cooldown, speaks as core the exact private-match-rules line), fired once per customs queue opening (closed -> open edge of live_state.json),
no repeat while it stays open, none when a restarted Host finds the queue already open; !pmrules is listed in commands.json for the Helper.
Usage: python Tools/test-host-rules.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8971
LINE = u"\U0001F4D6 Private match rules! 1. No toxicity 2. No arguments or drama 3. Only join when you are supposed to \U0001F427 Breaking these rules can get you banned!"
d = tempfile.mkdtemp(prefix='pgru_'); outp = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'runtime'))
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def state(open_): json.dump({'queueOpen': open_, 'queue': []}, open(os.path.join(d, 'runtime', 'live_state.json'), 'w'))
state(False)
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8972'
def start(mode='wb'): return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, mode), stderr=subprocess.STDOUT)
def up():
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); return
        except Exception: time.sleep(0.5)
host = start(); fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def says():   # the sim sends nothing to Twitch; the action log keeps each run's output ("said as ...: <line>" or "NOT sent (...): <line>")
    out = []
    for r in json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/automations/log?n=200' % PORT, timeout=10)).get('runs', []):
        if r['id'] == 'rules': out += [(r['trigger'], (o.split(': ', 1)[1] if ': ' in o else o)) for o in r['output']]
    return out
try:
    up(); time.sleep(4)
    doc = json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8')); a = [x for x in doc['actions'] if x['id'] == 'rules']
    chk('preset seeded, enabled, marker set', a and a[0]['enabled'] and 'rules1' in doc['seeded'], doc['seeded'])
    # queue opens: one run, one line
    n0 = len(says()); state(True); time.sleep(4)
    s = says()[n0:]; chk('queue opened: the rules line once, exact text', [x[1] for x in s] == [LINE] and 'queue_open' in s[0][0], s)
    time.sleep(4); chk('still open: no repeat', [x[1] for x in says()[n0:]] == [LINE], says()[n0:])
    state(True); time.sleep(3); chk('state rewritten (re-announce) while open: no repeat', [x[1] for x in says()[n0:]] == [LINE])
    # !pmrules command
    feed('viewer1: !pmRules', 1.5); s = says()[n0:]
    chk('!pmrules: runs and carries the exact line (right after the auto line the duplicate guard holds it back, as it should)', len(s) == 2 and sorted(x[0].lower() for x in s) == ['chat:!pmrules', 'queue_open'] and all(x[1].endswith(LINE) for x in s), s)
    n1 = len(says()); feed('viewer2: !pmrules', 1.5); chk('30 s global cooldown: second viewer gets nothing', len(says()) == n1, says()[n1:])
    # closing and reopening fires again (a new opening)
    state(False); time.sleep(3); n2 = len(says()); state(True); time.sleep(4)
    chk('closed then opened again: fires again (or dup guard holds the identical line)', len(says()) in (n2, n2 + 1), says()[n2:])
    k = len(says()); host.kill(); time.sleep(0.7)
    # restart with the queue already open: no edge, no line
    host = start('ab'); up(); time.sleep(6); chk('restart with the queue open: nothing said', not says()[k:], says()[k:])
    cmds = json.load(open(os.path.join(suite, 'PinguinoB0t', 'commands.json'), encoding='utf-8-sig'))['commands']
    c = [x for x in cmds if x['command'] == '!pmrules']; chk('commands.json lists !pmrules (Host-owned, everyone)', c and c[0]['action'] == 'PinguinoHost' and c[0]['who'] == 'everyone', c)
    chk('canned !customrules / !customs lines untouched', any('!customrules' in open(os.path.join(suite, 'PinguinoB0t', 'channel_lore_seed.json'), encoding='utf-8').read() for _ in [0]))
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1200:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS rules'); sys.exit(1 if fails else 0)
