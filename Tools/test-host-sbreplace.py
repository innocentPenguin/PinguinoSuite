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
    until(lambda: len(api('/api/automations')['doc']['actions']) >= 29, 30, 'presets seeded')
    doc = api('/api/automations')['doc']; sb = [a for a in doc['actions'] if a['id'].startswith('sb-')]
    if len(sb) < 21: fails.append('expected 21 sb- presets, got %d' % len(sb))
    safe_on = {'sb-latest-popup', 'sb-shout', 'sb-latest-cmd', 'sb-session-cmd', 'sb-goal-cmd'}
    dups = {'sb-follow', 'sb-sub', 'sb-resub', 'sb-gift', 'sb-cheer', 'sb-raid', 'sb-ban', 'sb-clip', 'sb-preroll', 'sb-whyad'}
    if {a['id'] for a in sb if a['enabled']} != safe_on: fails.append('before cutover only the non-duplicating presets may be ON: ' + str(sorted({a['id'] for a in sb if a['enabled']} ^ safe_on)))
    if {a['id'] for a in sb if a.get('cutover')} != dups: fails.append('cutover flags wrong')
    cs = api('/api/cutover')
    if cs['on'] or len(cs['actions']) != len(dups): fails.append('cutover state: ' + str(cs))
    # First 5 must stay silent before the cutover (Streamer.bot would pay twice)
    feed('event StreamOnline nobody'); time.sleep(1.0)
    feed('zed: hello'); time.sleep(0.5)
    try: g0 = json.load(open(os.path.join(d, 'host_globals.json')))
    except Exception: g0 = {}
    if g0.get('firstChatterClaimedUserIds', '[]') not in ('[]', ''): fails.append('First 5 claimed a chatter before the cutover: ' + str(g0.get('firstChatterClaimedUserIds')))
    r = api('/api/cutover', {'on': True})
    if not r['ok'] or r['changed'] != len(dups): fails.append('cutover on: ' + str(r))
    doc = api('/api/automations')['doc']; sb = [a for a in doc['actions'] if a['id'].startswith('sb-')]
    want_on = safe_on | dups
    if {a['id'] for a in sb if a['enabled']} != want_on: fails.append('after cutover wrong presets ON: ' + str(sorted({a['id'] for a in sb if a['enabled']} ^ want_on)))
    types = {t['type'] for a in sb for t in a['triggers']}
    for need in ('ban', 'raid_out', 'follow', 'redeem', 'stream_online'):
        if need not in types: fails.append('trigger type missing in presets: ' + need)
    for a in sb:   # every preset dry-runs without an error (no network, no chat, no OBS)
        r = api('/api/automations/test', {'id': a['id'], 'dry': True})
        if not r.get('ok'): fails.append('dry run failed: %s %s' % (a['id'], r))
        outs = ' | '.join(r['run'].get('output', []))
        if 'unknown step' in outs: fails.append('unknown step in ' + a['id'] + ': ' + outs)
    r = api('/api/automations/test', {'id': 'sb-preroll', 'dry': True})
    if 'run' not in r: fails.append('sb-preroll dry run: ' + str(r)); raise SystemExit(print('FAIL', fails))
    if '4:00' not in ' '.join(r['run']['output']): fails.append('ad preset did not expand {adIn}: ' + str(r['run']['output']))
    # steps that need the streamer / OBS fail politely (not signed in, OBS offline) instead of crashing
    for a in doc['actions']:
        if a['id'] == 'sb-suggest': a['enabled'] = True
    doc['actions'].append({'id': 'clipt', 'name': 'ClipNoDelay', 'enabled': True, 'triggers': [{'type': 'manual'}], 'steps': [{'type': 'create_clip', 'title': 'Clip! cmd', 'duration': 60}, {'type': 'obs_replay_save'}]})
    api('/api/automations', {'doc': doc})
    r = api('/api/automations/test', {'id': 'clipt', 'dry': False})
    outs = ' | '.join(r['run'].get('output', []))
    if 'Twitch clip failed' not in outs or 'NOT saved' not in outs and 'NOT running' not in outs: fails.append('clip without sign-in/OBS should fail politely: ' + outs)
    r = api('/api/automations/test', {'id': 'sb-preroll', 'dry': False}); outs = ' | '.join(r['run'].get('output', []))
    if 'ad_schedule failed' not in outs: fails.append('preroll without sign-in should fail politely: ' + outs)
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
    if not [i for i in api('/api/activity?since=0&type=first5')['items']]: fails.append('first5 not in the activity feed')
    if str(g.get('firstChatterPlace')) != '0': fails.append('First 5: game should be locked after 5 claims, place=' + str(g.get('firstChatterPlace')))
    feed('*mod: !pg status'); feed('*mod: !pg helper off'); time.sleep(0.8)
    b = {x['id']: x for x in api('/api/bots')['bots']}
    if b['helper']['enabled']: fails.append('!pg helper off did not switch the helper off')
    feed('*mod: !pg helper on'); time.sleep(0.8)
    if not {x['id']: x for x in api('/api/bots')['bots']}['helper']['enabled']: fails.append('!pg helper on did not switch it back')
    # activity feed + latest + shoutout queue
    for ln in ('event TwitchFollow ann', 'event TwitchSub bob 2', 'event TwitchCheer cy 300', 'event TwitchRaid dee 40', 'event TwitchRedeem eve 1'): feed(ln); time.sleep(0.3)
    until(lambda: len(api('/api/activity?since=0')['items']) >= 4, 10, 'activity items')
    act = api('/api/activity?since=0')
    types = [i['type'] for i in act['items'] if i['type'] != 'first5']
    if types[:4] != ['follow', 'sub', 'cheer', 'raid']: fails.append('activity order/types wrong: ' + str(types))
    if [i['seq'] for i in act['items']] != sorted(i['seq'] for i in act['items']): fails.append('activity seq not increasing')
    if any(i.get('amount') for i in act['items'] if i['type'] == 'cheer') is False: fails.append('cheer amount missing')
    ch = [i for i in act['items'] if i['type'] == 'cheer']
    if not ch or ch[0].get('amount') != 300: fails.append('cheer amount wrong: ' + str(ch))
    if api('/api/activity?since=%d' % act['seq'])['items']: fails.append('since=latest should be empty')
    if len(api('/api/activity?since=0&type=sub')['items']) != 1: fails.append('type filter')
    lat = api('/api/latest')
    if [e['kind'] for e in lat['latest'] if e['kind'] == 'follow'] != ['follow']: fails.append('latest feed')
    html = urllib.request.urlopen('http://127.0.0.1:%d/overlay/latest' % PORT, timeout=10).read().decode()
    if 'api/latest' not in html: fails.append('overlay page')
    feed('ann: !latest'); time.sleep(1.0)
    if 'Latest' not in ' '.join(o for r in api('/api/automations/log?n=100')['runs'] for o in r.get('output', []) if 'latest:' in o): fails.append('!latest produced no line')
    r1 = api('/api/shoutouts', {'user': 'someone', 'by': 'mod'}); r2 = api('/api/shoutouts', {'user': 'someone', 'by': 'mod'})
    if r1['result'] != 'queued' or r2['result'] != 'duplicate': fails.append('shoutout dedupe: %s %s' % (r1, r2))
    time.sleep(2.0)
    if api('/api/shoutouts')['pending']: fails.append('shoutout queue did not drain')
finally:
    host.kill()
print('HOST STREAMER.BOT REPLACEMENT: ' + ('PASS' if not fails else 'FAIL'))
for f in fails: print('  - ' + f)
sys.exit(1 if fails else 0)
