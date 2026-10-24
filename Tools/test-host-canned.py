"""Canned-command editor API (/api/canned): list, set text, enable/disable, aliases, add, validation, test line, cooldown, backup, delete, export and the write gate.
Usage: python Tools/test-host-canned.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8992; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcanned_'); outf = os.path.join(d, 'out.txt'); cf = os.path.join(d, 'canned.json')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'CannedFile': cf}, open(os.path.join(d, 'chat_settings.json'), 'w'))
json.dump({'_note': 'keep me', 'cooldownSec': 20, 'commands': [
    {'name': 'hug', 'text': '$(user) hugs $(touser)!'},
    {'name': 'luck', 'aliases': ['lucky'], 'text': 'You got $(luck)% luck'},
    {'name': 'old', 'text': 'old joke', 'enabled': False}]}, open(cf, 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8995'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', n, '|', extra)
def post(**b): return api('/api/canned', b)
try:
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    r = api('/api/canned'); chk('list has the three commands', r['ok'] and [c['name'] for c in r['commands']] == ['hug', 'luck', 'old'], r)
    chk('disabled one is shown as disabled', [c['enabled'] for c in r['commands']] == [True, True, False], r)
    r = post(action='test', name='hug', user='Ivan', touser='@Bobby'); chk('test line fills in user and touser', r['ok'] and r['line'] == 'Ivan hugs Bobby!', r)
    r = post(action='test', name='hug', user='Ivan', touser='https://evil.example'); chk('test line: a link as target falls back to the sender', r['ok'] and 'http' not in r['line'] and r['line'] == 'Ivan hugs Ivan!', r)
    r = post(action='test', text='You got $(luck)%', user='A'); chk('test luck number', r['ok'] and r['line'].startswith('You got ') and r['line'].endswith('%'), r)
    chk('a test never changes the file', json.load(open(cf))['commands'][0]['text'] == '$(user) hugs $(touser)!')
    r = post(action='set', name='hug', text='$(user) squeezes $(touser) tight!'); chk('set text', r['ok'] and r['command']['text'] == '$(user) squeezes $(touser) tight!', r)
    j = json.load(open(cf)); chk('file updated, other keys and entries kept', j['commands'][0]['text'].startswith('$(user) squeezes') and j['_note'] == 'keep me' and len(j['commands']) == 3, j)
    chk('previous file kept as .bak', os.path.exists(cf + '.bak') and json.load(open(cf + '.bak'))['commands'][0]['text'] == '$(user) hugs $(touser)!')
    r = post(action='set', name='hug', enabled=False); chk('disable', r['ok'] and r['command']['enabled'] is False and json.load(open(cf))['commands'][0].get('enabled') is False, r)
    r = post(action='set', name='hug', enabled=True); chk('enable again', r['ok'] and 'enabled' not in json.load(open(cf))['commands'][0], r)
    r = post(action='set', name='luck', aliases=['lucky', 'dice']); chk('aliases set', r['ok'] and json.load(open(cf))['commands'][1]['aliases'] == ['lucky', 'dice'], r)
    r = post(action='set', name='hug', aliases=['dice']); chk('alias already used by another command is refused', not r['ok'], r)
    r = post(action='set', name='hug', aliases=['ban']); chk('alias of a real command is refused', not r['ok'], r)
    r = post(action='add', name='tuck2', text='$(user) tucks $(touser) in!'); chk('add a command', r['ok'] and json.load(open(cf))['commands'][-1]['name'] == 'tuck2', r)
    r = post(action='add', name='tuck2', text='x'); chk('adding a duplicate is refused', not r['ok'], r)
    r = post(action='add', name='ban', text='nope'); chk('a real command name cannot be taken', not r['ok'], r)
    r = post(action='add', name='Bad Name', text='x'); chk('bad name refused', not r['ok'], r)
    for bad in ('/ban x', '!raid now', '.me hi', '', 'line\nbreak', 'x' * 401, 'hello $(evil) there'):
        r = post(action='set', name='hug', text=bad); chk('bad text refused: %r' % bad[:12], not r['ok'], r)
    chk('after the refusals the text is unchanged', json.load(open(cf))['commands'][0]['text'] == '$(user) squeezes $(touser) tight!')
    r = post(action='set', name='luck', choices=['one $(user)', 'two $(user)']); j = json.load(open(cf))['commands'][1]; chk('choices replace the text', r['ok'] and j.get('choices') == ['one $(user)', 'two $(user)'] and 'text' not in j, j)
    r = post(action='set', name='nope', text='x'); chk('unknown command refused', not r['ok'], r)
    r = post(action='cooldown', seconds=3); chk('cooldown out of range refused', not r['ok'], r)
    r = post(action='cooldown', seconds=45); chk('cooldown set', r['ok'] and json.load(open(cf))['cooldownSec'] == 45, r)
    r = post(action='bogus'); chk('unknown action refused', not r['ok'], r)
    chk('nothing is deleted by the other actions', {c['name'] for c in json.load(open(cf))['commands']} >= {'hug', 'luck', 'old', 'tuck2'})
    r = post(action='set', name='hug', text='tab' + chr(9) + 'here'); chk('control character in the text refused', not r['ok'], r)
    r = post(action='add', name='ctl', text='bell' + chr(7)); chk('control character on add refused', not r['ok'], r)
    for hostcmd in ('gamble', 'slots', 'duel', 'emote', 'alert'):
        r = post(action='add', name=hostcmd, text='nope'); chk('a Host command name cannot be taken: ' + hostcmd, not r['ok'], r)
    r = post(action='set', name='luck', aliases=['lucky', 'bet']); chk('an alias of a Host command is refused', not r['ok'], r)
    r = api('/api/canned?export=1'); chk('export: ok, version, rules, variables and every command as stored', r['ok'] and r['version'] == 1 and r['rules']['maxTextLength'] == 400 and '$(user)' in r['variables'] and {c['name'] for c in r['commands']} >= {'hug', 'luck', 'old', 'tuck2'} and 'ban' in r['rules']['reservedNames'], r)
    chk('export keeps stored fields (aliases / enabled false)', any(c['name'] == 'old' and c.get('enabled') is False for c in r['commands']))
    r = post(action='delete', name='tuck2'); chk('delete removes the command', r['ok'] and r['deleted'] == 'tuck2' and 'tuck2' not in {c['name'] for c in json.load(open(cf))['commands']}, r)
    chk('delete keeps the previous file as .bak', 'tuck2' in {c['name'] for c in json.load(open(cf + '.bak'))['commands']})
    r = post(action='delete', name='tuck2'); chk('deleting an unknown command is refused', not r['ok'], r)
    r = post(action='delete', name='Bad Name'); chk('delete with a bad name is refused', not r['ok'], r)
    chk('other entries survive a delete', {c['name'] for c in json.load(open(cf))['commands']} >= {'hug', 'luck', 'old'})
    try:
        urllib.request.urlopen(urllib.request.Request(B + '/api/canned', data=json.dumps({'action': 'cooldown', 'seconds': 30}).encode(), headers={'Content-Type': 'application/json', 'Origin': 'tauri://localhost'}), timeout=30); chk('a write from the shell without the token is refused', False)
    except urllib.error.HTTPError as e: chk('a write from the shell without the token is refused', e.code == 401, e.code)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
bad = [n for n, ok in res if not ok]
print('FAIL ' + '; '.join(bad) if bad else 'PASS canned editor (%d checks)' % len(res))
