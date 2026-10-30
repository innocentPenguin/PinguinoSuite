"""Per stream-day redeem history: the seeder reads 14's "days"/"recordStart"/"estimatedDays" (dry run flags a baseline != sum of days, per-month = sum of days), the Host merges seeded + live days and answers
today / week / month / all via /api/redeems and in chat (!hydrate [today|week|month|all|YYYY-MM-DD]), a period before recordStart answers "No record before Feb 2026.", the estimate never enters a total,
the answers survive a restart. Usage: python Tools/test-host-redeemdays.py [dll]"""
import datetime as dt, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WS = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrdays_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def seeder(*a): return subprocess.run([sys.executable, os.path.join(here, 'seed-redeems.py'), '--data', d] + list(a), capture_output=True, text=True)
def start(): return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + path), timeout=20))
def waitup():
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
def feed(l, w=0.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def out(): return open(outp, 'rb').read().decode('utf-8', 'replace')
def ask(user, text):
    o0 = len(out()); feed('%s: %s' % (user, text), 0.8)
    return [l[6:] for l in out()[o0:].splitlines() if l.startswith('[say] ')]
def G(): return api('/api/redeems')['groups']

now = dt.datetime.now(dt.timezone.utc); cut = (now - dt.timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M:%SZ'); nowz = now.strftime('%Y-%m-%dT%H:%M:%SZ')
old = (now - dt.timedelta(days=8)).strftime('%Y-%m-%d')
hyd = {'2026-02-14': 3, '2026-03-02': 4, '2026-09-15': 2, old: 1}
seed = {'generatedAt': nowz, 'cutoff': cut, 'baselineThrough': cut, 'recordStart': '2026-02-04', 'estimatedDays': {'pushups': {'2026-02-04..2026-02-14': 10}}, 'groups': [
    {'id': 'hydrate', 'title': 'Hydrate', 'baseline': 10, 'days': hyd, 'perMonth': {'2026-02': 3}, 'recordStart': '2026-02-14'},
    {'id': 'pushups', 'title': 'Pushups', 'baseline': 6, 'days': {'2026-04-01': 6}, 'perMonth': {'2026-04': 6}, 'recordStart': '2026-02-14'},
    {'id': 'tts', 'title': 'Text-to-Speech', 'baseline': 5, 'days': {'2026-07-04': 5}, 'recordStart': '2026-02-14'}]}
sp = os.path.join(d, 'seed.json'); json.dump(seed, open(sp, 'w'))
r = seeder('--seed-json', sp); chk('dry run lists days', r.returncode == 0 and 'DRY RUN' in r.stdout and 'MISMATCH' not in r.stdout and not os.path.exists(os.path.join(d, 'runtime', 'redeem_counts.json')), r.stdout[-300:] + r.stderr[-300:])
bad = dict(seed); bad['groups'] = [dict(seed['groups'][0], baseline=11)]; bp = os.path.join(d, 'bad.json'); json.dump(bad, open(bp, 'w'))
# baseline comes from the sum of the days (build() takes perMonth derived from days), so a lying "baseline" field cannot slip into the counts
r = seeder('--seed-json', bp, '--write'); c = json.load(open(os.path.join(d, 'runtime', 'redeem_counts.json'))) if r.returncode == 0 else {}
chk('baseline is the sum of the days', c.get('groups', {}).get('hydrate', {}).get('baseline') == 10, r.stdout[-200:] + r.stderr[-200:])
r = seeder('--seed-json', sp, '--write'); c = json.load(open(os.path.join(d, 'runtime', 'redeem_counts.json')))
h = c['groups']['hydrate']; chk('days, recordStart stored; estimate stored apart', h['days'] == hyd and h['recordStart'] == '2026-02-14' and h['baseline'] == 10 and c['groups']['pushups']['estimatedDays'] == {'2026-02-04..2026-02-14': 10} and c['groups']['text_to_speech']['baseline'] == 5, h)
host = start()
try:
    waitup()
    g = G()['hydrate']; pm = {}
    for k, n in hyd.items(): pm[k[:7]] = pm.get(k[:7], 0) + n
    chk('seeded API: all=10, today/week 0, perMonth = sum of days', g['all'] == 10 and g['total'] == 10 and g['today'] == 0 and g['week'] == 0 and {k: v for k, v in g['perMonth'].items() if k in pm and k != old[:7]} == {k: v for k, v in pm.items() if k != old[:7]} and g['days'] == hyd and g['recordStart'] == '2026-02-14', g)
    chk('estimate not in totals or days', G()['pushups']['total'] == 6 and G()['pushups']['estimatedDays'] == {'2026-02-04..2026-02-14': 10} and sum(G()['pushups']['days'].values()) == 6, G()['pushups'])
    feed('redeem ann a1 7d9b5951-aaaa %s Hydrate' % nowz); feed('redeem bob a2 4627369b-bbbb %s Hydrate!' % nowz); feed('redeem bob a2 4627369b-bbbb %s Hydrate!' % nowz)
    g = G()['hydrate']; today = [k for k in g['days'] if k not in hyd]
    chk('two live redemptions land on today', g['live'] == 2 and g['all'] == 12 and g['today'] == 2 and g['week'] >= 2 and g['month'] >= 2 and len(today) == 1 and g['days'][today[0]] == 2, g)
    chk('perMonth adds the live month', sum(g['perMonth'].values()) == 12, g['perMonth'])
    r = ask('viewer1', '!hydrate'); chk('!hydrate default', r == ['@viewer1 Penguin has hydrated 2 times today, 12 all-time'], r)
    r = ask('viewer2', '!hydrate all'); chk('!hydrate all', r == ['@viewer2 Penguin has hydrated 12 times all-time'], r)
    r = ask('viewer3', '!hydrate today'); chk('!hydrate today', r == ['@viewer3 Penguin has hydrated 2 times today'], r)
    r = ask('viewer4', '!hydrate week'); chk('!hydrate week', r == ['@viewer4 Penguin has hydrated %d times this week' % g['week']], r)
    r = ask('viewer5', '!hydrate month'); chk('!hydrate month', r == ['@viewer5 Penguin has hydrated %d times this month' % g['month']], r)
    r = ask('viewer6', '!hydrate 2026-02-14'); chk('a seeded day', r == ['@viewer6 Penguin has hydrated 3 times on 2026-02-14'], r)
    r = ask('viewer7', '!hydrate 2026-03'); chk('a seeded month', r == ['@viewer7 Penguin has hydrated 4 times on 2026-03'], r)
    r = ask('viewer8', '!hydrate 2026-01-20'); chk('before recordStart', r == ['@viewer8 No record before Feb 2026.'], r)
    r = ask('viewer9', '!hydrate nonsense'); chk('usage', len(r) == 1 and 'Usage: !hydrate' in r[0], r)
    r = ask('viewer1', '!texttospeech'); chk('other groups: the key without underscores', r == ['@viewer1 Text-to-Speech: 0 today, 0 this week, 0 this month, 5 all-time'], r)
    r = ask('viewer2', '!mimimimi week'); chk('a group nobody redeemed', r == ['@viewer2 Mimimimi: 0 this week'], r)
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup()
    g = G()['hydrate']; chk('days survive a restart', g['all'] == 12 and g['today'] == 2 and g['days'] == dict(hyd, **{today[0]: 2}), g)
    r = seeder('--seed-json', sp, '--write'); c = json.load(open(os.path.join(d, 'runtime', 'redeem_counts.json')))
    chk('a re-seed keeps the live days apart from the seeded days', c['groups']['hydrate']['liveDays'] == {today[0]: 2} and c['groups']['hydrate']['days'] == hyd and c['groups']['hydrate']['live'] == 2, c['groups']['hydrate'])
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(out()[-1500:].encode('ascii', 'replace').decode()) if fails else None; shutil.rmtree(d, True)
print(('FAIL ' + '; '.join(fails) if fails else 'PASS redeemdays').encode('ascii', 'replace').decode()); sys.exit(1 if fails else 0)
