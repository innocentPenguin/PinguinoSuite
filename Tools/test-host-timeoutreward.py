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

print('FAIL ' + '; '.join(fails) if fails else 'PASS timeoutreward'); sys.exit(1 if fails else 0)
