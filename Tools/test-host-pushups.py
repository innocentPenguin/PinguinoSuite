"""The pushup counter: !pushup / !pushups / !pu (everyone reads, mods change: add / remove / +N / -N / N / set / reset / on / off), persisted in Data/runtime/pushups.json across restarts,
GET /api/pushup -> {enabled,count}, POST /api/pushup {action,value}, the "pushup" widget is registered. Two counters (all-time + today; add/remove move both, reset only today) and a one-time seeded baseline (Tools/seed-pushups.py). Usage: python Tools/test-host-pushups.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, TOK = 8987, 'test-module-token'
d = tempfile.mkdtemp(prefix='pgpu_'); outp = os.path.join(d, 'out.txt'); pj = os.path.join(d, 'pushups.json')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8986', 'PINGUINO_MODULE_TOKEN': TOK})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def start():
    return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def get(p):
    return json.load(urllib.request.urlopen('http://127.0.0.1:%d%s' % (PORT, p), timeout=10))
def post(p, body):
    h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
    try: return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=json.dumps(body).encode(), headers=h), timeout=10))
    except urllib.error.HTTPError as e: return {'http': e.code}
def waitup():
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
def says(host, line, wait=0.8):
    n = len(open(outp, 'rb').read()); host.stdin.write(line.encode() + chr(10).encode()); host.stdin.flush(); time.sleep(wait)
    new = open(outp, 'rb').read()[n:].decode('utf-8', 'replace')
    return [l[len('[say] '):] for l in new.splitlines() if l.startswith('[say] ')]
host = start()
try:
    waitup()
    chk('starts at 0, enabled', get('/api/pushup') == {'enabled': True, 'count': 0, 'allTime': 0, 'session': 0, 'today': 0, 'week': 0, 'month': 0, 'days': {}}, get('/api/pushup'))
    r = says(host, 'viewer1: !pushup'); chk('reading names the viewer', r == ['@viewer1 Pushups: 0 today, 0 this week, 0 this month, 0 all-time'], r)
    r = says(host, 'viewer1: !pushups', 0.5); chk('a second read inside the cooldown is quiet', r == [], r)
    r = says(host, 'viewer2: !pu'); chk('!pu is an alias', r == ['@viewer2 Pushups: 0 today, 0 this week, 0 this month, 0 all-time'], r)
    r = says(host, 'viewer1: !pushup 5'); chk('a viewer cannot change it', len(r) == 1 and 'mods' in r[0].lower() and get('/api/pushup')['count'] == 0, r)
    for line, want in [('*mod1: !pushup add', 1), ('*mod1: !pushup plus', 2), ('*mod1: !pushup +', 3), ('*mod1: !pushup up', 4), ('*mod1: !pushup inc', 5), ('*mod1: !pushup done', 6), ('*mod1: !pushup did', 7),
                       ('*mod1: !pushup +3', 10), ('*mod1: !pushup 5', 15), ('*mod1: !pushup add 5', 20), ('*mod1: !pushup done 5', 25)]:
        r = says(host, line, 0.5); chk(line, r == ['@mod1 Pushups: %d today, %d this week, %d this month, %d all-time' % (want, want, want, want)], r)
    for line, want in [('*mod1: !pushup remove', 24), ('*mod1: !pushup minus', 23), ('*mod1: !pushup -', 22), ('*mod1: !pushup sub', 21), ('*mod1: !pushup down', 20), ('*mod1: !pushup dec', 19), ('*mod1: !pushup undo', 18),
                       ('*mod1: !pushup -3', 15), ('*mod1: !pushup minus 5', 10), ('*mod1: !pushup sub 4', 6)]:
        r = says(host, line, 0.5); chk(line, r == ['@mod1 Pushups: %d today, %d this week, %d this month, %d all-time' % (want, want, want, want)], r)
    r = says(host, '*mod1: !pushup -100', 0.5); chk('never below 0', r == ['@mod1 Pushups: 0 today, 0 this week, 0 this month, 0 all-time'], r)
    r = says(host, '*mod1: !pushups set 42', 0.5); chk('set N', r == ['@mod1 Pushups: 0 today, 0 this week, 0 this month, 42 all-time'], r)
    r = says(host, '*mod1: !pushup set', 0.5); chk('set without a number is refused', len(r) == 1 and 'set <number>' in r[0] and get('/api/pushup')['count'] == 42, r)
    r = says(host, '*mod1: !pu bogus', 0.5); chk('unknown word shows the usage', len(r) == 1 and 'Mods:' in r[0] and get('/api/pushup')['count'] == 42, r)
    chk('count is persisted', json.load(open(pj, encoding='utf-8-sig')) == {'enabled': True, 'count': 42, 'allTime': 42, 'session': 0, 'today': 0, 'week': 0, 'month': 0, 'days': {}}, open(pj).read() if os.path.exists(pj) else 'no file')
    r = post('/api/pushup', {'action': 'add', 'value': 8}); chk('POST add', r.get('ok') and r.get('count') == 50 and r.get('allTime') == 50 and r.get('session') == 8, r)
    r = post('/api/pushup', {'action': 'remove'}); chk('POST remove defaults to 1', r.get('count') == 49 and r.get('session') == 7, r)
    r = post('/api/pushup', {'action': 'set', 'value': 7}); chk('POST set', r.get('count') == 7 and r.get('allTime') == 7, r)
    r = post('/api/pushup', {'action': 'nope'}); chk('POST unknown action is refused', r.get('ok') is False, r)
    r = says(host, '*mod1: !pushup off', 0.5); chk('off', len(r) == 1 and 'off' in r[0].lower() and get('/api/pushup') == dict(get('/api/pushup'), enabled=False, count=7, allTime=7, session=7, today=7, week=7, month=7), r)
    r = says(host, 'viewer3: !pushup', 0.5); chk('viewers get nothing while it is off', r == [], r)
    host.kill(); host.wait(timeout=20); time.sleep(1)
    host = start(); waitup()
    chk('off + count survive a restart', get('/api/pushup') == dict(get('/api/pushup'), enabled=False, count=7, allTime=7, session=7, today=7, week=7, month=7), get('/api/pushup'))
    r = says(host, '*mod1: !pushup on', 0.5); chk('on', len(r) == 1 and 'Pushups: 7 today, 7 this week, 7 this month, 7 all-time' in r[0] and get('/api/pushup')['enabled'] is True, r)
    r = says(host, '*mod1: !pushup reset', 0.5); chk('reset clears only today', r == ['@mod1 Pushups today reset. Pushups: 0 today, 0 this week, 0 this month, 7 all-time'], r)
    # the seeded baseline: dry run writes nothing, --write backs the file up, the Host adds it once
    host.kill(); host.wait(timeout=20); time.sleep(1)
    sd = lambda *a: subprocess.run([sys.executable, os.path.join(here, 'seed-pushups.py'), '--data', d] + list(a), capture_output=True, text=True)
    before = open(pj).read(); r = sd(); chk('seed dry run', r.returncode == 0 and 'DRY RUN' in r.stdout and '812' in r.stdout and open(pj).read() == before, r.stdout + r.stderr)
    r = sd('--write'); baks = [f for f in os.listdir(d) if f.startswith('pushups.json.before-seed-')]; sj = json.load(open(pj))
    chk('seed written with a dated .bak, not yet applied', r.returncode == 0 and len(baks) == 1 and sj['baseline'] == 805 and sj['baselineApplied'] is False and sj['baselineNote'] == '161 redemptions x 5, 2026-10-30' and sj['allTime'] == 7, (r.stdout + r.stderr, baks, sj))
    chk('a second seed is refused', sd('--write').returncode != 0)
    host = start(); waitup(); g = get('/api/pushup')
    chk('the Host adds the baseline once: 7 + 805', g['allTime'] == 812 and g['count'] == 812 and g['session'] == 0 and g['baselineApplied'] is True and g['baseline'] == 805, g)
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup()
    chk('a restart never re-adds it', get('/api/pushup')['allTime'] == 812, get('/api/pushup'))
    r = says(host, '*mod1: !pushup +3', 0.5); chk('mods add on top of the baseline, both counters', r == ['@mod1 Pushups: 3 today, 3 this week, 3 this month, 815 all-time'], r)
    r = says(host, 'viewer9: !pushup', 0.5); chk('!pushup shows both', r == ['@viewer9 Pushups: 3 today, 3 this week, 3 this month, 815 all-time'], r)
    r = says(host, '*mod1: !pushup reset', 0.5); chk('reset keeps all-time with its baseline', r == ['@mod1 Pushups today reset. Pushups: 0 today, 0 this week, 0 this month, 815 all-time'] and get('/api/pushup')['allTime'] == 815, r)
    says(host, '*mod1: !pushup +4', 0.5)
    for w, per, want in (('viewer1', 'today', 4), ('viewer2', 'week', 4), ('viewer3', 'month', 4), ('viewer4', 'all', 819), ('viewer5', 'all-time', 819)): r = says(host, '%s: !pushup %s' % (w, per), 0.5); chk('!pushup ' + per, r == ['@%s Pushups %s: %d' % (w, {'today': 'today', 'week': 'this week', 'month': 'this month', 'all': 'all-time', 'all-time': 'all-time'}[per], want)], r)
    g = get('/api/pushup'); chk('API carries today/week/month and the day history', g['today'] == 4 and g['week'] == 4 and g['month'] == 4 and sum(g['days'].values()) == 4, g)
    chk('the pushup widget is registered', any(w.get('id') == 'pushup' and w.get('src') == 'pushup.html' for w in (get('/api/scene-widgets').get('widgets') or [])) if True else False, 'scene-widgets')
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS pushups'); sys.exit(1 if fails else 0)
