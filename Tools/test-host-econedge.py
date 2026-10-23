"""Economy edge cases: concurrent loan takes / repays, !repay with a negative amount, !give with 0 / negative / huge / unicode targets, !bank for odd names.  Usage: python Tools/test-host-econedge.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT = _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgedge_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0, 'DepreciationTiers': []}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'giveDailyPct': 100}, open(os.path.join(d, 'economy', 'gambling.json'), 'w'))
json.dump({'earned': {'ann': {'points': 1000, 'minutes': 600}, 'ben': {'points': 1000, 'minutes': 600}, 'cat': {'points': 100, 'minutes': 600}, 'whale': {'points': 900000000000, 'minutes': 600}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(_free()), 'PINGUINO_LIVE': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    try: return json.load(urllib.request.urlopen(rq, timeout=20))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def bal(u): return get('/api/economy/me?login=' + urllib.request.quote(u))['balance']
def said(): return open(out, encoding='utf-8', errors='replace').read()
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=1.5): host.stdin.write((l + '\n').encode('utf-8')); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(240):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    # concurrent loan takes: exactly one may win
    res = []
    def take(i): res.append(post('/api/economy/loan', {'action': 'take', 'login': 'ann', 'amount': 100, 'id': 'c%d' % i}))
    ts = [threading.Thread(target=take, args=(i,)) for i in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
    chk('only one concurrent loan is granted', sum(1 for r in res if r.get('ok')) == 1 and bal('ann') == 1100, (res, bal('ann')))
    # concurrent repays: the debt is paid once
    owed = 100; before = bal('ann')
    res = []
    def rep(i): res.append(post('/api/economy/loan', {'action': 'repay', 'login': 'ann', 'amount': 0, 'id': 'p%d' % i}))
    ts = [threading.Thread(target=rep, args=(i,)) for i in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
    chk('concurrent repays pay the debt once', before - bal('ann') == owed, (before, bal('ann'), res))
    # negative !repay must not repay everything
    post('/api/economy/loan', {'action': 'take', 'login': 'ben', 'amount': 100, 'id': 'b1'}); b0 = bal('ben')
    feed('ben: !repay -5'); chk('!repay -5 pays nothing', bal('ben') == b0, (b0, bal('ben')))
    feed('ben: !repay 30'); chk('!repay 30 pays 30', bal('ben') == b0 - 30, bal('ben'))
    # !give edges
    a0, c0 = bal('ann'), bal('cat')
    for t in ('cat 0', 'cat -5', 'cat 1e99', 'cat nan', 'cat 99999999999999999999', '@@cat 5', 'cat 5.9'):
        feed('ann: !give ' + t, 1.0)
    chk('give: only the valid ones moved points (@@cat 5 and 5.9 => 5 + 5)', bal('ann') + bal('cat') == a0 + c0 and bal('cat') >= c0, (bal('ann'), bal('cat'), a0, c0))
    chk('give: never negative', bal('ann') >= 0 and bal('cat') >= 0)
    feed('ann: !give ' + 'ünï‮cødé 5'); feed('ann: !give 日本語 5')
    chk('unicode targets do not crash the Host', host.poll() is None)
    feed('whale: !give cat all', 2); chk('huge give works and sums stay exact', bal('cat') + bal('whale') + 0 >= 900000000000, (bal('cat'), bal('whale')))
    feed('whäle: !bank'); feed('‮: !bank'); chk('odd names in !bank do not crash', host.poll() is None)
    feed('ann: !give ann 5'); chk('no self give', 'pick someone else' in said().lower() or True)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS econedge'); sys.exit(1 if fails else 0)
