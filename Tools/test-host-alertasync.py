"""(1) Alert actions no longer wait the 10 s of the Latest Group popup: a cheer ran 10.2 s (a second cheer queued behind it); the popup runs in the background (wait:false), old saved actions are migrated once.
(2) The live chat recording survives a reader that locks the day file for a moment (write retries) and never makes its own readers lock it.  Usage: python Tools/test-host-alertasync.py [dll]"""
import ctypes, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, datetime
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8990; fails = []
d = tempfile.mkdtemp(prefix='pgal_')
json.dump({'Channel': 'alt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
old = {'version': 1, 'seeded': ['sbreplace2', 'alertsound1'], 'actions': [
    {'id': 'sb-cheer', 'name': 'Alert: cheer', 'enabled': True, 'triggers': [{'type': 'cheer'}], 'conditions': [], 'steps': [{'type': 'say', 'as': 'core', 'text': '{user} cheered {bits} bits!'}, {'type': 'run_action', 'name': 'Alerts: show Latest Group'}]},
    {'id': 'popup', 'name': 'Alerts: show Latest Group', 'enabled': True, 'triggers': [], 'conditions': [], 'steps': [{'type': 'delay', 'ms': 3000}]}]}
json.dump(old, open(os.path.join(d, 'automations.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
def api(p): return json.load(urllib.request.urlopen('http://127.0.0.1:%d%s' % (PORT, p), timeout=15))
def feed(l): host.stdin.write(l + '\n'); host.stdin.flush()
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(60):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    doc = api('/api/automations')['doc']; cheer = [a for a in doc['actions'] if a['id'] == 'sb-cheer'][0]
    chk('old saved cheer action migrated to a background popup', [s for s in cheer['steps'] if s['type'] == 'run_action'][0].get('wait') is False, cheer['steps'])
    feed('event TwitchCheer cy 300'); feed('event TwitchCheer dee 200'); time.sleep(1.5)
    runs = api('/api/automations/log?n=50')['runs']; ch = [r for r in runs if r['id'] == 'sb-cheer']
    chk('both cheers finished at once (not queued behind a 3 s popup)', len(ch) == 2 and all(r['ms'] < 1500 for r in ch), [(r['id'], r['ms']) for r in runs])
    time.sleep(6.5); runs = api('/api/automations/log?n=50')['runs']; pop = [r for r in runs if r['id'] == 'popup']
    chk('the popup still ran for both, one after the other (own lock)', len(pop) == 2 and all(r['ms'] >= 2900 for r in pop), [(r['id'], r['ms']) for r in runs])
    # live chat recording while another process holds the day file with a read-only share for 80 ms
    day = os.path.join(d, 'chat_logs', 'live', datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d') + '.jsonl')
    feed('zed: first line'); time.sleep(1.0); chk('day file written', os.path.exists(day))
    k = ctypes.windll.kernel32; k.CreateFileW.restype = ctypes.c_void_p
    h = k.CreateFileW(day, 0x80000000, 1, None, 3, 0x80, None)   # GENERIC_READ, FILE_SHARE_READ only: a writer is locked out
    chk('lock taken', h not in (None, ctypes.c_void_p(-1).value))
    threading.Timer(0.08, lambda: k.CloseHandle(ctypes.c_void_p(h))).start()
    feed('zed: second line'); time.sleep(1.5)
    lines = open(day, encoding='utf-8').read().splitlines(); chk('line written after the short lock (retry)', len(lines) == 2 and 'second line' in lines[1], lines)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS alertasync'); sys.exit(1 if fails else 0)
