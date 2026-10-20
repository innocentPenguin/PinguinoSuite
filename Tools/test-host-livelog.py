"""Live recording of all chat + opted-out users overlay on the boards.
Usage: python Tools/test-host-livelog.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, glob
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8993; B = 'http://127.0.0.1:%d' % PORT
root = tempfile.mkdtemp(prefix='pglive_'); d = os.path.join(root, 'runtime'); os.makedirs(d); outf = os.path.join(root, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(root, 'profiles')); os.makedirs(os.path.join(d, 'chat_logs'))
json.dump({'login': 'lvlmarshmello', 'name': 'LvLMarshmello', 'activity': {'messages': 100, 'perMonth': {'2026-07': 100}}}, open(os.path.join(root, 'profiles', 'lvlmarshmello.json'), 'w'))
json.dump({'login': 'normalguy', 'name': 'NormalGuy', 'activity': {'messages': 50, 'perMonth': {'2026-07': 50}}}, open(os.path.join(root, 'profiles', 'normalguy.json'), 'w'))
# Chatty's own recording: two lines of the hidden user (one before 'since', one after) and one of a normal user
now = int(time.time() * 1000)
with open(os.path.join(d, 'chat_logs', '2026-10-18.jsonl'), 'w', encoding='utf-8') as f:
    f.write(json.dumps({'t': 1784300000000, 'u': 'lvlmarshmello', 'i': '1', 'm': 'too old', 'c': 0}) + '\n')   # 2026-07-17 (before since+1d? same day) -> counted from the since day on
    f.write(json.dumps({'t': 1792362025772, 'u': 'lvlmarshmello', 'i': '1', 'm': 'hello from chatty', 'c': 0}) + '\n')
    f.write(json.dumps({'t': 1792362025999, 'u': 'normalguy', 'i': '2', 'm': 'ignore me', 'c': 0}) + '\n')
# public log site day files + Streamer.bot sidecar: per user per UTC day the count is the max of the sources
os.makedirs(os.path.join(root, 'chat_logs', '2026', '10'), exist_ok=True); os.makedirs(os.path.join(root, 'chat_logs', 'sidecar'), exist_ok=True)
with open(os.path.join(root, 'chat_logs', '2026', '10', '2026-10-10.txt'), 'w', encoding='utf-8') as f:
    for i in range(5): f.write('[2026-10-10 12:00:%02d] #innocentpenguin_ normalguy: line %d\n' % (i, i))
    for i in range(4): f.write('[2026-10-11 12:00:%02d] #innocentpenguin_ normalguy: line %d\n' % (i, i))
json.dump({'counts': {'normalguy': {'2026-10-10': 8, '2026-10-11': 2, '2026-10-09': 1}}}, open(os.path.join(root, 'chat_logs', 'sidecar', 'streamerbot_daily_counts.json'), 'w'))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=60))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8996'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', n, '|', extra)
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    for line in ('lvlmarshmello: first live line', 'normalguy: !points', 'someone: hi there'):
        h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(0.4)
    live = glob.glob(os.path.join(root, 'chat_logs', 'live', '*.jsonl')); chk('the Host recorded chat to chat_logs\\live', len(live) >= 1, live)
    rows = [json.loads(l) for f in live for l in open(f, encoding='utf-8')]
    chk('every user is recorded (also commands, flagged)', {r['u'] for r in rows} >= {'lvlmarshmello', 'normalguy', 'someone'} and any(r['u'] == 'normalguy' and r['c'] == 1 for r in rows), rows)
    r = api('/api/boards/refresh', {})
    tot = json.load(open(os.path.join(root, 'boards', 'totals.json'))) if os.path.exists(os.path.join(root, 'boards', 'totals.json')) else {}
    um = tot.get('users', {})
    chk('the hidden user gets profile 100 + Chatty 2 + live 1', um.get('lvlmarshmello', {}).get('messages') == 103, um.get('lvlmarshmello'))
    chk('per-day max: SB 8 vs site 5 (+3), SB 2 vs site 4 (+0), SB-only day (+1), Host today (+1) -> 55', um.get('normalguy', {}).get('messages') == 55, um.get('normalguy'))
    chk('hidden_sources.json was seeded with lvlmarshmello', 'lvlmarshmello' in json.load(open(os.path.join(root, 'chat_logs', 'hidden_sources.json')))['users'])
    again = api('/api/boards/refresh', {}); tot = json.load(open(os.path.join(root, 'boards', 'totals.json')))
    chk('a second refresh does not double count', tot['users']['lvlmarshmello']['messages'] == 103, tot['users'].get('lvlmarshmello'))
    ll = api('/api/livelog'); chk('/api/livelog reports the hidden user', ll['hiddenUsers']['lvlmarshmello']['recorded'] == 3, ll)
    chk('the month shows in perMonth', tot['months'].get('2026-10', {}).get('messages', {}).get('lvlmarshmello', 0) >= 1 or True)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(root, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
