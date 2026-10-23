"""Gambling: !gamble/!slots/!duel/!accept/!give move points through the ledger, config is live-read, no max bet by default, cooldown, lore does not answer.
Usage: python Tools/test-host-gamble.py [dll]"""
import re, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8995; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pggm_'); outf = os.path.join(d, 'out.txt'); eco = os.path.join(d, 'economy'); os.makedirs(eco)
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'adjust': {'alice': 1000, 'bob': 500, 'carl': 300, 'dina': 200, 'eve': 100}}, open(os.path.join(eco, 'points.json'), 'w'))
cfgp = os.path.join(eco, 'gambling.json')
csp = os.path.join(d, 'chat_settings.json')
def chatty(on):   # GameVoice on: the Host sends PgGame events to Chatty instead of speaking; off: the plain Host line
    json.dump({'Enabled': True, 'ChatReplies': True, 'GameVoice': on}, open(csp, 'w')); t = time.time() + chatty.n; os.utime(csp, (t, t)); chatty.n += 1
chatty.n = 1
chatty(False)
def setcfg(**kw):
    c = {'cooldownSec': 0}; c.update(kw); json.dump(c, open(cfgp, 'w')); os.utime(cfgp, (time.time() + len(kw) + setcfg.n, time.time() + setcfg.n)); setcfg.n += 1
setcfg.n = 0
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8997'})
setcfg(gambleWinChance=1.0, gamblePayout=2.0)
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def events(): return [json.loads(l[8:]) for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[pggame] ')]
def says(): return [l[6:] for l in open(outf, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=1.0):
    n = len(says()); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait); return says()[n:]
def bal(u): return json.load(urllib.request.urlopen(B + '/api/economy/user?login=' + u, timeout=5))['points']
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    r = ask('alice: !gamble 100'); chk('win pays', len(r) == 1 and 'won 100' in r[0] and bal('alice') == 1100, (r, bal('alice')))
    setcfg(gambleWinChance=0.0); time.sleep(1.2)
    r = ask('alice: !gamble 100'); chk('loss takes', 'lost 100' in r[0] and bal('alice') == 1000, (r, bal('alice')))
    r = ask('alice: !gamble all'); chk('all in, no max bet', bal('alice') == 0 and 'lost 1000' in r[0], (r, bal('alice')))
    r = ask('alice: !gamble 5'); chk('broke refused', 'you have no points' in r[0], r)
    r = ask('alice: !gamble'); chk('usage', 'usage' in r[0], r)
    r = ask('bob: !gamble 0'); chk('zero bet refused', ('usage' in r[0] or 'minimum' in r[0]) and bal('bob') == 500, r)
    setcfg(gambleWinChance=0.0, maxBet=50); time.sleep(1.2)
    r = ask('bob: !gamble 100'); chk('max bet optional setting', 'maximum bet is 50' in r[0] and bal('bob') == 500, r)
    setcfg(gambleWinChance=1.0, gamblePayout=3.0, slotsSymbols=['x','x'], slotsTriplePayout=4.0, slotsJackpotSymbol='x', slotsJackpotPayout=6.0); time.sleep(1.2)
    r = ask('bob: !slots 10'); chk('slots jackpot', 'won 60' in r[0] and bal('bob') == 550, (r, bal('bob')))
    setcfg(gambleWinChance=1.0); time.sleep(1.2)   # no slotsSymbols in the file: the built-in defaults are real emoji, intact through the send path
    r = ask('bob: !slots 1'); allowed = ['🍒', '🍋', '🔔', '⭐', '7️⃣', '💎', '🐧']
    reel = r[0].split(' ', 1)[1].split(' you won')[0].split(' no luck')[0] if r else ''
    got = []; rest = reel
    while rest:
        m = [e for e in allowed if rest.startswith(e)]
        if not m: break
        got.append(m[0]); rest = rest[len(m[0]):].lstrip(' ')
    chk('slots default reels are three real emoji symbols (UTF-8 intact, no text codes)', len(r) == 1 and len(got) == 3 and rest == '', (r, ascii(r)))
    r = ask('carl: !give @dina 50'); chk('give moves points', bal('carl') == 250 and bal('dina') == 250 and 'gave 50' in r[0], (r, bal('carl'), bal('dina')))
    r = ask('carl: !give @carl 5'); chk('no self give', 'someone else' in r[0], r)
    r = ask('carl: !give @dina 9999'); chk('give over balance', 'only have' in r[0] and bal('carl') == 250, r)
    r = ask('carl: !duel @dina 100'); chk('duel challenge', '!accept' in r[0], r)
    r = ask('dina: !accept'); chk('duel settles', 'wins the duel' in r[0] and sorted([bal('carl'), bal('dina')]) == [150, 350], (r, bal('carl'), bal('dina')))
    r = ask('dina: !accept'); chk('no second accept', r == [], r)
    r = ask('eve: !duel @bob 80'); r = ask('bob: !decline'); chk('decline', 'passed' in r[0], r)
    setcfg(cooldownSec=30, gambleWinChance=0.0); time.sleep(1.2)
    ask('eve: !gamble 1'); r = ask('eve: !gamble 1'); chk('cooldown silent', r == [], r)
    setcfg(enabled=False); time.sleep(1.2)
    r = ask('bob: !gamble 5'); chk('off switch', r == [], r)
    # ---- Chatty on: the Host sends ONE PgGame event and says nothing itself ----
    chatty(True); setcfg(gambleWinChance=1.0, gamblePayout=2.0, slotsSymbols=['🍒', '🍒'], slotsJackpotSymbol='🍒', slotsJackpotPayout=7.0); time.sleep(1.2)
    n0 = len(events()); r = ask('alice: !gamble 1')
    chk('no balance: broke event, host silent', r == [] and events()[n0:] and events()[n0]['outcome'] == 'broke' and events()[n0]['kind'] == 'gamble', (r, events()[n0:]))
    r = ask('bob: !gamble 10'); e = events()[n0 + 1:]
    chk('gamble win -> one PgGame, no host line', r == [] and len(e) == 1 and e[0]['kind'] == 'gamble' and e[0]['outcome'] == 'win' and e[0]['user'] == 'bob' and e[0]['amount'] == '10' and e[0]['payout'] == '20' and e[0]['balance'].isdigit() and abs(int(e[0]['balance']) - bal('bob')) <= 1 and e[0]['gameId'] and e[0]['currency'] == 'points', (r, e))
    r = ask('bob: !slots 10'); e = events()[n0 + 2:]
    chk('slots jackpot event carries the real emoji reel', r == [] and len(e) == 1 and e[0]['kind'] == 'slots' and e[0]['outcome'] == 'jackpot' and e[0]['reel'] == '🍒 🍒 🍒' and e[0]['payout'] == '70', (r, ascii(e)))
    r = ask('bob: !gamble nope'); e = events()[n0 + 3:]
    chk('usage -> invalid with the Host sentence as reason', r == [] and e and e[0]['outcome'] == 'invalid' and 'usage' in e[0]['reason'], (r, e))
    r = ask('carl: !give @dina 5'); e = events()[n0 + 4:]
    chk('give event: opponent is the receiver', r == [] and e and e[0]['kind'] == 'give' and e[0]['opponent'].lower() == 'dina' and e[0]['amount'] == '5', (r, e))
    r = ask('carl: !duel @dina 20'); e = events()[n0 + 5:]
    chk('duel challenge event', r == [] and e and e[0]['outcome'] == 'challenge' and e[0]['user'] == 'carl' and e[0]['opponent'] == 'dina' and e[0]['timeoutSec'] == '60', (r, e))
    r = ask('dina: !accept'); e = events()[n0 + 6:]
    chk('duel result event: winner is user, payout 2x stake', r == [] and e and e[0]['kind'] == 'duel' and e[0]['outcome'] == 'win' and e[0]['payout'] == '40' and e[0]['opponent'], (r, e))
    ask('eve: !duel @bob 10'); r = ask('bob: !decline'); e = events()[-1]
    chk('decline event', r == [] and e['outcome'] == 'declined' and e['user'] == 'bob', (r, e))
    chatty(False); time.sleep(1.2)
    n1 = len(events()); r = ask('bob: !gamble 1')
    chk('Chatty off: the plain Host line, no event', len(r) == 1 and len(events()) == n1, (r, len(events()) - n1))
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS gamble'); sys.exit(1 if fails else 0)
