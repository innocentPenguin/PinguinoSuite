"""A clip entry's natural-language pattern must need the word clip/video/link: "play rl" / "watch rl" must never post a clip.
Checks the seed and (if present) the live Data/runtime/channel_lore.json.  Usage: python Tools/test-lore-clip-patterns.py"""
import json, os, re, sys
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []; n = 0
for f in ['PinguinoB0t/channel_lore_seed.json', 'Data/runtime/channel_lore.json']:
    p = os.path.join(suite, f)
    if not os.path.exists(p): continue
    ents = json.load(open(p, encoding='utf-8'))['entries']
    rl = next(e for e in ents if e['id'] == 'rl')
    for e in ents:
        if e.get('kind') != 'clip': continue
        for pat in e.get('patterns', []):
            n += 1
            for t in ['you used a bot to play rl', 'maybe dont play rl', 'watch rl', 'show me rl', 'send rl', 'post rl', 'lets play golf', 'watch the cat', 'play minecraft']:
                if re.search(pat, t, re.I): bad.append((f, e['id'], t))
    ok = any(re.search(pt, 'send me the rl clip', re.I) for pt in rl['patterns'])
    if not ok: bad.append((f, 'rl', 'send me the rl clip should still match'))
print('PASS lore clip patterns (%d checked)' % n if not bad else 'FAIL %s' % bad)
sys.exit(1 if bad else 0)
