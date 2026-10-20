#!/usr/bin/env python3
"""Build the chatter NAME HISTORY database (offline, rerunnable, read-only on its inputs).

    python Tools\\build-namehistory.py                 # writes Data\\namehistory\\names.json
    python Tools\\build-namehistory.py --root X --out Y  # use another suite root / output dir (tests)
    python Tools\\build-namehistory.py --helix-ids ids.json  # optional: merge a saved Helix /users?id= answer

Evidence tiers (nothing below CERTAIN is ever merged; LIKELY/POSSIBLE only go in "pairs"):
  CERTAIN   same Twitch id under different logins (Streamer.bot users.dat, Chatty live jsonl, multi.db,
            optional saved Helix answer) or an explicit entry in Data\\boards\\aliases.json.
  LIKELY    a chatter says in chat they renamed / that login X is their old or other account and X exists
            in the logs, or very similar names where one stops and the other starts with overlapping
            people they talk to.
  POSSIBLE  similar names with a clean hand-over in time, or a rename statement we cannot resolve.

Network is never touched. The public log sites and Helix are reached by other tools; this script only
reads what they already saved. Logins in Data\\chat_logs\\hidden_sources.json (opt-outs) are kept local
only and are never listed as a lookup target in the "lookups" file.
"""
import argparse, collections, datetime as dt, difflib, glob, json, os, re, sys

BOTS = {'pinguinob0t', 'chattypinguino', 'pinguinohelper', 'nightbot', 'streamelements', 'soundalerts',
        'synchrabot', 'rocketrankbot', 'potatbotat', 'sery_bot', 'moobot', 'fossabot'}
LINE = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] #\S+ ([A-Za-z0-9_]{2,26}): (.*)$')
TIERS = {'CERTAIN': 3, 'LIKELY': 2, 'POSSIBLE': 1}
STATEMENTS = [
    (re.compile(r"changed (?:my )?(?:twitch )?(?:user ?name|name|display ?name) to @?(\w{3,25})"), 'new'),
    (re.compile(r"changed (?:my )?(?:twitch )?(?:user ?name|name|display ?name) from @?(\w{3,25})"), 'old'),
    (re.compile(r"(?:my )?(?:old|previous|other|first) (?:twitch )?(?:acc(?:ount)?|name|user ?name)(?: (?:is|was|=|:))? @?(\w{3,25})"), 'old'),
    (re.compile(r"@?(\w{3,25}) (?:is|was) my (?:old|previous|other|first) (?:twitch )?(?:acc(?:ount)?|name|user ?name)"), 'old'),
    (re.compile(r"(?:my )?(?:new) (?:twitch )?(?:acc(?:ount)?|name|user ?name)(?: (?:is|was|=|:))? @?(\w{3,25})"), 'new'),
]
STATEMENT_HINT = re.compile(r'(?:changed (?:my )?(?:twitch )?(?:user ?name|name)|\b(?:old|previous|new) (?:acc|account|name|username))')


def jload(p, default=None):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def day_ts(s):
    return dt.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp()


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Seen:
    def __init__(self):
        self.first = {}; self.last = {}; self.n = collections.Counter(); self.ment = collections.defaultdict(collections.Counter)

    def add(self, login, ts, mentions=()):
        self.n[login] += 1
        if login not in self.first or ts < self.first[login]: self.first[login] = ts
        if login not in self.last or ts > self.last[login]: self.last[login] = ts
        for m in mentions: self.ment[login][m] += 1


def read_logs(root, seen):
    """Day files -> Seen, plus rename statements. Returns statements list."""
    statements = []
    for f in sorted(glob.glob(os.path.join(root, 'Data', 'chat_logs', '2026', '*', '*.txt')) +
                    glob.glob(os.path.join(root, 'Data', 'chat_logs', '*', '*', '*.txt'))):
        with open(f, encoding='utf-8-sig', errors='replace') as fh:
            for raw in fh:
                m = LINE.match(raw.rstrip('\n'))
                if not m: continue
                t, u, text = m.groups(); u = u.lower(); ts = day_ts(t)
                low = text.lower()
                ments = {x for x in re.findall(r'@(\w{3,25})', low) if x != u}
                seen.add(u, ts, ments)
                if STATEMENT_HINT.search(low) and u not in BOTS:
                    for rx, kind in STATEMENTS:
                        sm = rx.search(low)
                        if sm: statements.append({'speaker': u, 'target': sm.group(1), 'kind': kind, 'at': t, 'text': text[:200]}); break
    return statements


def read_live(root, seen, ids):
    for f in sorted(glob.glob(os.path.join(root, 'Data', 'chat_logs', 'live', '*.jsonl'))):
        with open(f, encoding='utf-8-sig', errors='replace') as fh:
            for l in fh:
                try: j = json.loads(l)
                except ValueError: continue
                u = (j.get('u') or '').lower()
                if not u: continue
                ts = (j.get('t') or 0) / 1000
                if ts: seen.add(u, ts)
                if j.get('i'): ids[str(j['i'])].setdefault(u, 'Chatty live jsonl')


def read_ids(root, ids):
    # Streamer.bot users.dat
    for p in glob.glob(os.path.join(root, 'Archive', '*', 'raw-data', 'users.dat')):
        d = jload(p, {}) or {}
        for x in d.get('users', []):
            if x.get('type') == 'twitch' and x.get('id') and x.get('name'):
                ids[str(x['id'])].setdefault(x['name'].lower(), 'Streamer.bot users.dat')
    # multi.db
    db = os.path.join(root, 'Data', 'runtime', 'multi', 'multi.db')
    if os.path.exists(db):
        import sqlite3
        try:
            c = sqlite3.connect('file:' + db.replace('\\', '/') + '?mode=ro', uri=True)
            for uid, u in c.execute("select user_id,user from messages where platform='twitch'"):
                if uid and u: ids[str(uid)].setdefault(u.lower(), 'multi.db')
        except Exception as e:
            print('multi.db skipped:', e, file=sys.stderr)


def read_helix(path, ids):
    """Saved Helix /users answers: {"data":[{"id","login"}...]} or a list of those; merged by id."""
    d = jload(path, None)
    rows = d.get('data', []) if isinstance(d, dict) else (d or [])
    for r in rows:
        if r.get('id') and r.get('login'): ids[str(r['id'])].setdefault(r['login'].lower(), 'Helix /users')


class UF:
    def __init__(self): self.p = {}
    def f(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def u(self, a, b): self.p[self.f(a)] = self.f(b)


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def similar_pairs(seen, linked, min_msgs=5):
    """Name-similar logins where one stops and the other starts. Returns list of dicts."""
    logins = [u for u in seen.n if u not in BOTS and seen.n[u] >= min_msgs]
    buckets = collections.defaultdict(set)
    for u in logins:
        n = norm(u); stem = re.sub(r'\d+$', '', n)
        for k in (n[:4], n[-4:], stem):
            if len(k) >= 4: buckets[k].add(u)
    cand = set()
    for b in buckets.values():
        if 1 < len(b) <= 60:
            for a in b:
                for c in b:
                    if a < c: cand.add((a, c))
    out = []
    for a, b in cand:
        old, new = (a, b) if seen.first[a] <= seen.first[b] else (b, a)
        if seen.last[old] > seen.first[new] + 86400: continue   # both active at once: two people / alts, not a rename
        gap = (seen.first[new] - seen.last[old]) / 86400
        if gap > 45: continue
        sim = difflib.SequenceMatcher(None, norm(old), norm(new)).ratio()
        if sim < 0.65: continue
        mo, mn = set(seen.ment[old]), set(seen.ment[new])
        jac = len(mo & mn) / len(mo | mn) if mo | mn else 0.0
        tier = 'LIKELY' if (sim >= 0.8 and gap <= 14) or (sim >= 0.65 and jac >= 0.3) else 'POSSIBLE'
        out.append({'from': old, 'to': new, 'tier': tier, 'nameSimilarity': round(sim, 2), 'mentionOverlap': round(jac, 2),
                    'gapDays': round(gap, 1), 'oldMsgs': seen.n[old], 'newMsgs': seen.n[new],
                    'oldLast': iso(seen.last[old]), 'newFirst': iso(seen.first[new]), 'source': 'name similarity + timing'})
    out.sort(key=lambda p: (-TIERS[p['tier']], -p['nameSimilarity'], p['gapDays']))
    return out[:500]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--helix-ids', default=None)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root); out = a.out or os.path.join(root, 'Data', 'namehistory')
    os.makedirs(out, exist_ok=True)

    seen = Seen(); ids = collections.defaultdict(dict)
    statements = read_logs(root, seen)
    read_live(root, seen, ids); read_ids(root, ids)
    if a.helix_ids: read_helix(a.helix_ids, ids)
    hidden = set((jload(os.path.join(root, 'Data', 'chat_logs', 'hidden_sources.json'), {}) or {}).get('users', {}))

    uf = UF(); why = {}          # why[(login)] = (tier, source) for how it joined its group
    id_of = {}
    for uid, names in ids.items():
        ns = list(names)
        for n in ns:
            id_of.setdefault(n, uid)
            seen.n.setdefault(n, 0)
        for n in ns[1:]:
            uf.u(ns[0], n)
            why[n] = ('CERTAIN', 'same Twitch id %s (%s)' % (uid, names[n]))
            why.setdefault(ns[0], ('CERTAIN', 'same Twitch id %s (%s)' % (uid, names[ns[0]])))
    aliases = (jload(os.path.join(root, 'Data', 'boards', 'aliases.json'), {}) or {}).get('aliases', {})
    alias_main = {}
    for al, main_ in aliases.items():
        al, main_ = al.lower(), main_.lower()
        uf.u(al, main_); alias_main[al] = main_
        why[al] = ('CERTAIN', 'Data\\boards\\aliases.json (Ivan alias; may be an alt account rather than a rename)')
        why.setdefault(main_, ('CERTAIN', 'Data\\boards\\aliases.json main'))

    groups = collections.defaultdict(set)
    for u in list(seen.n): groups[uf.f(u)].add(u)
    for u in list(uf.p): groups[uf.f(u)].add(u)
    chatters = []
    for names in groups.values():
        ordered = sorted(names, key=lambda n: (seen.first.get(n, 9e18), n))
        active = [n for n in names if n in seen.last]
        # canonical: the alias target if given, else the most recently seen login
        mains = {alias_main[n] for n in names if n in alias_main}
        canon = next(iter(mains)) if len(mains) == 1 else (max(active, key=lambda n: seen.last[n]) if active else ordered[-1])
        tid = next((id_of[n] for n in names if n in id_of), None)
        entries = []
        for n in ordered:
            tier, src = why.get(n, ('CERTAIN', 'logs (the login itself)'))
            e = {'login': n, 'firstSeen': iso(seen.first[n]) if n in seen.first else None,
                 'lastSeen': iso(seen.last[n]) if n in seen.last else None, 'messages': seen.n.get(n, 0),
                 'source': src, 'tier': tier}
            if n in hidden: e['optedOut'] = True
            entries.append(e)
        chatters.append({'canonicalLogin': canon, 'twitchId': tid, 'names': entries})
    chatters.sort(key=lambda c: c['canonicalLogin'])
    multi = [c for c in chatters if len(c['names']) > 1]

    # LIKELY/POSSIBLE candidates -- never merged above.
    merged = {uf.f(u) for u in seen.n}
    pairs = []
    for p in similar_pairs(seen, uf):
        if uf.f(p['from']) == uf.f(p['to']): continue          # already CERTAIN
        pairs.append(p)
    unresolved = []
    for s in statements:
        t, sp = s['target'], s['speaker']
        if t == sp or t in BOTS or uf.f(t) == uf.f(sp): continue
        if not (t in seen.n and seen.n[t] > 0):
            unresolved.append(s); continue            # target is not a login we saw: needs a human, never a pair
        old, new = (t, sp) if s['kind'] == 'old' else (sp, t)
        pairs.append({'from': old, 'to': new, 'tier': 'LIKELY', 'source': 'chat statement by ' + sp,
                      'statement': s['text'], 'statementAt': s['at']})
    # same pair from two sources: keep the stronger one, note both
    best = {}
    for p in pairs:
        k = frozenset((p['from'], p['to']))
        if k not in best or TIERS[p['tier']] > TIERS[best[k]['tier']]: best[k] = p
    pairs = sorted(best.values(), key=lambda p: (-TIERS[p['tier']], p['from']))
    # banned / impersonator accounts: never the same person as anyone, never a pair candidate
    banned = {}
    try: banned = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'boards', 'banned_accounts.json'), encoding='utf-8-sig')).get('accounts', {})
    except Exception: pass
    pairs = [p for p in pairs if p['from'] not in banned and p['to'] not in banned]
    for c in chatters:
        if any(n['login'] in banned for n in c['names']):
            c['banned'] = True; c['notSamePersonAs'] = 'impersonator / banned: ' + ' '.join(banned[n['login']] for n in c['names'] if n['login'] in banned)

    counts = {'chatters': len(chatters), 'withRenamesCertain': len(multi),
              'certainNames': sum(len(c['names']) for c in multi), 'withTwitchId': sum(1 for c in chatters if c['twitchId']),
              'idsKnown': len(ids), 'likelyPairs': sum(p['tier'] == 'LIKELY' for p in pairs),
              'possiblePairs': sum(p['tier'] == 'POSSIBLE' for p in pairs), 'statements': len(statements), 'unresolvedStatements': len(unresolved)}
    db = {'version': 1, 'built': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
          'note': 'names = same person over time. Only CERTAIN groups are merged. pairs are for review: never auto-merge.',
          'counts': counts, 'chatters': chatters, 'pairs': pairs,
          'unresolvedStatements': unresolved[:300]}
    with open(os.path.join(out, 'names.json'), 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    # who may be looked up on external sites: every login except opted-out ones
    with open(os.path.join(out, 'lookups.json'), 'w', encoding='utf-8') as f:
        json.dump({'note': 'logins safe to look up on public log sites / Helix. Opted-out logins are excluded.',
                   'skipOptedOut': sorted(hidden),
                   'ids': sorted(i for i, ns in ids.items() if not (set(ns) & hidden))}, f, indent=1)
    print(json.dumps(counts))
    return db


if __name__ == '__main__':
    main()
