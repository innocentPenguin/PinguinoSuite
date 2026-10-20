"""Leaderboard / subscriber / streak chat commands (viewer + mod), month words, aliases editing, and GET /api/commands-doc. Usage: python Tools/test-host-commands.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8981; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcmds_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
t0 = 1771300000   # Feb 2026
now = int(time.time())
ev = [{'At': t0, 'Type': 'gift', 'User': 'generous', 'Amount': 5, 'To': ''}, {'At': t0 + 5, 'Type': 'gift', 'User': 'sg_yen', 'Amount': 2, 'To': ''}, {'At': t0 + 9, 'Type': 'cheer', 'User': 'bitty', 'Amount': 350, 'To': ''},
      {'At': t0 + 20, 'Type': 'cheer', 'User': 'sg_yen', 'Amount': 1500, 'To': ''}, {'At': now - 3600, 'Type': 'cheer', 'User': 'bitty', 'Amount': 100, 'To': ''}]
json.dump(ev, open(os.path.join(d, 'chat_events.json'), 'w'))
os.makedirs(os.path.join(d, 'profiles'))
for u, n in (('talker', 500), ('generous', 20), ('bitty', 10), ('cyfirl', 600), ('sg_yen', 60)):
    json.dump({'login': u, 'name': u, 'activity': {'messages': n, 'perMonth': {'2026-02': n}}, 'roles': {}}, open(os.path.join(d, 'profiles', u + '.json'), 'w'))
os.makedirs(os.path.join(d, 'subs'))
json.dump({'version': 1, 'lastExportAt': '', 'processed': {}, 'users': {'talker': {'login': 'talker', 'tier': 2, 'tenure': 7, 'streak': 7, 'founder': True, 'lapsed': False, 'subType': 'recurring'}, 'cyfirl': {'login': 'cyfirl', 'tier': 1, 'tenure': 4, 'streak': 1, 'founder': False, 'lapsed': False}}}, open(os.path.join(d, 'subs', 'subscribers_master.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8983'; env['PINGUINO_STREAK_COOL_GLOBAL'] = '0'; env['PINGUINO_STREAK_COOL_USER'] = '0'; env['PINGUINO_SUBS_DOWNLOADS'] = ''
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=15))
def say(line, wait=0.5): host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait)
def log(): return open(out, encoding='utf-8', errors='replace').read()
def last(n=1):
    lines = [l[6:] for l in log().splitlines() if l.startswith('[say] ')]; return lines[-1] if n == 1 else lines[-n:]
res = []
def chk(n, ok):
    res.append((n, bool(ok)))
    if not ok: print("   got:", last(3))
def ask(line, wait=0.7):
    before = len([l for l in log().splitlines() if l.startswith('[say] ')]); say(line, wait)
    after = [l[6:] for l in log().splitlines() if l.startswith('[say] ')]; return after[before:]
try:
    for _ in range(60):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    say('#trial: hello', 0.3)
    # streaks data for month tests
    say('@msg-id=viewermilestone;msg-param-category=watch-streak;msg-param-id=s1;msg-param-value=33;login=talker;display-name=Talker;tmi-sent-ts=1792500000000 :tmi.twitch.tv USERNOTICE #trial :x', 0.5)
    get('/api/boards')
    r = ask('viewer1: !topgifters')
    chk('!topgifters lists the top with the alias folded and a link', len(r) == 1 and r[0].startswith('Top gifters (all time, subs gifted): 1. generous 5') and '2. cyfirl 2' in r[0] and 'sg_yen' not in r[0] and 'leaderboards#gifters' in r[0])
    r = ask('viewer1: !topgifters feb'); chk('!topgifters <month> filters to that month (Feb 2026)', len(r) == 1 and 'Feb 2026' in r[0] and '1. generous 5' in r[0])
    r = ask('viewer1: !topbitters'); chk('!topbitters = !topbits (sg_yen folded into cyfirl: 1500 + bits)', len(r) == 1 and r[0].startswith('Top bitters (all time, bits): 1. cyfirl 1,500'))
    r = ask('viewer1: !topyappers'); chk('!topyappers by messages (cyfirl 660 with the alias)', len(r) == 1 and '1. cyfirl 660' in r[0] and 'leaderboards#yappers' in r[0])
    r = ask('viewer1: !topstreaks'); chk('!topstreaks lists shared streaks and links the page', len(r) == 1 and 'Talker 33' in r[0] and r[0].endswith('https://innocentpenguin.com/leaderboards#streaks'))
    r = ask('viewer1: !topgifters 2025-01'); chk('an empty month says so', len(r) == 1 and 'Nobody' in r[0])
    r = ask('viewer1: !leaderboards'); chk('!leaderboards gives the link', len(r) == 1 and r[0].endswith('https://innocentpenguin.com/leaderboards'))
    r = ask('viewer1: !commands'); chk('!commands links the help page command list', len(r) == 1 and r[0].endswith('https://innocentpenguin.com/help#commands'))
    r = ask('generous: !gifted'); chk('!gifted: own total and rank', len(r) == 1 and '@generous you have gifted 5 subs' in r[0] and 'rank #1 of' in r[0])
    r = ask('sg_yen: !bits'); chk('!bits on an alias account shows the main account total', len(r) == 1 and '1,600' not in r[0] and 'cheered 1,500 bits' in r[0])
    r = ask('nobodyhere: !gifted'); chk('!gifted with nothing recorded is honest', len(r) == 1 and 'no gifted subs recorded' in r[0].replace('I have ', ''))
    r = ask('talker: !sub'); chk('!sub: tier, months, streak and founder', len(r) == 1 and 'Tier 2 subscriber for 7 months (7 in a row), Founder' in r[0])
    r = ask('nobodyhere: !sub'); chk('!sub without a record', len(r) == 1 and "don't have a subscription" in r[0])
    r = ask('viewer1: !founders'); chk('!founders lists the 10 badge holders', len(r) == 1 and r[0].startswith('10 Founders') and 'stinkyo1' in r[0])
    # mods only
    r = ask('viewer1: !alias list'); chk('mod commands are silent for viewers', r == [])
    r = ask('viewer1: !lookup cyfirl'); chk('!lookup is silent for viewers', r == [])
    r = ask('*mod1: !alias list'); chk('!alias list shows the folded accounts', len(r) == 1 and 'sg_yen > cyfirl' in r[0])
    r = ask('*mod1: !alias add oldtalker talker'); chk('!alias add', len(r) == 1 and 'Alias saved: oldtalker > talker' in r[0])
    r = ask('*mod1: !alias add talker oldtalker'); chk('a loop is refused', len(r) == 1 and 'loop' in r[0])
    r = ask('*mod1: !alias add Bad!Name talker'); chk('bad logins are refused', len(r) == 1 and 'letters, numbers' in r[0])
    a = json.load(open(os.path.join(d, 'boards', 'aliases.json')))['aliases']; chk('aliases.json was edited', a.get('oldtalker') == 'talker' and a.get('sg_yen') == 'cyfirl')
    r = ask('*mod1: !alias remove oldtalker'); a = json.load(open(os.path.join(d, 'boards', 'aliases.json')))['aliases']; chk('!alias remove', 'Alias removed' in r[0] and 'oldtalker' not in a)
    r = ask('*mod1: !lookup sg_yen'); chk('!lookup follows an alias and shows sub, gifts, bits, messages and streak', len(r) == 1 and 'you typed an alias' in r[0] and 'gifts 2' in r[0] and 'bits 1500' in r[0] and 'messages 660' in r[0])
    r = ask('*mod1: !subs status'); chk('!subs status', len(r) == 1 and 'Subscribers on record: 2 active' in r[0] and '10 founders' in r[0])
    r = ask('*mod1: !streaks status'); chk('!streaks status', len(r) == 1 and '1 people have shared one' in r[0])
    r = ask('*mod1: !boards status'); chk('!boards status', len(r) == 1 and r[0].startswith('Boards:'))
    r = ask('*mod1: !boards refresh', 2.0); chk('!boards refresh answers', len(r) >= 1 and 'Recomputing' in r[0])
    r = ask('*mod1: !names refresh', 1.5); chk('!names refresh answers', len(r) >= 1 and 'display names' in r[0])
    # the documentation
    doc = get('/api/commands-doc')
    names = {c['command'] for c in doc['viewer']}; mnames = {c['command'] for c in doc['mod']}
    chk('commands doc: viewer and mod lists with name, usage, description, permission', doc['ok'] and all(k in doc['viewer'][0] for k in ('command', 'usage', 'description', 'permission')) and doc['counts']['viewer'] == len(doc['viewer']))
    chk('every new viewer command is documented', {'!topgifters', '!topbits', '!topyappers', '!topstreak', '!streak', '!streakrecord', '!leaderboards', '!gifted', '!bits', '!sub', '!founders'} <= names)
    chk('every new mod command is documented as mods only', {'!alias', '!boards', '!subs', '!streaks', '!names', '!lookup'} <= mnames and not ({'!alias', '!lookup'} & names))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
