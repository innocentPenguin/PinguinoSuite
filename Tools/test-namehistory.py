#!/usr/bin/env python3
"""Offline fixture test for build-namehistory.py (no suite data, no network)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
b = __import__('build-namehistory')
r = tempfile.mkdtemp()
def w(p, t):
    p = os.path.join(r, p); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w', encoding='utf-8').write(t)
def day(d, rows):
    w('Data/chat_logs/2026/%s/2026-%s.txt' % (d[:2], d), ''.join('[2026-%s 20:00:%02d] #c %s: %s\n' % (d, i % 60, u, m) for i, (u, m) in enumerate(rows)))
day('03-01', [('oldname', 'hi @bob')] * 6 + [('bob', 'yo')] * 6)
day('03-05', [('newname', 'hi @bob')] * 6 + [('bob', 'yo')] * 6)         # oldname -> newname: id says same person
day('04-01', [('cooluser1', 'x @bob')] * 6)
day('04-03', [('cooluser2', 'x @bob')] * 6 + [('carl', 'i changed my name to nobodyseen')])
day('05-01', [('hidden1', 'hello')] * 6)
w('Data/chat_logs/live/2026-05-02.jsonl', '{"t":1777000000000,"u":"newname","i":"42","m":"x"}\n{"t":1770000000000,"u":"oldname","i":"42","m":"x"}\n')
w('Data/boards/aliases.json', '{"aliases":{"zed_old":"zed"}}')
w('Data/chat_logs/hidden_sources.json', '{"users":{"hidden1":{}}}')
w('Data/namehistory/helix_ids.json', '{"data":[{"id":"77","login":"helixnew"}]}')   # picked up by default
w('Data/chat_logs/live/2026-05-03.jsonl', '{"t":1777000000000,"u":"helixold","i":"77","m":"x"}\n{"t":1777000000001,"u":"troll","i":"88","m":"x"}\n')
w('Data/boards/banned_accounts.json', '{"accounts":{"troll":"banned impersonator"}}')
db = b.main(['--root', r])
by = {c['canonicalLogin']: c for c in db['chatters']}
assert {n['login'] for n in by['newname']['names']} == {'oldname', 'newname'}, by['newname']
assert all(n['tier'] == 'CERTAIN' for n in by['newname']['names'])
assert 'cooluser1' in by and 'cooluser2' in by, 'POSSIBLE/LIKELY names must stay separate'
assert any(p['from'] == 'cooluser1' and p['to'] == 'cooluser2' and p['tier'] in ('LIKELY', 'POSSIBLE') for p in db['pairs'])
assert any(s['speaker'] == 'carl' for s in db['unresolvedStatements'])
assert {n['login'] for n in by['zed']['names']} == {'zed', 'zed_old'}
assert {n['login'] for n in by['helixnew']['names']} == {'helixold', 'helixnew'}, 'Helix by id rename'
assert by['troll'].get('banned') and 'notSamePersonAs' in by['troll']
lk = json.load(open(os.path.join(r, 'Data', 'namehistory', 'lookups.json')))
assert 'hidden1' in lk['skipOptedOut']
print('namehistory fixtures OK')
