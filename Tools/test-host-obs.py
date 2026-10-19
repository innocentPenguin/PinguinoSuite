"""End-to-end check of the OBS parts of the Streamer.bot replacement against the REAL OBS (reads the OBS settings from the live host_secrets.json, runs a separate Host on a temp folder):
latest popup, ban alert (quiet), and !clip's replay-buffer save. The replay buffer is only started/stopped here when you pass --start-replay (it saves one replay file and deletes it again).
Usage: python Tools/test-host-obs.py [path-to-PinguinoHost.dll] [--start-replay]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obs_probe import Obs
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dll = args[0] if args else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
live = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Data', 'runtime', 'host_secrets.json'), encoding='utf-8-sig'))
PORT = 8881; fails = []; notes = []
d = tempfile.mkdtemp(prefix='pgobs_')
json.dump({'OverlayPort': PORT, **{k: live[k] for k in ('ObsHost', 'ObsPort', 'ObsPassword') if k in live}}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
host = subprocess.Popen(['dotnet', dll, '--no-sync', '--data', d], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def api(path, body=None, t=60):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=t))
def until(fn, secs, what):
    t = time.time() + secs
    while time.time() < t:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.4)
    fails.append('timeout: ' + what); return False
def run(aid): return ' | '.join(api('/api/automations/test', {'id': aid, 'dry': False})['run']['output'])
o = Obs()
def enabled(scene, src):
    i = o.call('GetSceneItemId', {'sceneName': scene, 'sourceName': src})['responseData']['sceneItemId']
    return o.call('GetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': i})['responseData']['sceneItemEnabled']
orig_url = o.call('GetInputSettings', {'inputName': 'Ban Alert - Among Us Ejected'})['responseData']['inputSettings'].get('url')
orig_ban, orig_latest = enabled('Ban Alert', 'Ban Alert - Among Us Ejected'), enabled('Alerts', 'Latest Group')
try:
    until(lambda: api('/api/status')['obsConnected'], 60, 'Host connects to OBS')
    # 1. latest popup shows the group, then hides it again (only when it started hidden, so a live scene is never disturbed)
    if not orig_latest:
        res = {}; t = threading.Thread(target=lambda: res.setdefault('o', run('sb-latest-popup'))); t.start(); time.sleep(3)
        if not enabled('Alerts', 'Latest Group'): fails.append('Latest Group was not shown')
        t.join(); time.sleep(0.5)
        if enabled('Alerts', 'Latest Group'): fails.append('Latest Group was not hidden again')
        notes.append('latest popup: shown then hidden OK')
    else: notes.append('latest popup skipped: Latest Group is visible right now')
    # 2. ban alert, quiet copy (volume 0.02) so it does not blast the speakers; real URL set + show + hide
    doc = api('/api/automations')['doc']; ban = json.loads(json.dumps([a for a in doc['actions'] if a['id'] == 'sb-ban'][0]))
    ban['id'] = 'banq'; ban['name'] = 'BanQuiet'; ban['enabled'] = True; ban['triggers'] = [{'type': 'manual'}]
    for s in ban['steps']:
        if s['type'] == 'sound': s['volume'] = 0.02
    doc['actions'].append(ban); api('/api/automations', {'doc': doc})
    if not orig_ban:
        res = {}; t = threading.Thread(target=lambda: res.setdefault('o', run('banq'))); t.start(); time.sleep(2.5)
        url = o.call('GetInputSettings', {'inputName': 'Ban Alert - Among Us Ejected'})['responseData']['inputSettings'].get('url', '')
        if 'user=tester' not in url.lower(): fails.append('ban url not set with the name: ' + url)
        if not enabled('Ban Alert', 'Ban Alert - Among Us Ejected'): fails.append('ban alert was not shown')
        t.join(); time.sleep(0.5)
        if enabled('Ban Alert', 'Ban Alert - Among Us Ejected'): fails.append('ban alert was not hidden again')
        notes.append('ban alert: url set, shown, hidden OK')
    else: notes.append('ban alert skipped: it is visible right now')
    # 3. replay buffer
    rep = [i for i in api('/api/prestream')['items'] if i['id'] == 'replay']
    notes.append('prestream replay item: ' + (rep[0]['status'] + ' ' + rep[0].get('detail', '') if rep else 'missing'))
    doc = api('/api/automations')['doc']; doc['actions'].append({'id': 'clipt', 'name': 'ClipNoDelay', 'enabled': True, 'triggers': [{'type': 'manual'}], 'steps': [{'type': 'obs_replay_save'}]}); api('/api/automations', {'doc': doc})
    running = o.call('GetReplayBufferStatus')['responseData']['outputActive']
    if not running:
        out = run('clipt'); notes.append('replay buffer OFF -> ' + out)
        if 'NOT running' not in out: fails.append('should report the replay buffer is not running: ' + out)
        if '--start-replay' in sys.argv:
            r = o.call('StartReplayBuffer'); time.sleep(3)
            if not r['requestStatus']['result']: notes.append('could not start the replay buffer: ' + str(r['requestStatus']))
            else:
                out = run('clipt'); notes.append('replay buffer ON  -> ' + out)
                if 'replay saved' not in out: fails.append('replay not saved: ' + out)
                else:
                    path = out.split('replay saved: ')[-1].strip()
                    if os.path.exists(path): os.remove(path); notes.append('(test replay file deleted again)')
                o.call('StopReplayBuffer')
    else:
        out = run('clipt'); notes.append('replay buffer was ON -> ' + out)
        if 'replay saved' not in out: fails.append('replay not saved: ' + out)
finally:
    try:
        if orig_url: o.call('SetInputSettings', {'inputName': 'Ban Alert - Among Us Ejected', 'inputSettings': {'url': orig_url}})
    except Exception: pass
    o.close(); host.kill()
print('HOST OBS: ' + ('PASS' if not fails else 'FAIL'))
for n in notes: print('  . ' + n)
for f in fails: print('  - ' + f)
sys.exit(1 if fails else 0)
