"""Customs planned round + queue shuffle: !customs plan N / POST plan, the round ends by itself when the planned matches are played (the round's players go to the END of the queue in pick order,
except the last match's players), one chat line, playedMatches restarts and the plan stays; !queue shuffle (waiting only, seeded) and !queue undo (merge rule), canUndoShuffle, persistence across a restart,
all while the Ranked tracker runs. Usage: python Tools/test-host-round.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WS = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pground_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_DUP_SECONDS': '0', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0', 'PINGUINO_SHUFFLE_SEED': '7'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def start():
    return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try: return json.load(urllib.request.urlopen(rq, timeout=20))
    except urllib.error.HTTPError as e: return {'http': e.code}
def waitup():
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(4)
def feed(l, w=1.0):
    host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def out(): return open(outp, 'rb').read().decode('utf-8', 'replace')
def mod(a, v=''): r = api('/api/customs/mod', {'action': a, 'value': v}); time.sleep(0.8); return r
def st(): return api('/api/customs/state')
def waiting(): return [q['username'] for q in st()['queue']]
host = start()
try:
    waitup()
    mod('activity', 'rl competitive'); mod('format', '1v1'); mod('streamer', 'out'); feed('#trial: !autonext off')
    feed('*mod1: !ranked start'); feed('*mod1: !ranked breakafter 0'); feed('*mod1: !ranked lossstreak 0')
    names = ['a%d' % i for i in range(1, 8)]
    for n in names[:6]: feed('%s: !register %sEpic' % (n, n), 0.4); feed('%s: !join' % n, 0.5)
    chk('six waiting in join order', waiting() == names[:6], waiting())
    s = st(); chk('state carries the new fields (0 / 0 / false)', s.get('plannedMatches') == 0 and s.get('playedMatches') == 0 and s.get('canUndoShuffle') is False, {k: s.get(k) for k in ('plannedMatches', 'playedMatches', 'canUndoShuffle')})
    r = mod('plan', '99'); chk('plan 99 refused', r.get('ok') is False, r)
    r = mod('plan', '2'); time.sleep(1.5); chk('plan 2', st()['plannedMatches'] == 2, (st().get('plannedMatches'), out()[-400:].encode('ascii','replace').decode()))
    o0 = len(out()); feed('viewer1: !customs plan 5'); chk('a viewer cannot set the plan', st()['plannedMatches'] == 2 and 'Only mods' in out()[o0:], out()[o0:][-300:].encode('ascii','replace').decode())
    o0 = len(out()); feed('#trial: !customs plan'); chk('!customs plan answers', 'Customs round: 2 matches planned, 0 played' in out()[o0:], out()[o0:][-300:])
    mod('next'); m = st()['match'] or {}; chk('match 1 = a1,a2', sorted((m.get('blue') or []) + (m.get('orange') or [])) == ['a1', 'a2'], m)
    g0 = api('/api/ranked')['games']; o0 = len(out()); mod('win', 'blue')
    s = st(); chk('match 1 counted, round continues', s['playedMatches'] == 1 and 'Customs round done' not in out()[o0:], (s['playedMatches'], out()[o0:][-300:]))
    chk('customs result did not touch ranked', api('/api/ranked')['games'] == g0)
    chk('after match 1: a3..a6 waiting', waiting() == ['a3', 'a4', 'a5', 'a6'], waiting())
    mod('next'); o0 = len(out()); mod('win', 'orange')
    o = out()[o0:]; s = st()
    chk('round done: one line', o.count('[say] Customs round done: 2 matches, players re-queued') == 1, o[-400:])
    chk('playedMatches restarted, plan stays', s['playedMatches'] == 0 and s['plannedMatches'] == 2, (s['playedMatches'], s['plannedMatches']))
    chk('round players back at the END in pick order, last match (a3,a4) stays out', waiting() == ['a5', 'a6', 'a1', 'a2'], waiting())
    chk('queue stays open', s['open'] is True, s['open'])
    # shuffle
    before = waiting(); r = mod('shuffle'); after = waiting(); s = st()
    chk('shuffle: same players, new order, undo available', sorted(after) == sorted(before) and after != before and s['canUndoShuffle'] is True, (before, after, s['canUndoShuffle']))
    feed('a7: !register a7Epic', 0.4); feed('a7: !join', 0.6); feed('a5: !leave', 0.8)
    r = mod('undoshuffle'); w = waiting(); exp = [n for n in before if n != 'a5'] + ['a7']
    chk('undo merges: old order, a5 dropped, a7 at the end', w == exp and st()['canUndoShuffle'] is False, (w, exp))
    o0 = len(out()); r = mod('undoshuffle'); chk('a second undo refuses cleanly', 'Nothing to undo' in out()[o0:] and waiting() == exp, out()[o0:][-300:])
    feed('viewer1: !queue shuffle', 0.8); chk('a viewer cannot shuffle', waiting() == exp and st()['canUndoShuffle'] is False)
    mod('shuffle'); sh = waiting()
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup()
    s = st(); chk('plan and the undo snapshot survive a restart', s['plannedMatches'] == 2 and s['canUndoShuffle'] is True and waiting() == sh, (s['plannedMatches'], s['canUndoShuffle'], waiting(), sh))
    mod('undoshuffle'); chk('undo after the restart restores the old order', waiting() == exp, waiting())
    mod('plan', '0'); chk('plan 0 = unlimited', st()['plannedMatches'] == 0)
finally:
    try: host.kill()
    except Exception: pass
    time.sleep(0.5); print(out()[-1500:].encode("ascii","replace").decode()) if fails else None; shutil.rmtree(d, True)
print(('FAIL ' + '; '.join(fails) if fails else 'PASS round').encode('ascii','replace').decode()); sys.exit(1 if fails else 0)
