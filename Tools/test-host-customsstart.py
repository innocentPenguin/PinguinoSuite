"""Customs start chat output: first line EXACTLY "Starting customs! The queue is open!" (!queue open and !activity casual/competitive/koth/viewers), then the !pmrules text as a SEPARATE second message
(queue_open automation, after the first line), no "Waiting for players" / "NOW PLAYING" text; KOTH keeps its note as its own line after. One Host per case (Core drops the same line said within 30 s).
Usage: python Tools/test-host-customsstart.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
FIRST = 'Starting customs! The queue is open!'
RULES = 'Private match rules!'
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def run(cmd, port, koth=False):
    d = tempfile.mkdtemp(prefix='pgcs_'); outp = os.path.join(d, 'out.txt')
    json.dump({'Channel': 'trial', 'OverlayPort': port}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = str(port + 1); env['PINGUINO_DUP_SECONDS'] = '1'
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
    def feed(l, w): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
    def out(): return open(outp, 'rb').read().decode('utf-8', 'replace')
    try:
        for _ in range(60):
            try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=3); break
            except Exception: time.sleep(0.5)
        time.sleep(4); feed('#trial: !queue close', 3); o0 = len(out()); feed('#trial: ' + cmd, 8); o = out()[o0:]
        runs = [r for r in json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/automations/log?n=200' % port, timeout=10)).get('runs', []) if r['id'] == 'rules' and 'queue_open' in r['trigger']]
        rules_out = ' '.join(' '.join(r['output']) for r in runs)
        chk(cmd + ': first line exact, once', o.count('[say] ' + FIRST) == 1, o[-500:])
        chk(cmd + ': rules line ran once as its own queue_open message (not in the first line)', len(runs) == 1 and RULES in rules_out and RULES not in FIRST, (runs, rules_out[:200]))
        chk(cmd + ': no old text', all(t not in o for t in ('NOW PLAYING', 'Waiting for players', 'now OPEN')), o[-500:])
        if koth: chk('koth: its own note comes after the first line', 'KING OF THE HILL' in o and o.index('KING OF THE HILL') > o.index(FIRST), o[-600:])
    finally:
        host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for i, (cmd, k) in enumerate([('!queue open', False), ('!activity casual', False), ('!activity competitive', False), ('!activity viewers', False), ('!activity koth', True)]):
    run(cmd, 8990 + i * 2, k)
print('FAIL ' + '; '.join(fails) if fails else 'PASS customsstart'); sys.exit(1 if fails else 0)
