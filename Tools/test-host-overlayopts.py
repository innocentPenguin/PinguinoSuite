"""Overlay fit options (sim Host, temp data): GET/POST /api/overlay-options, per-overlay + "*" merge, validation/clamping, null removes, ?js=1 form, file written, every overlay loads overlay-options.js.
Usage: python Tools/test-host-overlayopts.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8984; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgoo_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return urllib.request.urlopen(B + p, timeout=10).read().decode()
def post(p, o):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode() or '{}')
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
try:
    for _ in range(120):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    chk('nothing saved = empty options', json.loads(get('/api/overlay-options?name=queue'))['options'] == {})
    r = post('/api/overlay-options', {'name': '*', 'options': {'pad': 20}}); chk('set global', r.get('ok') and r['options']['pad'] == 20, r)
    r = post('/api/overlay-options', {'name': 'queue', 'options': {'scale': 1.2, 'anchor': 'TR', 'fit': True}}); chk('set per overlay (anchor lower-cased, fit 1)', r.get('ok') and r['options'] == {'pad': 20, 'scale': 1.2, 'anchor': 'tr', 'fit': 1}, r)
    chk('another overlay only gets the global one', json.loads(get('/api/overlay-options?name=players'))['options'] == {'pad': 20})
    r = post('/api/overlay-options', {'name': 'queue', 'options': {'scale': 99}}); chk('values are clamped', r['options']['scale'] == 4.0, r)
    chk('unknown key refused', post('/api/overlay-options', {'name': 'queue', 'options': {'evil': 1}}).get('ok') is False)
    chk('bad anchor refused', post('/api/overlay-options', {'name': 'queue', 'options': {'anchor': 'zz'}}).get('ok') is False)
    chk('name is required', post('/api/overlay-options', {'options': {'scale': 1}}).get('ok') is False)
    r = post('/api/overlay-options', {'name': 'queue', 'options': {'scale': None, 'fit': None}}); chk('null removes an option', r['options'] == {'pad': 20, 'anchor': 'tr'}, r)
    js = get('/api/overlay-options?name=queue&js=1'); chk('?js=1 is a script', js.startswith('window.OVERLAY_OPTIONS={') and js.endswith(';'), js[:50])
    fj = json.load(open(os.path.join(d, 'overlay_options.json'))); chk('saved to Data/runtime/overlay_options.json', fj['queue'] == {'anchor': 'tr'} and fj['*'] == {'pad': 20}, fj)
    r = post('/api/overlay-options', {'name': 'queue', 'options': None}); chk('options:null clears the overlay', 'anchor' not in r['options'], r)
    ov = os.path.join(suite, 'PinguinoB0t', 'overlays')
    for f in ('queue', 'players', 'players_vertical', 'wheel', 'subroll'):
        chk(f + '.html loads the shared script', 'overlay-options.js' in open(os.path.join(ov, f + '.html'), encoding='utf-8-sig').read())
    chk('shared script exists', os.path.exists(os.path.join(ov, 'overlay-options.js')))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS overlay options'); sys.exit(1 if fails else 0)
