#!/usr/bin/env python3
"""Static guard: every ?part= widget registered in PinguinoHost/HostScenes.cs points at a page that really has a matching `.part-<name>` CSS mode plus the script that sets the class,
and every part mode a page defines is registered as a scene widget (so none is dead or unreachable). No Host needed. Usage: python Tools/test-overlay-parts.py"""
import os, re, sys
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ov = os.path.join(suite, 'PinguinoB0t', 'overlays')
sc = open(os.path.join(suite, 'PinguinoHost', 'HostScenes.cs'), encoding='utf-8', errors='replace').read()
used = set(re.findall(r'Src = "([a-z_]+\.html)\?part=([a-z]+)"', sc))
fails = []
if len(used) < 8: fails.append('expected at least 8 part widgets in HostScenes.cs, found %d' % len(used))
defined = set()
for pg in sorted({p for p, _ in used}):
    t = open(os.path.join(ov, pg), encoding='utf-8', errors='replace').read()
    if 'get("part")' not in t or 'classList.add("part-"' not in t: fails.append(pg + ': no script that sets the part-* class')
    defined |= {(pg, m) for m in re.findall(r'\.part-([a-z]+)\b', t)}
for pg, part in sorted(used):
    if (pg, part) not in defined: fails.append('%s?part=%s is a widget but the page has no .part-%s rule' % (pg, part, part))
for pg, part in sorted(defined - used): fails.append('%s defines .part-%s but no scene widget uses it' % (pg, part))
if fails: print('FAIL overlay-parts: ' + '; '.join(fails)); sys.exit(1)
print('PASS overlay-parts (%d widgets)' % len(used))
