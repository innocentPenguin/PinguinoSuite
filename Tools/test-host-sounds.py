"""Alert + welcome sounds: default chimes are generated, GET/POST /api/alerts-settings (validation), the welcome chime on a first-ever message (gated by live/Offline, once per login),
and the one-time migration that adds alert_sound steps to already-seeded follow/sub presets.  Nothing is played (PINGUINO_SOUND_DRYRUN=1).  Usage: python Tools/test-host-sounds.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8984; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsnd_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
# an automations file saved by an older build: sb-follow / sb-cheer without the alert_sound step
old = {'seeded': ['spotify', 'sbreplace1', 'sbreplace2'], 'actions': [
    {'id': 'sb-follow', 'name': 'Alert: follow', 'enabled': True, 'triggers': [], 'steps': [{'type': 'say', 'as': 'core', 'text': 'hi {user}'}, {'type': 'run_action', 'name': 'Alerts: show Latest Group'}]},
    {'id': 'sb-cheer', 'name': 'Alert: cheer', 'enabled': True, 'triggers': [], 'steps': [{'type': 'say', 'as': 'core', 'text': 'bits'}, {'type': 'alert_sound', 'kind': 'cheer'}]}]}
for sub in ('', 'runtime'):
    os.makedirs(os.path.join(d, sub), exist_ok=True); json.dump(old, open(os.path.join(d, sub, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8985', 'PINGUINO_SOUND_DRYRUN': '1'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    try: return json.load(urllib.request.urlopen(rq, timeout=10))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def recent(kind): return [r for r in get('/api/alerts-settings')['recent'] if r['kind'] == kind]
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=0.6): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    r = get('/api/alerts-settings'); s = r['settings']
    chk('ok + kinds', r['ok'] and set(r['kinds']) >= {'follow', 'sub', 'resub', 'gift', 'cheer', 'raid'}, r.get('error'))
    files = [s['Sounds'][k]['File'] for k in r['kinds']] + [s['Welcome']['File']]
    chk('defaults point at generated files that exist', all(f and os.path.exists(f) for f in files), files)
    chk('generated wav is a real tiny wav', all(open(f, 'rb').read(4) == b'RIFF' and 2000 < os.path.getsize(f) < 100000 for f in files))
    chk('welcome defaults', s['Welcome']['Enabled'] is True and s['Welcome']['OnlyWhileLive'] is True and 0 < s['Welcome']['Volume'] <= 1, s['Welcome'])
    # ---- edit through the API
    p = post('/api/alerts-settings', {'Sounds': {'follow': {'Volume': 0.3}}, 'Welcome': {'Volume': 0.25}})
    chk('volume saved, other fields kept', p['ok'] and p['settings']['Sounds']['follow']['Volume'] == 0.3 and p['settings']['Sounds']['follow']['File'] == s['Sounds']['follow']['File'] and p['settings']['Welcome']['Volume'] == 0.25, p)
    chk('bad volume rejected', post('/api/alerts-settings', {'Welcome': {'Volume': 3}})['ok'] is False)
    chk('missing file rejected', post('/api/alerts-settings', {'Sounds': {'sub': {'File': 'C:\\nope\\x.wav'}}})['ok'] is False)
    chk('non-sound file rejected', post('/api/alerts-settings', {'Sounds': {'sub': {'File': os.path.join(d, 'host_secrets.json')}}})['ok'] is False)
    chk('unknown kind rejected', post('/api/alerts-settings', {'Sounds': {'zzz': {'Volume': 0.1}}})['ok'] is False)
    chk('unknown setting rejected', post('/api/alerts-settings', {'Nope': 1})['ok'] is False)
    t = post('/api/alerts-settings', {'test': 'follow'}); chk('test button plays (dry run)', t['ok'] and 'would play follow.wav' in t['result'], t)
    chk('test recorded', recent('follow') and abs(recent('follow')[-1]['volume'] - 0.3) < 1e-6, recent('follow'))
    chk('test with no sound set', post('/api/alerts-settings', {'Sounds': {'raid': {'File': ''}}})['ok'] and post('/api/alerts-settings', {'test': 'raid'})['ok'] is False)
    # ---- welcome chime: offline (not live) = silent, live/Offline mode = one chime per login
    feed('^early: hi')
    chk('no chime while offline (OnlyWhileLive)', not recent('welcome'), recent('welcome'))
    post('/api/alerts-settings', {'Welcome': {'OnlyWhileLive': False}})
    feed('^newbie: hi everyone'); chk('chime on a first message', len(recent('welcome')) == 1, recent('welcome'))
    feed('^newbie: hello again'); chk('once per login', len(recent('welcome')) == 1, recent('welcome'))
    feed('^pinguinob0t: hi'); feed('^streamer1: hi'); feed('plain: hi'); chk('bots, the streamer and non-first chatters get no chime', len(recent('welcome')) == 1, recent('welcome'))
    post('/api/alerts-settings', {'Welcome': {'Enabled': False}}); feed('^other: hi'); chk('disabled = silent', len(recent('welcome')) == 1)
    post('/api/alerts-settings', {'Welcome': {'Enabled': True}, 'MuteSounds': True}); feed('^third: hi'); chk('MuteSounds silences it', len(recent('welcome')) == 1)
    post('/api/alerts-settings', {'MuteSounds': False}); feed('^fourth: hi'); chk('unmuted plays again', len(recent('welcome')) == 2, recent('welcome'))
    # ---- migration
    doc = get('/api/automations')['doc']; acts = {a['id']: a for a in doc['actions']}
    f = [x['type'] for x in acts['sb-follow']['steps']]; c = [x['type'] for x in acts['sb-cheer']['steps']]
    chk('follow got alert_sound before the popup step', f == ['say', 'alert_sound', 'run_action'], f)
    chk('cheer not doubled', c.count('alert_sound') == 1, c)
    chk('marker set', 'alertsound1' in doc['seeded'], doc['seeded'])
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS sounds'); sys.exit(1 if fails else 0)
