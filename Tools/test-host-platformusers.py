"""platform_users.json is never wiped: a file that fails to parse is moved aside (.corrupt-*), the .bak is restored, writes are temp+replace with a .bak.
Usage: python Tools/test-host-platformusers.py [dll]"""
import glob, json, os, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, TOK = 8991, 'tok'
d = tempfile.mkdtemp(prefix='pgpu_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
good = {'yt:ucold': {'platform': 'youtube', 'name': 'OldViewer', 'id': 'UCold', 'seen': 1}}
open(os.path.join(d, 'platform_users.json'), 'w').write('{"yt:ucold": {"platform": "youtube", "na')   # cut off mid-write
json.dump(good, open(os.path.join(d, 'platform_users.json.bak'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8993', 'PINGUINO_MODULE_TOKEN': TOK})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
    if not ok: fails.append(n)
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    r = urllib.request.Request('http://127.0.0.1:%d/api/chat-in' % PORT, data=json.dumps({'platform': 'youtube', 'user': 'NewViewer', 'userId': 'UCnew', 'text': 'hello', 'msgId': 'm1'}).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK})
    urllib.request.urlopen(r, timeout=10); time.sleep(1.5)
    cor = glob.glob(os.path.join(d, 'platform_users.json.corrupt-*'))
    chk('the broken file is kept aside, not overwritten', len(cor) == 1 and open(cor[0]).read().endswith('"na'), cor)
    cur = json.load(open(os.path.join(d, 'platform_users.json')))
    chk('the .bak was restored and the new viewer added', 'yt:ucold' in cur and cur['yt:ucold']['name'] == 'OldViewer' and any(v['name'] == 'NewViewer' for v in cur.values()), cur)
    chk('no temp file left behind', not os.path.exists(os.path.join(d, 'platform_users.json.tmp')))
    chk('a .bak is kept on the next write', os.path.exists(os.path.join(d, 'platform_users.json.bak')))
finally:
    host.kill()
print('FAILS: %d' % len(fails)); sys.exit(1 if fails else 0)
