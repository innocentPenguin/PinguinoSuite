"""First-message link spam (Docs/SPAM_FIRST_MESSAGE.md): off by default; dry run only logs; live mode drops the line, times the account out and pays no welcome bonus;
mods / VIPs / subs / bots / non-first chatters are never flagged; the welcome bonus is skipped for an account that was banned during the delay.
Usage: python Tools/test-host-spamfirst.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8931; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgspam_'); out = os.path.join(d, 'out.txt'); logf = os.path.join(d, 'spam_first.log'); cfgf = os.path.join(d, 'config', 'spam_first.json')
os.makedirs(os.path.join(d, 'config'), exist_ok=True)
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8932', 'PINGUINO_WELCOME_DELAY_SEC': '2', 'PINGUINO_TEST_BANNED': 'bannedguy'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def pts(u):
    try: r = get('/api/economy/user?login=' + u); return r.get('points', r.get('balance', 0)) or 0
    except Exception: return 0
def log(): return open(logf, encoding='utf-8', errors='replace').read() if os.path.exists(logf) else ''
def cfg(**k): json.dump(k, open(cfgf, 'w'))
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=0.4): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
SPAM = 'Best viewers with viewers streamboo .org'
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    # 1. no config file: off
    feed('^off1: ' + SPAM); time.sleep(3.5)
    chk('off by default: nothing logged', log() == '', log()); chk('off by default: the welcome bonus is paid as usual', pts('off1') == 100, pts('off1'))
    # 2. enabled + dry run: only a log line
    cfg(enabled=True, dryRun=True); feed('^dry1: ' + SPAM); time.sleep(3.5)
    chk('dry run logs would timeout', 'would timeout dry1' in log(), log()); chk('dry run does not timeout', 'timeout dry1 600s' not in log().replace('would timeout dry1', ''), log())
    chk('dry run changes nothing else (bonus still paid)', pts('dry1') == 100, pts('dry1'))
    # 3. live: tonight's two accounts
    cfg(enabled=True, dryRun=False); feed('^succeedingsteelbqdzvkxr: ' + SPAM); feed('^dramaticlacencjhwz: ' + SPAM); time.sleep(3.5)
    L = log()
    chk('live: first spammer timed out', 'timeout succeedingsteelbqdzvkxr 600s [domain]' in L, L); chk('live: second spammer timed out', 'timeout dramaticlacencjhwz 600s' in L, L)
    chk('live: no welcome bonus for either', pts('succeedingsteelbqdzvkxr') == 0 and pts('dramaticlacencjhwz') == 0, (pts('succeedingsteelbqdzvkxr'), pts('dramaticlacencjhwz')))
    says = [l for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say]')]
    chk('live: no bot line mentions them', not any('succeedingsteel' in l or 'dramaticlace' in l for l in says), says)
    # 4. other link shapes + a normal first message
    feed('^link1: check out my channel twitch.tv/x'); feed('^link2: join https://discord.gg/abc'); feed('^link3: visit cheapviews dot com now'); feed('^normal1: hi everyone'); feed('^normal2: nice stream, love it!'); time.sleep(3.5)
    L = log()
    chk('twitch.tv/x is a candidate', 'timeout link1 ' in L, L); chk('https link is a candidate', 'timeout link2 ' in L, L); chk('"dot com" spelling is a candidate', 'timeout link3 ' in L, L)
    chk('normal first messages are untouched', 'normal1' not in L and 'normal2' not in L, L); chk('normal first messages still get the bonus', pts('normal1') == 100 and pts('normal2') == 100, (pts('normal1'), pts('normal2')))
    # 5. exemptions
    feed('*^modx: ' + SPAM); feed('%^vipx: ' + SPAM); feed('^$1subx: ' + SPAM); feed('^pinguinob0t: ' + SPAM); feed('^streamer1: ' + SPAM); feed('plainold: ' + SPAM); time.sleep(1.0)
    L = log()
    for n in ('modx', 'vipx', 'subx', 'pinguinob0t', 'streamer1', 'plainold'): chk('never flagged: ' + n, n not in L, L)
    # 6. a repeat from a flagged account is dropped without a second timeout
    n0 = log().count('timeout succeedingsteelbqdzvkxr 600s'); feed('^succeedingsteelbqdzvkxr: ' + SPAM); time.sleep(0.6)
    chk('one timeout per account', log().count('timeout succeedingsteelbqdzvkxr 600s') == n0 and 'dropped succeedingsteelbqdzvkxr' in log(), log())
    # 7. welcome bonus skipped for an account banned during the delay (PINGUINO_TEST_BANNED)
    cfg(enabled=False); feed('^bannedguy: hi everyone'); feed('^fineguy: hi everyone'); time.sleep(3.5)
    chk('banned during the delay: no welcome bonus', pts('bannedguy') == 0, pts('bannedguy')); chk('not banned: bonus paid', pts('fineguy') == 100, pts('fineguy'))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS spamfirst'); sys.exit(1 if fails else 0)
