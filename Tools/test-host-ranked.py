"""The Ranked activity through chat and the API: start/stop (!activity ranked / !ranked stop), !win !loss !undo (mods only), !ranked one line, bare !win stays ranked while customs runs (customs results: Master View or !customs win|loss <team>),
one chat line per command, state survives a restart, POST/GET /api/ranked. Usage: python Tools/test-host-ranked.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WS, TOK = _free(), _free(), 'test-module-token'
d = tempfile.mkdtemp(prefix='pgrkd_'); outp = os.path.join(d, 'out.txt'); rj = os.path.join(d, 'ranked.json')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_MODULE_TOKEN': TOK})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def start():
    return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen('http://127.0.0.1:%d%s' % (PORT, p), timeout=10))
def post(p, body):
    h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
    try: return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=json.dumps(body).encode(), headers=h), timeout=10))
    except urllib.error.HTTPError as e: return {'http': e.code}
def waitup():
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
def says(host, line, wait=0.8):
    n = len(open(outp, 'rb').read()); host.stdin.write(line.encode() + chr(10).encode()); host.stdin.flush(); time.sleep(wait)
    new = open(outp, 'rb').read()[n:].decode('utf-8', 'replace')
    return [l[len('[say] '):] for l in new.splitlines() if l.startswith('[say] ')]
host = start()
try:
    waitup()
    s = get('/api/ranked'); chk('starts off and empty', s['ok'] and s['active'] is False and s['games'] == [] and s['inProgress'] == 1 and s['net'] == 0 and s['limit'] == 5, s)
    chk('shape has every field', {'active', 'limit', 'games', 'net', 'inProgress', 'wins', 'losses', 'day', 'week'} <= set(s) and {'wins', 'losses', 'net'} <= set(s['week']), s)
    r = says(host, '*mod1: !activity ranked'); chk('!activity ranked starts it, one line', len(r) == 1 and 'Ranked is on' in r[0] and get('/api/ranked')['active'], r)
    says(host, '*mod1: !ranked breakafter 0'); says(host, '*mod1: !ranked lossstreak 0')   # the marks below are not about breaks
    r = says(host, '*mod1: !win'); chk('!win while ranked runs: one line, ranked only', r == ['@mod1 Ranked today: 1-0 (+1)'], r)
    r = says(host, '*mod1: !loss'); chk('!loss', r == ['@mod1 Ranked today: 1-1 (0)'], r)
    r = says(host, '*mod1: !w'); chk('!w', r == ['@mod1 Ranked today: 2-1 (+1)'], r)
    r = says(host, 'viewer1: !win'); chk('a viewer marks nothing and nothing is said', r == [] and get('/api/ranked')['games'] == ['W', 'L', 'W'], r)
    r = says(host, 'viewer1: !ranked', 0.5); chk('viewer !ranked: one line', r == ['@viewer1 Ranked today: 2-1 (+1)'], r)
    r = says(host, '*mod1: !undo'); chk('!undo', r == ['@mod1 Undone. Ranked today: 1-1 (0)'], r)
    r = says(host, '*mod1: !win'); chk('back to 2-1', r == ['@mod1 Ranked today: 2-1 (+1)'], r)
    # customs runs alongside: bare !win stays ranked, "!win blue" and "!customs win blue" are customs'
    says(host, '*mod1: !activity rl competitive', 1.5); act = get('/api/customs/state').get('activity')
    chk('customs activity is on (precondition)', act not in (None, '', 'none'), act)
    g0 = get('/api/ranked')['games']; says(host, '*mod1: !win blue', 1.0)
    chk('customs running: !win blue is not ranked', get('/api/ranked')['games'] == g0, get('/api/ranked'))
    r = says(host, '*mod1: !win', 0.8); chk('customs running: bare !win is still ranked', r == ['@mod1 Ranked today: 3-1 (+2)'], r)
    r = says(host, '*mod1: !customs win', 0.8); chk('!customs needs a team', len(r) == 1 and '!customs win|loss' in r[0], r)
    g0 = get('/api/ranked')['games']; says(host, '*mod1: !customs win blue', 1.0); chk('!customs win blue is not ranked', get('/api/ranked')['games'] == g0)
    r = says(host, '*mod1: !ranked undo', 0.8); chk('!ranked undo', r == ['@mod1 Undone. Ranked today: 2-1 (+1)'], r)
    says(host, '*mod1: !activity end', 1.5)
    chk('!activity end (customs) leaves ranked running, games kept', get('/api/ranked')['active'] is True and get('/api/ranked')['games'] == ['W', 'L', 'W'], get('/api/ranked'))
    r = says(host, '*mod1: !ranked stop', 0.6); chk('!ranked stop', r == ['@mod1 Ranked is off.'] and get('/api/ranked')['active'] is False, r)
    r = post('/api/ranked', {'action': 'win'}); chk('POST win while off is refused', r.get('ok') is False, r)
    r = post('/api/ranked', {'action': 'start'}); chk('POST start', r.get('ok') and r['active'], r)
    r = post('/api/ranked', {'action': 'loss'}); chk('POST loss', r['games'] == ['W', 'L', 'W', 'L'] and r['net'] == 0 and r['inProgress'] == 5, r)
    r = post('/api/ranked', {'action': 'undo'}); chk('POST undo', r['games'] == ['W', 'L', 'W'], r)
    r = post('/api/ranked', {'action': 'limit', 'value': 2}); chk('POST limit', r['limit'] == 2 and r['visible'] == ['L', 'W'], r)
    r = post('/api/ranked', {'action': 'limit', 'value': 0}); chk('POST limit 0 refused', r.get('ok') is False and r['limit'] == 2, r)
    r = post('/api/ranked', {'action': 'nope'}); chk('POST unknown action refused', r.get('ok') is False, r)
    chk('state file written', json.load(open(rj, encoding='utf-8-sig'))['active'] is True)
    host.kill(); host.wait(timeout=20); time.sleep(1)
    host = start(); waitup()
    s = get('/api/ranked'); chk('everything survives a restart', s['active'] is True and s['games'] == ['W', 'L', 'W'] and s['limit'] == 2, s)
    r = says(host, 'viewer2: !ranked week', 0.6); chk('!ranked week', r == ['@viewer2 Ranked this week: 2-1 (+1)'], r)
    r = says(host, '*mod1: !ranked limit 4', 0.6); chk('!ranked limit', len(r) == 1 and 'last 4' in r[0] and get('/api/ranked')['limit'] == 4, r)
    r = says(host, '*mod1: !ranked reset', 0.6); chk('!ranked reset', r == ['@mod1 Ranked reset. Ranked today: 0-0 (0)'] and get('/api/ranked')['games'] == [], r)
    r = says(host, '*mod1: !ranked stop', 0.6); chk('!ranked stop', r == ['@mod1 Ranked is off.'] and get('/api/ranked')['active'] is False, r)
    # breaks: API, chat, one announcement per break (also across a restart)
    BL = '[say] Break time: customs / 1v1 / play with viewers'
    def nbreak(): return sum(1 for l in open(outp, 'rb').read().decode('utf-8', 'replace').splitlines() if l == BL)
    post('/api/ranked', {'action': 'start'}); post('/api/ranked', {'action': 'breakafter', 'value': 3}); post('/api/ranked', {'action': 'lossstreak', 'value': 2})
    n0 = nbreak(); post('/api/ranked', {'action': 'win'}); post('/api/ranked', {'action': 'loss'}); r = post('/api/ranked', {'action': 'win'})
    chk('POST: break after 3 games', r['break']['active'] and r['break']['reason'] == '3 games' and r['break']['afterGames'] == 3 and r['break']['lossStreak'] == 2 and len(r['breaks']) == 1 and r['startedAt'] and r['month']['wins'] == 2, r)
    time.sleep(0.5); chk('one chat line for the break', nbreak() == n0 + 1, nbreak() - n0)
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup()
    s = get('/api/ranked'); chk('the break survives a restart', s['break']['active'] and s['break']['reason'] == '3 games' and s['breaks'][0]['reason'] == '3 games', s)
    r = post('/api/ranked', {'action': 'win'}); time.sleep(0.5); chk('no repeat of the line after the restart or while on the break', nbreak() == n0 + 1 and r['break']['active'], nbreak() - n0)
    r = says(host, '*mod1: !ranked resume', 0.6); chk('!ranked resume', len(r) == 1 and r[0].startswith('@mod1 Ranked is back.') and not get('/api/ranked')['break']['active'], r)
    r = post('/api/ranked', {'action': 'resume'}); chk('resume off a break is refused', r.get('ok') is False, r)
    r = says(host, '*mod1: !ranked break', 0.8); chk('!ranked break: the one line', r == ['Break time: customs / 1v1 / play with viewers'] and get('/api/ranked')['break']['reason'] == 'manual', r)
    r = says(host, '*mod1: !ranked resume', 0.6)
    r = post('/api/ranked', {'action': 'lossstreak', 'value': 99}); chk('lossstreak 99 refused', r.get('ok') is False, r)
    r = says(host, '*mod1: !ranked lossstreak 3', 0.6); chk('!ranked lossstreak', r == ['@mod1 Break after 3 losses in a row.'] and get('/api/ranked')['lossStreak'] == 3, r)
    r = says(host, '*mod1: !ranked breakafter 0', 0.6); chk('!ranked breakafter 0', r == ['@mod1 Break after games: off.'] and get('/api/ranked')['breakAfter'] == 0, r)
    post('/api/ranked', {'action': 'loss'}); post('/api/ranked', {'action': 'loss'}); r = post('/api/ranked', {'action': 'loss'})
    chk('3 losses in a row breaks', r['break']['active'] and r['break']['reason'] == '3 losses in a row', r['break'])
    r = says(host, '*mod1: !customs win blue', 0.6); chk('!customs win blue works during a ranked break (no ranked change)', (get('/api/ranked')['wins'], get('/api/ranked')['losses']) == (3, 4), get('/api/ranked'))
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS ranked'); sys.exit(1 if fails else 0)
