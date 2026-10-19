"""Chat-rate history + auto limits for ChattyPinguino in a sim Host. Usage: python Tools/test-host-rate.py [dll]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8901
d = tempfile.mkdtemp(prefix='pgrate_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'LiveOnly': False, 'GateEnabled': True, 'GateAuto': True, 'GateAutoQuietPct': 40, 'GateAutoBusyPct': 250, 'GateAutoMinMinutes': 60}, open(os.path.join(d, 'chat_settings.json'), 'w'))
json.dump({'WasLive': True}, open(os.path.join(d, 'settings.json'), 'w'))
streams = [{'start': 1000 + i * 100000, 'end': 1000 + i * 100000 + 3600, 'total': 600, 'perMinute': [10] * 60} for i in range(3)]
json.dump({'streams': streams}, open(os.path.join(d, 'chat_rate_history.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8902'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out = []; lock = threading.Lock()
def rd():
    for r in iter(host.stdout.readline, b''):
        with lock: out.append(r.decode('utf-8', 'replace').rstrip())
threading.Thread(target=rd, daemon=True).start()
def say(line, wait=1.0):
    with lock: n = len(out)
    host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait)
    with lock: return out[n:]
def rate(): return json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/chat-rate' % PORT, timeout=5))
res = []
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(11)   # the Host starts its chat ticker after ~8 s; the stream is then noticed as live
    for i in range(6): say('viewer%d: hello chat line %d' % (i, i), 0.2)
    t = ' | '.join(say('*mod: !chatbot status', 1.5))
    res.append(('auto limits from history (avg 10/min -> 4/25)', 'limits 4/25 auto' in t))
    time.sleep(70)   # the history file is written once a minute
    j = rate(); st = j['stats']
    res.append(('API: a live stream is being recorded (end 0)', len(j['streams']) == 4 and j['streams'][-1]['end'] == 0 and j['streams'][-1]['total'] >= 6))
    res.append(('API: stats with average, hourly table and limits', st['streams'] == 4 and st['avgPerMin'] > 0 and len(st['perHour']) >= 1 and st['effective']['auto'] is True))
finally:
    host.kill()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
