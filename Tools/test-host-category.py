"""StreamCategory (HostCategory.cs): the Host writes Data/twitch_category.json {game, at, ok} for the bots. PINGUINO_TEST_CATEGORY makes it deterministic (no Helix):
a name -> ok:true with that game and a fresh unix time; empty -> ok:false, game "". Usage: python Tools/test-host-category.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8995; fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def run(cat):
    d = tempfile.mkdtemp(prefix='pgcat_')
    json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8996'; env['PINGUINO_TEST_CATEGORY'] = cat
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        f = os.path.join(d, 'twitch_category.json')
        for _ in range(60):
            if os.path.exists(f): break
            time.sleep(0.5)
        time.sleep(0.5)
        return json.load(open(f, encoding='utf-8-sig')) if os.path.exists(f) else None
    finally:
        h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
j = run('Fortnite')
chk('category file written', j is not None); 
if j: chk('Fortnite ok and fresh', j['game'] == 'Fortnite' and j['ok'] is True and abs(time.time() - j['at']) < 120, j)
j = run('')
chk('failed lookup: ok false, no game', j is not None and j['ok'] is False and j['game'] == '', j)
print('FAIL ' + '; '.join(fails) if fails else 'PASS category'); sys.exit(1 if fails else 0)
