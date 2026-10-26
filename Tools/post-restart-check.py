#!/usr/bin/env python3
"""Post-restart check of the live Host. READ-ONLY: GET requests to loopback only, no posts, no chat, no OBS, no Twitch.
Usage: python Tools/post-restart-check.py [--base http://127.0.0.1:8770] [--since GITREV] [--no-routes] [--lenient]
Checks: /api/status, /api/live-state, /api/prestream (every item; fail/warn listed), /api/scene-health, every overlay page = 200 and carries the
overlay-options.js tag, /api/overlay-options/schema (profiles), /api/overlay-options/health, /api/economy/preview, /api/intro, and every GET route
the commits since the Host build added (git diff of PinguinoHost/*.cs: must answer anything but 404). /api/clips-pick and anything that reserves,
fires, polls or spins is never hit. --lenient (sim tests only: pre-stream fails count as WARN, a sim Host has no Twitch/OBS). Prints a summary table. Exit 0 = no FAIL (WARN does not fail), 1 = at least one FAIL.
Test it against a sim Host: python Tools/post-restart-check.py --base http://127.0.0.1:<port> (see Tools/test-host-postrestart.py)."""
import glob, json, os, re, subprocess, sys, time, urllib.request, urllib.error

here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
argv = sys.argv[1:]
def opt(n, d=None):
    return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
BASE = opt('--base', 'http://127.0.0.1:8770').rstrip('/')
if not re.match(r'^http://(127\.0\.0\.1|localhost|\[::1\]):\d+$', BASE):
    sys.exit('refusing: --base must be a loopback http://127.0.0.1:<port> address')
NEVER = re.compile(r'clips-pick|reserve|fire|spin|send|poll|claim|next|shout|/mod/|login|oauth|callback|restart|shutdown|stop|reset|delete|logout', re.I)
rows = []   # (status, name, detail)

def add(st, name, detail=''):
    rows.append((st, name, str(detail)[:200]))

def fetch(p, timeout=15):
    """GET only. Returns (code, body-text); code 0 = no answer."""
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + p, method='GET'), timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try: b = e.read().decode('utf-8', 'replace')
        except Exception: b = ''
        return e.code, b
    except Exception as e:
        return 0, str(e)

def post_only(route):
    """True when a PinguinoHost source line names this route together with a POST/PUT/DELETE test (GET 404 is then expected)."""
    pat = re.compile(r'(?:m|HttpMethod)\s*==\s*"(?:POST|PUT|DELETE)"')
    try:
        for fn in glob.glob(os.path.join(suite, 'PinguinoHost', '*.cs')):
            for ln in open(fn, encoding='utf-8', errors='replace'):
                if ('"' + route + '"') in ln and pat.search(ln): return True
    except Exception: pass
    return False

def jget(p):
    c, b = fetch(p)
    try: return c, json.loads(b)
    except Exception: return c, None

# 1. alive
c, st = jget('/api/status')
if c != 200 or not isinstance(st, dict):
    add('FAIL', 'host answers /api/status', 'HTTP %s %s' % (c, st)); uptime = None
else:
    uptime = st.get('uptimeSec')
    add('PASS', 'host answers /api/status', 'uptime %ss, sim=%s, chat=%s, eventsub=%s, obs=%s' % (uptime, st.get('sim'), st.get('chatConnected'), st.get('eventSubConnected'), st.get('obsConnected')))
    add('PASS' if st.get('ok') else 'FAIL', 'status ok flag', st.get('ok'))
c, ls = jget('/api/live-state')
add('PASS' if c == 200 and isinstance(ls, dict) and ls.get('ok') else 'FAIL', '/api/live-state', 'HTTP %s offlineMode=%s' % (c, (ls or {}).get('offlineMode')))

# 2. pre-stream list: every item
c, ps = jget('/api/prestream')
if c != 200 or not isinstance(ps, dict):
    add('FAIL', '/api/prestream', 'HTTP %s' % c)
else:
    items = ps.get('items') or []
    for it in items:
        s = str(it.get('status', '')).lower()
        add({'pass': 'PASS', 'warn': 'WARN', 'fail': 'WARN' if '--lenient' in argv else 'FAIL'}.get(s, 'WARN'), 'prestream: ' + str(it.get('id')), (it.get('label') or '') + (' - ' + it['detail'] if it.get('detail') else ''))
    add('PASS' if items else 'FAIL', 'prestream has items', '%d items, overall %s' % (len(items), ps.get('status')))

# 3. scenes
c, sh = jget('/api/scene-health')
if c != 200 or not isinstance(sh, dict):
    add('FAIL', '/api/scene-health', 'HTTP %s' % c)
else:
    add('PASS' if sh.get('ok') else 'WARN', 'scene health', '; '.join(sh.get('problems') or []) or 'no problems')
for prof in ('h', 'v'):
    c, sl = jget('/api/scene-layouts?profile=' + prof)
    ok = c == 200 and isinstance(sl, dict) and sl.get('ok') and len((sl.get('layout') or {}).get('widgets') or []) > 0
    add('PASS' if ok else 'FAIL', 'scene layout ' + prof, 'resolvedBy=%s game=%s' % ((sl or {}).get('resolvedBy'), (sl or {}).get('currentGame')) if ok else 'HTTP %s' % c)
c, sw = jget('/api/scene-widgets')
if c == 200 and isinstance(sw, dict):
    ws = sw.get('widgets') or []
    bad = [w.get('id') for w in ws if w.get('available') is False]
    add('PASS' if ws and not bad else 'WARN', 'scene widgets', '%d widgets%s' % (len(ws), ('; unavailable: ' + ', '.join(map(str, bad))) if bad else ''))
else:
    add('FAIL', '/api/scene-widgets', 'HTTP %s' % c)

# 4. every overlay page: 200 + the fit script tag
od = os.path.join(suite, 'PinguinoB0t', 'overlays')
pages = sorted(f for f in os.listdir(od) if f.endswith('.html')) if os.path.isdir(od) else []
for f in pages:
    c, b = fetch('/' + f)
    if c != 200:
        add('FAIL', 'page ' + f, 'HTTP %s' % c); continue
    skip = f.startswith('scene') or 'backup' in f
    add('PASS' if skip or 'overlay-options.js' in b else 'FAIL', 'page ' + f, ('stage/backup page, tag not required' if skip else 'has overlay-options.js') if (skip or 'overlay-options.js' in b) else 'missing overlay-options.js tag')
for p in ('/overlay-options.js', '/overlay/latest', '/overlay/goal?id=followers', '/overlay/subfooter', '/live_state.js'):
    c, b = fetch(p)
    add('PASS' if c == 200 and len(b) > 20 else 'FAIL', 'asset ' + p, 'HTTP %s, %d bytes' % (c, len(b)))
c, oh = jget('/api/overlay-options/health')
add('PASS' if c == 200 and isinstance(oh, dict) and not oh.get('missing') else 'FAIL', '/api/overlay-options/health', 'missing: %s' % (oh or {}).get('missing') if c == 200 else 'HTTP %s' % c)
c, osch = jget('/api/overlay-options/schema')
profs = (osch or {}).get('profiles') or []
add('PASS' if c == 200 and set(profs) >= {'1080p', '1440p', '4k', 'vertical'} else 'FAIL', '/api/overlay-options/schema', 'profiles %s' % profs if c == 200 else 'HTTP %s' % c)

# 5. other read endpoints named by 10
for p, nm in (('/api/economy/preview', 'economy preview'), ('/api/intro', 'intro')):
    c, b = fetch(p)
    add('PASS' if c in (200, 400, 405) else 'FAIL', nm + ' ' + p, 'HTTP %s (%s)' % (c, 'answers' if c in (200, 400, 405) else 'missing or down'))

# 6. routes added by the commits since the Host build (GET only, never the dangerous ones)
if '--no-routes' not in argv:
    base = opt('--since')
    try:
        if not base:
            dll = os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
            ts = os.path.getmtime(dll) if os.path.exists(dll) else (time.time() - uptime if uptime else None)
            if ts is None: raise RuntimeError('no build time (pass --since REV)')
            base = subprocess.run(['git', '-C', suite, 'log', '--before=@%d' % int(ts), '-1', '--format=%H'], capture_output=True, text=True, timeout=30).stdout.strip()
        if not base: raise RuntimeError('no commit before the Host build')
        diff = subprocess.run(['git', '-C', suite, 'diff', '--unified=0', base + '..HEAD', '--', 'PinguinoHost/*.cs'], capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace').stdout
        routes = {}
        for ln in diff.splitlines():
            if not ln.startswith('+') or ln.startswith('+++'): continue
            for m in re.finditer(r'\b(?:p|path)\s*==\s*"(/[A-Za-z0-9_\-./]+)"', ln):
                r = m.group(1)
                if re.search(r'(?:m|HttpMethod)\s*==\s*"(?:POST|PUT|DELETE)"', ln): continue
                routes[r] = 1
        todo = [r for r in sorted(routes) if not NEVER.search(r)]
        skipped = [r for r in sorted(routes) if NEVER.search(r)]
        for r in todo:
            c, b = fetch(r, 10)
            if c == 404 and post_only(r):
                add('WARN', 'new route ' + r, 'HTTP 404 on GET; the source serves it for POST/PUT/DELETE only (never probed, read-only check)')
                continue
            add('PASS' if c not in (0, 404) else 'FAIL', 'new route ' + r, 'HTTP %s' % c)
        add('PASS', 'new routes since %s' % base[:8], '%d probed, %d skipped on purpose (%s)' % (len(todo), len(skipped), ', '.join(skipped)[:120]))
    except Exception as e:
        add('WARN', 'new routes', 'could not work out: %s' % e)

# summary
w = max(len(r[1]) for r in rows)
print('%-5s  %-*s  %s' % ('', w, 'CHECK', 'DETAIL'))
for s, n, d in rows:
    print('%-5s  %-*s  %s' % (s, w, n, d))
cnt = {k: sum(1 for r in rows if r[0] == k) for k in ('PASS', 'WARN', 'FAIL')}
print('\nSUMMARY: %d PASS, %d WARN, %d FAIL  (%s)' % (cnt['PASS'], cnt['WARN'], cnt['FAIL'], BASE))
sys.exit(1 if cnt['FAIL'] else 0)
