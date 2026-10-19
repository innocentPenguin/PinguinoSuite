"""Streamer.bot replacement test for PinguinoHost (sim mode, temp folder): presets seeded disabled, new steps/triggers dry-run, First 5 game.
Usage: python Tools/test-host-sbreplace.py [path-to-PinguinoHost.dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8871; fails = []
d = tempfile.mkdtemp(prefix='pgsb_')
json.dump({'Channel': 'sbtest', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
def api(path, body=None):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
def feed(line): host.stdin.write(line + '\n'); host.stdin.flush()
def until(fn, secs, what):
    t = time.time() + secs
    while time.time() < t:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.3)
    fails.append('timeout: ' + what); return False
try:
    until(lambda: api('/api/status')['name'] == 'PinguinoHost', 30, 'host up')
    doc = api('/api/automations')['doc']; sb = [a for a in doc['actions'] if a['id'].startswith('sb-')]
    if len(sb) < 18: fails.append('expected 18 sb- presets, got %d' % len(sb))
    if any(a['enabled'] for a in doc['actions']): fails.append('a preset is enabled')
    types = {t['type'] for a in sb for t in a['triggers']}
    for need in ('ban', 'raid_out', 'follow', 'redeem', 'stream_online'):
        if need not in types: fails.append('trigger type missing in presets: ' + need)
    for a in sb:   # every preset dry-runs without an error (no network, no chat, no OBS)
        r = api('/api/automations/test', {'id': a['id'], 'dry': True})
        if not r.get('ok'): fails.append('dry run failed: %s %s' % (a['id'], r))
        outs = ' | '.join(r['run'].get('output', []))
        if 'unknown step' in outs: fails.append('unknown step in ' + a['id'] + ': ' + outs)
    r = api('/api/automations/test', {'id': 'sb-title-customs', 'dry': True})
    if 'CUSTYs' not in ' '.join(r['run']['output']): fails.append('title preset text missing')
    r = api('/api/automations/test', {'id': 'sb-preroll', 'dry': True})
    if '4:00' not in ' '.join(r['run']['output']): fails.append('ad preset did not expand {adIn}: ' + str(r['run']['output']))
    # save one of them enabled and make sure steps that need the streamer fail politely (not signed in) instead of crashing
    for a in doc['actions']:
        if a['id'] == 'sb-clip': a['enabled'] = True
        if a['id'] == 'sb-suggest': a['enabled'] = True
    api('/api/automations', {'doc': doc})
    r = api('/api/automations/test', {'id': 'sb-clip', 'dry': False})
    outs = ' | '.join(r['run'].get('output', []))
    if 'not signed in' not in outs and 'failed' not in outs: fails.append('clip without sign-in should fail politely: ' + outs)
    # suggestion box really appends to Data\files
    r = api('/api/automations/test', {'id': 'sb-suggest', 'dry': False, 'args': {'input': 'more cats', 'user': 'bob'}})
    f = os.path.join(d, 'files', 'suggestions.txt')
    if not os.path.exists(f) or 'more cats' not in open(f, encoding='utf-8').read(): fails.append('suggestions.txt not written')
    # First 5 game: stream online resets it, five different chatters claim the places, !first answers
    feed('event StreamOnline nobody')
    time.sleep(1.5)
    for i, n in enumerate(['ann', 'bob', 'cy', 'dee', 'eve', 'fay']): feed('%s: hello there %d' % (n, i)); time.sleep(0.4)
    feed('ann: !first'); time.sleep(1.0)
    g = json.load(open(os.path.join(d, 'host_globals.json')))
    stats = json.loads(g.get('firstPlaceStats', '{}')) if 'firstPlaceStats' in g else {}
    if stats.get('ann') != 1: fails.append('First 5: ann should have 1 first place, globals=' + str({k: v for k, v in g.items() if 'irst' in k})[:300])
    if str(g.get('firstChatterPlace')) != '0': fails.append('First 5: game should be locked after 5 claims, place=' + str(g.get('firstChatterPlace')))
finally:
    host.kill()
print('HOST STREAMER.BOT REPLACEMENT: ' + ('PASS' if not fails else 'FAIL'))
for f in fails: print('  - ' + f)
sys.exit(1 if fails else 0)
