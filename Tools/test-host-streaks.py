"""Watch streaks: backfill from chat logs (both log formats, duplicates), live USERNOTICE capture (idempotent), commands, board, API, profiles. Usage: python Tools/test-host-streaks.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8941; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgstreak_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles')); os.makedirs(os.path.join(d, 'chat_logs', '2026', '10')); os.makedirs(os.path.join(d, 'chat_logs', '2026', '02'))
for u in ('ash_wagawaga', 'lvlmarshmello', 'fresh_face'):
    json.dump({'login': u, 'roles': {'mod': False, 'sub': False}, 'seen': {'firstSeen': '2026-02-16'}}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
open(os.path.join(d, 'chat_logs', '2026', '10', '2026-10-11.txt'), 'w', encoding='utf-8').write(
 '[2026-10-11 01:12:39] #innocentpenguin_ ash_wagawaga: ash_wagawaga watched 190 consecutive streams and sparked a watch streak! happy\n'
 '[2026-10-11 01:12:39] ash_wagawaga: ash_wagawaga watched 190 consecutive streams and sparked a watch streak! happy\n'
 '[2026-10-11 01:13:00] #innocentpenguin_ somebody: hello there\n')
open(os.path.join(d, 'chat_logs', '2026', '10', '2026-10-16.txt'), 'w', encoding='utf-8').write(
 '[2026-10-16 22:23:41] #innocentpenguin_ ash_wagawaga: ash_wagawaga watched 195 consecutive streams and sparked a watch streak!\n')
open(os.path.join(d, 'chat_logs', '2026', '02', '2026-02-18.txt'), 'w', encoding='utf-8').write(
 '[2026-02-18 01:03:30] #innocentpenguin_ * LvLMarshmello watched 15 consecutive streams and sparked a watch streak! - "squad"\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8943'; env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p):
    rq = urllib.request.Request(B + p, data=b'{}', headers={'Content-Type': 'application/json', 'Origin': B}); return json.load(urllib.request.urlopen(rq, timeout=15))
def say(line, wait=0.5): host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait)
def said(): return open(out, encoding='utf-8', errors='replace').read()
def prof(u): return json.load(open(os.path.join(d, 'profiles', u + '.json')))
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    r = post('/api/streaks/backfill'); a = get('/api/streaks'); board = {b['login']: b for b in a['board']}
    chk('backfill finds the streak lines and ignores normal chat', r['streakLines'] == 4 and r['added'] == 3 and a['people'] == 2)
    chk('both log formats parsed (display-name system line too)', board['lvlmarshmello']['best'] == 15 and board['ash_wagawaga']['best'] == 195)
    chk('same event in the log twice counts once', board['ash_wagawaga']['shares'] == 2)
    chk('re-running the backfill adds nothing', post('/api/streaks/backfill')['added'] == 0)
    chk('profile roles written, other fields kept', prof('ash_wagawaga')['roles']['watchStreakBest'] == 195 and prof('ash_wagawaga')['seen']['firstSeen'] == '2026-02-16' and 'watchStreakBest' not in prof('fresh_face')['roles'])
    tag = r'@badge-info=;msg-id=viewermilestone;msg-param-category=watch-streak;msg-param-copoReward=450;msg-param-id=abc-1;msg-param-value=%d;login=fresh_face;display-name=Fresh_Face;system-msg=Fresh_Face\swatched\s%d\sconsecutive\sstreams;tmi-sent-ts=1792500000000 :tmi.twitch.tv USERNOTICE #trial :lets go'
    say(tag % (7, 7)); say(tag % (7, 7))
    a = get('/api/streaks'); board = {b['login']: b for b in a['board']}
    chk('live USERNOTICE is recorded, and the same msg-param-id twice only once', board['fresh_face']['best'] == 7 and board['fresh_face']['shares'] == 1)
    say(tag.replace('abc-1', 'abc-2') % (8, 8)); board = {b['login']: b for b in get('/api/streaks')['board']}
    chk('a later share raises current and best', board['fresh_face']['current'] == 8 and board['fresh_face']['best'] == 8)
    say('@msg-id=sub;msg-param-sub-plan=2000;msg-param-cumulative-months=5;login=some_sub;tmi-sent-ts=1792500001000 :tmi.twitch.tv USERNOTICE #trial :hi')
    notices = open(os.path.join(d, 'streaks', 'usernotices.jsonl'), encoding='utf-8').read()
    chk('other USERNOTICEs are kept, not dropped', '"msgId":"sub"' in notices and 'msg-param-sub-plan' in notices)
    say('viewer1: !streak'); say('viewer1: !streak ash_wagawaga', 0.8); say('viewer2: !streakrecord ash_wagawaga'); say('viewer3: !streak nobodyhere'); say('viewer4: !topstreaks', 0.8)
    t = said()
    chk('!streak for someone who never shared: honest answer', "haven't seen you share" in t)
    chk('!streak <user> shows the last shared value and the best', "last shared watch streak: 195" in t)
    chk('!streakrecord shows the best with a date', "best shared watch streak: 195" in t and 'Oct 16, 2026' in t)
    chk('unknown user: nobody has shared one yet', 'Nobody has shared a watch streak for nobodyhere yet' in t)
    chk('!topstreaks lists the best first', 'Top watch streaks (best shared): 1. ash_wagawaga 195 | 2.' in t)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
