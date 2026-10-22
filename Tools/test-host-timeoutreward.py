"""Channel-point TIMEOUT reward: fuzzy target (recent chatters), mods/broadcaster/bots untimeable (the redeemer is timed out instead), actor fallback
helper -> core (PinguinoBot) -> streamer, the valid flow (reason text, Chatty's follow-up line), no match / ambiguity, unique fail lines.
Runs the Host in --sim mode (no Twitch). Usage: python Tools/test-host-timeoutreward.py [dll]"""
import json, os, re, shutil, subprocess, sys, tempfile, threading, time, queue
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
fails = []
DONE = re.compile(r'^\[timeout-reward\] (timed out|no match|protected target|could not time out|cooldown)')

def run(chat, redeems, extra_env=None, cfg=None):
    """chat: sim chat lines first (build the roster); redeems: [(redeemer, typed)]. Returns the Host's stdout lines."""
    d = tempfile.mkdtemp(prefix='pgto_')
    json.dump({'Channel': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    if cfg: json.dump(cfg, open(os.path.join(d, 'timeout_reward.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    s = socket_free()
    env.update({'PINGUINO_COMPAT_WS_PORT': str(s), 'PINGUINO_TIMEOUT_FAST': '1'}); env.update(extra_env or {})
    p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    q = queue.Queue(); out = []
    threading.Thread(target=lambda: [q.put(l.rstrip('\n')) for l in p.stdout], daemon=True).start()
    def pump(t=0.2):
        end = time.time() + t
        while time.time() < end:
            try: out.append(q.get(timeout=0.05))
            except queue.Empty: pass
    pump(4)
    for c in chat: p.stdin.write(c + '\n'); p.stdin.flush(); pump(0.15)
    for who, typed in redeems: p.stdin.write('timeoutredeem %s %s\n' % (who, typed)); p.stdin.flush()
    end = time.time() + 20
    while time.time() < end and sum(1 for l in out if DONE.match(l)) < len(redeems): pump(0.2)
    pump(1.0)
    p.kill(); time.sleep(0.3); shutil.rmtree(d, True)
    return out

def socket_free():
    import socket
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
def dos(out): return [l for l in out if l.startswith('[timeout-do]')]
def says(out): return [l[6:] for l in out if l.startswith('[say] ')]
def check(cond, msg):
    if not cond: fails.append(msg)

ROSTER = ['LvLMarshmello: hi', 'alice: yo', 'bob_the_builder: hey', '*modguy: mod here', '#streamer1: boss', '%vippy: vip', 'pinguinob0t: beep', 'zed: z']
# 1) the three examples + exact + @ + valid flow text
out = run(ROSTER, [('r1', 'marsh'), ('r2', 'marhsmello'), ('r3', 'mello'), ('r4', '@LvLMarshmello'), ('r5', 'builder')], {})
d = dos(out)
check(len(d) == 5, 'expected 5 timeouts, got %d: %s' % (len(d), d))
for who, want in [('marsh', 'lvlmarshmello'), ('marhsmello', 'lvlmarshmello'), ('mello', 'lvlmarshmello'), ('@LvLMarshmello', 'lvlmarshmello'), ('builder', 'bob_the_builder')]:
    pass
check(sum(1 for l in d if 'user=lvlmarshmello' in l) == 4, 'the four marsh-style inputs should all hit lvlmarshmello: %s' % d)
check(any('user=bob_the_builder' in l for l in d), 'builder -> bob_the_builder: %s' % d)
check(all('actor=helper' in l for l in d), 'PinguinoHelper does the timeout first: %s' % d)
check(any('reason=Sorry! r1 redeemed your timeout! D:' in l for l in d), 'reason text: %s' % d)
check('LvLMarshmello has been timed out by r1' in says(out), 'Chatty follow-up line: %s' % says(out))
# the follow-up comes after the timeout
iv = [i for i, l in enumerate(out) if 'user=lvlmarshmello' in l and 'r1 redeemed' in l]; im = [i for i, l in enumerate(out) if l == '[say] LvLMarshmello has been timed out by r1']
check(iv and im and iv[0] < im[0], 'timeout must come before the announcement')

# 2) nothing close / ambiguous
out = run(ROSTER + ['Marshall99: x'], [('r1', 'qqqqzzzz'), ('r2', 'marsh')])
check(len(dos(out)) == 0, 'no match / ambiguous must not time anyone out: %s' % dos(out))
check(any('no match' in l and 'qqqqzzzz' in l for l in out), 'no-match is reported')
check(any('ambiguous' in l for l in out), 'marsh with two marsh-names is ambiguous (no timeout)')
check(len([s for s in says(out) if 'nobody in chat matched' in s]) == 2, 'one short line per failed lookup: %s' % says(out))

# 3) protected targets: mod, broadcaster, bot, (VIP only if configured) -> the redeemer is timed out, with one fail line each, all different
out = run(ROSTER, [('r1', 'modguy'), ('r2', 'streamer1'), ('r3', 'pinguinob0t'), ('r4', 'vippy')])
d = dos(out)
users = [re.search(r'user=(\S+)', l).group(1) for l in d]
check(set(['r1', 'r2', 'r3']) <= set(users), 'mod/broadcaster/bot targets time out the redeemer: %s' % users)
check(all('reason=You can\'t do that!' in l for l in d if re.search(r'user=r[123]\b', l)), 'reason is "You can\'t do that!"')
check('modguy' not in ' '.join(users) and 'streamer1' not in ' '.join(users) and 'pinguinob0t' not in ' '.join(users), 'a protected account was timed out: %s' % users)
check('vippy' in users, 'a VIP is timeable by default')
fl = [s for s in says(out) if re.search(r'\br[123]\b', s)]
check(len(fl) == 3 and len(set(fl)) == 3, 'three different fail lines: %s' % fl)
check(all(len(s.split()) < 15 for s in fl), 'fail lines under 15 words: %s' % fl)
out = run(ROSTER, [('r1', 'vippy')], None, {'protectVip': True})
check([re.search(r'user=(\S+)', l).group(1) for l in dos(out)] == ['r1'], 'protectVip: the VIP is protected, the redeemer is timed out')

# 4) actor fallback helper -> core -> streamer, and all failing
for fail, want in [('', 'helper'), ('helper', 'core'), ('helper,core', 'streamer')]:
    out = run(ROSTER, [('r1', 'alice')], {'PINGUINO_TIMEOUT_FAIL': fail})
    d = dos(out)
    check(len(d) == 1 and 'actor=' + want in d[0], 'fail=%r -> expected actor %s, got %s' % (fail, want, d))
    check('alice has been timed out by r1' in says(out), 'announcement still comes from Chatty (fail=%r)' % fail)
out = run(ROSTER, [('r1', 'alice')], {'PINGUINO_TIMEOUT_FAIL': 'helper,core,streamer'})
check(len(dos(out)) == 0 and not any('has been timed out' in s for s in says(out)), 'all actors failing: no timeout, no false announcement')
check(any('could not time out' in l for l in out), 'all actors failing is reported')

# 5) mod target, helper cannot: core times the redeemer out
out = run(ROSTER, [('r1', 'modguy')], {'PINGUINO_TIMEOUT_FAIL': 'helper'})
check(len(dos(out)) == 1 and 'actor=core' in dos(out)[0] and 'user=r1' in dos(out)[0], 'redeemer punishment also falls back: %s' % dos(out))

# 6) per-user cooldown of the reward is honoured (second redeem refunded, nobody timed out)
out = run(ROSTER, [('r1', 'alice'), ('r1', 'zed')], None, {'userCooldownSec': 60})
check(len(dos(out)) == 1 and any('cooldown' in l for l in out), 'user cooldown: %s' % dos(out))


# 7) self timeout: duration parser matrix, the "1" coin flip, mods refused, auto-complete, fallback line, event log
def run_self(items, extra=None, keep=False):
    d = tempfile.mkdtemp(prefix='pgto_')
    json.dump({'Channel': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
    env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    env.update({'PINGUINO_COMPAT_WS_PORT': str(socket_free()), 'PINGUINO_TIMEOUT_FAST': '1'}); env.update(extra or {})
    p = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    q = queue.Queue(); out = []
    threading.Thread(target=lambda: [q.put(l.rstrip('\n')) for l in p.stdout], daemon=True).start()
    def pump(t):
        end = time.time() + t
        while time.time() < end:
            try: out.append(q.get(timeout=0.05))
            except queue.Empty: pass
    pump(4)
    for c in ['*modguy: hi', '#streamer1: boss', 'pinguinob0t: beep']: p.stdin.write(c + '\n'); p.stdin.flush(); pump(0.15)
    for who, typed in items: p.stdin.write('selfredeem %s %s\n' % (who, typed)); p.stdin.flush()
    end = time.time() + 25
    while time.time() < end and sum(1 for l in out if re.match(r'^\[timeout-reward\] (self timed out|could not|self timeout refused)', l)) < len(items): pump(0.2)
    pump(1.0)
    log = open(os.path.join(d, 'timeout_events.jsonl'), encoding='utf-8').read() if os.path.exists(os.path.join(d, 'timeout_events.jsonl')) else ''
    p.kill(); time.sleep(0.3); shutil.rmtree(d, True)
    return out, log
matrix = [('5', 5), ('30', 30), ('30s', 30), ('30 sec', 30), ('2m', 120), ('5 min', 300), ('10 min', 300), ('999', 300), ('1h', 300), ('junk', 60), ('1 minute', 60), ('please 45 seconds ok', 45), ('2', 2)]
items = [('s%d' % i, t) for i, (t, _) in enumerate(matrix)]
out, log = run_self(items)
secs = {}
for l in dos(out):
    m = re.search(r'user=(\S+) secs=(\d+) reason=(.*)', l)
    if m: secs[m.group(1)] = (int(m.group(2)), m.group(3))
for i, (t, want) in enumerate(matrix):
    got = secs.get('s%d' % i, (None,))[0]
    check(got == want, 'self-timeout %r -> expected %s s, got %s' % (t, want, got))
check(all(r.startswith('You timed yourself out!') for _, r in secs.values()), 'self reason text')
check(sum(1 for l in dos(out) if 'actor=helper' in l) == len(matrix), 'self-timeout goes through the helper first')
check(len([l for l in out if l == '[timeout-reward] redemption fulfilled']) == len(matrix), 'each handled redemption is auto-completed')
check(all(any(s.startswith('s%d needs a break from us' % i) or ('s%d' % i) in s for s in says(out)) for i in range(len(matrix))), 'a Chatty line for each self-timeout: %s' % says(out)[:3])
check(len(log.strip().splitlines()) == len(matrix) and '"kind":"self"' in log, 'timeout events are logged (one jsonl line each)')
# "1": coin flip 1 s / 60 s with the explanation in the reason
out, log = run_self([('c%d' % i, '1') for i in range(14)])
vals = set(); notes = True
for l in dos(out):
    m = re.search(r'secs=(\d+) reason=(.*)', l)
    vals.add(int(m.group(1))); notes = notes and ("You didn't say secs or mins so I chose " + ('1 second' if m.group(1) == '1' else '60 seconds')) in m.group(2)
check(vals == {1, 60}, 'bare "1" must flip between 1 s and 60 s (saw %s)' % sorted(vals))
check(notes, 'the coin-flip reason says which was chosen')
# mods / broadcaster / bots: nothing, redemption canceled
out, log = run_self([('modguy', '30'), ('streamer1', '30'), ('pinguinob0t', '30')])
check(len(dos(out)) == 0 and len([l for l in out if 'redemption canceled' in l]) == 3, 'mods/broadcaster/bots cannot self-time-out (refunded, no timeout): %s' % dos(out))
# helper cannot -> core
out, log = run_self([('x1', '30')], {'PINGUINO_TIMEOUT_FAIL': 'helper'})
check(len(dos(out)) == 1 and 'actor=core' in dos(out)[0], 'self-timeout falls back helper -> core')
# all actors fail: canceled, nothing said
out, log = run_self([('x1', '30')], {'PINGUINO_TIMEOUT_FAIL': 'helper,core,streamer'})
check(len(dos(out)) == 0 and any('redemption canceled' in l for l in out) and not any('needs a break' in s for s in says(out)), 'all failing: refunded and quiet')

print('FAIL ' + '; '.join(fails) if fails else 'PASS timeoutreward'); sys.exit(1 if fails else 0)
