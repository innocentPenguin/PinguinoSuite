"""POST /api/channel/update and /api/mod/timeout: token always required, refusals, audit log.  Usage: python Tools/test-host-channel.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8994; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgchan_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8997'; env['PINGUINO_MODULE_TOKEN'] = 'test-module-token'
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
fails = []
def post(path, body, tok=None):
    hd = {'Content-Type': 'application/json', 'Origin': B}
    if tok: hd['Authorization'] = 'Bearer ' + tok
    try: r = urllib.request.urlopen(urllib.request.Request(B + path, data=json.dumps(body).encode(), headers=hd), timeout=20); return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    c, _ = post('/api/channel/update', {'title': 'x'}); chk('no token -> 401 even same-origin', c == 401, c)
    c, _ = post('/api/mod/timeout', {'user': 'troll', 'seconds': 10}, 'wrong'); chk('wrong token -> 401', c == 401, c)
    c, j = post('/api/channel/update', {}, 'test-module-token'); chk('empty update refused', c == 200 and j['ok'] is False, j)
    c, j = post('/api/channel/update', {'title': 'hi'}, 'test-module-token'); chk('not signed in -> ok false + error', j['ok'] is False and 'signed in' in j.get('error', ''), j)
    c, j = post('/api/mod/timeout', {'user': 'nightbot', 'seconds': 10}, 'test-module-token'); chk('bot refused', j['ok'] is False and 'bot' in j['error'], j)
    c, j = post('/api/mod/timeout', {'user': 'innocentpenguin_', 'seconds': 10}, 'test-module-token'); chk('broadcaster refused', j['ok'] is False and 'broadcaster' in j['error'], j)
    c, j = post('/api/mod/timeout', {'user': 'bad name!', 'seconds': 10}, 'test-module-token'); chk('bad name refused', j['ok'] is False, j)
    c, j = post('/api/say', {'text': 'hi'}); chk('say: no token -> 401', c == 401, c)
    c, j = post('/api/say', {'text': ''}, 'test-module-token'); chk('say: empty refused', j['ok'] is False, j)
    c, j = post('/api/say', {'text': 'hello there'}, 'test-module-token'); chk('say: answers ok/duplicate/via', 'ok' in j and 'duplicate' in j and 'via' in j, j)
    log = os.path.join(d, 'runtime', 'mod_audit.log'); time.sleep(0.3)
    txt = open(log, encoding='utf-8').read() if os.path.exists(log) else ''
    chk('audit log has the calls', txt.count('\n') >= 5 and 'mod/timeout' in txt and 'channel/update' in txt, txt[:200])
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS channel/update + mod/timeout')
sys.exit(1 if fails else 0)
