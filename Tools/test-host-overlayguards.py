#!/usr/bin/env python3
"""Static guards for overlay pages: long names, emoji, RTL, hostile text must not break a stream.
No Host needed. Usage: python Tools/test-overlay-guards.py"""
import os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
ov = os.path.join(here, '..', 'PinguinoB0t', 'overlays')
fails = []

def page(n):
    with open(os.path.join(ov, n), encoding='utf-8') as f:
        return f.read()

def need(cond, msg):
    if not cond:
        fails.append(msg)

# 1. every player/viewer name box truncates (ellipsis) and isolates its text direction
for f, pat in [('players.html', r'\.nm > span \{[^}]*\}'), ('players_vertical.html', r'\.nm > span \{[^}]*\}'),
               ('queue.html', r'\.name \{[^}]*\}'), ('queue.html', r'\.epic \{[^}]*\}'),
               ('subroll.html', r'\.row \.nm \{[^}]*\}')]:
    m = re.search(pat, page(f))
    need(m is not None, f + ': rule ' + pat + ' missing')
    if m:
        need('text-overflow:ellipsis' in m.group(0), f + ': ' + pat + ' has no ellipsis')
        need('unicode-bidi:plaintext' in m.group(0), f + ': ' + pat + ' has no unicode-bidi:plaintext')

# 2. long unbroken words wrap instead of overflowing
for f, sel in [('wheel.html', '#wait'), ('wheel.html', '#pick'), ('wheel.html', '#final'), ('customs.html', '#d'), ('chat.html', '.m')]:
    m = re.search(re.escape(sel) + r'\s*\{[^}]*\}', page(f))
    need(m is not None and 'overflow-wrap:anywhere' in m.group(0), f + ': ' + sel + ' lacks overflow-wrap:anywhere')

# 3. viewer-controlled text never reaches innerHTML unescaped: every innerHTML line that builds names uses esc()
for f in ['players.html', 'players_vertical.html', 'queue.html', 'subroll.html']:
    s = page(f)
    need('function esc(' in s, f + ': esc() helper missing')
    for i, line in enumerate(s.splitlines(), 1):
        if 'innerHTML' in line and re.search(r'\.(user|name|epic|Username|Epic|display)\b', line) and 'esc(' not in line:
            need(False, '%s:%d innerHTML with a name but no esc()' % (f, i))
for f in ['chat.html', 'customs.html']:
    need('innerHTML' not in page(f), f + ': uses innerHTML (viewer text must go through textContent)')

# 4. list sizes are capped so 40 players / 300 subs cannot grow the overlay without bound
q = page('queue.html')
need(re.search(r'MAX_ROWS\s*=\s*\d+', q) is not None, 'queue.html: MAX_ROWS cap missing')

if fails:
    print('FAIL overlay-guards')
    for x in fails:
        print('  -', x)
    sys.exit(1)
print('PASS overlay-guards')
