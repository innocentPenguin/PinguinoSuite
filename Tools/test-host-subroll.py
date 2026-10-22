"""Sub roll-call overlay + queue-overlay Subs! card (sim Host, temp data, mock roster): every current subscriber is served in each sort mode, lapsed subs, bots, the streamer and
!optmeout viewers never appear, tier groups are T3/T2/T1, the roll starts/stops through the state (nonce changes), the mod command starts it (viewers get nothing) and answers with ONE short line,
the ?js=1 forms load from a file:// overlay, and the queue overlay gets ONE "Subs!" card (T1 not gifted, T2, T3; months then watch time) as the first idle item, with options and config migration.
Usage: python Tools/test-host-subroll.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8982; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsr_'); outf = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'subs'))
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def u(t, ten, sub, lapsed=False, typ='recurring'): return {'tier': t, 'tenure': ten, 'streak': 1, 'subscribed': sub, 'founder': False, 'subType': typ, 'lapsed': lapsed}
users = {'zed': u(3, 20, '2025-01-01T00:00:00Z'), 'amy': u(3, 30, '2024-06-01T00:00:00Z'), 'bob': u(2, 5, '2026-03-01T00:00:00Z'), 'cat': u(2, 12, '2026-01-01T00:00:00Z'),
         'dan': u(1, 3, '2026-09-01T00:00:00Z', typ='gift'), 'eve': u(1, 40, '2023-01-01T00:00:00Z', typ='prime'), 'old': u(1, 9, '2025-05-05T00:00:00Z', lapsed=True),
         'nightbot': u(1, 1, '2026-01-01T00:00:00Z'), 'secretsam': u(1, 8, '2026-02-02T00:00:00Z'), 'innocentpenguin_': u(1, 1, '2026-02-02T00:00:00Z')}
json.dump({'users': users, 'processed': {}}, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
json.dump({'secretsam': {'Login': 'secretsam', 'Name': 'SecretSam', 'Privacy': 'anon'}}, open(os.path.join(d, 'chat_memory.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8981', 'PINGUINO_ECONOMY_TESTHOOK': '1'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return urllib.request.urlopen(B + p, timeout=10).read().decode()
def post(p, o=None):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o or {}).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode() or '{}')
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.8):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def names(mode): return [s['login'] for s in json.loads(get('/api/subroll?mode=' + mode))['subs']]
try:
    for _ in range(120):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    now = int(time.time())
    for i, (usr, g) in enumerate((('eve', 2), ('zed', 9), ('dan', 1))):   # gifts + watch time come from the board events
        post('/api/boards/event', {'user': usr, 'metric': 'gifts', 'amount': g, 'ts': now, 'id': 'g%d' % i})
    post('/api/boards/event', {'user': 'bob', 'metric': 'watchtime', 'amount': 5000, 'ts': now, 'id': 'w1'})
    post('/api/boards/event', {'user': 'amy', 'metric': 'watchtime', 'amount': 100, 'ts': now, 'id': 'w2'})
    allx = set(names('alpha'))
    chk('exactly the current, public subscribers', allx == {'zed', 'amy', 'bob', 'cat', 'dan', 'eve'}, allx)
    chk('alphabetical', names('alpha') == ['amy', 'bob', 'cat', 'dan', 'eve', 'zed'], names('alpha'))
    chk('watch time high to low', names('watch')[:2] == ['bob', 'amy'], names('watch'))
    chk('by months subscribed', names('length')[:3] == ['eve', 'amy', 'zed'], names('length'))
    chk('tier order T3 > T2 > T1, months inside a tier', names('tier') == ['amy', 'zed', 'cat', 'bob', 'eve', 'dan'], names('tier'))
    chk('most gifted first', names('gifted')[:2] == ['zed', 'eve'], names('gifted'))
    chk('newest first / oldest first', names('newest')[0] == 'dan' and names('oldest')[0] == 'eve', (names('newest'), names('oldest')))
    chk('random keeps everybody', set(names('random')) == allx, names('random'))
    g = json.loads(get('/api/subroll?mode=tiergroups'))['groups']
    chk('tier groups are T3, T2, T1', [x['tier'] for x in g] == [3, 2, 1] and [len(x['subs']) for x in g] == [2, 2, 2], g)
    chk('an unknown mode falls back to the config mode', json.loads(get('/api/subroll?mode=nonsense'))['mode'] == 'tier')
    chk('no private data in the answer', 'secretsam' not in get('/api/subroll').lower() and 'nightbot' not in get('/api/subroll').lower())
    chk('config written with defaults', os.path.exists(os.path.join(d, 'subroll.json')))
    js = get('/api/subroll?js=1&mode=alpha'); chk('?js=1 is a script', js.startswith('window.SUBROLL={') and js.endswith(';'), js[:40])
    st0 = json.loads(get('/api/subroll/state'))
    chk('starts idle', st0['running'] is False, st0)
    st1 = post('/api/subroll/start', {'mode': 'alpha', 'style': 'pages'})
    chk('start sets running, mode, style and a new nonce', st1['running'] and st1['mode'] == 'alpha' and st1['style'] == 'pages' and st1['nonce'] > st0['nonce'], st1)
    chk('bad mode refused', post('/api/subroll/start', {'mode': 'zzz'}).get('ok') is False)
    st2 = post('/api/subroll/stop'); chk('stop', st2['running'] is False and st2['nonce'] > st1['nonce'], st2)
    chk('state ?js=1', get('/api/subroll/state?js=1').startswith('window.SUBROLL_STATE='))
    r = ask('viewer1: !subs roll alpha'); chk('a viewer gets nothing and starts nothing', r == [] and json.loads(get('/api/subroll/state'))['running'] is False, r)
    r = ask('*mod: !subs roll watch spotlight'); st = json.loads(get('/api/subroll/state'))
    chk('a mod starts it', st['running'] and st['mode'] == 'watch' and st['style'] == 'spotlight', st)
    chk('and the bot answers with ONE short line, never the list', len(r) == 1 and len(r[0]) < 200 and 'amy' not in r[0].lower(), r)
    r = ask('*mod: !subs roll alpha pages sprinkled'); st = json.loads(get('/api/subroll/state'))
    chk('layout is its own word next to mode and style', st['running'] and st['mode'] == 'alpha' and st['style'] == 'pages' and st['layout'] == 'sprinkled', st)
    chk('start by POST takes a layout, a bad one is refused, default is flat', post('/api/subroll/start', {'mode': 'alpha'})['layout'] == 'flat' and post('/api/subroll/start', {'layout': 'zzz'}).get('ok') is False)
    r = ask('*mod: !subs roll stop'); chk('stop by chat', len(r) == 1 and json.loads(get('/api/subroll/state'))['running'] is False, r)
    # queue overlay: ONE "Subs!" card, first in the sequence: T1 (not gifted) then T2 then T3, months then watch time
    qj = json.loads(get('/api/queue-idle')); qi = qj['items']
    chk('Subs! card is the first item of the sequence', qi and qi[0][0]['id'] == 'subs|all' and len(qi[0]) == 1, [[c['id'] for c in ch] for ch in qi][:3])
    chk('no separate tier cards any more', not any(c['id'] in ('tier3|all', 'tier2|all') for ch in qi for c in ch))
    sc = qi[0][0]
    chk('title Subs!, kind subs, unit months', sc['title'].startswith('Subs!') and sc['kind'] == 'subs' and sc['unit'] == 'months', sc)
    chk('one list T1 > T2 > T3, months inside a tier; the gifted T1 sub (dan) left out, gifted T2/T3 kept', [r['name'].lower() for r in sc['rows']] == ['eve', 'cat', 'bob', 'amy', 'zed'] and [r['tier'] for r in sc['rows']] == [1, 2, 2, 3, 3], sc['rows'])
    chk('tiers listed, watch time as second column, ranks run on', sc['tiers'] == [1, 2, 3] and [r['rank'] for r in sc['rows']] == [1, 2, 3, 4, 5] and [r['extra'] for r in sc['rows']][2] == 5000, sc)
    chk('scroll settings are served', qj['visibleRows'] >= 3 and qj['scrollSpeed'] >= 10 and qj['scrollPauseSeconds'] >= 0.5, qj)
    cfgp = os.path.join(d, 'queue_idle.json'); cj = json.load(open(cfgp))
    chk('config written: version 2, Subs! first, editable options', cj.get('version') == 2 and cj['sequence'][0]['metric'] == 'subs' and cj['sequence'][0]['giftedT1'] is False and cj['sequence'][0]['giftedT23'] is True and 'scrollSpeed' in cj, cj)
    # edit the config: gifted T1 allowed, gifted T2/T3 not -> the list changes
    cj['sequence'][0]['giftedT1'] = True; cj['sequence'][0]['giftedT23'] = False
    json.dump(cj, open(cfgp, 'w')); time.sleep(61)   # the answer is cached for 60 s
    sc2 = json.loads(get('/api/queue-idle'))['items'][0][0]
    chk('giftedT1 / giftedT23 options are honoured (no gifted subs in T2/T3 in this roster, dan joins T1)', [r['name'].lower() for r in sc2['rows']] == ['eve', 'dan', 'cat', 'bob', 'amy', 'zed'], sc2['rows'])
    cj['sequence'][0]['giftedT1'] = False; cj['sequence'][0]['giftedT23'] = True; cj['sequence'][0]['layout'] = 'sprinkled'
    json.dump(cj, open(cfgp, 'w')); time.sleep(61)
    sc3 = json.loads(get('/api/queue-idle'))['items'][0][0]
    chk('layout sprinkled: T2/T3 spread through T1 (eve alone in T1 here, so they surround it), layout reported', sc3['layout'] == 'sprinkled' and sorted(r['name'].lower() for r in sc3['rows']) == ['amy', 'bob', 'cat', 'eve', 'zed'], sc3)
    # an old (version-less) config is migrated and backed up
    json.dump({'enabled': True, 'idleSeconds': 33, 'sequence': [{'metric': 'points', 'period': 'all'}]}, open(cfgp, 'w')); time.sleep(61)
    qj3 = json.loads(get('/api/queue-idle')); cj3 = json.load(open(cfgp))
    chk('old config migrated: backup kept, Subs! first, own idleSeconds kept', os.path.exists(cfgp + '.bak-v1') and cj3['version'] == 2 and cj3['sequence'][0]['metric'] == 'subs' and cj3['idleSeconds'] == 33 and qj3['idleSeconds'] == 33, cj3)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS sub roll'); sys.exit(1 if fails else 0)
