"""Actions & Events test for PinguinoHost: runs the Host in --sim mode on a temp folder, creates automations through the API and drives chat / events through stdin.
Usage: python Tools/test-host-auto.py [path-to-PinguinoHost.dll]"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8861; fails = []; MOCK_POSTS = []

class M(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj):
        d = json.dumps(obj).encode(); self.send_response(200); self.send_header('Content-Length', str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self): self._send({'say': 'from the mock site', 'n': 7})
    def do_POST(self):
        MOCK_POSTS.append(json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')); self._send({'ok': True, 'say': 'queued: ' + MOCK_POSTS[-1].get('args', '')})
srv = ThreadingHTTPServer(('127.0.0.1', 8862), M); threading.Thread(target=srv.serve_forever, daemon=True).start()

d = tempfile.mkdtemp(prefix='pgauto_')
json.dump({'Channel': 'autotest', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)

def api(path, body=None):
    rq = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def feed(line): host.stdin.write(line + '\n'); host.stdin.flush()
def runs(): return api('/api/automations/log?n=100')['runs']
def until(fn, secs, what):
    t = time.time() + secs
    while time.time() < t:
        try:
            if fn(): return True
        except Exception: pass
        time.sleep(0.3)
    fails.append('timeout: ' + what); return False
def said(text): return any(text in o for r in runs() for o in r.get('output', []))
def ran(name): return sum(1 for r in runs() if r['action'] == name and not r['test'])

try:
    until(lambda: api('/api/status')['name'] == 'PinguinoHost', 30, 'host up'); time.sleep(25)   # the bot modules finish loading a little after the API is up (slower when the PC is busy)
    seeded = api('/api/automations')['doc']
    if sum(1 for x in seeded['actions'] if x['id'].startswith('spotify-') and x['enabled'] is False) != 8: fails.append('spotify presets missing or enabled')
    acts = [
        {'id': 'lurk', 'name': 'Lurk', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!lurkx'], 'permission': 'everyone', 'cooldownSec': 30}],
         'steps': [{'type': 'inc_var', 'name': 'lurkers'}, {'type': 'say', 'as': 'core', 'text': 'Enjoy the lurk {user}! total {count}'}]},
        {'id': 'modonly', 'name': 'ModOnly', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!modonly'], 'permission': 'mod'}], 'steps': [{'type': 'say', 'text': 'mod command ok'}]},
        {'id': 'cheer', 'name': 'BigCheer', 'enabled': True, 'triggers': [{'type': 'cheer', 'min': 100}], 'steps': [{'type': 'say', 'text': 'thanks {user} for {bits} bits'}]},
        {'id': 'raid', 'name': 'RaidIn', 'enabled': True, 'triggers': [{'type': 'raid'}], 'conditions': [{'left': '{viewers}', 'op': '>=', 'right': '10'}],
         'steps': [{'type': 'if', 'left': '{viewers}', 'op': '>', 'right': '50', 'then': [{'type': 'say', 'text': 'huge raid'}], 'else': [{'type': 'say', 'text': 'nice raid {raider}'}]}, {'type': 'run_action', 'name': 'Helper'}]},
        {'id': 'helper', 'name': 'Helper', 'enabled': True, 'triggers': [{'type': 'manual'}], 'steps': [{'type': 'say', 'text': 'helper ran'}, {'type': 'stop'}, {'type': 'say', 'text': 'never said'}]},
        {'id': 'web', 'name': 'WebCall', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!site']}], 'steps': [
            {'type': 'http', 'method': 'GET', 'url': 'http://127.0.0.1:8862/x', 'say': True}, {'type': 'say', 'text': 'status {http.status} n={http.n}'},
            {'type': 'http', 'method': 'GET', 'url': 'http://example.com/', 'say': True}]},
        {'id': 'song', 'name': 'Song', 'enabled': True, 'triggers': [{'type': 'command', 'names': ['!sr']}], 'steps': [{'type': 'module_command', 'url': 'http://127.0.0.1:8862/api/chat-command', 'command': 'sr'}]},
        {'id': 'off', 'name': 'Disabled', 'enabled': False, 'triggers': [{'type': 'command', 'names': ['!off']}], 'steps': [{'type': 'say', 'text': 'should not run'}]},
    ]
    r = api('/api/automations', {'doc': {'version': 1, 'actions': acts}});
    if not r.get('ok'): fails.append('save: ' + str(r))
    if api('/api/automations/log')['runs']: fails.append('log should start empty')

    feed('viewer: !lurkx'); until(lambda: said('Enjoy the lurk viewer! total 1'), 10, 'command ran with variables')
    feed('viewer2: !lurkx'); time.sleep(1.5)
    if ran('Lurk') != 1: fails.append('global cooldown: Lurk ran %d times' % ran('Lurk'))
    feed('viewer: !modonly'); time.sleep(1.5)
    if ran('ModOnly') != 0: fails.append('mod command ran for a viewer')
    feed('*mod1: !modonly'); until(lambda: said('mod command ok'), 10, 'mod command ran for a mod')
    feed('viewer: !off'); time.sleep(1.0)
    if said('should not run'): fails.append('disabled action ran')
    feed('event TwitchCheer bob 50'); time.sleep(1.0)
    if ran('BigCheer') != 0: fails.append('cheer below min ran')
    feed('event TwitchCheer bob 500'); until(lambda: said('thanks bob for 500 bits'), 10, 'cheer trigger with {bits}')
    feed('event TwitchRaid ann 5'); time.sleep(1.0)
    if said('nice raid') or said('huge raid'): fails.append('raid condition (>=10) did not block 5 viewers')
    feed('event TwitchRaid ann 20'); until(lambda: said('nice raid ann') and said('helper ran'), 10, 'raid: else branch + run_action')
    if said('never said'): fails.append('stop step did not stop')
    feed('event TwitchRaid ann 80'); until(lambda: said('huge raid'), 10, 'raid: then branch')
    feed('viewer: !site'); until(lambda: said('status 200 n=7'), 10, 'http step saved the answer as variables')
    if not said('from the mock site'): fails.append('http say field not said')
    if not said('http blocked'): fails.append('external URL was not blocked')
    feed('viewer3: !sr never gonna give you up')
    until(lambda: said('queued: never gonna give you up'), 10, 'module command round trip')
    if not MOCK_POSTS or MOCK_POSTS[0].get('command') != 'sr' or MOCK_POSTS[0].get('user') != 'viewer3': fails.append('module command body: ' + str(MOCK_POSTS[:1]))
    elif MOCK_POSTS[0].get('subTier') != 0 or MOCK_POSTS[0].get('isVip') is not False: fails.append('module command body lacks subTier/isVip: ' + str(MOCK_POSTS[:1]))

    t = api('/api/automations/test', {'id': 'lurk'})
    if not t.get('ok') or not any('(dry run) would say' in o for o in t['run']['output']): fails.append('dry run: ' + str(t))
    if api('/api/automations/test', {'id': 'nope'}).get('ok'): fails.append('test of an unknown action should fail')
    bad = api('/api/automations', {'doc': {'actions': [{'name': 'x', 'triggers': [{'type': 'chat', 'pattern': '(['}]}]}})
    if bad.get('ok'): fails.append('invalid regex was accepted')

    # Streamer.bot import (only if the data folder exists on this machine)
    p = api('/api/automations/import', {'mode': 'preview'})
    if p.get('ok'):
        txt = json.dumps(p)
        if 'sk-' in txt: fails.append('import preview leaked a key-like string')
        m = api('/api/automations/import', {'mode': 'merge'})
        doc = api('/api/automations')['doc']
        imp = [a for a in doc['actions'] if a.get('imported')]
        if m['added'] != len(imp) or any(a.get('enabled') for a in imp): fails.append('imported actions must be added disabled')
        if 'sk-' in json.dumps(doc): fails.append('import copied a key-like string')
finally:
    try: host.stdin.close()
    except Exception: pass
    try: host.kill()
    except Exception: pass
print('HOST AUTO: ' + ('PASS' if not fails else 'FAIL - ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
