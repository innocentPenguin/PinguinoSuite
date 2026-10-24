"""Mod-made plain commands on top of the canned system: !addcom / !editcom / !delcom (mods + broadcaster only), name collisions, allowed tokens, only custom entries editable, audit, !commands list, per-command cooldown field.
Usage: python Tools/test-host-customcmds.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.environ.get('PGSUITE') or os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8981; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcc_'); outf = os.path.join(d, 'out.txt'); cf = os.path.join(d, 'canned.json')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'CannedFile': cf, 'Enabled': True}, open(os.path.join(d, 'chat_settings.json'), 'w'))
json.dump({'cooldownSec': 20, 'commands': [{'name': 'hug', 'text': '$(user) hugs $(touser)!'}]}, open(cf, 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8982'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.8):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def cmds(): return {c['name']: c for c in json.load(open(cf))['commands']}
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('viewer: !addcom !nope hello there'); chk('a viewer gets nothing', r == [] and 'nope' not in cmds(), r)
    r = ask('*modguy: !addcom !socials Follow me, $(user)! $(count) $(link:discord)'); c = cmds().get('socials')
    chk('a mod adds a command: one short reply, stored in the canned file as custom', len(r) == 1 and 'added !socials' in r[0] and c and c['custom'] is True and c['cooldownSec'] == 10 and c['addedBy'] == 'modguy' and '$(count)' in c['text'], (r, c))
    chk('the existing entries stay', 'hug' in cmds())
    r = ask('*modguy: !addcom socials again'); chk('a second add of the same name says use !editcom', len(r) == 1 and 'editcom' in r[0], r)
    r = ask('*modguy: !addcom !ban hi everyone'); chk('a real command name is refused', len(r) == 1 and 'taken' in r[0] and 'ban' not in cmds(), r)
    for n in ('song', 'points', 'gamble', 'commands', 'addcom', 'rank'):
        r = ask('*modguy: !addcom !%s some text here' % n); chk('collision refused: !' + n, len(r) == 1 and 'taken' in r[0] and n not in cmds(), r)
    r = ask('*modguy: !addcom !hug some text here'); chk('an existing canned joke cannot be taken over', len(r) == 1 and 'taken' in r[0] and cmds()['hug']['text'].startswith('$(user) hugs'), r)
    r = ask('*modguy: !addcom !luckme $(luck) is yours'); chk('$(luck) is not a custom token', len(r) == 1 and 'only' in r[0] and 'luckme' not in cmds(), r)
    r = ask('*modguy: !addcom !x2 $(foo) bar baz'); chk('unknown tokens refused', len(r) == 1 and 'only' in r[0] and 'x2' not in cmds(), r)
    r = ask('*modguy: !addcom !bang !ban someone now'); chk('text starting with ! refused', len(r) == 1 and 'cannot start' in r[0], r)
    r = ask('*modguy: !addcom !nolink see $(link:nope)'); chk('unknown link key refused', len(r) == 1 and 'not a known link' in r[0] and 'nolink' not in cmds(), r)
    r = ask('*modguy: !addcom'); chk('usage when empty', len(r) == 1 and 'use: !addcom' in r[0], r)
    r = ask('*modguy: !addcom !bad-name text text'); chk('bad name refused', len(r) == 1 and 'letters' in r[0], r)
    r = ask('#caster: !addcom !welcomeinfo Be nice to each other'); chk('the broadcaster can add', len(r) == 1 and 'added !welcomeinfo' in r[0] and 'welcomeinfo' in cmds(), r)
    r = ask('*modguy: !editcom !socials New text for $(user)'); chk('edit changes the text, one reply', len(r) == 1 and 'updated !socials' in r[0] and cmds()['socials']['text'] == 'New text for $(user)' and cmds()['socials']['editedBy'] == 'modguy', r)
    r = ask('*modguy: !editcom !hug hijacked'); chk('only custom commands can be edited', len(r) == 1 and 'not a custom command' in r[0] and cmds()['hug']['text'].startswith('$(user) hugs'), r)
    r = ask('viewer: !editcom !socials hijacked'); chk('a viewer cannot edit', r == [] and cmds()['socials']['text'] == 'New text for $(user)', r)
    r = ask('*modguy: !commands'); chk('!commands lists the custom ones after the link', len(r) == 1 and 'innocentpenguin.com/commands' in r[0] and 'Custom:' in r[0] and '!socials' in r[0] and '!welcomeinfo' in r[0], r)
    api = get('/api/canned'); chk('the editor API sees them (same store)', any(c['name'] == 'socials' for c in api['commands']), api['ok'])
    r = ask('*modguy: !delcom !hug'); chk('a built-in joke cannot be deleted from chat', len(r) == 1 and 'not a custom command' in r[0] and 'hug' in cmds(), r)
    r = ask('viewer: !delcom !socials'); chk('a viewer cannot delete', r == [] and 'socials' in cmds(), r)
    r = ask('*modguy: !delcom !socials'); chk('delete removes it, one reply', len(r) == 1 and 'deleted !socials' in r[0] and 'socials' not in cmds(), r)
    r = ask('*modguy: !delcom !socials'); chk('deleting again says it is not a custom command', len(r) == 1 and 'not a custom command' in r[0], r)
    time.sleep(8.5)
    r = ask('*modtwo: !commands'); chk('the list drops the deleted one', 'socials' not in r[0] and '!welcomeinfo' in r[0], r)
    time.sleep(0.5)
    aud = ''
    for root, _, files in os.walk(d):
        for f in files:
            if f.startswith('mod_audit') and f.endswith('.jsonl'): aud += open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
    chk('audit has who added / edited / deleted', 'addcom' in aud and 'editcom' in aud and 'delcom' in aud and 'modguy' in aud and 'caster' in aud and 'viewer' not in aud, aud[:400])
    chk('no secrets in the audit', 'token' not in aud.lower())
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS custom commands')
sys.exit(1 if fails else 0)
