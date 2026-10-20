"""Subscriber roster import: master list, dedupe, highest tier, lapsed, hash no-ops, profiles. Usage: python Tools/test-host-subs.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8921; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsubs_'); dl = tempfile.mkdtemp(prefix='pgdl_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
for u in ('shadowrlttv', 'carl', 'dana', 'nobody_here'):
    json.dump({'login': u, 'roles': {'mod': False, 'vip': False, 'sub': False, 'subMonths': 0}, 'notes': 'keep'}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
H = 'Username,Subscribe Date,Current Tier,Tenure,Streak,Sub Type,Founder\n'
A = H + 'shadowrlttv,2026-09-17T01:28:47Z,Tier 2,6,6,recurring,false\nshadowrlttv,2026-06-21T03:24:37Z,Tier 1,6,6,recurring,false\ncarl,2026-10-11T22:36:11Z,Tier 1,1,1,gift,false\ndana,2026-01-02T00:00:00Z,Tier 3,9,4,recurring,true\n'
B_ = H + 'carl,2026-10-20T00:00:00Z,Tier 1,2,2,recurring,false\nshadowrlttv,2026-10-17T01:28:47Z,Tier 1,7,7,recurring,false\n'
def put(name, text, mtime):
    p = os.path.join(dl, name); open(p, 'w', newline='').write(text); os.utime(p, (mtime, mtime)); return p
now = time.time()
put('subscriber-list.csv', A, now - 7200)
for i in range(1, 4): put('subscriber-list (%d).csv' % i, A, now - 7200)      # identical copies
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8923'; env['PINGUINO_SUBS_DOWNLOADS'] = dl
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p):
    rq = urllib.request.Request(B + p, data=b'{}', headers={'Content-Type': 'application/json', 'Origin': B}); return json.load(urllib.request.urlopen(rq, timeout=15))
def prof(u): return json.load(open(os.path.join(d, 'profiles', u + '.json')))
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    r = post('/api/subs/import'); a = get('/api/subs')
    chk('4 identical copies import once', len(r['imported']) == 1 and a['files'] == 1)
    u = a['users']
    chk('one row per user, 3 users', a['total'] == 3 and set(u) == {'shadowrlttv', 'carl', 'dana'})
    chk('highest tier kept when a user has two rows', u['shadowrlttv']['tier'] == 2 and u['shadowrlttv']['subscribed'].startswith('2026-06-21'))
    chk('founder kept, tier 3', u['dana']['founder'] is True and u['dana']['tier'] == 3 and u['dana']['streak'] == 4)
    p = prof('shadowrlttv')
    chk('profile roles written, other fields kept', p['roles']['subTier'] == 2 and p['roles']['subMonths'] == 6 and p['roles']['sub'] is True and p['notes'] == 'keep')
    chk('profile of a non-subscriber untouched', 'subTier' not in prof('nobody_here')['roles'])
    r = post('/api/subs/import'); chk('re-import is a no-op', r['imported'] == [] and get('/api/subs')['files'] == 1)
    # a newer export: dana is gone (lapsed, kept), carl has more months, shadowrlttv dropped to tier 1 (highest tier kept)
    put('subscriber-list (9).csv', B_, now)
    r = post('/api/subs/import'); a = get('/api/subs'); u = a['users']
    chk('newer export merged', len(r['imported']) == 1 and a['files'] == 2)
    chk('absent user is flagged lapsed, not deleted', u['dana']['lapsed'] is True and a['total'] == 3 and prof('dana')['roles']['lapsed'] is True and prof('dana')['roles']['sub'] is False)
    chk('max tenure/streak, tier never lowered, sub type from the newest row', u['carl']['tenure'] == 2 and u['carl']['subType'] == 'recurring' and u['shadowrlttv']['tier'] == 2 and u['shadowrlttv']['tenure'] == 7)
    # an OLDER export imported late must not lapse anyone or lower anything
    put('subscriber-list (old).csv', H + 'newbie,2026-05-01T00:00:00Z,Tier 1,3,3,prime,false\n', now - 99999)
    r = post('/api/subs/import'); a = get('/api/subs')
    chk('older export adds people but lapses nobody', a['total'] == 4 and a['users']['carl'].get('lapsed') is False and a['users']['shadowrlttv'].get('lapsed') is False)
    chk('files are copied next to the master', len(os.listdir(os.path.join(d, 'subs', 'files'))) == 3)
finally:
    host.kill(); shutil.rmtree(dl, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
