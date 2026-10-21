"""!commands aliases + section/importance in the commands doc, !rank / !setrank (replaces RocketRankBot's !rank).  Usage: python Tools/test-host-rank.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrank_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8989'
env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'
fx = os.path.join(d, 'profile.json'); env['PINGUINO_RANK_FIXTURE'] = fx; calls = os.path.join(d, 'calls.txt'); env['PINGUINO_RANK_CALLLOG'] = calls
def seg(n, tier, div, r, pid=None): return {'type': 'playlist', 'attributes': {'playlistId': pid}, 'metadata': {'name': n}, 'stats': {'tier': {'metadata': {'name': tier}}, 'division': {'metadata': {'name': div}}, 'rating': {'value': r}}}
json.dump({'data': {'segments': [{'type': 'overview'}, seg('Ranked Duel 1v1', 'Champion I', 'Division II', 1003.0), seg('Ranked Doubles 2v2', 'Grand Champion II', 'Division I', 1750), seg('Ranked Standard 3v3', 'Champion II', 'Division III', 1280), seg('Dropshot', 'Diamond II', 'Division III', 1020, 29), seg('Heatseeker', 'Platinum I', 'Division I', 780, 63), seg('Hoops', 'Champion I', 'Division I', 1010, 27), seg('Rumble', 'Gold III', 'Division II', 640, 28)], 'platformInfo': {'platformUserHandle': 'Somebody'}}}, open(fx, 'w'))
json.dump({'data': {'segments': [seg('Ranked Doubles 2v2', 'Diamond III', 'Division II', 1150, 11)], 'platformInfo': {'platformUserHandle': 'Somebody'}}}, open(os.path.join(d, 'profile.somebody.json'), 'w'))
def ncalls(): return len(open(calls).read().split()) if os.path.exists(calls) else 0
outp = os.path.join(d, 'out.txt')
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
fails = []
def say(line):
    n = open(outp, 'rb').read().count(b'[say] ')
    h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(0.7)
    t = open(outp, 'rb').read().decode('utf-8', 'replace'); i = t.split('[say] ')
    return i[-1].split('\n')[0].strip() if len(i) - 1 > n else None
def chk(name, ok, extra=''):
    if not ok: fails.append('%s %s' % (name, extra))
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    for c in ('!commands', '!command', '!cmds', '!cmd'):
        r = say('viewer: ' + c); chk(c + ' alias', r == 'All my commands, by category and importance: https://innocentpenguin.com/commands', r)
    doc = json.load(urllib.request.urlopen(B + '/api/commands-doc', timeout=10))
    vs = {'Essentials', 'Stream info', 'Chat history', 'Fun', 'Your settings'}; ms = {'Chat commands', 'Stream', 'Viewers'}
    chk('every viewer row has section + importance', all(c.get('section') in vs and isinstance(c.get('importance'), int) for c in doc['viewer']), [c['command'] for c in doc['viewer'] if c.get('section') not in vs][:5])
    chk('every mod row has section + importance', all(c.get('section') in ms and isinstance(c.get('importance'), int) for c in doc['mod']), [c['command'] for c in doc['mod'] if c.get('section') not in ms][:5])
    chk('!queue sits in Essentials for viewers and Stream for mods', any(c['command'] == '!queue' and c['section'] == 'Essentials' for c in doc['viewer']) and any(c['command'] == '!queue' and c['section'] == 'Stream' for c in doc['mod']))
    r = say('viewer: !rank'); chk('live from the tracker', r == 'Ranked 1v1: Champion I Div II (1003) | Ranked 2v2: Grand Champion II Div I (1750) | Ranked 3v3: Champion II Div III (1280)', r)
    r = say('viewer: !rank /2s'); chk('single playlist', r == 'Ranked 2v2: Grand Champion II Div I (1750)', r)
    chk('one tracker call so far (all playlists in one pull)', ncalls() == 1, ncalls())
    for q, want in (('dropshot', 'Dropshot: Diamond II Div III (1020)'), ('heatseek', 'Heatseeker: Platinum I Div I (780)'), ('hoops', 'Hoops: Champion I Div I (1010)'), ('rumble', 'Rumble: Gold III Div II (640)')):
        r = say('viewer: !rank ' + q); chk('!rank ' + q, r == want, r)
    r = say('viewer: !rank 2v2'); chk('2v2 form', r == 'Ranked 2v2: Grand Champion II Div I (1750)', r)
    r = say('viewer: !rank snowday'); chk('missing playlist is said, not guessed', r and 'No Snowday rank found' in r, r)
    chk('still one tracker call after 7 lookups of the same account', ncalls() == 1, ncalls())
    r = say('viewer: !rank somebody 2s'); chk('another Epic account is looked up', r == 'Somebody - Ranked 2v2: Diamond III Div II (1150)', r)
    r = say('viewer: !rank somebody 3s'); chk('same account within 15 min: cached, 3s not on file', r and 'No Ranked 3v3 rank found' in r, r)
    chk('two accounts, two calls total', ncalls() == 2, ncalls())
    json.dump({'alice': {'Username': 'alice', 'Platform': 'epic', 'GameId': 'Somebody'}}, open(os.path.join(d, 'players.json'), 'w'))
    r = say('viewer: !rank alice 2s'); chk('a linked twitch name finds the Epic account (cached, no new call)', r and 'Ranked 2v2: Diamond III Div II (1150)' in r and ncalls() == 2, (r, ncalls()))
    rl = os.path.join(d, 'ranks', 'rl_ranks.json')
    chk('owner ranks are saved for the profile push', os.path.exists(rl) and json.load(open(rl))['users'].get('innocentpenguin_', {}).get('ranks', {}).get('dropshot') == 'Diamond II Div III (1020)', open(rl).read()[:300] if os.path.exists(rl) else 'missing')
    r = say('viewer: !rank bad/name!'); chk('weird names refused', r and 'Epic name' in r, r)
    r = say('viewer: !setrank 2v2 SSL (1900)'); chk('viewer cannot set', r is None, r)
    r = say('*modguy: !setrank 2v2 Supersonic Legend (1900) @spam http://x.y'); chk('mod set', r and 'saved' in r.lower(), r)
    r = say('viewer: !rank 2s'); chk('cleaned + updated', r == 'Ranked 2v2: Supersonic Legend (1900)', r)
    r = say('*modguy: !setrank Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300)'); chk('bulk set', r and 'saved' in r.lower(), r)
    r = say('*modguy: !setrank peak SSL'); chk('peak', r and 'saved' in r.lower(), r)
    r = say('viewer: !rank'); chk('final line (manual wins for 24 h)', r == 'Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300) | Peak: SSL', r)
    # playlist matching: ids first (10 11 13 27 28 29 30 34), then names without case / "Ranked" / spaces
    json.dump({'data': {'segments': [seg('Whatever Psyonix Calls It', 'Gold I', 'Division I', 500, 27), seg('Ranked Snow Day', 'Silver II', 'Division II', 400), seg('Ranked Rumble', 'Bronze III', 'Division I', 300), seg('Official Tournament', 'Platinum II', 'Division III', 800, 34), seg('Ranked 4v4 Quads', 'Diamond I', 'Division I', 900)], 'platformInfo': {'platformUserHandle': 'Namer'}}}, open(os.path.join(d, 'profile.namer.json'), 'w'))
    for q, want in (('hoops', 'Hoops: Gold I Div I (500)'), ('snowday', 'Snowday: Silver II Div II (400)'), ('rumble', 'Rumble: Bronze III Div I (300)'), ('tournament', 'Tournament: Platinum II Div III (800)'), ('4s', 'Ranked 4v4: Diamond I Div I (900)')):
        r = say('viewer: !rank namer ' + q); chk('playlist match for namer ' + q, r == 'Namer - ' + want, r)
    sys.path.insert(0, here)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS !rank / !setrank')
sys.exit(1 if fails else 0)
