"""Leak test for the Helper knowledge pack (Tools/build-helper-pack.py).
  1. a trap data dir: secrets, token-like strings, e-mails, internal paths, lore names and opted-out people must all be dropped from the PUBLIC pack,
     mod-only content must stay out of it and appear in the mod pack;
  2. the real pack built from the real Data folder is scanned for key names, token-like strings, e-mails, every name in Data/lore, opted-out people,
     and the literal values of every secret in the Data/runtime secret files.
Usage: python Tools/test-helper-pack.py"""
import importlib.util, json, os, re, shutil, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
spec = importlib.util.spec_from_file_location('bhp', os.path.join(here, 'build-helper-pack.py')); bhp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bhp)
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   extra:', extra)
def wj(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(o, open(p, 'w', encoding='utf-8'))
def ents(p): return json.load(open(p, encoding='utf-8'))['entries']
def alltext(es): return ' '.join(e['title'] + ' ' + e['keywords'] + ' ' + e['text'] for e in es)

# ---- 1. traps ----
t = tempfile.mkdtemp(prefix='pgpack_'); s = os.path.join(t, 'suite'); d = os.path.join(s, 'Data'); out = os.path.join(d, 'helper')
try:
    wj(os.path.join(s, 'PinguinoB0t', 'commands.json'), {'commands': [
        {'command': '!hello', 'who': 'everyone', 'usage': '!hello', 'description': 'Says hello to chat.', 'category': 'Fun'},
        {'command': '!leaky', 'who': 'everyone', 'usage': '!leaky', 'description': 'Shows the api_key for the bot.'},
        {'command': '!arch', 'who': 'everyone', 'usage': '!arch', 'description': 'Reads Data\\runtime\\players.json from the Host.'},
        {'command': '!ban2', 'who': 'mods', 'usage': '!ban2 @user', 'description': 'Mods only thing.'}]})
    wj(os.path.join(d, 'runtime', 'helper_facts.json'), {'Discord': 'https://discord.gg/abc', 'Note': 'internal note', 'Taught': [
        {'id': 't1', 'text': 'Ask zebrafanatic for the secret handshake.'},
        {'id': 't2', 'text': 'Mail ivan@example.com for help.'},
        {'id': 't3', 'text': 'Use code ' + 'A1b2C3d4' * 5 + ' at checkout.'},
        {'id': 't4', 'text': 'Quietkid likes cats.'},
        {'id': 't5', 'text': 'The stream is at 8pm on weekdays.'},
        {'id': 't6', 'text': 'Hidden one.', 'publicSafe': False}]})
    wj(os.path.join(d, 'runtime', 'links.json'), {'links': {'website': 'https://innocentpenguin.com'}})
    wj(os.path.join(d, 'runtime', 'channel_lore.json'), {'entries': [
        {'id': 'ok', 'kind': 'info', 'triggers': ['!ok'], 'response': 'A public info line.', 'publicSafe': True, 'enabled': True},
        {'id': 'priv', 'kind': 'info', 'triggers': ['!priv'], 'response': 'Not for sharing.', 'publicSafe': False, 'enabled': True},
        {'id': 'jk', 'kind': 'person', 'triggers': ['!jk'], 'response': 'a person joke', 'publicSafe': True, 'enabled': True}]})
    wj(os.path.join(d, 'runtime', 'chat_memory.json'), {'1': {'Login': 'quietkid', 'Privacy': 'optout', 'Aliases': []}})
    wj(os.path.join(d, 'lore', 'person_cards', 'zebrafanatic.json'), {})
    wj(os.path.join(d, 'lore', 'people_graph.json'), {'nodes': [{'login': 'graphperson'}]})
    os.makedirs(os.path.join(s, 'Docs'), exist_ok=True)
    open(os.path.join(s, 'Docs', 'HELPER_PUBLIC.md'), 'w').write('## Safe\nA safe public summary.\n\n## Unsafe\nSee the vault for the token and graphperson.\n')
    open(os.path.join(s, 'Docs', 'HELPER_MOD.md'), 'w').write('## Mod thing\nMods can do a mod thing.\n')
    r = bhp.build(s, d, out, net=False)
    pub, mod = ents(os.path.join(out, 'knowledge.json')), ents(os.path.join(out, 'knowledge_mod.json'))
    pt, mt = alltext(pub), alltext(mod)
    chk('public pack has the safe command, fact, taught note, lore and doc', all(x in pt for x in ('Says hello', 'discord.gg/abc', 'stream is at 8pm', 'A public info line', 'safe public summary')), pt[:300])
    chk('secret key names dropped', 'api_key' not in pt)
    chk('internal paths / architecture dropped', 'players.json' not in pt and 'Host' not in pt)
    chk('lore names dropped (person card, people graph)', 'zebrafanatic' not in pt.lower() and 'graphperson' not in pt.lower())
    chk('opted-out person dropped', 'quietkid' not in pt.lower())
    chk('e-mail and token-like string dropped', 'example.com' not in pt and 'A1b2C3d4' not in pt)
    chk('publicSafe=false, person lore and the internal Note stay out', 'Not for sharing' not in pt and 'person joke' not in pt and 'Hidden one' not in pt and 'internal note' not in pt)
    chk('mod command is only in the mod pack', 'Mods only thing' in mt and 'Mods only thing' not in pt)
    chk('mod how-to is only in the mod pack', 'a mod thing' in mt and 'a mod thing' not in pt)
    chk('both packs carry a version and a date', all(isinstance(json.load(open(os.path.join(out, f)))['version'], int) and json.load(open(os.path.join(out, f)))['date'] for f in ('knowledge.json', 'knowledge_mod.json')))
    chk('the drop report counts reasons, not content', sum(r['dropped'].values()) >= 7 and 'zebrafanatic' not in json.dumps(r), r)
    v1 = r['version']; r2 = bhp.build(s, d, out, net=False); chk('version goes up on every build', r2['version'] == v1 + 1)
    # the mod tier is not allowed to hold secrets either
    wj(os.path.join(s, 'PinguinoB0t', 'commands.json'), {'commands': [{'command': '!tok', 'who': 'mods', 'usage': '!tok', 'description': 'Prints the oauth token.'}]})
    bhp.build(s, d, out, net=False); chk('mod tier drops secrets too', 'oauth' not in alltext(ents(os.path.join(out, 'knowledge_mod.json'))).lower())
finally:
    shutil.rmtree(t, True)

# ---- 2. the real pack ----
rd = os.path.join(suite, 'Data'); t2 = tempfile.mkdtemp(prefix='pgpack_real_')
try:
    if os.path.isdir(os.path.join(rd, 'runtime')):
        r = bhp.build(suite, rd, t2, net=False)
        pub = ents(os.path.join(t2, 'knowledge.json')); pt = alltext(pub)
        chk('real public pack is not empty', len(pub) > 20, r)
        chk('real public pack: no key names', not bhp.SECRET_RX.search(pt), bhp.SECRET_RX.search(pt))
        chk('real public pack: no token-like strings', not bhp.TOKEN_RX.search(pt))
        chk('real public pack: no e-mails', not bhp.EMAIL_RX.search(pt))
        chk('real public pack: no internal architecture words', not bhp.ARCH_RX.search(pt), bhp.ARCH_RX.search(pt))
        names = bhp.deny_names(rd); low = pt.lower(); hit = [n for n in names if re.search(r'(?<![a-z0-9_])' + re.escape(n) + r'(?![a-z0-9_])', low)]
        chk('real public pack: no name from Data/lore or an opted-out person (%d names)' % len(names), not hit, len(hit))
        # literal secret values from the secret files must not appear anywhere in either pack
        vals = set()
        sec = re.compile(r'token|secret|key|pass|jwt|auth|code|bearer|cookie', re.I)   # not Channel / Account / Sender names: those are public
        def walk(o, k=''):
            if isinstance(o, dict):
                for kk, v in o.items(): walk(v, kk if sec.search(kk) else k)
            elif isinstance(o, list):
                for v in o: walk(v, k)
            elif isinstance(o, str) and len(o) >= 12 and not o.startswith('http') and sec.search(k): vals.add(o)
        for fn in ('bots_secrets.json', 'host_secrets.json'):
            walk(bhp.read_json(os.path.join(rd, 'runtime', fn), {}))
        cs = bhp.read_json(os.path.join(rd, 'runtime', 'chat_settings.json'), {}) or {}
        if isinstance(cs.get('ApiKey'), str) and len(cs['ApiKey']) >= 8: vals.add(cs['ApiKey'])
        both = pt + ' ' + alltext(ents(os.path.join(t2, 'knowledge_mod.json')))
        chk('real packs: no literal secret value from the secret files (%d checked)' % len(vals), not any(v in both for v in vals))
        # lore kinds: only info/link lore may enter
        lore = bhp.read_json(os.path.join(rd, 'runtime', 'channel_lore.json'), {}) or {}
        bad = [e for e in lore.get('entries', []) if (e.get('kind') not in ('info', 'link') or e.get('publicSafe') is False) and any(x['id'] == 'lore:' + str(e.get('id')) for x in pub)]
        chk('real public pack: no joke/person/non-public lore entries', not bad, [e.get('id') for e in bad])
    else:
        print('   (no real Data folder here, real-pack scan skipped)')
finally:
    shutil.rmtree(t2, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
