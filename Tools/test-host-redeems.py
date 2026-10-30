"""Redeem counters: seeder dry run / write with .bak, group fold across renamed ids and titles, dedupe on a repeated redemption id, the cut-off (older redemptions are not counted), the Pushups estimate
staying out of the total, GET /api/redeems, {redeem.<group>} in an automation, persistence across a restart. Usage: python Tools/test-host-redeems.py [dll]"""
import glob, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WS = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgredeem_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def seeder(*a): return subprocess.run([sys.executable, os.path.join(here, 'seed-redeems.py'), '--data', d] + list(a), capture_output=True, text=True)
def start(): return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=20))
def waitup():
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
def feed(l, w=0.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def out(): return open(outp, 'rb').read().decode('utf-8', 'replace')
def G(): return api('/api/redeems')['groups']
CUT = '2026-10-30T01:00:00Z'

# --- seeder: dry run writes nothing, --write needs --through, then writes with a backup of an existing file
r = seeder(); chk('dry run prints the baseline', r.returncode == 0 and 'pushups' in r.stdout and '161' in r.stdout and 'DRY RUN' in r.stdout, r.stdout[-300:] + r.stderr[-300:])
chk('dry run wrote nothing', not os.path.exists(os.path.join(d, 'runtime', 'redeem_counts.json')))
r = seeder('--write'); chk('--write without --through is refused', r.returncode != 0 and not os.path.exists(os.path.join(d, 'runtime', 'redeem_counts.json')), r.stdout[-200:])
r = seeder('--write', '--through', CUT, '--add', 'timeout_someone=3'); chk('seed written', r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
cp = os.path.join(d, 'runtime', 'redeem_counts.json'); c = json.load(open(cp))
chk('baselines from the doc', c['groups']['pushups']['baseline'] == 161 and c['groups']['hydrate']['baseline'] == 924 and c['groups']['suggestion']['baseline'] == 357 and c['groups']['timeout_someone']['baseline'] == 9, {k: v['baseline'] for k, v in c['groups'].items()})
chk('estimate stored apart, not in baseline', c['groups']['pushups'].get('estimated', {}).get('count') == 10 and c['groups']['pushups']['baseline'] == 161)
r = seeder('--write', '--through', CUT); baks = glob.glob(cp + '.before-seed-*.bak')
chk('a second seed keeps a dated .bak of the old counts file', len(baks) == 1, baks)

host = start()
try:
    waitup()
    g = G(); chk('API shape', g['pushups']['total'] == 161 and g['pushups']['baseline'] == 161 and g['pushups']['live'] == 0 and g['pushups']['perMonth']['2026-04'] == 38 and g['pushups']['baselineThrough'] == CUT and g['pushups']['estimated']['count'] == 10, g.get('pushups'))
    # fold across renamed ids and titles: old id, newest id, SoundAlerts template title with trailing space/case, plain title only
    feed('redeem alice r1 09c78a1c-767e-4f07-a4ae-2f4a4935fc10 2026-10-30T02:00:00Z Pushups')
    feed('redeem bob r2 5567e401-0000-0000-0000-000000000000 2026-10-30T02:05:00Z Do Pushups Now!')
    feed('redeem cara r3 - 2026-10-30T02:10:00Z  pushups ')
    feed('redeem dan r4 b618f97f-1111 2026-11-01T03:00:00Z Whatever The Old Name Was')
    g = G(); chk('4 renamed/re-created pushups reward ids and titles fold into one group', g['pushups']['live'] == 4 and g['pushups']['total'] == 165, g['pushups'])
    chk('per month adds live to baseline', g['pushups']['perMonth']['2026-10'] == 29 and g['pushups']['perMonth']['2026-11'] == 1, g['pushups']['perMonth'])
    chk('estimated stays out of the total', g['pushups']['total'] == g['pushups']['baseline'] + g['pushups']['live'])
    # dedupe: the same redemption id again (EventSub redelivery), also with another title
    feed('redeem alice r1 09c78a1c-767e-4f07-a4ae-2f4a4935fc10 2026-10-30T02:00:00Z Pushups'); feed('redeem alice r1 - - Pushups')
    chk('a repeated redemption id counts once', G()['pushups']['live'] == 4, G()['pushups'])
    # cut-off: at or before baselineThrough is already in the baseline
    feed('redeem eve r5 09c78a1c-767e-4f07 2026-10-30T00:59:59Z Pushups'); feed('redeem eve r6 09c78a1c-767e-4f07 2026-10-30T01:00:00Z Pushups')
    chk('redemptions at or before the cut-off are not counted', G()['pushups']['live'] == 4, G()['pushups'])
    feed('redeem eve r7 09c78a1c-767e-4f07 2026-10-30T01:00:01Z Pushups'); chk('one second after the cut-off is counted', G()['pushups']['live'] == 5 and G()['pushups']['lastRedeemAt'].startswith('2026-11-01'), G()['pushups'])
    feed('redeem fay r8 4ef5ade3-aaaa 2026-10-30T05:00:00Z Hydrate'); feed('redeem fay r9 - 2026-10-30T05:01:00Z hydrate!')
    chk('hydrate folds on id and on an alias', G()['hydrate']['live'] == 2 and G()['hydrate']['total'] == 926, G()['hydrate'])
    feed('redeem gus r10 aaaaaaaa-no-group 2026-10-30T05:02:00Z Brand New Reward'); chk('an unknown reward joins no group', all(v['live'] == 0 for k, v in G().items() if k not in ('pushups', 'hydrate')), {k: v['live'] for k, v in G().items()})
    # chat variable
    acts = [{'id': 'cnt', 'name': 'Counter', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!zzcount']}], 'steps': [{'type': 'say', 'text': 'pushups so far: {redeem.pushups} hydrate: {redeem.hydrate} none: {redeem.nope}'}]}]
    chk('automation saved', api('/api/automations', {'doc': {'version': 1, 'actions': acts}}).get('ok'))
    feed('viewer: !zzcount', 2.0); said = [o for r in api('/api/automations/log?n=20')['runs'] for o in r.get('output', [])]
    chk('{redeem.<group>} in chat', any('pushups so far: 166 hydrate: 926 none: 0' in o for o in said), said[-3:])
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup()
    g = G(); chk('counts survive a restart', g['pushups']['live'] == 5 and g['pushups']['total'] == 166 and g['hydrate']['total'] == 926, g['pushups'])
    feed('redeem alice r1 - 2026-10-30T02:00:00Z Pushups'); feed('redeem alice r2 - 2026-10-30T02:00:00Z Pushups')
    chk('the seen ids survive a restart too', G()['pushups']['live'] == 5, G()['pushups'])
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(out()[-1500:].encode('ascii', 'replace').decode()) if fails else None; shutil.rmtree(d, True)
print(('FAIL ' + '; '.join(fails) if fails else 'PASS redeems').encode('ascii', 'replace').decode()); sys.exit(1 if fails else 0)
