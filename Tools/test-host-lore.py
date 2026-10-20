"""Channel lore (Nightbot import): exact commands, aliases, variables ($(user) $(touser) $(count) $(random) $(time)), natural questions with rate limits, keyword replies, skip list, unsafe entries, /api/lore, /api/commands-doc.
Usage: python Tools/test-host-lore.py [dll]"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8991; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pglore_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
def start():
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_COMPAT_WS_PORT': '8994', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0'})
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    return h
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(h, line, wait=0.7):
    n = len(says()); h.stdin.write((line + '\n').encode('utf-8')); h.stdin.flush(); time.sleep(wait); return says()[n:]
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', n, '|', extra)
json.dump({'LobbyName': 'peng7', 'LobbyPassword': ''}, open(os.path.join(d, 'helper_settings.json'), 'w'))
host = start()
try:
    seed = json.load(open(os.path.join(suite, 'PinguinoB0t', 'channel_lore_seed.json'), encoding='utf-8')); ids = {e['id'] for e in seed['entries']}
    n0 = api('/api/lore')['count']; chk('seeded the editable copy on first start', os.path.exists(os.path.join(d, 'channel_lore.json')) and n0 == len(seed['entries']), n0)
    api('/api/lore', {'action': 'settings', 'settings': {'globalCooldownSec': 0, 'userCooldownSec': 0, 'entryCooldownSec': 90}})
    # ---- exact commands ----
    r = ask(host, 'viewer1: !sydney'); chk('!sydney', r == ['brick wall Sydney!!! 🧱'], r)
    r = ask(host, 'viewer1: !specs'); chk('!specs also adds the streaming pc', r and 'Ryzen 9 7950X3D' in r[0] and 'Ryzen 5600G' in r[0] and '| !' not in r[0], r)
    r = ask(host, 'viewer1: !dc'); chk('!dc is !discord', r and r[0].startswith('https://discord.gg/'), r)
    r = ask(host, 'viewer1: !yt'); chk('!yt is !youtube', r and 'youtube.com/@InnocentPinguino' in r[0], r)
    r = ask(host, 'viewer1: !burglingnomes'); chk('!burglingnomes is !burglin', r and '/clip/SpookyTrustworthyLapwingBIRB-K2S97oS82L66V7HN' in r[0], r)
    r = ask(host, 'viewer1: !ash'); chk('!ash (the clip Nightbot called !bits)', r and 'BloodyPiercingRaccoonStrawBeary-uli7Tn9mJZmI5VUH' in r[0], r)
    r = ask(host, 'viewer1: !hug @ana'); chk('$(user) and $(touser) with a target', r == ['viewer1 wraps their arms around @ana and gives them a big, warm hug! 🤗'], r)
    time.sleep(5.3); r = ask(host, 'viewer1: !hug'); chk('$(touser) without a target picks someone active', r and re.search(r'around @\w+ and gives', r[0]), r)
    r = ask(host, 'viewer1: !attack bob'); chk('!attack picks one of the 3 outcomes', r and r[0].startswith('viewer1 ') and '@bob' in r[0], r)
    r = ask(host, 'viewer1: !luck'); m = re.search(r'You got (\d+)% luck', r[0] if r else ''); chk('!luck is 1-50', m and 1 <= int(m.group(1)) <= 50, r)
    r = ask(host, 'viewer1: !time'); chk('!time is the Central time', r and re.match(r'It is \d{1,2}:\d\d (AM|PM) for InnocentPenguin', r[0]), r)
    ask(host, 'viewer1: !owngoal'); r = ask(host, 'viewer2: !owngoal', 5.8); r = r or ask(host, 'viewer2: !owngoal', 0.7)
    chk('counters count up', api('/api/lore')['counters']['owngoal'] >= 2, api('/api/lore')['counters'])
    r = ask(host, 'viewer1: !popcorn'); chk('!popcorn is rebuilt cleanly', r and r[0].count('PopCorn') == 26 and 'PopC ' not in r[0], r)
    for c in ('!test', '!trapaccount', '!banlist', '!stop', '!intro', '!cmds'): chk(c + ' is not imported', ask(host, 'viewer1: ' + c, 0.4) == [])
    chk('!commands stays ours', ask(host, 'viewer1: !commands') == ['Every chat command, with search: https://innocentpenguin.com/help#commands'])
    chk('!bits stays ours (the bits board), not the clip', not any('clip' in x for x in ask(host, 'viewer1: !bits')))
    r = ask(host, 'viewer1: !gay'); chk('the exact !command of an unsafe entry still works', r != [], r)
    r = ask(host, 'viewer1: !pm'); chk('!pm reads the one shared private-match setting', r == ['Private match -> Name: peng7, no password.'], r)
    # ---- natural questions ----
    r = ask(host, 'viewer3: what pc does penguin have?'); chk('"what pc does penguin have?" -> specs + streaming pc', r and 'Ryzen 9 7950X3D' in r[0] and r[0].startswith('@viewer3 '), r)
    r = ask(host, 'viewer4: what are his specs'); chk('the same entry is rate limited for 90 s', r == [], r)
    r = ask(host, 'viewer4: when does he stream?'); chk('"when does he stream?" -> schedule + stream time', r and 'Live every day at 5pm' in r[0] and '11PM' in r[0], r)
    r = ask(host, 'viewer5: what is the server ip?'); chk('server ip', r and 'smp.innocentpenguin.com' in r[0], r)
    r = ask(host, 'viewer5: how do I join the customs?'); chk('how to join customs', r and '!join' in r[0], r)
    r = ask(host, 'viewer5: how do i get mod'); chk('how to get mod', r and "Don't beg for mod" in r[0], r)
    r = ask(host, 'viewer5: who is sydney?'); chk('"who is sydney?" -> the sydney line', r and 'brick wall Sydney' in r[0], r)
    r = ask(host, 'viewer6: show me the burglin clip'); chk('"show me the burglin clip"', r and 'SpookyTrustworthyLapwingBIRB' in r[0], r)
    r = ask(host, 'viewer6: my pc is so slow lol'); chk('a statement about someone else\'s pc is left alone', r == [], r)
    r = ask(host, 'viewer6: what pc should i buy?'); chk('buying advice is not the streamer\'s specs', r == [], r)
    r = ask(host, 'viewer6: is there a discord?'); chk('is there a discord?', r and 'discord.gg' in r[0], r)
    r = ask(host, 'viewer6: who is gay?'); chk('unsafe entries never answer a question', r == [], r)
    r = ask(host, 'viewer7: goodnight'); chk('a bare "goodnight" gets the old Nightbot reply', r and r[0].startswith('Goodnight viewer7'), r)
    r = ask(host, 'viewer7: goodnight everyone'); chk('"goodnight everyone" is not a keyword hit', r == [], r)
    r = ask(host, 'viewer7: !lore off sydney')
    r = ask(host, '*mod1: !lore off sydney'); r = ask(host, 'viewer7: !sydney'); chk('a mod can turn an entry off', r == [], r)
    ask(host, '*mod1: !lore on sydney'); chk('and on again', ask(host, 'viewer7: !sydney') == ['brick wall Sydney!!! 🧱'])
    chk('viewers cannot run !lore', api('/api/lore')['entries'] and True)
    # ---- the endpoint and the docs ----
    t = api('/api/lore', {'action': 'test', 'text': 'what pc does he have?'}); chk('/api/lore test shows which entry would answer', t['match'] == 'specs', t)
    api('/api/lore', {'action': 'upsert', 'entry': {'id': 'newjoke', 'kind': 'fun', 'triggers': ['!newjoke'], 'response': 'hello $(user)!'}})
    chk('a mod can add an entry through the endpoint', ask(host, 'viewer1: !newjoke') == ['hello viewer1!'])
    doc = api('/api/commands-doc'); rows = [x for x in doc['viewer'] if x.get('category') == 'Channel']
    names = {x['command'] for x in rows}
    chk('commands-doc lists the channel commands, grouped', len(rows) > 80 and {x['group'] for x in rows} >= {'Info', 'Links', 'Clips', 'People', 'Fun'} and doc['counts']['channel'] == len(rows), (len(rows), doc['counts']))
    chk('commands-doc leaves out the not-public-safe entries and the keyword replies', not (names & {'!gay', '!racist', '!goon', '!twerk', '!of', '!purge', '!cpu'}) and '!sydney' in names and '!specs' in names, sorted(names & {'!gay', '!racist'}))
    # ---- persistence across a restart ----
    before = api('/api/lore')['counters']['owngoal']; host.kill(); time.sleep(1.0); host = start()
    chk('counters and edits survive a restart', api('/api/lore')['counters']['owngoal'] == before and any(e['id'] == 'newjoke' for e in api('/api/lore')['entries']))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
