"""Overlay assistant (Plan 6 part D) against a fake Claude API and a fake site: new files apply at once, replacing needs Apply, undo, tool limits (traversal refused), off switch, no key,
daily cap, key never logged, and the site bridge round trip (poll pending -> answer -> reply posted once).  Usage: python Tools/test-host-overlaychat.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, CL, SITE = 8986, 8987, 8988; B = 'http://127.0.0.1:%d' % PORT; KEY = 'sk-test-SECRETKEY-123'; SITEKEY = 'site-test-KEY-456'
d = tempfile.mkdtemp(prefix='pgoch_'); ov = os.path.join(d, 'ov'); os.makedirs(ov); open(os.path.join(ov, 'queue.html'), 'w').write('<h1>queue</h1>\n<p>old</p>')
json.dump({'OverlayDir': ov, 'WebSyncKey': SITEKEY}, open(os.path.join(d, 'settings.json'), 'w')); json.dump({'Channel': 'ovc', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'config')); cfgp = os.path.join(d, 'config', 'overlaychat.json')
def setcfg(**kw):
    c = {'enabled': True, 'model': 'claude-test', 'dailyCalls': 40, 'maxTokens': 1000}; c.update(kw); json.dump(c, open(cfgp, 'w'))
setcfg()
seen = {'models': [], 'keys': [], 'tools': None, 'replies': [], 'siteauth': []}
pending_site = [{'id': 'm1', 'user': 'ivan', 'text': 'make a goal bar'}]
class Claude(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length']))); seen['keys'].append(self.headers.get('x-api-key')); seen['tools'] = [t['name'] for t in b['tools']]; seen['models'].append(b['model'])
        msgs = b['messages']; first = msgs[0]['content']; results = [c for m in msgs if isinstance(m['content'], list) for c in m['content'] if c.get('type') == 'tool_result']; n = len(results)
        def tool(name, inp, tid): return {'content': [{'type': 'text', 'text': 'working'}, {'type': 'tool_use', 'id': tid, 'name': name, 'input': inp}], 'stop_reason': 'tool_use'}
        def text(t): return {'content': [{'type': 'text', 'text': t}], 'stop_reason': 'end_turn'}
        if 'goal bar' in first: out = tool('write_file', {'path': 'goal/goal.html', 'content': '<div style="background:#111;color:#f60">goal</div>'}, 't1') if n == 0 else text('Created the goal bar.')
        elif 'change queue' in first: out = tool('read_file', {'path': 'queue.html'}, 't1') if n == 0 else tool('write_file', {'path': 'queue.html', 'content': '<h1>queue</h1>\n<p>NEW orange</p>'}, 't2') if n == 1 else text('I prepared a change; apply it to use it.')
        elif 'undo queue' in first: out = tool('undo_file', {'path': 'queue.html'}, 't1') if n == 0 else text('Restored.')
        elif 'escape' in first: out = tool('write_file', {'path': '../evil.html', 'content': 'x'}, 't1') if n == 0 else tool('read_file', {'path': 'C:\\Windows\\win.ini'}, 't2') if n == 1 else tool('write_file', {'path': 'secrets.json', 'content': '{}'}, 't3') if n == 2 else text('Refused: ' + '|'.join(r['content'][:30] for r in results))
        else: out = text('hello')
        o = json.dumps(out).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
class Site(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        seen['siteauth'].append(self.headers.get('Authorization')); o = json.dumps({'items': pending_site}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(o))); self.end_headers(); self.wfile.write(o)
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length']))); seen['replies'].append(b); self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
for port, h in ((CL, Claude), (SITE, Site)): threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', port), h).serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8989', 'PINGUINO_ANTHROPIC_BASE': 'http://127.0.0.1:%d' % CL, 'ANTHROPIC_API_KEY': KEY, 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'PINGUINO_SITE_POLL_SEC': '1'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def post(path, body): return json.load(urllib.request.urlopen(urllib.request.Request(B + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B}), timeout=60))
def up():
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); return
        except Exception: time.sleep(0.5)
def start(e): return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=e, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
qf = os.path.join(ov, 'queue.html'); host = None
try:
    host = start(dict(env, PINGUINO_SITE_BASE='http://127.0.0.1:1')); up(); time.sleep(1)   # site unreachable for the first part
    r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'hi'}); chk('plain answer', r['ok'] and r['text'] == 'hello', r)
    chk('only the four tools, key and model sent', seen['tools'] == ['list_files', 'read_file', 'write_file', 'undo_file'] and seen['keys'][-1] == KEY and seen['models'][-1] == 'claude-test', (seen['tools'], seen['models']))
    r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'make a goal bar'}); chk('new file applies at once', r['ok'] and r['files'] == [{'path': 'goal/goal.html', 'created': True}] and os.path.exists(os.path.join(ov, 'goal', 'goal.html')), r)
    r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'change queue to orange'}); chk('replace only proposes', r['ok'] and len(r['proposals']) == 1 and open(qf).read() == '<h1>queue</h1>\n<p>old</p>', r)
    pr = r['proposals'][0]; chk('proposal has a diff', '+1 / -1' in pr['diff'] and '+ <p>NEW orange</p>' in pr['diff'] and '- <p>old</p>' in pr['diff'], pr)
    a = post('/api/overlaychat/apply', {'id': pr['id'], 'user': 'ivan'}); chk('apply writes it', a['ok'] and 'NEW orange' in open(qf).read(), a)
    a = post('/api/overlaychat/apply', {'id': pr['id'], 'user': 'ivan'}); chk('a proposal applies once', a['ok'] is False, a)
    a = post('/api/overlaychat/apply', {'id': 'nope', 'user': 'ivan'}); chk('unknown proposal', a['ok'] is False, a)
    r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'undo queue'}); chk('undo restores the old file', r['ok'] and open(qf).read() == '<h1>queue</h1>\n<p>old</p>', (r, open(qf).read()))
    r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'escape the folder'}); t = r['text']
    chk('traversal, drive path and protected names are refused', r['ok'] and t.count('error') == 3 and not os.path.exists(os.path.join(d, 'evil.html')) and not os.path.exists(os.path.join(ov, 'secrets.json')), t)
    st = json.load(urllib.request.urlopen(B + '/api/overlaychat/status', timeout=5)); chk('status', st['enabled'] and st['hasKey'] and st['callsToday'] >= 8 and 'ANTHROPIC' not in json.dumps(st), st)
    setcfg(enabled=False); r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'hi'}); chk('off switch', r['ok'] is False and 'switched off' in r['error'], r)
    setcfg(dailyCalls=st['callsToday'] + 1); r = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'hi'}); r2 = post('/api/overlaychat/ask', {'user': 'ivan', 'text': 'hi'})
    chk('daily cap stops the calls', r['ok'] and r2['ok'] is False and 'daily limit' in r2['error'], (r, r2))
    logs = ''.join(open(os.path.join(r_, f), encoding='utf-8', errors='replace').read() for r_, _, fs in os.walk(d) for f in fs if f.endswith(('.jsonl', '.log')))
    chk('the key never reaches a log', KEY not in logs and SITEKEY not in logs)
    chk('chat log written', os.path.exists(os.path.join(d, 'runtime', 'overlaychat.jsonl')))
    # bridge
    host.kill(); host.wait(); setcfg(); os.remove(os.path.join(d, 'runtime', 'overlaychat_usage.json'))
    host = start(env); up()
    for _ in range(30):
        if seen['replies']: break
        time.sleep(1)
    chk('bridge answers the pending message', seen['replies'] and seen['replies'][0]['id'] == 'm1' and 'goal bar' in seen['replies'][0]['reply']['text'].lower() or (seen['replies'] and seen['replies'][0]['reply']['files']), seen['replies'][:1])
    chk('bridge used the site key', 'Bearer ' + SITEKEY in seen['siteauth'], seen['siteauth'][:2])
    n = len(seen['models']); time.sleep(3.5); chk('the same message is not asked twice', len(seen['models']) == n, (n, len(seen['models'])))
finally:
    if host: host.kill()
    time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS overlay chat')
sys.exit(1 if fails else 0)
