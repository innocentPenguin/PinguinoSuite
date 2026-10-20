"""Overlay folder API (Plan 6 part C): list/read/write/rename/delete-to-trash confined to the overlay root; traversal, extension, size, protected-name and token guards; backups and audit log.
Usage: python Tools/test-host-overlays.py [dll]"""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8994; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgovl_'); ov = os.path.join(d, 'myoverlays'); os.makedirs(os.path.join(ov, 'alerts'))
open(os.path.join(ov, 'queue.html'), 'w').write('<h1>queue</h1>'); open(os.path.join(ov, 'alerts', 'follow.html'), 'w').write('<p>follow</p>')
open(os.path.join(ov, 'notes.exe'), 'w').write('x'); open(os.path.join(ov, 'secrets.json'), 'w').write('{"k":1}'); open(os.path.join(d, 'outside.html'), 'w').write('outside')
json.dump({'OverlayDir': ov}, open(os.path.join(d, 'settings.json'), 'w'))
json.dump({'Channel': 'ovltest', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8995'
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def post(path, body, hdr=None):
    h = {'Content-Type': 'application/json', 'Origin': B}; h.update(hdr or {})
    return json.load(urllib.request.urlopen(urllib.request.Request(B + path, data=json.dumps(body).encode(), headers=h), timeout=10))
def get(path): return json.load(urllib.request.urlopen(B + path, timeout=10))
def trash():
    t = os.path.join(d, 'runtime', 'overlay_trash'); return [os.path.join(r, f) for r, _, fs in os.walk(t) for f in fs] if os.path.isdir(t) else []
def up():
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); return
        except Exception: time.sleep(0.5)
host = None
try:
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); up(); time.sleep(1)
    l = get('/api/overlays'); paths = [f['path'] for f in l['files']]
    chk('lists the allowed files', paths == ['alerts/follow.html', 'queue.html'], paths)
    chk('protected and disallowed files are hidden', 'notes.exe' not in paths and 'secrets.json' not in paths)
    r = get('/api/overlays/file?path=queue.html'); chk('read', r['ok'] and r['text'] == '<h1>queue</h1>', r)
    r = get('/api/overlays/file?path=alerts%2Ffollow.html'); chk('read in a subfolder', r['ok'] and r['text'] == '<p>follow</p>', r)
    for bad in ['../outside.html', '..\\outside.html', '/etc/passwd', 'C:\\Windows\\win.ini', 'alerts/../../outside.html', 'a/./b.html', 'overlay_trash/x.html', '.git/config', 'notes.exe', 'secrets.json', 'settings.json', 'x/secret_key.json', '', 'a//b.html', 'name.html.', 'bad|name.html']:
        r = get('/api/overlays/file?path=' + urllib.request.quote(bad)); chk('read refuses ' + repr(bad), r['ok'] is False, r)
        r = post('/api/overlays/write', {'path': bad, 'text': 'x'}); chk('write refuses ' + repr(bad), r['ok'] is False, r)
    chk('nothing escaped', open(os.path.join(d, 'outside.html')).read() == 'outside' and not os.path.exists(os.path.join(d, 'x')))
    r = post('/api/overlays/write', {'path': 'goal/goal.html', 'text': '<b>goal</b>'}); chk('new file in a new folder', r['ok'] and r['created'], r); chk('written', open(os.path.join(ov, 'goal', 'goal.html')).read() == '<b>goal</b>')
    chk('new file leaves no backup', trash() == [])
    r = post('/api/overlays/write', {'path': 'queue.html', 'text': '<h1>queue v2</h1>'}); chk('replace', r['ok'] and not r['created'], r)
    tr = trash(); chk('old copy is in the trash', len(tr) == 1 and open(tr[0]).read() == '<h1>queue</h1>', tr)
    chk('the overlay server serves the new file', urllib.request.urlopen(B + '/queue.html', timeout=5).read() == b'<h1>queue v2</h1>')
    r = post('/api/overlays/write', {'path': 'bad.json', 'text': '{oops'}); chk('invalid json refused', r['ok'] is False, r)
    r = post('/api/overlays/write', {'path': 'big.html', 'text': 'x' * (2 * 1024 * 1024 + 1)}); chk('text size cap', r['ok'] is False, r)
    r = post('/api/overlays/write', {'path': 'tool.exe', 'text': 'x'}); chk('exe refused', r['ok'] is False, r)
    r = post('/api/overlays/write', {'path': 'logo.png', 'base64': base64.b64encode(b'\x89PNG....').decode()}); chk('binary write', r['ok'] and open(os.path.join(ov, 'logo.png'), 'rb').read() == b'\x89PNG....', r)
    r = post('/api/overlays/write', {'path': 'logo2.png', 'base64': '!!!notbase64'}); chk('bad base64 refused', r['ok'] is False, r)
    r = get('/api/overlays/file?path=logo.png'); chk('binary read gives size only', r['ok'] and r['binary'] and 'text' not in r, r)
    r = post('/api/overlays/rename', {'from': 'goal/goal.html', 'to': 'goal/goal2.html'}); chk('rename', r['ok'] and os.path.exists(os.path.join(ov, 'goal', 'goal2.html')), r)
    r = post('/api/overlays/rename', {'from': 'goal/goal2.html', 'to': 'queue.html'}); chk('rename never overwrites', r['ok'] is False, r)
    r = post('/api/overlays/rename', {'from': 'goal/goal2.html', 'to': 'goal/goal2.css'}); chk('rename keeps the type', r['ok'] is False, r)
    r = post('/api/overlays/rename', {'from': 'goal/goal2.html', 'to': '../goal.html'}); chk('rename refuses traversal', r['ok'] is False, r)
    r = post('/api/overlays/delete', {'path': 'goal/goal2.html'}); chk('delete', r['ok'] and not os.path.exists(os.path.join(ov, 'goal', 'goal2.html')), r)
    chk('deleted file is recoverable', any(open(f).read() == '<b>goal</b>' for f in trash() if f.endswith('goal2.html')), trash())
    r = post('/api/overlays/delete', {'path': 'nope.html'}); chk('delete missing', r['ok'] is False, r)
    r = post('/api/overlays/delete', {'path': '../outside.html'}); chk('delete refuses traversal', r['ok'] is False and os.path.exists(os.path.join(d, 'outside.html')), r)
    log = open(os.path.join(d, 'runtime', 'mod_audit.log'), encoding='utf-8').read(); chk('every change audited', all(k in log for k in ('overlay/write', 'overlay/rename', 'overlay/delete')), log[-300:])
    host.kill(); host.wait(); env2 = dict(env, PINGUINO_MODULE_TOKEN='tok')
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env2, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); up()
    try: urllib.request.urlopen(urllib.request.Request(B + '/api/overlays/write', data=b'{"path":"t.html","text":"x"}', headers={'Content-Type': 'application/json'}), timeout=5); chk('no token refused', False)
    except urllib.error.HTTPError as e: chk('no token refused', e.code == 401, e.code)
    r = post('/api/overlays/write', {'path': 't.html', 'text': 'x'}, {'Origin': '', 'Authorization': 'Bearer tok'}); chk('token accepted', r['ok'], r)
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS overlay files')
sys.exit(1 if fails else 0)
