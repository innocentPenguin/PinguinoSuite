"""!commands aliases + section/importance in the commands doc, stored ranks: !rank <player>, !refreshrank, !setrank <player> (the streamer's own !rank is RocketRankBot's).  Usage: python Tools/test-host-rank.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
import socket
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSP = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrank_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = str(WSP)
env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'
fx = d; env['PINGUINO_RANK_FIXTURE'] = fx; calls = os.path.join(d, 'calls.txt'); env['PINGUINO_RANK_CALLLOG'] = calls
json.dump({'1v1': 'Champion I Div II (1003)', '2v2': 'Grand Champion II Div I (1750)', '3v3': 'Champion II Div III (1280)', 'dropshot': 'Diamond II Div III (1020)'}, open(os.path.join(d, 'rank.somebody.json'), 'w'))
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
    vs = {'Essentials', 'Stream info', 'Chat history', 'Fun', 'Your settings', 'Music'}; ms = {'Chat commands', 'Stream', 'Viewers'}
    chk('every viewer row has section + importance', all(c.get('section') in vs and isinstance(c.get('importance'), int) for c in doc['viewer']), [c['command'] for c in doc['viewer'] if c.get('section') not in vs][:5])
    chk('every mod row has section + importance', all(c.get('section') in ms and isinstance(c.get('importance'), int) for c in doc['mod']), [c['command'] for c in doc['mod'] if c.get('section') not in ms][:5])
    chk('!queue sits in Essentials for viewers and Stream for mods', any(c['command'] == '!queue' and c['section'] == 'Essentials' for c in doc['viewer']) and any(c['command'] == '!queue' and c['section'] == 'Stream' for c in doc['mod']))
    # ---- stored ranks: the streamer's own !rank is RocketRankBot's, a register fetches once, !rank answers from the store ----
    r = say('viewer: !rank'); chk('bare !rank: no answer from us', r is None, r)
    r = say('viewer: !rank innocentpenguin_'); chk('the streamer by name: no answer from us', r is None, r)
    r = say('viewer: !rank 2s'); chk('!rank with only a playlist: no answer', r is None, r)
    json.dump({'alice': {'Username': 'alice', 'Platform': 'epic', 'GameId': 'Somebody'}}, open(os.path.join(d, 'players.json'), 'w'))
    r = say('alice: !register Somebody'); time.sleep(5.5)
    chk('register fetched once', ncalls() == 1, ncalls())
    r = say('viewer: !rank alice'); chk('stored ranks with a date', r and r.startswith('Somebody - Ranked 1v1: Champion I Div II (1003) | Ranked 2v2: Grand Champion II Div I (1750) | Ranked 3v3: Champion II Div III (1280) (as of '), r)
    r = say('viewer: !rank somebody 2s'); chk('found by Epic name, one playlist', r and r.startswith('Somebody - Ranked 2v2: Grand Champion II Div I (1750) (as of '), r)
    r = say('viewer: !rank alice dropshot'); chk('extra playlist from the same fetch', r and 'Dropshot: Diamond II Div III (1020)' in r, r)
    r = say('viewer: !rank alice snowday'); chk('missing playlist is said, not guessed', r and 'no Snowday rank saved' in r, r)
    chk('no fetch for any of the lookups', ncalls() == 1, ncalls())
    rl = os.path.join(d, 'ranks', 'rl_ranks.json')
    chk('ranks are saved for the profile push', os.path.exists(rl) and json.load(open(rl))['users'].get('alice', {}).get('ranks', {}).get('dropshot') == 'Diamond II Div III (1020)', open(rl).read()[:300] if os.path.exists(rl) else 'missing')
    r = say('viewer: !rank nobodyhere'); chk('unknown player', r and 'has no saved rank' in r, r)
    r = say('alice: !register Somebody'); time.sleep(5.5); chk('same name again: no second fetch', ncalls() == 1, ncalls())
    r = say('viewer: !refreshrank alice'); chk('viewers cannot refresh', r is None and ncalls() == 1, (r, ncalls()))
    r = say('*modguy: !refreshrank alice'); chk('mod refresh = one fetch', r and r.startswith('Refreshed Somebody') and ncalls() == 2, (r, ncalls()))
    r = say('viewer: !setrank alice 2v2 SSL (1900)'); chk('viewer cannot set', r is None, r)
    r = say('*modguy: !setrank alice 2v2 Supersonic Legend (1900) @spam http://x.y'); chk('mod set (cleaned)', r and r.startswith("Saved Somebody's rank (as of "), r)
    r = say('viewer: !rank alice 2s'); chk('hand-set rank answers', r and r.startswith('Somebody - Ranked 2v2: Supersonic Legend (1900) (as of '), r)
    r = say('*modguy: !setrank alice Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300)'); chk('bulk set', r and r.startswith('Saved'), r)
    r = say('viewer: !rank alice'); chk('final line', r and r.startswith('Somebody - Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300) (as of '), r)
    r = say('*modguy: !setrank 2v2 SSL'); chk('mod must name the player first', r and 'Name the player first' in r, r)
    r = say('*modguy: !setrank newbie 3v3 Gold I Div I (500)'); chk('mod can write a rank for someone not registered yet', r and r.startswith('Saved newbie'), r)
    r = say('viewer: !rank newbie 3s'); chk('and it answers', r and r.startswith('newbie - Ranked 3v3: Gold I Div I (500)'), r)
    sys.path.insert(0, here)
    r = say('viewer: !rank lookup nobodyhere'); chk('!rank lookup through chat (fixture source: nothing found, nothing stored)', r is not None and r.startswith('Could not read nobodyhere') or (r or '').startswith("Live lookup isn't available"), r)
    r = say('viewer2: !rank lookup'); chk('!rank lookup needs a name', r is not None and r.startswith('Usage: !rank lookup'), r)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS stored ranks')
sys.exit(1 if fails else 0)
