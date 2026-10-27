"""For 100 (needs live-Host write permission). Run against the LIVE Host, stream must be OFFLINE, no chat is sent.
 1. End-activity: reads the start state, POST /api/customs/mod activity=end, checks customs widgets hidden, starts one activity, checks visible, ends again, checks hidden + queue closed.
 2. !leftbehind: if sb-leftbehind is missing from /api/automations, POSTs the doc with the action added (same as the leftbehind1 migration), then checks it exists + enabled.
Usage: python Tools/live-verify-activity-leftbehind.py [--base http://127.0.0.1:8770] [--skip-activity] [--skip-leftbehind]"""
import json, sys, time, urllib.request
base = 'http://127.0.0.1:8770'
if '--base' in sys.argv: base = sys.argv[sys.argv.index('--base') + 1]
def api(p, b=None):
    rq = urllib.request.Request(base + p, data=None if b is None else json.dumps(b).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=25))
res = []
def chk(n, ok, x=''):
    res.append((n, ok)); print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
KEYS = ('players', 'players_vertical', 'queue', 'customs')
def vis():
    l = api('/api/scene-layouts?profile=h'); v = {w['id']: w.get('visible') for w in l['layout']['widgets']}; return l.get('customsHidden'), {k: v.get(k) for k in KEYS}
if '--skip-activity' not in sys.argv:
    st = api('/api/customs/state'); print('start state: activity=%s open=%s queue=%d vis=%s' % (st.get('activity'), st.get('open'), len(st.get('queue', [])), vis()))
    r = api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'}); hid, v = vis()
    chk('end: activity none, queue closed', r['ok'] and r['customs']['activity'] == 'none' and not r['customs']['open'], r['customs'])
    chk('end: customs widgets players, players_vertical, queue, customs hidden', hid and not any(v.values()), (hid, v))
    r = api('/api/customs/mod', {'action': 'activity', 'value': 'rl competitive'}); time.sleep(1); hid, v = vis()
    chk('start: activity running, widgets visible again', r['ok'] and r['customs']['activity'] != 'none' and not hid and all(v.values()), (r['customs'].get('activity'), hid, v))
    r = api('/api/customs/mod', {'action': 'activity', 'value': 'rl end'}); time.sleep(1); hid, v = vis()
    chk('end again: none, queue closed and empty, widgets hidden', r['customs']['activity'] == 'none' and not r['customs']['open'] and not r['customs']['queue'] and hid and not any(v.values()), (r['customs'], hid, v))
if '--skip-leftbehind' not in sys.argv:
    doc = api('/api/automations')['doc']
    if not any(a['id'] == 'sb-leftbehind' for a in doc['actions']):
        doc['actions'].append({'id': 'sb-leftbehind', 'name': 'Command: !leftbehind', 'group': 'Streamer.bot replacement', 'enabled': True,
            'importNotes': 'the link of the channel we raided (https://twitch.tv/<target>), for anyone who was not taken along. Answers nothing before a raid / after the next stream starts.',
            'triggers': [{'type': 'command', 'names': ['!leftbehind'], 'cooldownSec': 3, 'userCooldownSec': 30}], 'conditions': [],
            'steps': [{'type': 'raid_target'}, {'type': 'if', 'left': '{raid.line}', 'op': 'notempty', 'right': '', 'then': [{'type': 'say', 'as': 'core', 'text': '{raid.line}'}], 'else': []}]})
        print('POST /api/automations:', api('/api/automations', {'doc': doc}))
    a = [x for x in api('/api/automations')['doc']['actions'] if x['id'] == 'sb-leftbehind']
    chk('sb-leftbehind exists once and is enabled', len(a) == 1 and a[0]['enabled'], a)
    cmds = json.dumps(api('/api/commands/all')); chk('!leftbehind listed in /api/commands/all', '!leftbehind' in cmds)
bad = [n for n, ok in res if not ok]; print('FAILS: %d' % len(bad)); sys.exit(1 if bad else 0)
