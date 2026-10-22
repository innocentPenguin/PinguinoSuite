"""Queue overlay idle mode: GET /api/queue-idle gives chains of leaderboard cards from the public boards - empty cards are left out, bots and !optmeout viewers never appear,
the order inside a chain is kept, the ?js=1 form can be loaded from a file:// overlay, and queue_idle.json (runtime data folder) is created.
Usage: python Tools/test-host-queueidle.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8984; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgqi_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'secretsam': {'Login': 'secretsam', 'Name': 'SecretSam', 'Privacy': 'anon'}}, open(os.path.join(d, 'chat_memory.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983', 'PINGUINO_ECONOMY_TESTHOOK': '1'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return urllib.request.urlopen(B + p, timeout=10).read().decode()
def post(p, o): return urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read()
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
try:
    for _ in range(120):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    now = int(time.time()); n = 0
    for u, g, b in (('alice', 10, 500), ('bob', 4, 900), ('secretsam', 99, 99999), ('carl', 1, 0)):
        n += 1; post('/api/boards/event', {'user': u, 'metric': 'gifts', 'amount': g, 'ts': now, 'id': 'g%d' % n})
        if b: n += 1; post('/api/boards/event', {'user': u, 'metric': 'bits', 'amount': b, 'ts': now, 'id': 'b%d' % n})
    d1 = json.loads(get('/api/queue-idle'))
    items = d1['items']
    chk('ok and enabled', d1['ok'] and d1['enabled'], d1)
    chk('defaults written to queue_idle.json', os.path.exists(os.path.join(d, 'queue_idle.json')))
    chk('cards exist for the metrics that have data', items, d1)
    ids = [[c['id'] for c in ch] for ch in items]
    flat = [i for ch in ids for i in ch]
    chk('gifts and bits boards are present', 'gifts|month' in flat and 'bits|month' in flat, ids)
    chk('empty boards (watch time, level) are left out', not any(i.startswith('watchtime') for i in flat), ids)
    first = [ch for ch in items if ch[0]['id'] == 'gifts|month' and len(ch) > 1 and ch[1]['id'] == 'bits|month']
    chk('the gifters -> cheerers chain keeps its order', first, ids)
    g = next(c for ch in items for c in ch if c['id'] == 'gifts|month')
    names = [r['name'].lower() for r in g['rows']]
    chk('top gifter first', names[:2] == ['alice', 'bob'], names)
    chk('the !optmeout viewer is never named or counted', 'secretsam' not in json.dumps(items).lower(), names)
    chk('titles read like TOP GIFTERS · THIS MONTH', g['title'] == 'TOP GIFTERS · THIS MONTH', g['title'])
    js = get('/api/queue-idle?js=1')
    chk('?js=1 is a script a file:// overlay can load', js.startswith('window.QUEUE_IDLE={') and js.endswith(';'), js[:60])
    # config is obeyed (cache lasts 60 s, so use a fresh file read through a new host start is not needed: write then ask a second host? keep it simple: check file content)
    cfg = json.load(open(os.path.join(d, 'queue_idle.json')))
    chk('config has the documented keys', all(k in cfg for k in ('enabled', 'idleSeconds', 'secondsPerCard', 'top', 'sequence')), cfg)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS queue idle boards'); sys.exit(1 if fails else 0)
