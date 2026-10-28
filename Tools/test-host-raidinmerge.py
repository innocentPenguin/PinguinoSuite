"""Incoming-raid action (sb-raid): thanks, emote row and welcome are ONE chat message. Fresh seed + migration of a saved 3-say layout (sim mode, temp folder).
Usage: python Tools/test-host-raidinmerge.py [path-to-PinguinoHost.dll]"""
import json, os, subprocess, sys, tempfile, time, urllib.request, glob
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
    if not ok: fails.append(n)
def run(port, pre):
    d = tempfile.mkdtemp(prefix='pgrim_')
    json.dump({'Channel': 'rimtest', 'OverlayPort': port}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    if pre is not None: json.dump(pre, open(os.path.join(d, 'automations.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    try:
        doc = None; t = time.time() + 30
        while time.time() < t:
            try:
                doc = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/automations' % port, timeout=5))['doc']
                if len(doc['actions']) >= 20 or pre is not None and 'raidinmerge1' in doc.get('seeded', []): break
            except Exception: time.sleep(0.5)
        return doc, d
    finally:
        h.kill()
def says(doc): return [s for s in next(a for a in doc['actions'] if a['id'] == 'sb-raid')['steps'] if s['type'] == 'say']
doc, d = run(8872, None)
s = says(doc)
chk('fresh seed: one say in the incoming-raid action', len(s) == 1, s)
chk('fresh seed: the one message carries thanks, emotes and welcome', len(s) == 1 and all(x in s[0]['text'] for x in ('{raider} just raided', 'innoce108Pinguinoraid', 'Welcome everyone')) and len(s[0]['text']) <= 500, s)
old = {'seeded': ['spotify', 'spotify2', 'musicoff1', 'songhelper1', 'raidshort1', 'raidflow2', 'raidmerge1'], 'actions': [
    {'id': 'sb-raid', 'name': 'Alert: incoming raid', 'enabled': True, 'triggers': [{'type': 'raid'}], 'conditions': [], 'steps': [
        {'type': 'delay', 'ms': 500}, {'type': 'say', 'as': 'core', 'text': 'A {raider}'}, {'type': 'say', 'as': 'core', 'text': 'B EMOTES'},
        {'type': 'delay', 'ms': 2500}, {'type': 'say', 'as': 'core', 'text': 'C welcome'}, {'type': 'alert_sound', 'kind': 'raid'}, {'type': 'delay', 'ms': 12000, 'skipSmallRaid': True}]}]}
doc, d = run(8873, old)
s = says(doc); steps = next(a for a in doc['actions'] if a['id'] == 'sb-raid')['steps']
chk('migration: three saved says become one, in order', len(s) == 1 and s[0]['text'] == 'A {raider} B EMOTES C welcome', s)
chk('migration: first delay and the steps after the lines stay, the delay between them goes', [x['type'] for x in steps] == ['delay', 'say', 'alert_sound', 'delay'], [x['type'] for x in steps])
chk('migration: dated backup written', len(glob.glob(os.path.join(d, 'automations.json.before-raidinmerge-*.bak'))) == 1)
print('FAILS: %d' % len(fails)); sys.exit(1 if fails else 0)
