"""Everything about music is said by PinguinoHelper (Ivan 10-24): a saved automations.json whose song presets say as core is migrated once (dated backup, marker songhelper1) to helper,
the "Skip Song" reward gets its preset (redeem, command skip, as helper), other module commands (speak) keep their sender, a fresh seed has no core/chat song say, and the Spotify announcement
relay setting reads helper even when an old file says core. Also a source scan: no module_command step in HostAuto.cs seeds says as core for a song command.
Usage: python Tools/test-host-songsender.py [dll]"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8991
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
SONG = {'sr', 'oops', 'blocksong', 'srclear', 'skip', 'song', 'queue', 'volume', 'last', 'pos'}
src = open(os.path.join(suite, 'PinguinoHost', 'HostAuto.cs'), encoding='utf-8-sig').read()
chk('source: no seeded song module_command says as core', not re.search(r'"command", (?:"(?:%s)"|cmd) \}[^\n]*\{ "as", "core" \}' % '|'.join(SONG), src))
chk('source: redeem seed for Song Request says helper', not re.search(r'"command", "sr" \}, \{ "redeem", true \}, \{ "as", "core" \}', src))
d = tempfile.mkdtemp(prefix='pgss_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
url = 'http://127.0.0.1:8771/api/chat-command'
def preset(i, cmd, names, as_): return {'id': 'spotify-' + i, 'name': i, 'group': 'Spotify', 'enabled': True, 'triggers': [{'type': 'command', 'names': names, 'permission': 'everyone', 'cooldownSec': 0, 'userCooldownSec': 0, 'consume': True}], 'conditions': [], 'steps': [{'type': 'module_command', 'url': url, 'command': cmd, 'as': as_}]}
speak = {'id': 'speak-redeem', 'name': 'Speak', 'enabled': True, 'triggers': [{'type': 'redeem', 'title': 'Speak'}], 'conditions': [], 'steps': [{'type': 'module_command', 'url': url, 'command': 'speak', 'redeem': True, 'as': 'core'}]}
old = {'actions': [preset('sr', 'sr', ['!sr'], 'core'), preset('oops', 'oops', ['!oops'], 'helper'), preset('block', 'blocksong', ['!blocksong'], 'core'), preset('clear', 'srclear', ['!srclear'], 'chat'), speak],
       'seeded': ['spotify', 'spotify-redeem', 'spotify2', 'musicoff1', 'speak']}
json.dump(old, open(os.path.join(d, 'automations.json'), 'w'))
json.dump({'Enabled': False, 'As': 'core'}, open(os.path.join(d, 'spotify_announce.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8993'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
    a = {x['id']: x for x in json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8-sig'))['actions']}
    as_ = lambda i: a[i]['steps'][0].get('as') if i in a else None
    chk('sr / oops / block / clear all helper', [as_(i) for i in ('spotify-sr', 'spotify-oops', 'spotify-block', 'spotify-clear')] == ['helper'] * 4, [as_(i) for i in ('spotify-sr', 'spotify-oops', 'spotify-block', 'spotify-clear')])
    chk('speak keeps its sender', as_('speak-redeem') == 'core', as_('speak-redeem'))
    sk = a.get('spotify-skip-redeem')
    chk('Skip Song redeem preset', sk and sk['triggers'][0].get('title') == 'Skip Song' and sk['steps'][0]['command'] == 'skip' and sk['steps'][0].get('redeem') is True and sk['steps'][0]['as'] == 'helper', sk)
    j = json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8-sig'))
    chk('marker and dated backup', 'songhelper1' in j['seeded'] and [f for f in os.listdir(d) if f.startswith('automations.json.before-songhelper-')], os.listdir(d))
    st = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/spotify-announce' % PORT, timeout=5))
    chk('announcement relay reads helper', st['settings']['As'] == 'helper', st)
    req = urllib.request.Request('http://127.0.0.1:%d/api/spotify-announce' % PORT, json.dumps({'As': 'core'}).encode(), {'Content-Type': 'application/json'})
    try: r = json.load(urllib.request.urlopen(req, timeout=5)); chk('saving core is forced to helper', r['settings']['As'] == 'helper', r)
    except Exception as e: chk('save announce', False, str(e))
    host.kill(); time.sleep(0.5)
    host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'ab'), stderr=subprocess.STDOUT)
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    j2 = json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8-sig'))
    chk('restart migrates nothing again', len([f for f in os.listdir(d) if f.startswith('automations.json.before-songhelper-')]) == 1 and [x['id'] for x in j2['actions'] if x['id'].startswith('spotify')] == [x['id'] for x in j['actions'] if x['id'].startswith('spotify')], os.listdir(d))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
# fresh seed
d = tempfile.mkdtemp(prefix='pgss2_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    bad = []
    for x in json.load(open(os.path.join(d, 'automations.json'), encoding='utf-8-sig'))['actions']:
        for s in x.get('steps', []):
            if s.get('type') == 'module_command' and s.get('command') in SONG and s.get('as', 'core') != 'helper': bad.append((x['id'], s.get('as')))
    chk('fresh seed: no song say as core/chat', not bad, bad)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS songsender'); sys.exit(1 if fails else 0)
