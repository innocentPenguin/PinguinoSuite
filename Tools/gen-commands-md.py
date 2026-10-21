"""Regenerates PinguinoB0t/COMMANDS.md from PinguinoB0t/commands.json (the source of truth). Run from anywhere: python Tools/gen-commands-md.py"""
import json, os
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(suite, 'PinguinoB0t', 'commands.json'), encoding='utf-8'))
cats = {}
for c in d['commands']: cats.setdefault((c['who'].startswith('mods'), c['category']), []).append(c)
esc = lambda t: t.replace('|', r'\|')
out = ['# PinguinoBot commands', '', 'The website reads `commands.json`, which is the source of truth (the Host also serves it at `GET /api/commands-doc` with viewer / mod lists and a permission field). This page is generated from it (python Tools/gen-commands-md.py); edit the JSON, not this page.']
for mod in (False, True):
    out.append('\n## ' + ('Moderator commands' if mod else 'Viewer commands') + '\n')
    for (m, cat), cs in sorted(cats.items()):
        if m != mod: continue
        out += ['### ' + cat, '', '| Command | Usage | What it does |', '|---|---|---|']
        for c in cs: out.append('| `%s` | `%s` | %s |' % (c['command'], esc(c['usage']), esc(c['description'])))
        out.append('')
open(os.path.join(suite, 'PinguinoB0t', 'COMMANDS.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
