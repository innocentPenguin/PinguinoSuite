"""Scene setgame fallback (sim Host, temp data): when live_state.json obs.twitchGame CHANGES, the Host calls Scenes SetGameAll so the layout tagged with the category is served;
a game chosen in Master View (setgame) is not re-asserted while the category stays the same; first sighting never overrides an existing choice.
Usage: python Tools/test-host-gamewatch.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8984; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pggw_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8983'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p): return urllib.request.urlopen(B + p, timeout=10).read().decode()
def post(p, o): return json.loads(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'}), timeout=10).read())
def lay(): return json.loads(get('/api/scene-layouts?profile=h'))
def state(g): json.dump({'obs': {'twitchGame': g}}, open(os.path.join(d, 'live_state.json'), 'w'))
def waitgame(g, secs=14):
    for _ in range(secs * 2):
        if lay().get('currentGame') == g: return True
        time.sleep(0.5)
    return False
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
try:
    for _ in range(120):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    state('Rocket League')
    base = lay()['name']
    post('/api/scene-layouts', {'action': 'settings', 'profile': 'h', 'autoSwitch': True})
    post('/api/scene-layouts', {'action': 'clonetogames', 'profile': 'h', 'from': base, 'games': ['Rocket League', 'Fortnite', 'Just Chatting']})
    chk('first sighting with no game set is applied', waitgame('Rocket League'), lay().get('currentGame'))
    r = lay(); chk('tagged layout served for the category', r.get('resolvedBy') == 'game' and r['game'] == 'Rocket League', (r.get('resolvedBy'), r.get('game')))
    chk('both profiles got it', json.loads(get('/api/scene-layouts?profile=v')).get('currentGame') == 'Rocket League')
    post('/api/scene-layouts', {'action': 'setgame', 'profile': '*', 'game': 'Fortnite'})
    time.sleep(12)
    chk('Master View choice is not overridden while the category is unchanged', lay().get('currentGame') == 'Fortnite', lay().get('currentGame'))
    state('Just Chatting')
    chk('a category change is applied', waitgame('Just Chatting'), lay().get('currentGame'))
    r = lay(); chk('and its layout is served', r.get('resolvedBy') == 'game' and r['game'] == 'Just Chatting', (r.get('resolvedBy'), r.get('game')))
    state('Some Unknown Game')
    chk('unknown game: set, active layout is the fallback', waitgame('Some Unknown Game') and lay().get('resolvedBy') == 'active')
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS gamewatch'); sys.exit(1 if fails else 0)
