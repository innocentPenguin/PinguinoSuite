"""Raid flow + links + hide-my-page removal (sim Host):
 - the Host's self-test ('alerttest'): raid lines at once, goodnight held while a raid is pending, released on raid_out / !unraid / after the max hold
 - seeded 'Raid scheduled' = shoutout, emotes, Discord ({link:discord}); no hardcoded invite left in the saved actions (the stale one is migrated)
 - /api/links follows the site (fake site up, then down: last good copy stays)
 - hidden_pages.json is backed up and cleared at start; page_hide is ignored
Usage: python Tools/test-host-raidflow.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, glob
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 9071; B = 'http://127.0.0.1:%d' % PORT; SITE = 9073
d = tempfile.mkdtemp(prefix='pgrf_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'runtime'), exist_ok=True)
# an install that still has the expired invite saved in an action
OLD = 'https://discord.gg/be6bus4GKh'
json.dump({'seeded': [], 'actions': [{'id': 'mine', 'name': 'mine', 'enabled': True, 'triggers': [{'type': 'command', 'command': '!x'}], 'steps': [{'type': 'say', 'as': 'core', 'text': 'join ' + OLD}]}]}, open(os.path.join(d, 'automations.json'), 'w'))
os.makedirs(os.path.join(d, 'economy'), exist_ok=True)
json.dump(['bob', 'Carol'], open(os.path.join(d, 'economy', 'hidden_pages.json'), 'w'))
import datetime
json.dump({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'ctx': {'channel': 'innocentpenguin_'}}, open(os.path.join(d, 'held_offline.json'), 'w'))   # a goodnight held when the Host went down
state = {'up': True, 'discord': 'https://discord.gg/fromsite1'}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if not state['up']: self.send_response(503); self.end_headers(); return
        b = json.dumps({'discord': state['discord'], 'twitch_clips': 'https://clips.example/x', 'bad': 'javascript:alert(1)'}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '9072', 'PINGUINO_LINKS_URL': 'http://127.0.0.1:%d/api/links' % SITE})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def out(): return open(outf, encoding='utf-8', errors='replace').read()
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=8))
def waitfor(f, secs=20):
    t = time.time()
    while time.time() - t < secs:
        try:
            if f(): return True
        except Exception: pass
        time.sleep(0.4)
    return False
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    chk('host up', waitfor(lambda: get('/api/status'), 60))
    chk('links follow the site', waitfor(lambda: get('/api/links')['links']['discord'] == 'https://discord.gg/fromsite1'), get('/api/links').get('links'))
    lk = get('/api/links')['links']
    chk('other site keys arrive, non-http values are refused', lk.get('twitch_clips') == 'https://clips.example/x' and 'bad' not in lk, lk)
    state['up'] = False; time.sleep(4.5)
    chk('site down: the last good copy stays', get('/api/links')['links']['discord'] == 'https://discord.gg/fromsite1')
    state['up'] = True; state['discord'] = 'https://discord.gg/fromsite2'
    chk('site back with a new invite', waitfor(lambda: get('/api/links')['links']['discord'] == 'https://discord.gg/fromsite2'))
    acts = json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8'))['actions']
    txt = json.dumps(acts)
    chk('no stale invite left in saved actions', 'be6bus4GKh' not in txt)
    mine = [a for a in acts if a['id'] == 'mine'][0]
    chk('the user action now reads {link:discord}', mine['steps'][0]['text'] == 'join {link:discord}', mine['steps'])
    rs = [a for a in acts if a['id'] == 'sb-raidstart'][0]['steps']
    chk('raid scheduled: emotes, then the discord token, no shoutout of the target', all(s.get('type') != 'shoutout_queue' for s in rs) and 'Prepare your emotes' in rs[0]['text'] and rs[-1]['text'].endswith('{link:discord}'), [s.get('type') for s in rs])
    ro = [a for a in acts if a['id'] == 'sb-raidout'][0]['steps']
    chk('raid out: the !leftbehind line (no link), then stop stream', '!leftbehind' in ro[0]['text'] and 'http' not in ro[0]['text'] and 'link:discord' not in json.dumps(ro) and ro[-1].get('request') == 'StopStream', ro)
    chk('hidden flags cleared with a dated backup', not os.path.exists(os.path.join(d, 'economy', 'hidden_pages.json')) and glob.glob(os.path.join(d, 'economy', 'hidden_pages.json.before-unhide-*.bak')))
    bk = glob.glob(os.path.join(d, 'economy', 'hidden_pages.json.before-unhide-*.bak')); chk('the backup holds the 2 cleared flags', bk and len(json.load(open(bk[0]))) == 2, bk)
    def recovered(): return not os.path.exists(os.path.join(d, 'held_offline.json')) and any('held goodnight recovered' in open(f, encoding='utf-8', errors='replace').read() for f in glob.glob(os.path.join(d, '**', 'host.jsonl'), recursive=True))
    chk('a goodnight held before a restart is run at start and the marker removed', waitfor(recovered, 30))
    h.stdin.write(b'alerttest\n'); h.stdin.flush()
    chk('self-test finished', waitfor(lambda: '[alerttest] ' in out(), 60))
    bad = [l for l in out().splitlines() if 'FAIL' in l and 'alerttest' in l.lower() or l.strip().startswith('[alerttest] FAIL')]
    res = [l for l in out().splitlines() if '[alerttest]' in l]
    chk('self-test all pass (raid flow + offline hold)', any('ALL PASS' in l for l in res), res[-8:])
finally:
    h.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(str(f)[:400] for f in fails) if fails else 'PASS raidflow'); sys.exit(1 if fails else 0)
