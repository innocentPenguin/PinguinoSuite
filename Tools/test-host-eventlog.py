"""Structured logs: GET /api/eventlog?kind=chat|players|backend&since=&before=&limit=  (shape, paging, players log derived from the customs state, backfill).  Usage: python Tools/test-host-eventlog.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgel_'); os.makedirs(os.path.join(d, 'config')); os.makedirs(os.path.join(d, 'runtime', 'console')); os.makedirs(os.path.join(d, 'chat_logs', 'live'))
json.dump({'Channel': 'elog', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
now = int(time.time() * 1000)
os.makedirs(os.path.join(d, 'ovl')); json.dump({'OverlayDir': os.path.join(d, 'ovl')}, open(os.path.join(d, 'settings.json'), 'w'))
# backfill sources: a finished match and a chat log with a !join / !kick
json.dump([{'Id': 7, 'Format': '2v2', 'Mode': 'random', 'CreatedAt': now // 1000 - 3600, 'FinishedAt': now // 1000 - 3000, 'Winner': 'Blue',
            'Blue': [{'Username': 'ann'}, {'Username': 'ben'}], 'Orange': [{'Username': 'cat'}, {'Username': 'dan'}]}], open(os.path.join(d, 'runtime', 'matches.json'), 'w'))
with open(os.path.join(d, 'chat_logs', 'live', '2026-01-01.jsonl'), 'w') as f:
    f.write(json.dumps({'t': now - 7200000, 'u': 'ann', 'i': '1', 'm': '!join', 'c': 1}) + '\n')
    f.write(json.dumps({'t': now - 7100000, 'u': 'someone', 'i': '2', 'm': 'hello chat', 'c': 0}) + '\n')
    f.write(json.dumps({'t': now - 7000000, 'u': 'pinguinob0t', 'i': '3', 'm': 'hi', 'c': 0}) + '\n')
with open(os.path.join(d, 'runtime', 'console', 'host.jsonl'), 'w') as f:
    f.write(json.dumps({'ts': now / 1000 - 100, 'level': 'info', 'source': 'obs', 'msg': 'scene switched'}) + '\n')
    f.write(json.dumps({'ts': now / 1000 - 90, 'level': 'debug', 'source': 'obs', 'msg': 'noise'}) + '\n')
    f.write(json.dumps({'ts': now / 1000 - 80, 'level': 'error', 'source': 'overlay', 'msg': 'broke'}) + '\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8993', 'PINGUINO_LIVE': '0'})
fails = []; host = None
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def feed(l, w=1.5): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def types(kind, extra=''): return [e['type'] for e in get('/api/eventlog?kind=%s&limit=1000%s' % (kind, extra))['events']]
try:
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    # ---- backfill
    r = get('/api/eventlog?kind=players&limit=1000'); ev = r['events']
    chk('players shape', r['ok'] and all(k in ev[0] for k in ['id', 'ts', 'kind', 'type', 'user', 'text', 'group', 'detail']), ev[:1])
    teams = [e for e in ev if e['type'] == 'teams']
    chk('teams backfilled as blue/orange lists', teams and teams[0]['detail']['blue'] == ['ann', 'ben'] and teams[0]['detail']['orange'] == ['cat', 'dan'] and teams[0]['group'] == 'match-7', teams)
    clr = [e for e in ev if e['type'] == 'match_clear']
    chk('end-of-game bulk removal grouped with count', len(clr) == 4 and all(e['group'] == 'end-7' and e['detail']['count'] == 4 for e in clr), clr)
    chk('game_end backfilled', any(e['type'] == 'game_end' and e['detail']['winner'] == 'Blue' for e in ev))
    chk('chat !join backfilled', any(e['type'] == 'join' and e['user'] == 'ann' and e['detail'].get('derived') for e in ev))
    chk('filter by group', len(get('/api/eventlog?kind=players&group=end-7')['events']) == 4)
    chk('filter by user (team member)', any(e['type'] == 'teams' for e in get('/api/eventlog?kind=players&user=ben')['events']))
    # ---- chat
    c = get('/api/eventlog?kind=chat&limit=50')['events']
    chk('chat events', [e['type'] for e in c] == ['command', 'chat', 'bot'] or sorted(e['type'] for e in c) == ['bot', 'chat', 'command'], [e['type'] for e in c])
    chk('chat detail', c and 'userId' in c[0]['detail'] and c[0]['kind'] == 'chat')
    # ---- backend
    b = get('/api/eventlog?kind=backend&limit=1000')['events']
    chk('backend has info/error, not debug', any(e['text'] == 'scene switched' for e in b) and any(e['detail']['level'] == 'error' for e in b) and not any(e['text'] == 'noise' for e in b))
    chk('backend type = source, level filter', [e['text'] for e in get('/api/eventlog?kind=backend&level=error')['events'] if e['text'] == 'broke'] == ['broke'] and any(e['type'] == 'obs' for e in b))
    # ---- overlay change entries (backend)
    ovl = None
    try:
        import urllib.request as ur
        rq = ur.Request(B + '/api/overlays/write', json.dumps({'path': 'zz_test.html', 'text': '<html></html>'}).encode(), {'Content-Type': 'application/json', 'Origin': B}); ovl = json.load(ur.urlopen(rq, timeout=10))
    except Exception as ex: ovl = {'ok': False, 'error': str(ex)}
    chk('overlay write ok', ovl.get('ok'), ovl)
    if ovl.get('ok'):
        ob = [e for e in get('/api/eventlog?kind=backend&type=overlay')['events']]
        chk('overlay change in backend feed', ob and ob[-1]['detail']['file'] == 'zz_test.html' and ob[-1]['detail']['action'] == 'created', ob)
    # ---- paging
    allp = get('/api/eventlog?kind=players&limit=1000')['events']
    p1 = get('/api/eventlog?kind=players&limit=3'); chk('limit + more + newest first page', p1['count'] == 3 and p1['more'] and p1['events'] == allp[-3:], p1['count'])
    p2 = get('/api/eventlog?kind=players&limit=3&before=%d' % p1['next']); chk('backward paging', p2['count'] >= 1 and all(e['ts'] < p1['oldest'] for e in p2['events']))
    chk('forward since', all(e['ts'] > allp[0]['ts'] for e in get('/api/eventlog?kind=players&since=%d' % allp[0]['ts'])['events']))
    chk('bad kind rejected', get('/api/eventlog?kind=nope')['ok'] is False)
    # ---- live derivation from the customs state
    feed('#ivan: !queue open', 2)
    for u in ['u1', 'u2', 'u3', 'u4']: feed('%s: !register %sepic' % (u, u), 1.0); feed('%s: !join' % u, 1.5)
    chk('live join events', types('players', '&type=join').count('join') >= 4 + 1, types('players', '&type=join'))
    feed('u4: !leave', 2.5); lv = get('/api/eventlog?kind=players&type=leave&user=u4')['events']
    chk('self leave tagged', any(e['text'].endswith('left the queue') for e in lv), lv)
    feed('*modx: !kick u3', 2.5); kk = get('/api/eventlog?kind=players&user=u3&type=kick')['events']
    chk('mod kick tagged with by', kk and kk[0]['detail'].get('by') == 'modx', kk)
    feed('*modx: !queue clear', 2.5); bulk = [e for e in get('/api/eventlog?kind=players&limit=1000')['events'] if e['type'] in ('queue_clear', 'removed') and e['user'] in ('u1', 'u2')]
    chk('queue clear logged per player', len(bulk) >= 2, bulk)
    ids = [e['id'] for e in get('/api/eventlog?kind=players&limit=1000')['events']]; chk('ids unique', len(ids) == len(set(ids)))
    persisted = [json.loads(l) for l in open(os.path.join(d, 'runtime', 'eventlog', 'players.jsonl'), encoding='utf-8') if l.strip()]
    chk('players log persisted', len(persisted) == len(ids), (len(persisted), len(ids)))
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS eventlog'); sys.exit(1 if fails else 0)
