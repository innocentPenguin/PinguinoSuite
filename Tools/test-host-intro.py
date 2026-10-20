"""Sub intro clips: first chat message of each stream per sub, queue order (T3 > T2 > T1, FIFO), no duplicates, slots, skip/clear, settings, media route. Usage: python Tools/test-host-intro.py [dll]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8909; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgintro_'); clips = os.path.join(d, 'clips'); os.makedirs(clips)
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Dir': clips, 'MaxPlaySec': 20}, open(os.path.join(d, 'intro_settings.json'), 'w'))
for n in ['t1guy.mp4', 't2guy.webm', 't3guy.mp4', 't3other.mp4', 'vert3_v.mp4', 'giffy.gif', '_default_t1.mp4']:
    open(os.path.join(clips, n), 'wb').write(b'FAKEVIDEO' + n.encode())
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8910'; env['PINGUINO_LIVE'] = '1'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body=None):
    rq = urllib.request.Request(B + p, data=json.dumps(body or {}).encode(), headers={'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def say(line): host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(0.3)
def play(slot):
    r = get('/api/intro/poll?slot=' + slot); return r.get('play')
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(10)   # the live check runs every 2 s in the sim; PINGUINO_LIVE=1 makes it live
    for s in ['t1', 't2', 't3', 't3v']: play(s)   # opens the four browser sources
    say('$1t1guy: hello'); say('$3t3guy: hi'); say('$2t2guy: hey'); say('$3t3other: yo'); say('$1t1guy: second message'); say('plainviewer: not a sub'); say('$1noclipper: hi')
    a = get('/api/intro')
    chk('5 intros queued once each (second message and the non-sub add nothing; noclipper uses the T1 default clip)', len(a['queue']) + (1 if a['current'] else 0) == 5)
    p = play('t3'); chk('the highest tier plays first (T3 on the t3 source)', p and p['user'].lower() == 't3guy')
    chk('other sources stay empty while one plays', play('t2') is None and play('t1') is None)
    get('/api/intro/done?id=%d' % p['id'])
    p2 = play('t3'); chk('next is the other T3 (FIFO within a tier)', p2 and p2['user'].lower() == 't3other')
    get('/api/intro/done?id=%d' % p2['id'])
    p3 = play('t2'); chk('then T2', p3 and p3['user'].lower() == 't2guy')
    post('/api/intro/skip')
    p4 = play('t1'); chk('after a skip the T1 plays', p4 and p4['user'].lower() in ('t1guy', 'noclipper'))
    get('/api/intro/done?id=%d' % p4['id'])
    p5 = play('t1'); chk('the second T1 (default clip) plays last', p5 and p5['user'].lower() in ('t1guy', 'noclipper'))
    get('/api/intro/done?id=%d' % p5['id'])
    chk('queue is empty at the end', get('/api/intro')['queue'] == [] and get('/api/intro')['current'] is None)
    say('$1t1guy: third message'); chk('same person is not replayed in the same stream', get('/api/intro')['queue'] == [])
    say('$3vert3: hi vertical'); pv = play('t3v'); chk('a vertical T3 clip goes to the t3v source', pv and pv['user'].lower() == 'vert3')
    get('/api/intro/done?id=%d' % pv['id'])
    r = post('/api/intro/test', {'login': 'giffy', 'tier': 2}); pg = play('t2'); chk('test button queues a name; a gif gets the short gif length', r['ok'] and pg and pg['maxSec'] == 6)
    get('/api/intro/done?id=%d' % pg['id'])
    r = post('/api/intro/test', {'login': 'nobody', 'tier': 3}); chk('test for a name with no clip says so', r['ok'] is False and 'no clip' in r['error'])
    post('/api/intro/test', {'login': 't3guy', 'tier': 3}); post('/api/intro/test', {'login': 't3guy', 'tier': 3})
    chk('a queued intro is not duplicated', len(get('/api/intro')['queue']) == 1)
    post('/api/intro/clear'); chk('clear empties the queue', get('/api/intro')['queue'] == [])
    post('/api/intro/reset'); say('$1t1guy: after reset'); chk('reset lets people play again', len(get('/api/intro')['queue']) == 1)
    post('/api/intro/clear')
    post('/api/intro/settings', {'T3': False}); say('$3someone: hi'); chk('a tier switched off queues nothing', get('/api/intro')['queue'] == [])
    post('/api/intro/settings', {'T3': True, 'Enabled': False}); say('$3t3other: hi again'); post('/api/intro/reset'); chk('intros switched off queue nothing', get('/api/intro')['queue'] == [])
    post('/api/intro/settings', {'Enabled': True})
    time.sleep(0.2)
    r = urllib.request.urlopen(B + '/intro/media/t3guy.mp4', timeout=10); chk('media route serves the clip', r.read().startswith(b'FAKEVIDEO') and r.headers['Content-Type'] == 'video/mp4')
    try: urllib.request.urlopen(B + '/intro/media/..%5Chost_secrets.json', timeout=10); bad = True
    except urllib.error.HTTPError as e: bad = False
    chk('media route refuses anything outside the clip folder', not bad)
    chk('overlay and controls pages are served', b'/api/intro/poll' in urllib.request.urlopen(B + '/overlay/intro?slot=t1', timeout=10).read() and b'Sub intros' in urllib.request.urlopen(B + '/intro', timeout=10).read())
    # a source that is not open: its intros are skipped, not stuck
    post('/api/intro/reset'); time.sleep(16); say('$3t3guy: hi'); get('/api/intro/poll?slot=t1')
    chk('an intro for a browser source that is not open is skipped (no blocking)', play('t1') is None and get('/api/intro')['current'] is None)
finally:
    host.kill()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
