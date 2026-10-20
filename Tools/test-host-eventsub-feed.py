"""EventSub gift / raid out / poll / prediction / hype train items in /api/activity.  Usage: python Tools/test-host-eventsub-feed.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8995; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgesub_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8998'
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
fails = []
def send(l): h.stdin.write((l + '\n').encode()); h.stdin.flush(); time.sleep(0.5)
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    send('eventsub channel.subscription.gift ' + json.dumps({'user_login': 'gifty', 'tier': '1000', 'total': 5, 'cumulative_total': 42, 'is_anonymous': False}))
    send('eventsub channel.subscription.gift ' + json.dumps({'user_login': 'anon', 'tier': '2000', 'total': 1, 'is_anonymous': True}))
    send('eventsub channel.raid ' + json.dumps({'from_broadcaster_user_id': 'x', 'from_broadcaster_user_login': 'raider', 'viewers': 30}))
    send('eventsub channel.poll.begin ' + json.dumps({'id': 'p1', 'title': 'Best map?', 'choices': [{'id': 'a', 'title': 'Mannfield', 'votes': 0}, {'id': 'b', 'title': 'Champions', 'votes': 0}], 'ends_at': '2026-10-20T14:00:00Z'}))
    send('eventsub channel.poll.progress ' + json.dumps({'id': 'p1', 'title': 'Best map?', 'choices': []}))
    send('eventsub channel.poll.end ' + json.dumps({'id': 'p1', 'title': 'Best map?', 'status': 'completed', 'choices': [{'id': 'a', 'title': 'Mannfield', 'votes': 7}, {'id': 'b', 'title': 'Champions', 'votes': 3}]}))
    send('eventsub channel.prediction.lock ' + json.dumps({'id': 'q1', 'title': 'Win?', 'outcomes': [{'id': 'y', 'title': 'Yes', 'users': 4, 'channel_points': 900}]}))
    send('eventsub channel.prediction.end ' + json.dumps({'id': 'q1', 'title': 'Win?', 'status': 'resolved', 'winning_outcome_id': 'y', 'outcomes': []}))
    send('eventsub channel.hype_train.begin ' + json.dumps({'id': 'h1', 'level': 1, 'total': 300, 'progress': 300, 'goal': 500, 'type': 'regular'}))
    items = json.load(urllib.request.urlopen(B + '/api/activity?since=0', timeout=5))['items']
    by = lambda k: [i for i in items if i['type'] == k]
    g = by('gift'); chk('two gifts', len(g) == 2, g)
    if len(g) == 2:
        chk('gift grouped: gifter, amount, tier, cumulative', g[0]['user'] == 'gifty' and g[0]['amount'] == 5 and g[0]['tier'] == 1 and g[0].get('cumulative') == 42, g[0])
        chk('anonymous flagged', g[1].get('anonymous') is True and g[1]['tier'] == 2, g[1])
    r = by('raid'); chk('raid in', len(r) == 1 and r[0]['user'] == 'raider' and r[0]['amount'] == 30, r)
    p = by('poll'); chk('poll begin + end, no progress', [i['state'] for i in p] == ['begin', 'end'], p)
    if len(p) == 2: chk('poll data carries choices + status', p[1]['data']['status'] == 'completed' and p[1]['data']['choices'][0]['votes'] == 7, p[1])
    q = by('prediction'); chk('prediction lock + end', [i['state'] for i in q] == ['lock', 'end'] and q[1]['data']['winningOutcomeId'] == 'y', q)
    hy = by('hype'); chk('hype begin', len(hy) == 1 and hy[0]['data']['level'] == '1' and hy[0]['data']['goal'] == '500', hy)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS eventsub feed items')
sys.exit(1 if fails else 0)
