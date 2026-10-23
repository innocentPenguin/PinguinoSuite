"""Builds PinguinoB0t/channel_lore_seed.json from the Nightbot export (Docs/imports/nightbot-custom-commands.txt).
The Host copies the seed to Data/runtime/channel_lore.json the first time it starts (that copy is the editable one; this script never touches it).
Run:  python Tools/build-channel-lore.py [--report]"""
import json, re, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SUITE = os.path.dirname(HERE)
SRC = os.path.join(SUITE, 'Docs', 'imports', 'nightbot-custom-commands.txt')
OUT = os.path.join(SUITE, 'PinguinoB0t', 'channel_lore_seed.json')

# ---------------- parse the PDF text (lines are wrapped at ~90 characters, sometimes in the middle of a word) ----------------
noise = re.compile(r'^(Command|Custom Default|Page \d+ of \d+Show \d+|Show \d+|Page \d+ of \d+|\d+/\d+/\d+, .*Commands|https://nightbot\.tv/commands.*|Commands|Commands are used.*|New Command|Search commands\.\.\.|Custom|Default|Copyright .*NightDev.*|Terms of Service.*)$')
SPACE_AFTER = {('!1v1', 'party'), ('!7tv', 'perks'), ('!howtojoin', 'will '), ('!penguin', 'Also '), ('!prime', 'the S'), ('!purge', 'boats'), ('!gsu', 'Pengu')}   # the wrap landed on a space
entries = []; cur = None
for ln in open(SRC, encoding='utf-8').read().splitlines():
    t = ln.strip()
    if not t or noise.match(t): continue
    if re.match(r'^![A-Za-z0-9_]+$', t): cur = {'cmd': t, 'lines': []}; entries.append(cur); continue
    if re.match(r'^(goodnight|hi|meow|w)$', t) and cur and cur['cmd'] in ('!zylo', 'goodnight', 'hi', 'meow'): cur = {'cmd': t, 'lines': []}; entries.append(cur); continue   # the four keyword replies at the end of the export
    if cur is not None: cur['lines'].append(ln.rstrip())
parsed = {}
for e in entries:
    ls = e['lines']; s = ''
    for i, l in enumerate(ls):
        if i == 0: s = l; continue
        prev = ls[i - 1]; last = prev.split(' ')[-1]
        if last.startswith('http') and ' ' not in l.strip() and not l.startswith('http'): s += l            # a wrapped URL
        elif len(prev) >= 78 and (e['cmd'], l[:5]) in SPACE_AFTER: s += ' ' + l
        elif len(prev) >= 78: s += l
        else: s += ' ' + l
    parsed[e['cmd']] = s.strip()

# ---------------- curation ----------------
SKIP = {'!pm': 'contains a game password', '!test': 'Nightbot title/game setter (ops only, documented in the report, never imported)', '!trapaccount': 'must never be mentioned in chat',
        '!banlist': 'a private ban note', '!stop': 'an internal queue joke, not for viewers', '!intro': 'a Nightbot status note (intros are our own system now)', '!cmds': 'ours: !commands', '!commands': 'ours (links to the site /help)', '!bits': 'ours: !bits is the bits board (the same clip is !ash)'}
UNSAFE = {'!gay', '!racist', '!racism', '!grindr', '!goon', '!weiner', '!feetfinder', '!of', '!onlyfans', '!tinder', '!topgooner', '!twerk', '!pinguino', '!hebunga', '!cpu', '!vc', '!purge'}
ALIAS = {'!discord': ['!dc'], '!youtube': ['!yt'], '!burglin': ['!burglingnomes'], '!racist': ['!racism'], '!ash': [], '!minecraft': ['!piglin'], '!mcrules': []}
ALIAS_OF = {a for v in ALIAS.values() for a in v}
KIND = {}
for c in 'ash burglin cat crimson geoguesser golf goon howbigisit minecraft oopsie peak racist repo rl settings squishy uk weiner yen blizzy marsh vc bits'.split(): KIND['!' + c] = 'clip'
for c in '7tv discord youtube tiktok steam geo tracker roblox modpack tts prime save support gsu ubisoft drops phil grindr'.split(): KIND['!' + c] = 'link'
for c in 'specs streamingpc controller schedule streamtime server ip mcrules customrules customs howtojoin mod vip age height weight name realrank odds time burger food mods hc'.split(): KIND['!' + c] = 'info'
for c in 'attack ban hug luck lurk unlurk water happy sad popcorn turtles twerk vanish whiff owngoal cheese cups endstream ad 1v1 purge gay of onlyfans feetfinder tinder topgooner pinguino cpu hebunga dictators thebest cute'.split(): KIND['!' + c] = 'fun'
for c in 'abdul blake blizy coy flayir goat kara koops marshmallow marshmellow mashka mello pineapple quinn robo rose samu shadow snowy spedy speedy sydney unninocence vhoggie w wyatt yoohoo zylo developer'.split(): KIND['!' + c] = 'person'

Q = r'(?:what|whats|what\'s|which|when|where|who|whos|who\'s|how|is|are|does|do|did|can|will|why)'
NOT_BUYING = r'\b(?:should i|recommend|buy|build me|my own)\b'
# natural-language patterns (regex, case-insensitive). q=True means the message has to look like a question; clips are asked for as a command ("show me the ... clip")
INTENT = {
    '!specs': dict(p=[r'\bspecs?\b', r'\b(?:what|which)\b.*\b(?:pc|computer|gpu|cpu|graphics card|processor|ram|rig)\b', r'\b(?:pc|computer|rig)\b.*\b(?:have|use|using|run|play on)\b', r'\bhow much ram\b'], also=['!streamingpc'], not_=NOT_BUYING, pr=5),
    '!streamingpc': dict(p=[r'\bstream(?:ing)? (?:pc|computer|setup|rig)\b', r'\b(?:pc|computer) (?:he|you|penguin|peng) stream(?:s)? (?:on|with)\b'], pr=6),
    '!controller': dict(p=[r'\b(?:what|which) controller\b', r'\bcontroller\b.*\b(?:he|you|penguin|peng) (?:use|play|have)\b'], pr=4),
    '!schedule': dict(p=[r'\bwhen\b.*\b(?:stream|live|go live|start|on)\b', r'\b(?:stream|streaming) (?:schedule|times?|hours)\b', r'\bwhat time\b.*\b(?:stream|live|start|on)\b', r'\bschedule\b'], also=['!streamtime'], pr=5),
    '!streamtime': dict(p=[r'\bstream ?time\b'], pr=4),
    '!server': dict(p=[r'\b(?:which|what|how many) (?:minecraft )?servers?\b', r'\bis there (?:a )?(?:minecraft|mc) server\b'], also=['!ip'], pr=4),
    '!ip': dict(p=[r'\b(?:server|smp|mc|minecraft)\b.*\b(?:ip|address)\b', r'\b(?:what|whats)(?:\'s| is)? the ip\b', r'\bip (?:for|of) the (?:server|smp|minecraft)\b'], pr=5),
    '!mcrules': dict(p=[r'\b(?:mc|minecraft|server|smp) rules\b', r'\bwhat are the (?:mc|minecraft|server|smp) rules\b'], pr=4),
    '!customrules': dict(p=[r'\bcustoms? rules\b', r'\brules (?:for|of|in) (?:the )?customs?\b'], pr=5),
    '!customs': dict(p=[r'\bwhat (?:are|is) (?:the )?customs\b', r'\bhow (?:do )?customs work\b'], pr=3),
    '!howtojoin': dict(p=[r'\bhow\b.*\b(?:join|play|get in)\b.*\b(?:customs?|queue|lobby|games?)\b', r'\bhow (?:do|can|to) (?:i|we|you)? ?(?:join|get into) (?:the )?(?:customs?|queue)\b', r'\bhow does the queue work\b', r'\bhow (?:do )?(?:i|you) play with (?:penguin|peng|viewers)\b'], pr=6),
    '!mod': dict(p=[r'\bhow\b.*\b(?:get|become|be)\b.*\bmod(?:erator)?\b', r'\b(?:can|could) i (?:be|get|become)( a)? mod\b'], pr=5),
    '!vip': dict(p=[r'\bhow\b.*\b(?:get|become|be)\b.*\bvip\b', r'\b(?:can|could) i (?:be|get|become)( a)? vip\b'], pr=5),
    '!age': dict(p=[r'\bhow old (?:is|are)\b.*\b(?:penguin|peng|he|you)\b', r'\bwhat(?:\'s| is) (?:his|your|penguin\'?s?) age\b'], pr=4),
    '!height': dict(p=[r'\bhow tall (?:is|are)\b', r'\bwhat(?:\'s| is) (?:his|your|penguin\'?s?) height\b'], pr=4),
    '!weight': dict(p=[r'\bhow much (?:does|do) (?:he|you|penguin|peng) weigh\b', r'\bwhat(?:\'s| is) (?:his|your|penguin\'?s?) weight\b'], pr=4),
    '!name': dict(p=[r'\bwhat(?:\'s| is) (?:his|your|penguin\'?s?) (?:real |irl )?name\b', r'\bwhat(?:\'s| is) penguin\'?s? real name\b'], pr=4),
    '!realrank': dict(p=[r'\bwhat(?:\'s| is) (?:his|your|the) (?:real|irl|true) rank\b', r'\bwhat rank (?:is|are) (?:he|you|penguin|peng)\b'], pr=4),
    '!odds': dict(p=[r'\b(?:gamble|gambling|slots|duels?) odds\b', r'\bodds (?:of|for|on) (?:winning|gambling|slots|duels?)\b', r'\bwhat are the odds\b'], pr=4),
    '!time': dict(p=[r'\bwhat time is it\b', r'\bwhat(?:\'s| is) the time\b', r'\bwhat time is it for (?:him|penguin|peng)\b'], pr=3),
    '!tracker': dict(p=[r'\b(?:rl |rocket league |rank )?tracker\b'], pr=4),
    '!steam': dict(p=[r'\bsteam (?:id|code|profile|name|friend)\b', r'\badd (?:him|you|penguin|peng) on steam\b'], pr=4),
    '!geo': dict(p=[r'\bgeo ?guess?r (?:profile|account|link)\b'], pr=3),
    '!discord': dict(p=[r'\bdiscord\b'], pr=4),
    '!youtube': dict(p=[r'\byoutube\b(?! video)'], pr=3),
    '!tiktok': dict(p=[r'\btik ?tok\b'], pr=3),
    '!7tv': dict(p=[r'\b7tv\b', r'\bseven ?tv\b', r'\bhow (?:do )?(?:i|you) (?:get|see) (?:the )?emotes\b'], pr=4),
    '!tts': dict(p=[r'\btts\b', r'\btext[- ]to[- ]speech\b'], pr=4),
    '!prime': dict(p=[r'\b(?:twitch )?prime (?:sub|gaming)\b', r'\bhow (?:do )?(?:i|you) (?:use|sub with) prime\b', r'\buse (?:my )?prime\b'], pr=5),
    '!save': dict(p=[r'\bmobile fees\b', r'\bsave money\b.*\b(?:sub|bits)\b', r'\bsub(?:scribe)? on (?:mobile|phone)\b'], pr=3),
    '!support': dict(p=[r'\bhow\b.*\b(?:support|help)\b.*\b(?:penguin|peng|stream|channel|him)\b', r'\bways to support\b'], pr=4),
    '!drops': dict(p=[r'\bdrops?\b.*\b(?:enabled|on|active|working)\b', r'\bare there (?:any )?drops\b'], pr=4),
    '!roblox': dict(p=[r'\broblox (?:user|username|name|account|profile)\b', r'\bwhat(?:\'s| is) (?:his|your|penguin\'?s?) roblox\b'], pr=4),
    '!ubisoft': dict(p=[r'\b(?:ubisoft|r6|siege|uplay) (?:user|username|name|id|account)\b'], pr=4),
    '!modpack': dict(p=[r'\bmod ?pack\b'], pr=4),
    '!food': dict(p=[r'\b(?:favorite|favourite|fav) food\b'], pr=2),
    '!burger': dict(p=[r'\bburgie\b', r'\bburger (?:command|order|game)\b'], pr=3),
    '!gsu': dict(p=[r'\bgsu\b', r'\bgovernor\'?s? state\b'], pr=4),
    '!mods': dict(p=[r'\bmore mods\b'], pr=1),
    '!hc': dict(p=[r'\bhardcore\b.*\b(?:died|death|deaths|dead)\b'], pr=2),
}
NEEDS_Q = {'!specs', '!streamingpc', '!controller', '!schedule', '!streamtime', '!server', '!ip', '!mcrules', '!customrules', '!customs', '!howtojoin', '!mod', '!vip', '!age', '!height', '!weight', '!name', '!realrank', '!odds', '!time', '!tracker', '!steam', '!geo',
           '!discord', '!youtube', '!tiktok', '!7tv', '!tts', '!prime', '!save', '!support', '!drops', '!roblox', '!ubisoft', '!modpack', '!food', '!burger', '!gsu', '!mods', '!hc'}
CLIP_WORDS = {'!ash': 'ash|bits clip|he gives bits', '!burglin': 'burglin|burgling ?nomes', '!cat': 'cat', '!crimson': 'crimson', '!geoguesser': 'geo ?guess?er', '!golf': 'golf', '!howbigisit': 'how big is it', '!minecraft': 'minecraft|piglin', '!oopsie': 'oopsie',
              '!peak': 'peak', '!repo': 'repo', '!rl': 'rl|rocket league', '!settings': 'settings', '!squishy': 'squishy', '!uk': 'uk', '!yen': 'yen|20 subs|gifted 20', '!blizzy': 'blizzy', '!marsh': 'marsh'}
COMMON_WORD_NAMES = {'rose', 'snowy', 'shadow', 'coy', 'goat', 'w', 'cute', 'developer', 'thebest', 'zylo', 'unninocence', 'mello', 'robo', 'quinn', 'samu'}
NO_CONTEXT = {'!w', '!thebest', '!zylo', '!cute', '!developer', '!goat', '!unninocence', '!ad', '!endstream', '!cups', '!cheese', '!turtles', '!happy', '!sad', '!popcorn', '!vanish', '!water', '!unlurk', '!lurk'}
PERSON_PATTERNS = {'!sydney': [r'brick\s*wall\s*sydney', r'sydney.{0,10}brick\s*wall'], '!marshmallow': [r'who stole the marshmallow', r'stole the marshmallow'], '!speedy': [r'\bspeedy\b'], '!spedy': [r'\bspedy\b'], '!koops': [r'\bkoops\b']}
NOTES = {'!sydney': 'running joke: "brick wall Sydney"', '!marshmallow': 'long-running mystery: who stole the marshmallow (hours of VOD review, never solved)', '!purge': 'story of the day Penguin removed every entity except boats in Minecraft', '!hc': 'Penguin has nearly died in hardcore Minecraft 3 times to himself',
         '!mods': 'quote from Yoohoo15 about adding mods', '!ban': 'a joke command: nobody is actually banned', '!w': 'speedy and Yen', '!ash': 'the same clip as Nightbot\'s !bits (our !bits is the bits board)'}
DYNAMIC = {'!time': 'time', '!luck': 'luck'}
COUNTERS = {'!owngoal': 'owngoal', '!whiff': 'whiff'}
OVERRIDE = {
    '!discord': ('https://discord.gg/fktz5sq4b8', 'the export had no text for !discord/!dc; this is the invite the website uses - confirm'),
    '!popcorn': (' '.join(['PopCorn'] * 26), ''),
    '!attack': None, '!goat': None,
}

def entry(cmd, text):
    c = cmd.lstrip('!'); kind = KIND.get(cmd, 'fun')
    e = {'id': c, 'kind': kind, 'triggers': [cmd], 'aliases': ALIAS.get(cmd, []), 'response': text, 'variants': [], 'contextual': False, 'publicSafe': cmd not in UNSAFE, 'enabled': True, 'patterns': [], 'anyShape': False, 'also': [], 'tags': [], 'note': NOTES.get(cmd, ''), 'source': 'nightbot'}
    e['response'] = re.sub(r'\s*\|\s*!\w+( for main)?$', '', e['response']) if cmd in ('!specs', '!streamingpc') else e['response']
    if cmd in OVERRIDE and OVERRIDE[cmd]: e['response'] = OVERRIDE[cmd][0]; e['needsConfirm'] = OVERRIDE[cmd][1]
    if cmd == '!discord': e['needsConfirm'] = OVERRIDE[cmd][1]
    if cmd == '!attack':
        arr = text[text.index('['):text.index(']')]; m = re.findall(r'"([^"]+)"', arr)
        e['variants'] = ['$(user) ' + x.strip() for x in m]; e['response'] = e['variants'][0] if e['variants'] else text; e['kind'] = 'fun'; e['tags'] = ['random', 'touser']
    if cmd == '!luck': e['response'] = 'You got $(random 1 50)% luck BROCHACHO, GET GOOD :)'; e['tags'] = ['random']
    if cmd == '!time': e['response'] = 'It is $(time US/Central) for InnocentPenguin'; e['tags'] = ['dynamic']
    if cmd in COUNTERS: e['response'] = text.replace('$(count)', '$(count ' + COUNTERS[cmd] + ')'); e['counter'] = COUNTERS[cmd]; e['tags'] = ['counter']
    if cmd in ('!hug', '!ban'): e['tags'] = ['touser']
    if cmd == '!yen': e['tags'] = ['clip', 'person']
    if kind == 'clip': e['tags'] = e['tags'] or ['clip']
    # natural-language triggers
    pats = []; it = INTENT.get(cmd)
    if it: pats = list(it['p']); e['also'] = it.get('also', []); e['priority'] = it.get('pr', 3); e['not'] = it.get('not_', '')
    if cmd in CLIP_WORDS and e['publicSafe']:
        w = CLIP_WORDS[cmd]; pats = [r'\b(?:clip|video|link|show|send|post|play|watch)\b.*\b(?:' + w + r')\b', r'\b(?:' + w + r')\b.*\b(?:clip|video)\b']; e['anyShape'] = True; e['priority'] = 2
    if kind == 'person' and cmd not in NO_CONTEXT:
        n = re.escape(c); pats = [r'\bwho(?:\'?s| is| are)\s+(?:the\s+)?' + n + r'\b'] + PERSON_PATTERNS.get(cmd, [])
        if c not in COMMON_WORD_NAMES: pats.append(r'^\W*' + n + r'\W*$')
        e['anyShape'] = bool(PERSON_PATTERNS.get(cmd)); e['priority'] = 2
    if cmd in PERSON_PATTERNS and kind == 'person': e['anyShape'] = True
    if cmd in NO_CONTEXT: pats = []
    e['patterns'] = pats
    e['contextual'] = bool(pats) and e['publicSafe'] and cmd not in NO_CONTEXT
    if cmd in NEEDS_Q: e['anyShape'] = False
    if cmd in ('!time',): e['anyShape'] = False
    return e

out = []; skipped = []; unsafe = []; merged = []
for cmd, text in parsed.items():
    if cmd in SKIP: skipped.append((cmd, SKIP[cmd])); continue
    if cmd in ALIAS_OF: merged.append(cmd); continue
    if cmd in ('!dc',) or not text and cmd not in ('!discord',):
        if cmd != '!discord': skipped.append((cmd, 'no response text in the export')); continue
    if cmd == '!racism' or cmd == '!racist' and not text: continue
    if cmd == '!racist' and not text.startswith('http'): continue
    e = entry(cmd, text)
    if cmd in UNSAFE: unsafe.append(cmd)
    out.append(e)
# the four keyword replies (no "!"): the whole message has to be that word
for w in ('goodnight', 'hi', 'meow', 'w'):
    if w in parsed:
        out.append({'id': 'bare_' + w, 'kind': 'fun', 'triggers': [], 'aliases': [], 'response': parsed[w], 'variants': [], 'contextual': False, 'publicSafe': True, 'enabled': True, 'bare': w, 'patterns': [], 'anyShape': False, 'also': [], 'tags': ['keyword'], 'note': 'answers when a message is exactly "' + w + '" (like Nightbot did)', 'source': 'nightbot'})
seed = {'version': 1, 'settings': {'channelName': 'InnocentPenguin', 'contextual': True, 'bareWords': True, 'entryCooldownSec': 600, 'globalCooldownSec': 20, 'commandCooldownSec': 5}, 'counters': {'owngoal': 0, 'whiff': 0}, 'entries': out}
json.dump(seed, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if '--report' in sys.argv or True:
    print('parsed', len(parsed), '| entries', len(out), '| skipped', len(skipped), '| alias-merged', len(merged), '| exact-command-only (publicSafe=false)', len(unsafe), '| contextual', sum(1 for e in out if e['contextual']))
    for s in skipped: print('  skipped', s)
