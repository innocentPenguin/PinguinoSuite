"""Overlay scenes (sim Host, temp data): GET/POST /api/scene-layouts + /api/scene-widgets: default layouts per profile (h 1920x1080, v 1080x1920), save/activate/duplicate/rename/delete, validation + clamping, params/style sanitising, custom widgets, ?js=1, file saved.
Usage: python Tools/test-host-scenes.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8986; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgsc_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8985'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return urllib.request.urlopen(B + p, timeout=10).read().decode()
def post(p, o):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode() or '{}')
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def wid(r, i): return [w for w in r['layout']['widgets'] if w['id'] == i][0]
try:
    for _ in range(120):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    reg = json.loads(get('/api/scene-widgets'))
    ids = [w['id'] for w in reg['widgets']]
    chk('registry lists every overlay + alerts', {'queue', 'players', 'players_vertical', 'subroll', 'wheel', 'alerts'} <= set(ids), ids)
    hud = ['goal', 'latest', 'subfooter', 'chat', 'customs', 'nowplaying']
    chk('HUD widgets registered and available', set(hud) <= set(ids) and all(w['available'] for w in reg['widgets'] if w['id'] in hud), [(w['id'], w['available']) for w in reg['widgets']])
    chk('registry says which pages exist on disk (queue yes)', [w['available'] for w in reg['widgets'] if w['id'] == 'queue'] == [True], reg)
    h1 = json.loads(get('/api/scene-layouts?profile=h')); v1 = json.loads(get('/api/scene-layouts?profile=v'))
    chk('h default is 1920x1080 and v 1080x1920', (h1['width'], h1['height'], v1['width'], v1['height']) == (1920, 1080, 1080, 1920), (h1['width'], v1['width']))
    chk('default layout exists and is active', h1['active'] == 'default' and h1['names'] == ['default'], h1['names'])
    chk('h shows players, hides players_vertical; v the opposite', wid(h1, 'players')['visible'] and not wid(h1, 'players_vertical')['visible'] and wid(v1, 'players_vertical')['visible'] and not wid(v1, 'players')['visible'])
    al = wid(h1, 'alerts'); chk('alerts: Multi page on 8766, z 100, available', al['z'] == 100 and [w for w in reg['widgets'] if w['id'] == 'alerts'][0]['src'].startswith('http://127.0.0.1:8766/') and [w for w in reg['widgets'] if w['id'] == 'alerts'][0]['available'], al)
    chk('every widget is in the layout', len(h1['layout']['widgets']) == len(ids))
    chk('bad profile refused', json.loads(get('/api/scene-layouts?profile=x')).get('ok') is False)
    # save: validation, clamping, sanitising
    lay = {'widgets': [{'id': 'queue', 'x': 99999, 'y': -5, 'w': 5, 'h': 300, 'scale': 50, 'z': 500, 'opacity': 7, 'visible': True, 'params': {'layout': 'sprinkled', 'bad key!': 'a<script>b'}, 'style': {'radius': 9999, 'rotate': 45, 'bg': 'red;}</style>', 'shadow': 'true', 'evil': 1}},
                          {'id': 'nonsense'}, {'id': 'queue'}, {'id': 'custom-x', 'src': '../secret.html'}, {'id': 'custom-ok', 'src': 'mything.html', 'x': 10}]}
    r = post('/api/scene-layouts', {'action': 'save', 'profile': 'h', 'name': 'Race Day', 'layout': lay, 'activate': True})
    chk('save ok and active', r.get('ok') and r['active'] == 'Race Day' and r['name'] == 'Race Day', r)
    q = wid(r, 'queue')
    chk('numbers clamped', q['x'] == 8000 and q['y'] == -5 and q['w'] == 20 and q['scale'] == 8 and q['z'] == 99 and q['opacity'] == 1, q)
    chk('params sanitised (no tag chars), style clamped, unknown style key dropped', q['params'].get('layout') == 'sprinkled' and all('<' not in v for v in q['params'].values()) and q['style']['radius'] == 400 and q['style']['rotate'] == 45 and q['style']['shadow'] is True and 'evil' not in q['style'] and ';' not in q['style']['bg'] and '<' not in q['style']['bg'], q)
    got = [w['id'] for w in r['layout']['widgets']]
    chk('unknown / duplicate / path-escaping widgets dropped, custom accepted', got.count('queue') == 1 and 'nonsense' not in got and 'custom-x' not in got and wid(r, 'custom-ok')['src'] == 'mything.html', got)
    chk('z is capped at 99 for others, alerts stay pinned at 100', q['z'] == 99 and wid(r, 'alerts')['z'] == 100, (q['z'], wid(r, 'alerts')['z']))
    chk('missing registry widgets are filled with defaults', {'players', 'wheel', 'alerts'} <= set(got))
    chk('the layout is served as active', json.loads(get('/api/scene-layouts?profile=h'))['name'] == 'Race Day')
    js = get('/api/scene-layouts?profile=h&js=1'); chk('?js=1 is a script', js.startswith('window.SCENE_LAYOUT={') and js.endswith(';'), js[:40])
    chk('?layout=default gets the other layout without activating it', json.loads(get('/api/scene-layouts?profile=h&layout=default'))['name'] == 'default' and json.loads(get('/api/scene-layouts?profile=h'))['active'] == 'Race Day')
    # duplicate / rename / activate / delete
    r = post('/api/scene-layouts', {'action': 'duplicate', 'profile': 'h', 'from': 'Race Day', 'name': 'Copy'}); chk('duplicate', r.get('ok') and 'Copy' in r['names'], r)
    chk('duplicate onto a used name refused', post('/api/scene-layouts', {'action': 'duplicate', 'profile': 'h', 'from': 'Race Day', 'name': 'Copy'}).get('ok') is False)
    r = post('/api/scene-layouts', {'action': 'rename', 'profile': 'h', 'name': 'Copy', 'to': 'Calm'}); chk('rename', r.get('ok') and 'Calm' in r['names'] and 'Copy' not in r['names'], r)
    r = post('/api/scene-layouts', {'action': 'activate', 'profile': 'h', 'name': 'Calm'}); chk('activate', r.get('ok') and r['active'] == 'Calm', r)
    chk('activate unknown refused', post('/api/scene-layouts', {'action': 'activate', 'profile': 'h', 'name': 'nope'}).get('ok') is False)
    r = post('/api/scene-layouts', {'action': 'delete', 'profile': 'h', 'name': 'Calm'}); chk('deleting the active layout moves active to another', r.get('ok') and r['active'] != 'Calm' and 'Calm' not in r['names'], r)
    for n in list(r['names'])[:-1]: post('/api/scene-layouts', {'action': 'delete', 'profile': 'h', 'name': n})
    last = json.loads(get('/api/scene-layouts?profile=h'))['names']
    chk('the last layout cannot be deleted', post('/api/scene-layouts', {'action': 'delete', 'profile': 'h', 'name': last[0]}).get('ok') is False and len(last) == 1, last)
    # per-game layouts
    first = json.loads(get('/api/scene-layouts?profile=h'))['names'][0]
    r = post('/api/scene-layouts', {'action': 'clonetogames', 'profile': 'h', 'from': first, 'games': ['Rocket League', 'Fortnite', 'Rocket League']})
    chk('clone to games makes tagged copies (no duplicates)', r.get('ok') and r['tags'].get(first + ' - Rocket League') == 'Rocket League' and r['tags'].get(first + ' - Fortnite') == 'Fortnite' and len(r['names']) == 3, r)
    chk('without autoSwitch the active layout is served', json.loads(get('/api/scene-layouts?profile=h'))['resolvedBy'] == 'active')
    r = post('/api/scene-layouts', {'action': 'settings', 'profile': 'h', 'autoSwitch': True, 'game': 'rocket league'})
    g1 = json.loads(get('/api/scene-layouts?profile=h'))
    chk('autoSwitch serves the layout tagged with the current game (case-insensitive)', r.get('autoSwitch') is True and g1['resolvedBy'] == 'game' and g1['name'] == first + ' - Rocket League' and g1['game'] == 'Rocket League', g1['name'])
    chk('setgame for both profiles', post('/api/scene-layouts', {'action': 'setgame', 'profile': '*', 'game': 'Fortnite'}).get('ok') and json.loads(get('/api/scene-layouts?profile=h'))['name'] == first + ' - Fortnite' and json.loads(get('/api/scene-layouts?profile=v'))['currentGame'] == 'Fortnite')
    chk('a game without a layout falls back to active', post('/api/scene-layouts', {'action': 'setgame', 'profile': '*', 'game': 'Minecraft'}).get('ok') and json.loads(get('/api/scene-layouts?profile=h'))['resolvedBy'] == 'active')
    chk('explicit ?layout= still wins', json.loads(get('/api/scene-layouts?profile=h&layout=' + (first + ' - Fortnite').replace(' ', '%20')))['resolvedBy'] == 'layout')
    r = post('/api/scene-layouts', {'action': 'tag', 'profile': 'h', 'name': first, 'game': 'Just Chatting'}); chk('tag a layout', r['tags'][first] == 'Just Chatting' and 'Just Chatting' in r['games'], r)
    chk('HUD widgets are off by default (both profiles)', all(not wid(h1, i)['visible'] and not wid(v1, i)['visible'] for i in hud))
    chk('wheel keeps takeover, others do not', wid(h1, 'wheel')['takeover'] is True and wid(h1, 'chat')['takeover'] is False)
    chk('chat.html and customs.html exist with the options tag', all(os.path.exists(os.path.join(suite, 'PinguinoB0t', 'overlays', n)) and 'overlay-options.js' in open(os.path.join(suite, 'PinguinoB0t', 'overlays', n), encoding='utf-8').read() for n in ('chat.html', 'customs.html')))
    chk('alerts are off by default (they stay a standalone source)', not wid(h1, 'alerts')['visible'])
    chk('profiles are independent (v untouched)', json.loads(get('/api/scene-layouts?profile=v'))['names'] == ['default'])
    chk('unknown action refused', post('/api/scene-layouts', {'action': 'zap', 'profile': 'h'}).get('ok') is False)
    fj = json.load(open(os.path.join(d, 'scene_layouts.json'))); chk('saved to Data/runtime/scene_layouts.json', 'h' in fj['profiles'], list(fj.get('profiles', {})))
    ov = os.path.join(suite, 'PinguinoB0t', 'overlays')
    chk('scene.html exists and is not flagged by the overlay-options health check', os.path.exists(os.path.join(ov, 'scene.html')) and 'scene' not in json.loads(get('/api/overlay-options/health'))['missing'])
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS scenes'); sys.exit(1 if fails else 0)
