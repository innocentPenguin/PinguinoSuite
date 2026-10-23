"""Timeout reward x people graph: chat friends get a friendly plain line, unknown pairs / opted-out people / bots get the normal line, and nothing from the
private graph (example messages, counts, dates) ever reaches chat. Runs the Host in --sim with a temp graph (PINGUINO_PEOPLE_GRAPH). Usage: python Tools/test-host-timeoutgraph.py [dll]"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, queue
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
fails = []; LAST = []
SECRET = 'SECRET-EXAMPLE-LINE'
GRAPH = {'built': 'test', 'nodes': [], 'groups': [{'group': 1, 'size': 3, 'members': ['gus', 'hana', 'ivo']}],
         'edges': [{'a': 'alice', 'b': 'bobby', 'aToB': 900, 'bToA': 800, 'mutual': 800, 'tags': ['chat friends'], 'example': ['2026-04-07', 'alice', SECRET]},
                   {'a': 'carl', 'b': 'dora', 'aToB': 50, 'bToA': 40, 'mutual': 40, 'tags': ['chat friends'], 'example': ['2026-04-07', 'carl', SECRET]},
                   {'a': 'erin', 'b': 'finn', 'aToB': 9, 'bToA': 9, 'mutual': 9, 'tags': ['chat friends'], 'example': ['2026-04-07', 'erin', SECRET]},
                   {'a': 'optout1', 'b': 'bobby', 'aToB': 900, 'bToA': 800, 'mutual': 800, 'tags': ['chat friends'], 'example': ['x', 'y', SECRET]},
                   {'a': 'pinguinob0t', 'b': 'bobby', 'aToB': 900, 'bToA': 800, 'mutual': 800, 'tags': ['chat friends'], 'example': ['x', 'y', SECRET]}]}

def free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n

def run(chat, redeems, extra=None):
    d = tempfile.mkdtemp(prefix='pgtg_')
    json.dump({'Channel': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    json.dump({'optout1': {'Privacy': 'anon'}}, open(os.path.join(d, 'chat_memory.json'), 'w'))
    g = os.path.join(d, 'graph.json'); json.dump(GRAPH, open(g, 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_COMPAT_WS_PORT': str(free()), 'PINGUINO_TIMEOUT_FAST': '1', 'PINGUINO_PEOPLE_GRAPH': g}); env.update(extra or {})
    p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    q = queue.Queue(); out = []
    threading.Thread(target=lambda: [q.put(l.rstrip('\n')) for l in p.stdout], daemon=True).start()
    def pump(t):
        end = time.time() + t
        while time.time() < end:
            try: out.append(q.get(timeout=0.05))
            except queue.Empty: pass
    t0 = time.time()
    while time.time() - t0 < 40 and not any('ready' in l for l in out): pump(0.3)
    pump(1)
    for c in chat: p.stdin.write(c + '\n'); p.stdin.flush(); pump(0.15)
    for who, typed in redeems: p.stdin.write('timeoutredeem %s %s\n' % (who, typed)); p.stdin.flush(); pump(1.5)
    pump(1.0); LAST[:] = out; p.kill(); time.sleep(0.3); shutil.rmtree(d, True)
    return out

def check(c, m):
    if not c: fails.append(m)
def says(o): return [l[6:] for l in o if l.startswith('[say] ')]
def lvl(o): return [re.search(r'closeness (\w+)', l).group(1) for l in o if 'people-graph closeness' in l]

ROSTER = ['bobby: hi', 'dora: yo', 'finn: x', 'hana: x', 'optout1: x', 'pinguinob0t: beep', 'plain: z']
# friends (duo, buddies) -> friendly plain line with both names; acquainted / crowd / none / opted out / bot -> the normal line
out = run(ROSTER, [('alice', 'bobby'), ('carl', 'dora'), ('erin', 'finn'), ('gus', 'hana'), ('zed', 'plain'), ('alice', 'optout1')])
check(lvl(out) == ['duo', 'buddies', 'acquainted', 'crowd', 'none', 'none'], 'closeness levels: %s' % lvl(out))
s = [x for x in says(out) if 'timed out' in x]
check(len(s) == 6, 'one line per redeem: %s' % s)
check('alice' in s[0] and 'bobby' in s[0] and 'has been timed out by' not in s[0], 'duo line names both: %s' % s)
check(all(n in s[1] for n in ('dora', 'carl')) and 'has been timed out by' not in s[1], 'buddies line names both: %s' % s)
check(all(x.endswith('has been timed out by ' + w) for x, w in zip(s[2:], ['erin', 'gus', 'zed', 'alice'])), 'acquainted / crowd / unknown / opted-out get the normal line: %s' % s)
check(not any(SECRET in l for l in out), 'private example text leaked into the output')
# bot on one side never counts even with an edge
out = run(ROSTER, [('zed', 'pinguinob0t')])
check(lvl(out) == [] , 'bots are protected targets, no graph lookup: %s' % lvl(out))
# no graph file -> normal behaviour
# IDEAS #35: friendly failure lines (refund wording kept, varied, no immediate repeat)
out = run(ROSTER, [('zed', 'qqqqzzzz'), ('zed2', 'wwwwxxxx'), ('zed3', 'eeeerrrr')])
nm = [x for x in says(out) if 'nobody in chat matched' in x]
check(len(nm) == 3 and len(set(nm)) == 3 and all('points' in x.lower() and ('back' in x or 'refund' in x) for x in nm), 'no-match lines: %s' % nm)
out = run(ROSTER, [('zed', 'plain')], {'PINGUINO_TIMEOUT_FAIL': 'helper,core,streamer'})
cl = [x for x in says(out) if 'points' in x.lower() and 'back' in x]
check(len(cl) == 1 and 'plain' in cl[0], 'could-not-time-out line: %s' % says(out))
if os.environ.get("TG_DEBUG"): print(chr(10).join(LAST[-40:]))
if fails: print('FAIL'); [print(' -', f) for f in fails]; sys.exit(1)
print('PASS timeout people-graph')
