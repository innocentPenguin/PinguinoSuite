"""Builds the Helper's knowledge pack for !helper / !ask / !pinguino.

  Data/helper/knowledge.json      PUBLIC tier (everyone). Version + date.
  Data/helper/knowledge_mod.json  MOD tier: extra entries, only read for role >= 3.

Public sources: PinguinoB0t/commands.json (viewer commands), Data/runtime/helper_facts.json (Minecraft/Discord/site facts + approved Taught notes),
Data/runtime/links.json, Data/runtime/channel_lore.json (kinds info + link, publicSafe != false), the site FAQ (best effort, cached), Docs/HELPER_PUBLIC.md
(hand-written summaries, one "## Title" section per entry) and a short bot-capabilities summary.
Mod tier adds: mod commands and Docs/HELPER_MOD.md.

GUARDRAILS (every public entry passes `leak_reason`, anything that trips it is DROPPED and reported by reason, never by content):
no secrets/tokens/key names, no emails, no internal architecture words, nothing naming people from Data/lore (person cards, people graph, lore users)
and nobody who opted out of the bots (chat_memory Privacy, unping.json). Data/lore is only ever read as a deny-list, never copied.

Usage: python Tools/build-helper-pack.py [--suite DIR] [--data DIR] [--out DIR] [--no-net]   (nightly: Docs/NIGHTLY_CHECKLIST.md)"""
import argparse, datetime, json, os, re, sys, urllib.request

ALLOWED_NAMES = {'innocentpenguin', 'innocentpenguin_', 'innocentpinguino', 'pinguinob0t', 'pinguinohelper', 'chattypinguino', 'penguino'}
SECRET_RX = re.compile(r"(api[_ -]?key|apikey|client[_ -]?secret|\bsecret\b|access[_ -]?token|refresh[_ -]?token|\btoken\b|oauth|\bbearer\b|authorization|\bse_jwt\b|\bjwt\b|aikey|webhook|private[_ -]?key|\bvault\b)", re.I)
TOKEN_RX = re.compile(r"(eyJ[A-Za-z0-9_\-]{10,}|oauth:[A-Za-z0-9]{10,}|\bsk-[A-Za-z0-9\-]{10,}|(?<![A-Za-z0-9/._\-])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9/._\-]))")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ARCH_RX = re.compile(r"(streamer\.bot|PinguinoHost|\bHost\b|\.json\b|\.cs\b|\bData[\\/]|/api/|127\.0\.0\.1|localhost|\bHelix\b|\bC#|\bport 87\d\d\b|\bsession 0\d\b|\bmodule token\b)", re.I)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


def deny_names(data):
    """Everyone who must never be named in the pack: Data/lore (cards, graph, lore users) and anybody who opted out."""
    names = set()
    lore = os.path.join(data, 'lore')
    cards = os.path.join(lore, 'person_cards')
    if os.path.isdir(cards):
        for fn in os.listdir(cards):
            if fn.lower().endswith('.json'):
                names.add(fn[:-5].lower())
    g = read_json(os.path.join(lore, 'people_graph.json'), {}) or {}
    for n in g.get('nodes', []) if isinstance(g, dict) else []:
        if isinstance(n, dict) and n.get('login'):
            names.add(str(n['login']).lower())
    for fn in ('channel_lore.json',):
        c = read_json(os.path.join(lore, fn), {}) or {}
        for it in c.get('items', []) if isinstance(c, dict) else []:
            for u in it.get('users', []) or []:
                names.add(str(u).lower())
    # opted out
    rt = os.path.join(data, 'runtime')
    mem = read_json(os.path.join(rt, 'chat_memory.json'), {}) or {}
    for v in mem.values() if isinstance(mem, dict) else []:
        if isinstance(v, dict) and v.get('Privacy') and v.get('Login'):
            names.add(str(v['Login']).lower())
            for a in v.get('Aliases', []) or []:
                names.add(str(a).lower())
    un = read_json(os.path.join(rt, 'unping.json'), {}) or {}
    if isinstance(un, dict):
        for x in un.get('logins', []) or []:
            names.add(str(x).lower())
        for k, v in un.items():
            if v is True:
                names.add(str(k).lower())
    return {n for n in names if len(n) >= 4 and n not in ALLOWED_NAMES}


def leak_reason(text, names, public=True):
    """'' when clean, else a short reason (never the matched content)."""
    t = text or ''
    if SECRET_RX.search(t):
        return 'secret-or-key-name'
    if TOKEN_RX.search(t):
        return 'token-like-string'
    if EMAIL_RX.search(t):
        return 'email'
    low = t.lower()
    for n in names:
        if re.search(r'(?<![a-z0-9_])' + re.escape(n) + r'(?![a-z0-9_])', low):
            return 'private-or-opted-out-name'
    if public and ARCH_RX.search(t):
        return 'internal-architecture'
    return ''


def clip(s, n=400):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n - 3].rsplit(' ', 1)[0] + '...'


def sections(path):
    """## Title / body sections of a hand-written markdown file."""
    try:
        txt = open(path, encoding='utf-8-sig').read()
    except Exception:
        return []
    out = []
    for m in re.finditer(r'^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)', txt, re.S | re.M):
        body = clip(m.group(2))
        if body:
            out.append((m.group(1).strip(), body))
    return out


CAPABILITIES = ("I'm PinguinoHelper. I answer questions about the stream, commands, the queue and the website, and point you to the right page. "
                "I can't ban, time out, change settings, give points or contact Ivan. Mods handle that.")


def build(suite, data, out, net=True, today=None):
    names = deny_names(data)
    rt = os.path.join(data, 'runtime')
    dropped = {}
    pub, mod = [], []

    def add(lst, public, eid, title, text, keywords='', source=''):
        text = clip(text)
        if not text:
            return
        why = leak_reason(title + ' ' + keywords + ' ' + text, names, public)
        if why:
            dropped[why] = dropped.get(why, 0) + 1
            return
        lst.append({'id': eid, 'title': clip(title, 80), 'keywords': clip(keywords, 120), 'text': text, 'source': source})

    # commands
    cmds = (read_json(os.path.join(suite, 'PinguinoB0t', 'commands.json'), {}) or {}).get('commands', [])
    for c in cmds:
        if not c.get('command') or c.get('publicSafe') is False:
            continue
        who = str(c.get('who', '')).lower()
        title = c['command'] + (' ' + ' '.join(c.get('aliases', [])) if c.get('aliases') else '')
        text = (c.get('usage') or c['command']) + ' - ' + (c.get('description') or '')
        if c.get('examples'):
            text += ' Example: ' + c['examples'][0]
        kw = ' '.join(filter(None, [c.get('category', ''), c.get('section', '')]))
        if who.startswith('everyone') or who == 'automatic':
            add(pub, True, 'cmd:' + c['command'], title, text, kw, 'commands.json')
        elif who.startswith('mod'):
            add(mod, False, 'modcmd:' + c['command'], title, text + ' (mods only)', kw, 'commands.json')

    # facts + approved Taught notes
    facts = read_json(os.path.join(rt, 'helper_facts.json'), {}) or {}
    skip = {'Note', 'Taught'}
    for k, v in facts.items():
        if k in skip or not isinstance(v, str) or not v.strip():
            continue
        label = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k)
        add(pub, True, 'fact:' + k, label, label + ': ' + v, 'minecraft discord website server ip' if k.startswith(('Mc', 'Discord', 'Website')) else '', 'helper_facts')
    for t in facts.get('Taught', []) or []:
        if isinstance(t, dict) and t.get('publicSafe') is not False and t.get('text'):
            add(pub, True, 'taught:' + str(t.get('id', len(pub))), 'Taught note', t['text'], '', 'teach')

    # links (the source of truth)
    links = (read_json(os.path.join(rt, 'links.json'), {}) or {}).get('links', {})
    for k, v in links.items():
        if isinstance(v, str) and v.startswith('http'):
            add(pub, True, 'link:' + k, 'Link ' + k, k.capitalize() + ' link: ' + v, 'link url ' + k, 'links.json')

    # public channel lore: only info + link entries that are not publicSafe=false (jokes and people entries stay out)
    lore = read_json(os.path.join(rt, 'channel_lore.json'), {}) or {}
    for e in lore.get('entries', []):
        if e.get('publicSafe') is False or e.get('enabled') is False or e.get('kind') not in ('info', 'link') or not e.get('response'):
            continue
        add(pub, True, 'lore:' + str(e.get('id')), ' '.join(e.get('triggers') or [e.get('id', '')]), e['response'], ' '.join(e.get('tags') or []), 'channel_lore')

    # site FAQ (best effort, cached)
    faq_cache = os.path.join(out, 'faq_cache.json')
    faq = None
    settings = read_json(os.path.join(rt, 'helper_settings.json'), {}) or {}
    url = settings.get('FactsUrl', 'https://innocentpenguin.com/api/faq')
    if net and url:
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': 'PinguinoHost/1.0'})
            faq = json.load(urllib.request.urlopen(rq, timeout=8))
            os.makedirs(out, exist_ok=True)
            json.dump(faq, open(faq_cache, 'w', encoding='utf-8'))
        except Exception:
            faq = None
    if faq is None:
        faq = read_json(faq_cache)
    items = []
    if isinstance(faq, dict):
        lst = faq.get('faq') or faq.get('items')
        if isinstance(lst, list):
            items = [x for x in lst if isinstance(x, dict)]
        else:
            items = [{'key': k, 'answer': v} for k, v in faq.items() if isinstance(v, str)]
    elif isinstance(faq, list):
        items = [x for x in faq if isinstance(x, dict)]
    for i, x in enumerate(items):
        q = x.get('question') or x.get('q') or x.get('title') or x.get('key') or ''
        a = x.get('answer') or x.get('a') or x.get('text') or ''
        if q and isinstance(a, str) and a.strip():
            add(pub, True, 'faq:' + str(x.get('key') or i), str(q), str(q) + ' ' + a, 'faq', 'site faq')

    # hand-written summaries
    for i, (t, b) in enumerate(sections(os.path.join(suite, 'Docs', 'HELPER_PUBLIC.md'))):
        add(pub, True, 'doc:%d' % i, t, b, '', 'HELPER_PUBLIC.md')
    for i, (t, b) in enumerate(sections(os.path.join(suite, 'Docs', 'HELPER_MOD.md'))):
        add(mod, False, 'moddoc:%d' % i, t, b, 'mod', 'HELPER_MOD.md')
    add(pub, True, 'about:helper', 'What the helper can do', CAPABILITIES, 'helper bot can cannot capabilities', 'built-in')

    # re-check mod tier against the secret rules and opted-out names too (done in add); write
    os.makedirs(out, exist_ok=True)
    today = today or datetime.date.today().isoformat()
    ver = 1
    old = read_json(os.path.join(out, 'knowledge.json'), {}) or {}
    if isinstance(old, dict) and isinstance(old.get('version'), int):
        ver = old['version'] + 1
    stamp = {'version': ver, 'date': today, 'built': datetime.datetime.now().isoformat(timespec='seconds')}
    for fn, tier, lst in (('knowledge.json', 'public', pub), ('knowledge_mod.json', 'mod', mod)):
        with open(os.path.join(out, fn), 'w', encoding='utf-8') as f:
            json.dump(dict(stamp, tier=tier, entries=lst), f, indent=1, ensure_ascii=False)
    return {'public': len(pub), 'mod': len(mod), 'dropped': dropped, 'version': ver}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', default=os.path.dirname(here))
    ap.add_argument('--data', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--no-net', action='store_true')
    a = ap.parse_args()
    data = a.data or os.path.join(a.suite, 'Data')
    out = a.out or os.path.join(data, 'helper')
    r = build(a.suite, data, out, net=not a.no_net)
    print('helper pack v%d: %d public, %d mod entries; dropped %s' % (r['version'], r['public'], r['mod'], r['dropped'] or 'none'))


if __name__ == '__main__':
    main()
