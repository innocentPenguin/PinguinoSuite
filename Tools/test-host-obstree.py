"""Live OBS tree (Plan 6 part A) against Tools/mock-obs.py (no real OBS): scenes with prefix folders, items with live visibility, nested groups, scene switch and item toggle by id,
refusals (unknown scene/item, bad token when one is set), OBS offline -> connected:false, obs_folders.json overrides.  Usage: python Tools/test-host-obstree.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, OBS = 8991, 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgobst_'); os.makedirs(os.path.join(d, 'config'))
json.dump({'Channel': 'obstest', 'OverlayPort': PORT, 'ObsHost': '127.0.0.1', 'ObsPort': OBS, 'ObsPassword': 'pw-test'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8993'
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def up():
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); return
        except Exception: time.sleep(0.5)
def find(items, name):
    for i in items:
        if i['name'] == name: return i
        r = find(i.get('children') or [], name)
        if r: return r
mock = None; host = None
try:
    host = subprocess.Popen(['dotnet', dll, '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up(); time.sleep(1); t = api('/api/obs/tree'); chk('offline says so', t['connected'] is False and t['scenes'] == [], t)
    r = api('/api/obs/scene', {'scene': 'Starting'}); chk('offline scene refused', r['ok'] is False, r)
    mlog = open(os.path.join(d, 'mock.log'), 'wb')
    mock = subprocess.Popen([sys.executable, os.path.join(here, 'mock-obs.py'), str(OBS), 'pw-test'], stdout=mlog, stderr=subprocess.STDOUT)
    for _ in range(40):
        time.sleep(1)
        t = api('/api/obs/tree')
        if t['connected']: break
    chk('connects through the real auth handshake', t['connected'], t)
    names = [s['name'] for s in t['scenes']]; chk('scenes listed top-first', names[0] == 'Just Me' and names[-1] == 'Starting' and len(names) == 7, names)
    by = {s['name']: s for s in t['scenes']}
    chk('slash folder', by['Games / Rocket League']['folder'] == 'Games' and by['Games / Rocket League']['label'] == 'Rocket League', by['Games / Rocket League'])
    chk('bracket folder', by['[RL] Main']['folder'] == '[RL]' and by['[RL] Main']['label'] == 'Main', by['[RL] Main'])
    chk('dash folder only when 2+ share it', by['Chat - Talk']['folder'] == 'Chat' and by['Chat - Solo']['label'] == 'Solo', by['Chat - Talk'])
    chk('plain scene has no folder', by['Just Me']['folder'] == '' and by['Starting']['folder'] == '')
    chk('folders list', sorted(t['folders']) == ['Chat', 'Games', '[RL]'], t['folders'])
    chk('current scene flagged', t['current'] == 'Games / Rocket League' and by['Games / Rocket League']['current'] and not by['Starting']['current'])
    items = t['items']; chk('items of the live scene top-first', [i['name'] for i in items] == ['Game', 'Overlays', 'Camera'], [i['name'] for i in items])
    g = find(items, 'Overlays'); chk('group nested with children', g and g['group'] and [c['name'] for c in g['children']] == ['Chat', 'Alerts'], g)
    chk('live visibility', find(items, 'Game')['enabled'] is False and find(items, 'Camera')['enabled'] is True and find(items, 'Chat')['enabled'] is False)
    chk('item ids', find(items, 'Camera')['id'] == 1 and find(items, 'Alerts')['id'] == 11)
    t2 = api('/api/obs/tree?scene=Starting'); chk('other scene has no items in the mock', t2['scene'] == 'Starting' and t2['items'] == [], t2['items'])
    # actions
    r = api('/api/obs/item', {'scene': 'Games / Rocket League', 'itemId': 3, 'enabled': True}); chk('enable item', r.get('ok') and r['enabled'] is True, r)
    time.sleep(2.2); chk('visibility followed', find(api('/api/obs/tree')['items'], 'Game')['enabled'] is True)
    r = api('/api/obs/item', {'scene': 'Games / Rocket League', 'itemId': 1, 'toggle': True}); chk('toggle item', r.get('ok') and r['enabled'] is False, r)
    r = api('/api/obs/item', {'scene': 'Games / Rocket League', 'itemId': 12, 'toggle': True}); chk('group member toggled through its group', r.get('ok') and r['enabled'] is True, r)
    r = api('/api/obs/item', {'scene': 'Games / Rocket League', 'itemId': 999, 'enabled': True}); chk('unknown item refused', r['ok'] is False, r)
    r = api('/api/obs/item', {'scene': 'Nope', 'itemId': 1, 'enabled': True}); chk('unknown scene refused for items', r['ok'] is False, r)
    r = api('/api/obs/scene', {'scene': 'Nope'}); chk('unknown scene refused', r['ok'] is False, r)
    r = api('/api/obs/scene', {'scene': 'Starting'}); chk('switch scene', r.get('ok'), r); time.sleep(2.2); chk('current followed', api('/api/obs/tree')['current'] == 'Starting')
    # folder overrides
    json.dump({'scenes': {'Just Me': 'Solo stuff'}}, open(os.path.join(d, 'config', 'obs_folders.json'), 'w')); time.sleep(2.2)
    t = api('/api/obs/tree'); jm = [s for s in t['scenes'] if s['name'] == 'Just Me'][0]; chk('obs_folders.json override', jm['folder'] == 'Solo stuff' and 'Solo stuff' in t['folders'], jm)
    # shared file for the bot
    tp = os.path.join(d, 'runtime', 'obs_tree.json'); chk('tree file for the bot', os.path.exists(tp) and json.load(open(tp))['connected'] is True)
    log = open(os.path.join(d, 'runtime', 'mod_audit.log'), encoding='utf-8').read(); chk('actions audited', 'obs\tscene' in log and 'obs\titem' in log, log[-200:])
    # token required for actions when one is configured
    host.kill(); host.wait(); env2 = dict(env, PINGUINO_MODULE_TOKEN='tok')
    host = subprocess.Popen(['dotnet', dll, '--no-sync', '--data', d, '--suite', suite], env=env2, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); up()
    try:
        rq = urllib.request.Request(B + '/api/obs/scene', data=b'{"scene":"Starting"}', headers={'Content-Type': 'application/json'}); urllib.request.urlopen(rq, timeout=5); chk('no token refused', False)
    except urllib.error.HTTPError as e: chk('no token refused', e.code == 401, e.code)
finally:
    for pr in (host, mock):
        if pr: pr.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS obs tree')
sys.exit(1 if fails else 0)
