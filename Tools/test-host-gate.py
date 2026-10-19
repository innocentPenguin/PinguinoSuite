"""ChattyPinguino activity gate + pre-stream countdown in a sim Host. Usage: python Tools/test-host-gate.py [dll]"""
import datetime, json, os, subprocess, sys, tempfile, threading, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8899
d = tempfile.mkdtemp(prefix='pggate_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
goal = datetime.datetime.now() + datetime.timedelta(seconds=45)
json.dump({'LiveOnly': False, 'GateEnabled': True, 'GateQuietPerMin': 2, 'GateBusyPerMin': 6, 'GateWindowSec': 60, 'CountdownGoLiveAt': goal.strftime('%H:%M:%S'),
           'CountdownTimes': '20s,10s', 'CountdownLine': 'COUNT {left}', 'CountdownLineNow': 'GO NOW'}, open(os.path.join(d, 'chat_settings.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8900'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out = []; lock = threading.Lock()
def rd():
    for r in iter(host.stdout.readline, b''):
        with lock: out.append(r.decode('utf-8', 'replace').rstrip())
threading.Thread(target=rd, daemon=True).start()
def say(line, wait=1.2):
    with lock: n = len(out)
    host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait)
    with lock: return out[n:]
res = []
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    for i in range(8): say('viewer%d: hello everyone this is chat line %d' % (i, i), 0.3)
    o = say('*mod: !chatbot status', 1.5); t = ' | '.join(o)
    res.append(('status shows the gate busy', 'busy' in t))
    o = say('viewer1: @pinguinob0t hello there, are you awake?', 1.5)
    res.append(('busy: @mention gets no reply', not any(x.startswith('[say]') and 'COUNT' not in x for x in o)))
    o = say('*mod: !chatbot status', 1.5); t = ' | '.join(o)
    res.append(('skipped counter went up', ' 0 skipped' not in t and 'skipped' in t))
    o = say('*mod: !golive 23:59', 1.5)
    res.append(('!golive sets the override', any('Countdown set for 23:59' in x for x in o)))
    say('*mod: !golive off', 1.0)
    time.sleep(max(0, (goal - datetime.datetime.now()).total_seconds()) + 3)
    with lock: t = '\n'.join(out)
    res.append(('countdown 20 s line sent', 'COUNT 20 seconds' in t))
    res.append(('countdown 10 s line sent', 'COUNT 10 seconds' in t))
    res.append(('start line sent', 'GO NOW' in t))
    res.append(('each countdown line only once', t.count('COUNT 20 seconds') == 1 and t.count('GO NOW') == 1))
finally:
    host.kill()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
