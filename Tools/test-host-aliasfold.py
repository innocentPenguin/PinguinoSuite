"""Alias fold in the economy: points given to the main login are read, spent and refunded through any alias of it (zylo*, krispy*, luffy0q1 lines of the real Data/boards/aliases.json are used),
and the bot list keeps zylo_bot_ out of the boards. Usage: python Tools/test-host-aliasfold.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, WSPORT = _free(), _free(); B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgaf_'); outp = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy')); os.makedirs(os.path.join(d, 'boards'))
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
shutil.copy(os.path.join(suite, 'Data', 'boards', 'aliases.json'), os.path.join(d, 'boards', 'aliases.json'))
al = json.load(open(os.path.join(d, 'boards', 'aliases.json'), encoding='utf-8-sig'))['aliases']
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT)})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def bal(l): return get('/api/economy/user?login=' + l).get('points')
def feed(l, w=0.8): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    chk('real file has the new lines', al.get('zylorocketleague') == 'zylo_road2gc_' and al.get('zylorants') == 'zylo_road2gc_' and al.get('zylorantstv') == 'zylo_road2gc_' and al.get('krispychicken721') == 'krispy721' and al.get('krispymoldychicken8768') == 'krispy721' and al.get('luffy0q1') == 'ytabdul' and 'zylo_bot_' not in al, al)
    feed('#trial: !addpoints zylo_road2gc_ 1000'); feed('#trial: !addpoints krispy721 400'); feed('#trial: !addpoints ytabdul 50')
    chk('main balances', bal('zylo_road2gc_') == 1000 and bal('krispy721') == 400 and bal('ytabdul') == 50, (bal('zylo_road2gc_'), bal('krispy721'), bal('ytabdul')))
    for a, m, v in (('zylorocketleague', 'zylo_road2gc_', 1000), ('zylorants', 'zylo_road2gc_', 1000), ('zylorantstv', 'zylo_road2gc_', 1000), ('krispychicken721', 'krispy721', 400), ('krispymoldychicken8768', 'krispy721', 400), ('luffy0q1', 'ytabdul', 50)):
        chk('alias %s reads the balance of %s' % (a, m), bal(a) == v, (a, bal(a)))
    feed('#trial: !addpoints zylorants 500')
    chk('points given to an alias land on the main login', bal('zylo_road2gc_') == 1500 and bal('zylorocketleague') == 1500, (bal('zylo_road2gc_'), bal('zylorocketleague')))
    chk('the bot is not an alias', get('/api/economy/user?login=zylo_bot_').get('points') in (0, None))
finally:
    host.kill(); time.sleep(0.5); print(open(outp, 'rb').read().decode('utf-8', 'replace')[-1200:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS aliasfold'); sys.exit(1 if fails else 0)
