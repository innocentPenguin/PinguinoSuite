"""The pushup counter: !pushup / !pushups / !pu (everyone reads, mods change: add / remove / +N / -N / N / set / reset / on / off), persisted in Data/runtime/pushups.json across restarts,
GET /api/pushup -> {enabled,count}, POST /api/pushup {action,value}, the "pushup" widget is registered. Usage: python Tools/test-host-pushups.py [dll]"""
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
    chk('starts at 0, enabled', get('/api/pushup') == {'enabled': True, 'count': 0}, get('/api/pushup'))
    r = says(host, 'viewer1: !pushup'); chk('reading names the viewer', r == ['@viewer1 Pushups: 0'], r)
    r = says(host, 'viewer1: !pushups', 0.5); chk('a second read inside the cooldown is quiet', r == [], r)
    r = says(host, 'viewer2: !pu'); chk('!pu is an alias', r == ['@viewer2 Pushups: 0'], r)
    r = says(host, 'viewer1: !pushup 5'); chk('a viewer cannot change it', len(r) == 1 and 'mods' in r[0].lower() and get('/api/pushup')['count'] == 0, r)
    for line, want in [('*mod1: !pushup add', 1), ('*mod1: !pushup plus', 2), ('*mod1: !pushup +', 3), ('*mod1: !pushup up', 4), ('*mod1: !pushup inc', 5), ('*mod1: !pushup done', 6), ('*mod1: !pushup did', 7),
                       ('*mod1: !pushup +3', 10), ('*mod1: !pushup 5', 15), ('*mod1: !pushup add 5', 20), ('*mod1: !pushup done 5', 25)]:
        r = says(host, line, 0.5); chk(line, r == ['@mod1 Pushups: %d' % want], r)
    for line, want in [('*mod1: !pushup remove', 24), ('*mod1: !pushup minus', 23), ('*mod1: !pushup -', 22), ('*mod1: !pushup sub', 21), ('*mod1: !pushup down', 20), ('*mod1: !pushup dec', 19), ('*mod1: !pushup undo', 18),
                       ('*mod1: !pushup -3', 15), ('*mod1: !pushup minus 5', 10), ('*mod1: !pushup sub 4', 6)]:
        r = says(host, line, 0.5); chk(line, r == ['@mod1 Pushups: %d' % want], r)
    r = says(host, '*mod1: !pushup -100', 0.5); chk('never below 0', r == ['@mod1 Pushups: 0'], r)
    r = says(host, '*mod1: !pushups set 42', 0.5); chk('set N', r == ['@mod1 Pushups: 42'], r)
    r = says(host, '*mod1: !pushup set', 0.5); chk('set without a number is refused', len(r) == 1 and 'set <number>' in r[0] and get('/api/pushup')['count'] == 42, r)
    r = says(host, '*mod1: !pu bogus', 0.5); chk('unknown word shows the usage', len(r) == 1 and 'Mods:' in r[0] and get('/api/pushup')['count'] == 42, r)
    chk('count is persisted', json.load(open(pj, encoding='utf-8-sig')) == {'enabled': True, 'count': 42}, open(pj).read() if os.path.exists(pj) else 'no file')
    r = post('/api/pushup', {'action': 'add', 'value': 8}); chk('POST add', r.get('ok') and r.get('count') == 50, r)
    r = post('/api/pushup', {'action': 'remove'}); chk('POST remove defaults to 1', r.get('count') == 49, r)
    r = post('/api/pushup', {'action': 'set', 'value': 7}); chk('POST set', r.get('count') == 7, r)
    r = post('/api/pushup', {'action': 'nope'}); chk('POST unknown action is refused', r.get('ok') is False, r)
    r = says(host, '*mod1: !pushup off', 0.5); chk('off', len(r) == 1 and 'off' in r[0].lower() and get('/api/pushup') == {'enabled': False, 'count': 7}, r)
    r = says(host, 'viewer3: !pushup', 0.5); chk('viewers get nothing while it is off', r == [], r)
    host.kill(); host.wait(timeout=20); time.sleep(1)
    host = start(); waitup()
    chk('off + count survive a restart', get('/api/pushup') == {'enabled': False, 'count': 7}, get('/api/pushup'))
    r = says(host, '*mod1: !pushup on', 0.5); chk('on', len(r) == 1 and 'Pushups: 7' in r[0] and get('/api/pushup')['enabled'] is True, r)
    r = says(host, '*mod1: !pushup reset', 0.5); chk('reset', r == ['@mod1 Pushups: 0'], r)
    chk('the pushup widget is registered', any(w.get('id') == 'pushup' and w.get('src') == 'pushup.html' for w in (get('/api/scene-widgets').get('widgets') or [])) if True else False, 'scene-widgets')
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS pushups'); sys.exit(1 if fails else 0)
