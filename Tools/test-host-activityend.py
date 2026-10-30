"""Ending an activity from Master View (POST /api/customs/mod {action:activity,value:'rl end'}): the activity is none, the queue is closed and empty, the match is cleared, and the customs overlays
(players, queue, customs HUD parts) are served hidden by /api/scene-layouts - and shown again by the next activity start (visibility only, the saved layout is untouched). Also for an end typed in chat.
Usage: python Tools/test-host-activityend.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8981; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgae_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8982', 'PINGUINO_DUP_SECONDS': '0'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
res = []
def chk(n, ok, x=''):
    res.append((n, ok))
    if not ok: print('  FAIL', n, x)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=20))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def lay(profile='h'): return api('/api/scene-layouts?profile=' + profile)
def vis(l): return {w['id']: w.get('visible') for w in l['layout']['widgets']}
PAGES = ('players.html', 'players_vertical.html', 'queue.html', 'customs.html', 'pm.html')   # pm.html is in the group too (it also hides itself while no private match is active)
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
    l0 = lay(); v0 = vis(l0)
    chk('before any activity the layout is untouched (players + queue on)', not l0.get('customsHidden') and v0['players'] and v0['queue'], v0)
    r = api('/api/customs/mod', {'action': 'activity', 'value': 'rl competitive'})
    chk('start: ok, activity competitive, queue open', r['ok'] and r['customs']['activity'] == 'competitive' and r['customs']['open'], r)
    feed('alice: !register AliceEpic'); feed('alice: !join'); feed('bob: !register BobEpic'); feed('bob: !join')
    st = api('/api/customs/state'); chk('two players in the queue', len(st['queue']) >= 2, st['queue'])
    chk('running: overlays shown', vis(lay())['players'] and vis(lay())['queue'] and not lay().get('customsHidden'))
    r = api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'}); st = r['customs']
    chk('end: activity none, queue closed and empty, match cleared', r['ok'] and st['activity'] == 'none' and not st['open'] and len(st['queue']) == 0 and not (st.get('match') and st['match'].get('players')), st)
    l1 = lay(); v1 = vis(l1); reg = {w['id']: w['src'] for w in l1['registry']}
    GROUP = [i for i, src in reg.items() if src.split('?')[0] in PAGES]
    chk('every registry widget on a customs page is in the hidden group (players/queue/customs incl. all ?part= parts)', len(GROUP) >= 10 and all(i in GROUP for i in ('players_teams', 'players_header', 'queue_list', 'queue_idle', 'customs_status', 'customs_info')), GROUP)
    chk('the wheel is not in it (a tournament runs after customs ended)', not any(i.startswith('wheel') for i in GROUP))
    chk('end: customs overlays served hidden at once', l1.get('customsHidden') is True and all(v1.get(i) is False for i in GROUP), v1)
    chk('end: other widgets keep their state', all(v1[k] == v0[k] for k in v0 if k not in GROUP), (v0, v1))
    chk('end: the saved layout is untouched (names, widget count)', [w['id'] for w in l1['layout']['widgets']] == [w['id'] for w in l0['layout']['widgets']] and lay('v').get('customsHidden') is True)
    api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'})   # a second End when already none is harmless
    chk('second end: still none and hidden', api('/api/customs/state')['activity'] == 'none' and lay().get('customsHidden') is True)
    api('/api/customs/mod', {'action': 'activity', 'value': 'rl casual'})
    l2 = lay(); v2 = vis(l2)
    chk('start again: overlays shown again as before', l2.get('customsHidden') is False and v2 == v0, v2)
    feed('#trial: !activity end', 3)   # chat path, no Master View involved: the next layout read sees the change
    l3 = lay()
    chk('end typed in chat: hidden on the next read', api('/api/customs/state')['activity'] == 'none' and l3.get('customsHidden') is True and vis(l3)['players'] is False, vis(l3))
    feed('#trial: !activity koth', 3)
    chk('chat start shows them again', lay().get('customsHidden') is False and vis(lay())['players'] is True)
    # a queue opened with !queue open (no activity chosen) is customs too: End hides the overlays whichever way it started
    feed('#trial: !activity end', 3); feed('#trial: !queue open', 3)
    chk('queue opened without an activity: overlays shown', lay().get('customsHidden') is False and vis(lay())['players'] is True and api('/api/customs/state')['open'], lay().get('customsHidden'))
    api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'})
    chk('End after !queue open: hidden', api('/api/customs/state')['open'] is False and lay().get('customsHidden') is True and vis(lay())['players'] is False, vis(lay()))
    # no layout read between the start and the End (the OBS overlay is not polling yet): End alone must set the flag, checked in the saved file
    feed('#trial: !queue open', 2); feed('yt1: !register YtOne', 1); feed('yt1: !join', 1)
    api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'}); time.sleep(1)
    sv = json.load(open(os.path.join(d, 'scene_layouts.json')))
    chk('End without any layout read: customsHidden is set in the saved file', sv.get('customsHidden') is True and api('/api/customs/state')['open'] is False, sv.get('customsHidden'))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
