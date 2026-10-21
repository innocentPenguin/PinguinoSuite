"""Command profiles: GET/POST /api/commands/* (edit tier/cooldowns/enabled, validation, archive + restore, usage stats, audit log), central enforcement is silent, /api/commands-doc follows.
Usage: python Tools/test-host-cmdprofiles.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8989; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgcp_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'cpt', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8990', 'PINGUINO_LIVE': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B}), timeout=10))
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def start():
    h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(2); return h
h = start()
def feed(l, w=1.0): h.stdin.write((l + '\n').encode()); h.stdin.flush(); time.sleep(w)
def prof(i): return next((c for c in get('/api/commands/profiles')['commands'] if c['id'] == i), None)
def ran(line, who='viewer1'):
    # the duplicate-message guard swallows identical repeats, so "ran" = the command got past the gate (its usage counter moved)
    u = (prof('!uptime') or {}).get('uses', 0); n = len(says()); feed(who + ': ' + line, 1.2); p = prof('!uptime')
    return p is not None and p['uses'] > u
try:
    r = get('/api/commands/profiles'); cs = r['commands']; up = prof('!uptime')
    keys = ['id', 'name', 'aliases', 'description', 'category', 'permission', 'cooldownGlobal', 'cooldownUser', 'enabled', 'uses', 'lastUsed', 'ownerBot', 'editedBy', 'editedAt']
    chk('list', r['ok'] and len(cs) > 100 and up and up['permission'] == 'everyone' and up['ownerBot'] == 'Host' and up['enabled'] is True and up['archived'] is False and all(k in up for k in keys), up)
    chk('mod command default', prof('!removepoints')['permission'] == 'mod' and prof('!addpoints')['permission'] == 'broadcaster')
    chk('baseline runs', ran('!uptime'))
    u0 = prof('!uptime'); chk('usage counted', u0['uses'] == 1 and u0['lastUsed'] > 0, u0)
    r = post('/api/commands/profile', {'id': '!uptime', 'permission': 'mod', 'by': 'ivan'})
    chk('edit tier', r['ok'] and r['command']['permission'] == 'mod' and r['command']['editedBy'] == 'ivan' and r['command']['editedAt'] > 0 and r['command']['defaultPermission'] == 'everyone', r)
    chk('viewer swallowed silently', not ran('!uptime'))
    chk('mod still runs', ran('!uptime', '*mod1'))
    chk('blocked use not counted', prof('!uptime')['uses'] == 2, prof('!uptime')['uses'])
    post('/api/commands/profile', {'id': '!uptime', 'permission': 'sub', 'by': 'ivan'}); chk('sub tier blocks a plain viewer', not ran('!uptime'))
    post('/api/commands/profile', {'id': '!uptime', 'permission': 'everyone', 'cooldownUser': 30, 'by': 'ivan'})
    chk('first use passes', ran('!uptime', 'viewer2')); chk('user cooldown blocks the repeat', not ran('!uptime', 'viewer2')); chk('other users unaffected', ran('!uptime', 'viewer3'))
    r = post('/api/commands/profile', {'id': '!uptime', 'cooldownUser': 0, 'cooldownGlobal': 30, 'by': 'ivan'}); chk('global cooldown set', r['ok'] and r['command']['cooldownGlobal'] == 30, r)
    post('/api/commands/profile', {'id': '!uptime', 'cooldownGlobal': 0, 'by': 'ivan'})
    r = post('/api/commands/profile', {'id': '!uptime', 'enabled': False, 'by': 'ivan'}); chk('disable', r['ok'] and r['command']['enabled'] is False)
    chk('disabled is swallowed', not ran('!uptime', '*mod1'))
    post('/api/commands/profile', {'id': '!uptime', 'enabled': True, 'description': 'How long we have been live', 'category': 'Info', 'by': 'ivan'})
    p2 = prof('!uptime'); chk('description + category', p2['description'] == 'How long we have been live' and p2['category'] == 'Info' and p2['enabled'], p2)
    for bad in [{'permission': 'king'}, {'cooldownGlobal': -1}, {'cooldownUser': 'x'}, {'enabled': 'yes'}, {'nope': 1}, {'name': '!other'}, {'description': 'x' * 500}]:
        b = dict(bad); b.update({'id': '!uptime', 'by': 'ivan'}); r = post('/api/commands/profile', b); chk('refused %s' % list(bad)[0], r['ok'] is False and r.get('error'), r)
    chk('unknown id', post('/api/commands/profile', {'id': '!nothere', 'enabled': False, 'by': 'x'})['ok'] is False)
    r = post('/api/commands/archive', {'id': '!uptime', 'by': 'ivan'}); chk('archive', r['ok'], r)
    chk('gone from list', prof('!uptime') is None); chk('swallowed while archived', not ran('!uptime', '*mod1'))
    a = get('/api/commands/archive')['commands']; e = next((x for x in a if x['id'] == '!uptime'), None)
    chk('in archive with who/when/profile', e and e['archivedBy'] == 'ivan' and e['archivedAt'] > 0 and e['archived'] is True and e['category'] == 'Info' and e['description'] == 'How long we have been live', e)
    chk('doc hides it', all(c['command'] != '!uptime' for c in get('/api/commands-doc')['all']))
    chk('archive twice refused', post('/api/commands/archive', {'id': '!uptime', 'by': 'ivan'})['ok'] is False)
    r = post('/api/commands/restore', {'id': '!uptime', 'by': 'ivan'}); chk('restore returns the command', r['ok'] and r['command']['id'] == '!uptime' and r['command']['category'] == 'Info', r)
    chk('back in list, gone from archive', prof('!uptime') and not any(x['id'] == '!uptime' for x in get('/api/commands/archive')['commands'])); chk('runs again', ran('!uptime', 'viewer9'))
    chk('restore unknown refused', post('/api/commands/restore', {'id': '!zzz', 'by': 'ivan'})['ok'] is False)
    post('/api/commands/profile', {'id': '!uptime', 'permission': 'mod', 'by': 'ivan'}); doc = get('/api/commands-doc')
    chk('mod-only never in the public viewer list', all(c['command'] != '!uptime' for c in doc['viewer']) and any(c['command'] == '!uptime' for c in doc['mod']))
    # ---- roles (tags): a SET of allowed roles per command ----
    ro = get('/api/commands/profiles')['roleOptions']; chk('role options', [x['id'] for x in ro] == ['everyone', 'sub', 'sub1', 'sub2', 'sub3', 'vip', 'mod', 'broadcaster'] and all(x['label'] for x in ro), ro)
    chk('default roles mirror the old ladder', prof('!removepoints')['roles'] == ['mod', 'broadcaster'] and prof('!addpoints')['roles'] == ['broadcaster'] and prof('!join')['roles'] == ['everyone'] and prof('!join')['defaultRoles'] == ['everyone'])
    def setroles(r): return post('/api/commands/profile', {'id': '!uptime', 'roles': r, 'by': 'ivan'})
    r = setroles(['sub2', 'vip']); chk('roles saved: broadcaster added, canonical order, permission derived', r['ok'] and r['command']['roles'] == ['sub2', 'vip', 'broadcaster'] and r['command']['permission'] == 'sub', r)
    chk('plain viewer blocked', not ran('!uptime', 'plainv')); chk('tier 2 sub passes', ran('!uptime', '$2subtwo')); chk('tier 1 sub blocked', not ran('!uptime', '$1subone')); chk('vip passes', ran('!uptime', '%vipguy'))
    chk('mod NOT listed -> blocked', not ran('!uptime', '*modguy')); chk('broadcaster always passes', ran('!uptime', '#ivan'))
    r = setroles(['sub', 'mod']); chk('any-tier sub + mod', ran('!uptime', '$3subthree') and ran('!uptime', '*modguy') and not ran('!uptime', '%vipguy'), r)
    r = setroles(['everyone', 'mod']); chk('everyone is exclusive', r['ok'] and r['command']['roles'] == ['everyone'] and r['command']['permission'] == 'everyone', r); chk('everyone: viewer passes', ran('!uptime', 'plainv2'))
    r = setroles([]); chk('empty = broadcaster only', r['ok'] and r['command']['roles'] == ['broadcaster'] and r['command']['permission'] == 'broadcaster', r); chk('mod blocked when broadcaster-only', not ran('!uptime', '*modguy'))
    r = setroles(['mod']); chk('broadcaster cannot be removed', r['command']['roles'] == ['mod', 'broadcaster'], r)
    for bad in [['king'], 'mod', [1], ['follower']]:
        r = setroles(bad); chk('roles refused %s' % bad, r['ok'] is False and r.get('error'), r)
    r = post('/api/commands/profile', {'id': '!uptime', 'permission': 'vip', 'by': 'ivan'}); chk('legacy permission maps to a tag set', r['ok'] and r['command']['roles'] == ['vip', 'mod', 'broadcaster'] and r['command']['permission'] == 'vip', r)
    r = post('/api/commands/profile', {'id': '!uptime', 'roles': ['mod'], 'permission': 'sub', 'by': 'ivan'}); chk('roles win over permission', r['command']['roles'] == ['mod', 'broadcaster'], r)
    r = setroles(prof('!uptime')['defaultRoles']); chk('reset to default via defaultRoles', r['command']['roles'] == ['everyone'], r)
    r = setroles(['sub', 'sub1']); doc = get('/api/commands-doc'); chk('sub-visible roles stay on the public list', any(c['command'] == '!uptime' for c in doc['viewer']))
    setroles(['vip']); doc = get('/api/commands-doc'); chk('no everyone/sub role -> mod list, not public', all(c['command'] != '!uptime' for c in doc['viewer']) and any(c['command'] == '!uptime' for c in doc['mod']))
    setroles(['mod'])
    cfg = os.path.join(d, 'config'); log = open(os.path.join(cfg, 'commands_audit.log'), encoding='utf-8').read()
    chk('audit log', 'ivan' in log and 'roles everyone -> mod,broadcaster' in log and 'archived' in log and 'restored' in log, log[-300:])
    chk('files exist', all(os.path.exists(os.path.join(cfg, f)) for f in ['command_profiles.json', 'commands_archive.json']))
    get('/api/commands/profiles'); h.kill(); time.sleep(1); h = start()
    p3 = prof('!uptime'); chk('persisted', p3 and p3['permission'] == 'mod' and p3['uses'] >= 4 and p3['editedBy'] == 'ivan', p3)
    chk('unedited command untouched', prof('!join')['permission'] == 'everyone')
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS cmdprofiles'); sys.exit(1 if fails else 0)
