"""Trial run of EVERY Host feature end to end in sim mode (no Twitch, no real chat, no real OBS): game commands, helper, chat bot, !pg, events, automations,
APIs, pages. Prints a pass/fail table. Usage: python Tools/test-host-trial.py [path-to-PinguinoHost.dll]"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import base64, json, os, socket, subprocess, sys, tempfile, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obs_probe import _frame, _recv
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8891; rows = []; out = []; lock = threading.Lock()
d = tempfile.mkdtemp(prefix='pgtrial_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8896'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
def reader():
    for raw in iter(host.stdout.readline, b''):
        with lock: out.append(raw.decode('utf-8', 'replace').rstrip())
threading.Thread(target=reader, daemon=True).start()
def api(path, body=None, t=20):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=t))
def page(path): return urllib.request.urlopen('http://127.0.0.1:%d%s' % (PORT, path), timeout=15).read().decode('utf-8', 'replace')
def say(line, wait=1.3):
    with lock: start = len(out)
    host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait)
    with lock: return out[start:]
BAD = ('ERROR', 'Exception', 'COMPILE FAILED', 'Unhandled')
def case(area, name, fn):
    try:
        ok, note = fn()
    except Exception as ex:
        ok, note = False, 'exception: %s' % ex
    rows.append((area, name, 'PASS' if ok else 'FAIL', (note or '')[:90].replace('\n', ' ')))
def chat(line, must=None, silent=False, wait=1.3):
    def f():
        o = say(line, wait); text = ' | '.join(o)
        if any(b in text for b in BAD): return False, 'error in output: ' + text
        says = [x for x in o if x.startswith('[say]') or x.startswith('[pg]')]
        if silent: return (not says), 'unexpected reply: ' + text if says else 'silent'
        if must is None: return True, (says[0][6:] if says else '(no reply)')
        return (any(m.lower() in text.lower() for m in must)), (says[0][6:] if says else 'NO REPLY')
    return f
try:
    for _ in range(60):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
    # --- game commands (PinguinoB0t / BVQ) ---
    case('game', '!register', chat('bob: !register epic123', ['Registered']))
    case('game', '!register (second player)', chat('amy: !register amyepic', ['Registered']))
    for c, who in [('!join', 'bob'), ('!pos', 'bob'), ('!mmr', 'bob'), ('!stats', 'bob'), ('!rank', 'bob'), ('!top', 'bob'), ('!lobby', 'bob'), ('!leave', 'amy'), ('!check', 'bob'), ('!win', 'bob'), ('!pick', 'bob'), ('!finish', 'bob'), ('!koth', 'bob'), ('!mode', 'bob')]:
        case('game', c, chat(who + ': ' + c))
    for c in ['!queue', '!balance', '!next', '!reroll', '!format 3v3', '!kick amy', '!setmmr bob 1200']:
        case('game (mod)', c, chat('*mod: ' + c))
    case('game', 'mod command refused for viewers', chat('bob: !setmmr bob 3000'))
    api('/api/bots', {'id': 'helper', 'settings': {'LiveOnly': False}}); api('/api/bots', {'id': 'chat', 'settings': {'LiveOnly': False}}); time.sleep(11)   # bots re-read their settings every ~10 s
    # --- helper (key-word gated) ---
    case('helper', 'how do I join (key word)', chat('newbie: how do i join the custom games?'))
    time.sleep(9)   # the helper spaces its information answers
    case('helper', 'minecraft ip', chat('eve: what is the minecraft ip'))
    time.sleep(9)
    case('helper', '!discord', chat('eve: !discord'))
    case('helper', 'unrelated chatter -> helper stays quiet', chat('eve: nice weather today', silent=True))
    # --- chat bot ---
    case('chat', '@PinguinoB0t mention (offline = sleeping reply)', chat('bob: hey @PinguinoB0t how are you'))
    case('chat', 'name "pinguino" alone', chat('bob: pinguino hello'))
    case('chat', '!memory', chat('bob: !memory'))
    case('chat', '!forgetme / !rememberme', chat('bob: !forgetme'))
    # --- host chat commands ---
    case('host', '!pg status (mod)', chat('*mod: !pg status', ['core']))
    case('host', '!pg help (mod)', chat('*mod: !pg', ['status']))
    case('host', '!pg ignored for viewers', chat('bob: !pg status', silent=True))
    def toggle():
        say('*mod: !pg chat off'); b = {x['id']: x for x in api('/api/bots')['bots']}
        off = not b['chat']['enabled']; say('*mod: !pg chat on'); b = {x['id']: x for x in api('/api/bots')['bots']}
        return off and b['chat']['enabled'], 'toggled off and on'
    case('host', '!pg chat off/on', toggle)
    case('host', '!pg test (each bot says hi)', chat('*mod: !pg test', ['test core', 'test chat'], wait=5))
    # --- cutover and Streamer.bot replacements ---
    def cut():
        a = api('/api/cutover'); b = api('/api/cutover', {'on': True}); c = api('/api/cutover')
        return (not a['on']) and b['ok'] and c['on'] and b['changed'] >= 10, 'on=%s changed=%s' % (c['on'], b.get('changed'))
    case('cutover', 'switch ON enables the duplicate-prone actions', cut)
    def runs(): return api('/api/automations/log?n=200')['runs']
    def ran(name_part): return [r for r in runs() if name_part in r['action'] and not r['test']]
    evs = [('TwitchFollow ann', 'Alert: follow'), ('TwitchSub bob 1', 'Alert: sub'), ('TwitchReSub cy 2', 'Alert: resub'), ('TwitchGiftBomb dee 5', 'Alert: gifted'), ('TwitchCheer eve 300', 'Alert: cheer'), ('TwitchRaid fay 25', 'Alert: incoming raid'), ('TwitchBan gus 1', 'Alert: ban')]
    for ev, _ in evs: say('event ' + ev, 0.4)
    t_end = time.time() + 45
    while time.time() < t_end and not all(ran(n) for _, n in evs): time.sleep(1)
    for ev, expect in evs:
        def f(ev=ev, expect=expect):
            r = ran(expect)
            return bool(r) and r[0]['ok'], (' | '.join(r[0]['output'])[:80] if r else 'did not run within 45 s')
        case('events', ev.split()[0] + ' -> ' + expect, f)
    def act():
        a = api('/api/activity?since=0')['items']; types = {i['type'] for i in a}
        need = {'follow', 'sub', 'resub', 'gift', 'cheer', 'raid'}
        return need <= types, 'types: ' + ','.join(sorted(types))
    case('activity', 'all event kinds reach the feed', act)
    case('activity', 'seq increases, since filter works', lambda: (lambda a: (len(a['items']) > 0 and api('/api/activity?since=%d' % a['seq'])['items'] == [], 'seq=%s' % a['seq']))(api('/api/activity?since=0')))
    def first5():
        for n in ['a1', 'a2', 'a3', 'a4', 'a5', 'a6']: say(n + ': hello', 0.5)
        f = api('/api/activity?since=0&type=first5')['items']
        return len(f) >= 5, '%d first-5 entries' % len(f)
    say('event StreamOnline x', 1.5)
    case('first5', 'five chatters fill the places, feed gets them', first5)
    case('first5', '!first / !firsts answer', chat('a1: !firsts', ['First', 'record', 'Leaderboard', 'No First']))
    def latest_cmd():
        say('bob: !latest', 1.8); r = ran('!latest')
        return bool(r) and any('Latest' in o for o in r[0]['output']), (r[0]['output'][-1][:80] if r else 'did not run')
    case('latest', '!latest command', latest_cmd)
    case('latest', 'overlay page + feed API', lambda: ('api/latest' in page('/overlay/latest') and api('/api/latest')['ok'], ''))
    def shout():
        a = api('/api/shoutouts', {'user': 'somebody', 'by': 'mod'}); b = api('/api/shoutouts', {'user': 'somebody', 'by': 'mod'})
        return a['result'] == 'queued' and b['result'] == 'duplicate', '%s then %s' % (a['result'], b['result'])
    case('shoutout', 'queue + duplicate guard', shout)
    def clip_dry():
        r = api('/api/automations/test', {'id': 'sb-clip', 'dry': True}, 60)
        return r['ok'], ' | '.join(r['run']['output'])[:80]
    case('clip', '!clip dry run (Twitch clip + OBS replay)', clip_dry)
    def clip_real():
        doc = api('/api/automations')['doc']; doc['actions'].append({'id': 'cq', 'name': 'ClipQ', 'enabled': True, 'triggers': [{'type': 'manual'}], 'steps': [{'type': 'create_clip'}, {'type': 'obs_replay_save'}]}); api('/api/automations', {'doc': doc})
        r = api('/api/automations/test', {'id': 'cq', 'dry': False}, 60); o = ' | '.join(r['run']['output'])
        return 'Twitch clip failed' in o and ('NOT saved' in o or 'NOT running' in o), o[:90]
    case('clip', '!clip without Twitch/OBS fails politely', clip_real)
    def ads():
        r = api('/api/automations/test', {'id': 'sb-preroll', 'dry': False}); o = ' | '.join(r['run']['output'])
        return 'ad_schedule failed' in o, o[:90]
    case('ads', '!preroll without Twitch fails politely', ads)
    case('ads', '!whyad text', lambda: (lambda o: ('Sorry for the ad' in o and '!preroll' in o, o[:60]))(' | '.join(api('/api/automations/test', {'id': 'sb-whyad', 'dry': True})['run']['output'])))
    def sess():
        say('event TwitchFollow zoe', 1.5); say('event TwitchCheer zoe 150', 1.5)
        s = api('/api/session'); g = api('/api/goals')
        return s['ok'] and s['counts']['follows'] >= 1 and 'This stream' in s['line'] and len(g['goals']) >= 2 and all('line' in x for x in g['goals']), s['line'][:80]
    case('session', 'session numbers + goals from the feed', sess)
    def cred():
        c = api('/api/credits'); ct = api('/api/credits?test=1'); pg = page('/overlay/credits'); gp = page('/overlay/goal?id=followers')
        ok = c['id'] == 'credits' and 'zoe' in [x.lower() for x in c['events']['follows']] and ct['events']['follows'] and 'api/credits' in pg and 'api/goals' in gp and 'bob' in [x.lower() for x in c['users']['users']]
        return ok, 'follows=%s chatters=%d' % (c['events']['follows'], len(c['users']['users']))
    case('credits', 'credits JSON (events, users, top) + overlays', cred)
    def ws_compat():
        s = socket.create_connection(('127.0.0.1', 8896), timeout=6); key = base64.b64encode(os.urandom(16)).decode()
        CR = chr(13) + chr(10)
        s.sendall(('GET / HTTP/1.1' + CR + 'Host: 127.0.0.1:8896' + CR + 'Upgrade: websocket' + CR + 'Connection: Upgrade' + CR + 'Sec-WebSocket-Key: ' + key + CR + 'Sec-WebSocket-Version: 13' + CR + CR).encode())
        resp = b''
        while (CR + CR).encode() not in resp: resp += s.recv(1)
        def ask(o): s.sendall(_frame(json.dumps(o))); return _recv(s)
        a = ask({'id': 'credits', 'request': 'GetCredits'}); b = ask({'id': '2', 'request': 'GetActions'}); c = ask({'id': '3', 'request': 'DoAction', 'action': {'id': 'nope'}}); d2 = ask({'id': '4', 'request': 'DoAction', 'action': {'name': 'Command: !whyad'}}); e = ask({'id': '5', 'request': 'Nope'})
        s.close()
        return a['id'] == 'credits' and 'events' in a and b['count'] >= 20 and c['status'] == 'error' and d2['status'] == 'ok' and e['status'] == 'error', 'credits/actions/doaction ok'
    until_ws = time.time() + 40
    while time.time() < until_ws:
        try: socket.create_connection(('127.0.0.1', 8896), timeout=1).close(); break
        except Exception: time.sleep(1)
    case('websocket', 'Streamer.bot-compatible WebSocket (GetCredits, GetActions, DoAction)', ws_compat)
    def newsteps():
        doc = api('/api/automations')['doc']; doc['actions'].append({'id': 'ft', 'name': 'FirstToday', 'enabled': True, 'triggers': [{'type': 'first_today'}], 'steps': [{'type': 'log', 'text': 'first today {user}'}, {'type': 'alert_sound', 'kind': 'follow'}, {'type': 'press_key', 'key': 'Bogus'}]}); api('/api/automations', {'doc': doc})
        say('newperson: hello', 2.0); r = [x for x in runs() if x['action'] == 'FirstToday' and not x['test']]
        say('newperson: again', 1.5); r2 = [x for x in runs() if x['action'] == 'FirstToday' and not x['test']]
        o = ' | '.join(r[0]['output']) if r else ''
        return len(r) == 1 and len(r2) == 1 and 'no sound set' in o and 'unknown key' in o, o[:90]
    case('steps', 'first_today fires once per day; alert_sound and press_key behave', newsteps)
    # --- APIs and pages ---
    def mgmt():
        v = api('/api/vars', {'name': 'tv', 'value': '7', 'persist': True}); l = api('/api/vars')['vars']; dl = api('/api/vars/delete', {'name': 'tv'})
        tr = api('/api/automations/triggers')['triggers']; hk = api('/api/automations/hotkeys'); ex = api('/api/automations/export'); q = api('/api/queues')
        en = api('/api/automations/enable', {'group': 'Spotify', 'on': False}); ep = api('/api/endpoints')
        ok = v['ok'] and any(x['name'] == 'tv' and x['value'] == '7' for x in l) and dl['ok'] and len(tr) > 10 and hk['ok'] and ex['doc']['actions'] and q['queues'][0]['name'] == 'actions' and en['changed'] >= 8 and len(ep['endpoints']) >= 5
        return ok, '%d triggers, %d actions exported' % (len(tr), len(ex['doc']['actions']))
    case('mgmt', 'vars, triggers, hotkeys, export, queues, enable, endpoints', mgmt)
    def pause():
        api('/api/queues/pause', {'name': 'actions'}); say('bob: !whyad', 1.0)
        before = len([r for r in api('/api/automations/log?n=200')['runs'] if 'whyad' in r['action'].lower() and not r['test']])
        say('bob: !whyad', 1.5); paused_ok = len([r for r in api('/api/automations/log?n=200')['runs'] if 'whyad' in r['action'].lower() and not r['test']]) == before
        api('/api/queues/resume', {'name': 'actions'}); time.sleep(31); say('bob: !whyad', 2.0)
        after = len([r for r in api('/api/automations/log?n=200')['runs'] if 'whyad' in r['action'].lower() and not r['test']])
        return paused_ok and after > before, 'paused runs ignored, resumed runs work'
    case('mgmt', 'pause stops automatic runs, resume restores', pause)
    for path in ['/api/status', '/api/summary', '/api/prestream', '/api/bots', '/api/lease', '/api/cutover', '/api/latest', '/api/shoutouts', '/api/session', '/api/goals', '/api/credits', '/api/vars', '/api/queues', '/api/endpoints', '/api/automations/triggers', '/api/automations/hotkeys', '/api/automations/export', '/api/activity', '/api/automations', '/api/automations/log']:
        case('api', 'GET ' + path, (lambda p=path: (api(p).get('ok', True) is not False, '')))
    for path in ['/', '/automations', '/overlay/latest']:
        case('page', 'GET ' + path, (lambda p=path: (len(page(p)) > 500, '')))
    def prestream():
        p = api('/api/prestream'); return 'items' in p and len(p['items']) > 8, '%d items, status %s' % (len(p['items']), p.get('status'))
    case('api', 'prestream has items', prestream)
    case('log', 'console log has no ERROR lines', lambda: (lambda t: ('"level":"error"' not in t, 'errors in host.jsonl' if '"level":"error"' in t else 'clean'))(open(os.path.join(d, 'console', 'host.jsonl'), encoding='utf-8').read()))
    with lock: allout = '\n'.join(out)
    case('log', 'stdout has no exceptions', lambda: (not any(b in allout for b in ('Exception', 'COMPILE FAILED', 'Unhandled')), 'clean'))
finally:
    host.kill()
w = max(len(r[1]) for r in rows)
print('%-12s %-*s  %s  %s' % ('AREA', w, 'CASE', 'RESULT', 'NOTE'))
for a, n, r, note in rows: print('%-12s %-*s  %s    %s' % (a, w, n, r, note))
bad = [r for r in rows if r[2] != 'PASS']
print('\nHOST TRIAL: %d/%d passed' % (len(rows) - len(bad), len(rows)))
sys.exit(1 if bad else 0)
