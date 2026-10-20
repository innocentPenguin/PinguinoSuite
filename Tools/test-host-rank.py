"""!rank / !setrank (replaces RocketRankBot's !rank).  Usage: python Tools/test-host-rank.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgrank_'); json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8989'
env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'
fx = os.path.join(d, 'profile.json'); env['PINGUINO_RANK_FIXTURE'] = fx
def seg(n, tier, div, r): return {'type': 'playlist', 'metadata': {'name': n}, 'stats': {'tier': {'metadata': {'name': tier}}, 'division': {'metadata': {'name': div}}, 'rating': {'value': r}}}
json.dump({'data': {'segments': [{'type': 'overview'}, seg('Ranked Duel 1v1', 'Champion I', 'Division II', 1003.0), seg('Ranked Doubles 2v2', 'Grand Champion II', 'Division I', 1750), seg('Ranked Standard 3v3', 'Champion II', 'Division III', 1280)]}}, open(fx, 'w'))
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
    r = say('viewer: !rank'); chk('live from the tracker', r == 'Ranked 1v1: Champion I Div II (1003) | Ranked 2v2: Grand Champion II Div I (1750) | Ranked 3v3: Champion II Div III (1280)', r)
    r = say('viewer: !rank /2s'); chk('single playlist', r == 'Ranked 2v2: Grand Champion II Div I (1750)', r)
    r = say('viewer: !rank somebody'); chk('other viewers not guessed', r and 'only know' in r, r)
    r = say('viewer: !setrank 2v2 SSL (1900)'); chk('viewer cannot set', r is None, r)
    r = say('*modguy: !setrank 2v2 Supersonic Legend (1900) @spam http://x.y'); chk('mod set', r and 'saved' in r.lower(), r)
    r = say('viewer: !rank 2s'); chk('cleaned + updated', r == 'Ranked 2v2: Supersonic Legend (1900)', r)
    r = say('*modguy: !setrank Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300)'); chk('bulk set', r and 'saved' in r.lower(), r)
    r = say('*modguy: !setrank peak SSL'); chk('peak', r and 'saved' in r.lower(), r)
    r = say('viewer: !rank'); chk('final line (manual wins for 24 h)', r == 'Ranked 1v1: Grand Champion I Div I (1400) | Ranked 2v2: GC2 (1700) | Ranked 3v3: Champion III (1300) | Peak: SSL', r)
    sys.path.insert(0, here)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS !rank / !setrank')
sys.exit(1 if fails else 0)
