"""Short chat lines: the !shop list is two items and about 100 characters (no "coming soon" tail, no sub explainer), "already in the queue" is said once per 5 minutes per user,
the raid emote line is migrated from 188 to under 100 characters (one time, dated backup), and the seed no longer carries the long line.
Usage: python Tools/test-host-trims.py [dll]"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8961
d = tempfile.mkdtemp(prefix='pgtr_'); outp = os.path.join(d, 'out.txt')
OLD = 'Raid started! Prepare your emotes! innoce108Arrive innoce108W innoce108Danceydance innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Hype innoce108Hello innoce108W'
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'seeded': ['spotify', 'spotify2', 'musicoff1', 'songhelper1'], 'actions': [{'id': 'sb-raidstart', 'name': 'Raid scheduled', 'enabled': True, 'triggers': [], 'conditions': [],
           'steps': [{'type': 'say', 'as': 'core', 'text': OLD}, {'type': 'delay', 'ms': 700}, {'type': 'say', 'as': 'core', 'text': 'Another line that stays as it is'}]}]}, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8962', 'PINGUINO_DUP_SECONDS': '0'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
res = []
def chk(n, ok, x=''):
    res.append((n, ok))
    if not ok: print('  FAIL', n, x)
def says(): return [l[6:] for l in open(outp, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=1.5):
    n = len(says()); host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait); return says()[n:]
try:
    for _ in range(80):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
    a = json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8'))
    tx = [s.get('text', '') for x in a['actions'] if x.get('id') == 'sb-raidstart' for s in x['steps'] if s.get('text')]
    chk('raid line migrated to under 100 characters, other lines untouched', tx[0].startswith('Raid started! Prepare your emotes!') and len(tx[0]) < 100 and tx[1] == 'Another line that stays as it is', tx)
    chk('migration is marked done and left a dated backup', 'raidshort1' in a.get('seeded', []) and any(f.startswith('automations.json.before-raidshort-') for f in os.listdir(d)), a.get('seeded'))
    r = ask('viewer1: !shop')
    chk('!shop list: one reply, two items, under 130 characters, stake range kept', len(r) == 1 and len(r[0]) < 130 and r[0].count('!shop') == 2 and 'Coming soon' not in r[0] and re.search(r'\d+-\d+', r[0]), r)
    ask('#trial: !queue open', 3)
    ask('alice: !register AliceEpic', 2)
    r1 = ask('alice: !join', 2); r2 = ask('alice: !join', 2); r3 = ask('alice: !join', 2)
    chk('joined once with its position', len([x for x in r1 if 'joined the queue at position' in x]) == 1, r1)
    chk('already in the queue: said once, then quiet for 5 minutes', len([x for x in r2 if 'already in the queue' in x]) == 1 and not [x for x in r3 if 'already in the queue' in x], (r2, r3))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
