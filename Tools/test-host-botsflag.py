"""A bot's Enabled flag only changes through the Host's bots API / !pg command, each change is logged (who + when) in console/host.jsonl, other Host actions never touch it,
and an unreadable bots.json is reported once. Usage: python Tools/test-host-botsflag.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8933; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgbf_'); bj = os.path.join(d, 'bots.json'); hl = os.path.join(d, 'console', 'host.jsonl')
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def reg(): return json.load(open(bj, encoding='utf-8'))['Bots']
json.dump({'Bots': {r: {'Enabled': True, 'Title': r, 'Account': r, 'Sender': 'none'} for r in ('core', 'chat', 'helper')}}, open(bj, 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8934'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', os.environ.get('PG_SUITE', suite)], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def post(p, o):
    r = urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json'})
    try: return urllib.request.urlopen(r, timeout=15).read().decode('utf-8', 'replace')
    except Exception as e: return 'ERR ' + str(e)
def get(p):
    try: return urllib.request.urlopen(B + p, timeout=10).read().decode('utf-8', 'replace')
    except Exception as e: return 'ERR ' + str(e)
def feed(l, w=0.6): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
def logtxt(): return open(hl, encoding='utf-8', errors='replace').read() if os.path.exists(hl) else ''
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    time.sleep(1)
    # unrelated Host work leaves every flag on and logs nothing about the flag
    post('/api/bots', {'id': 'chat', 'settings': {}}); get('/api/bots'); get('/api/status'); feed('viewer1: hello'); feed('viewer2: !discord')
    chk('flags untouched by other work', all(v['Enabled'] for v in reg().values()), reg())
    chk('no "switched" line yet', 'switched ON' not in logtxt() and 'switched OFF' not in logtxt())
    post('/api/bots', {'id': 'chat', 'enabled': False}); time.sleep(0.5)
    chk('api off changes only chat', reg()['chat']['Enabled'] is False and reg()['helper']['Enabled'] and reg()['core']['Enabled'], reg())
    t = logtxt(); chk('api change logged with who', 'chat switched OFF (was on) by api' in t, t[-400:])
    post('/api/bots', {'id': 'chat', 'enabled': False}); time.sleep(0.4)
    chk('same value again: not logged twice', logtxt().count('chat switched OFF') == 1)
    feed('*mod1: !pg chat on'); time.sleep(0.5)
    chk('!pg on re-enables', reg()['chat']['Enabled'] is True, reg())
    chk('!pg change logged with who', 'chat switched ON (was off) by !pg chat command' in logtxt(), logtxt()[-400:])
    # an unreadable bots.json is reported once per distinct problem
    open(bj, 'w').write('{ not json'); get('/api/bots'); get('/api/bots'); time.sleep(0.5)
    chk('unreadable bots.json warned once', logtxt().count('bots.json could not be read') == 1, logtxt().count('bots.json could not be read'))
except Exception as e:
    fails.append('exc '+str(e)); print(open(os.path.join(d,'out.txt'),errors='replace').read()[-1500:])
finally:
    host.terminate()
    try: host.wait(10)
    except Exception: host.kill()
    shutil.rmtree(d, ignore_errors=True)
print('FAIL: ' + '; '.join(fails) if fails else 'PASS botsflag'); sys.exit(1 if fails else 0)
