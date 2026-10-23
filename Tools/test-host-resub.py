"""Live resub keeps the sub master + viewer profile fresh (sim Host, temp data): EventSub channel.subscription.message -> roles.subMonths / subStreak, tenure only grows, same event id twice changes nothing,
new subscriber gets a master record, streak follows the event. Usage: python Tools/test-host-resub.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8982; d = tempfile.mkdtemp(prefix='pgrs_')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'subs')); os.makedirs(os.path.join(d, 'profiles'))
master = {'version': 1, 'lastExportAt': '', 'processed': {}, 'users': {'resubber': {'login': 'resubber', 'tier': 1, 'tenure': 10, 'streak': 4, 'subscribed': '2026-01-01T00:00:00Z', 'founder': False, 'subType': 'paid', 'lapsed': False}}}
json.dump(master, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
json.dump({'login': 'resubber', 'name': 'Resubber', 'roles': {'sub': True, 'subTier': 1, 'subMonths': 10, 'subStreak': 4}}, open(os.path.join(d, 'profiles', 'resubber.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8981', 'PINGUINO_SIM_SUBS': '1'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, str(x)[:300]))
def ev(login, tier, months, streak, eid):
    e = {'id': eid, 'user_login': login, 'tier': tier, 'cumulative_months': months, 'streak_months': streak, 'message': {'text': 'hi'}}
    h.stdin.write(('eventsub channel.subscription.message ' + json.dumps(e) + '\n').encode()); h.stdin.flush()
def M(): return json.load(open(os.path.join(d, 'subs', 'subscribers_master.json')))
def P(n='resubber'): return json.load(open(os.path.join(d, 'profiles', n + '.json')))['roles']
def wait(f, secs=15):
    for _ in range(secs * 4):
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.25)
    return False
try:
    time.sleep(6)
    ev('resubber', '2000', 11, 5, 'evt-1')
    chk('master tenure/streak/tier updated', wait(lambda: M()['users']['resubber']['tenure'] == 11), M()['users']['resubber'])
    u = M()['users']['resubber']; chk('streak and tier follow the event', u['streak'] == 5 and u['tier'] == 2, u)
    chk('profile roles carry subMonths/subStreak/subTier', wait(lambda: P()['subMonths'] == 11) and P()['subStreak'] == 5 and P()['subTier'] == 2 and P()['sub'] is True, P())
    ev('resubber', '1000', 11, 5, 'evt-1'); time.sleep(3)
    chk('same event id twice: no change (tier stays 2)', M()['users']['resubber']['tier'] == 2 and M()['resubSeen'].count('evt-1') == 1, M().get('resubSeen'))
    ev('resubber', '1000', 8, 2, 'evt-2'); time.sleep(3)
    u = M()['users']['resubber']; chk('tenure only grows (8 < 11 kept), streak takes the event value', u['tenure'] == 11 and u['streak'] == 2 and u['tier'] == 2, u)
    ev('newsub', '1000', 3, 3, 'evt-3'); time.sleep(3)
    chk('unknown subscriber gets a master record', 'newsub' in M()['users'] and M()['users']['newsub']['tenure'] == 3 and M()['users']['newsub']['lapsed'] is False, M()['users'].keys())
    chk('no profile file is invented for them', not os.path.exists(os.path.join(d, 'profiles', 'newsub.json')))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS resub'); sys.exit(1 if fails else 0)
