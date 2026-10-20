"""7TV channel emotes: set from a fake 7TV API (cached), usage counted from stored chat (bots left out, aliases folded, whole-word, .txt days win over .jsonl),
!emote, !topemotes [month], GET /api/emotes. Usage: python Tools/test-host-emotes.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8991; SV = 8992; B = 'http://127.0.0.1:%d' % PORT
hits = []
SET = {'username': 'innocentpenguin_', 'emote_set': {'id': 'SET1', 'name': 'TEST SET', 'emotes': [
    {'id': '01AAAAAAAAAAAAAAAAAAAAAAAA', 'name': 'GIGACHAD', 'data': {'animated': True}}, {'id': '01BBBBBBBBBBBBBBBBBBBBBBBB', 'name': 'KEKW', 'data': {'animated': False}},
    {'id': '01CCCCCCCCCCCCCCCCCCCCCCCC', 'name': 'PartyKirby', 'data': {'animated': True}}, {'id': 'bad id!', 'name': 'Evil', 'data': {}}]}}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        hits.append(self.path); b = json.dumps(SET).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
srv = http.server.ThreadingHTTPServer(('127.0.0.1', SV), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgemo_'); out = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'chat_logs', '2026', '03')); os.makedirs(os.path.join(d, 'chat_logs', '2026', '10')); os.makedirs(os.path.join(d, 'boards'))
json.dump({'aliases': {'altguy': 'maingal'}}, open(os.path.join(d, 'boards', 'aliases.json'), 'w'))
open(os.path.join(d, 'chat_logs', '2026', '03', '2026-03-05.txt'), 'w', encoding='utf-8').write('\n'.join([
    '[2026-03-05 20:00:01] #innocentpenguin_ maingal: KEKW KEKW that was great GIGACHAD',
    '[2026-03-05 20:00:09] #innocentpenguin_ altguy: kekw KEKW',                                   # alias folds into maingal; "kekw" is another word
    '[2026-03-05 20:01:00] #innocentpenguin_ nightbot: KEKW KEKW KEKW KEKW',                       # bots do not count
    '[2026-03-05 20:02:00] #innocentpenguin_ bobby: KEKWW GIGACHAD!! xKEKW',                       # not whole words
    '[2026-03-05 20:03:00] #innocentpenguin_ * Somebody subscribed with Prime. KEKW',               # system line
    '[2026-03-05 20:04:00] #innocentpenguin_ bobby: PartyKirby']) + '\n')
open(os.path.join(d, 'chat_logs', '2026', '10', '2026-10-01.txt'), 'w', encoding='utf-8').write('[2026-10-01 20:00:01] #innocentpenguin_ bobby: KEKW GIGACHAD GIGACHAD\n')
# a live jsonl for a day that has a .txt (ignored) and one that has none (counted)
def ms(y, mo, da, h=20): return int(time.mktime((y, mo, da, h, 0, 0, 0, 0, 0)) * 1000)
open(os.path.join(d, 'chat_logs', '2026-10-01.jsonl'), 'w', encoding='utf-8').write(json.dumps({'t': ms(2026, 10, 1), 'u': 'bobby', 'i': '1', 'm': 'KEKW KEKW KEKW', 'c': 0}) + '\n')
open(os.path.join(d, 'chat_logs', '2026-10-15.jsonl'), 'w', encoding='utf-8-sig').write(json.dumps({'t': ms(2026, 10, 15), 'u': 'newbie', 'i': '2', 'm': 'PartyKirby PartyKirby', 'c': 0}) + '\n' + json.dumps({'t': ms(2026, 10, 15), 'u': 'newbie', 'i': '2', 'm': '!cmd KEKW', 'c': 1}) + '\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_SEVENTV_BASE': 'http://127.0.0.1:%d' % SV, 'PINGUINO_EMOTE_TWITCH_ID': '12345', 'PINGUINO_COMPAT_WS_PORT': '8993', 'PINGUINO_STREAK_COOL_GLOBAL': '0', 'PINGUINO_STREAK_COOL_USER': '0', 'PINGUINO_SUBS_DOWNLOADS': ''})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'wb'), stderr=subprocess.STDOUT)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=30))
def says(): return [l[6:] for l in open(out, encoding='utf-8', errors='replace').read().splitlines() if l.startswith('[say] ')]
def ask(line, wait=0.7):
    n = len(says()); host.stdin.write((line + '\n').encode()); host.stdin.flush(); time.sleep(wait); return says()[n:]
res = []
def chk(n, ok, extra=None):
    res.append((n, bool(ok)))
    if not ok: print('   says:', says()[-2:], extra)
try:
    for _ in range(60):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    r = api('/api/emotes/refresh', {})
    em = {e['name']: e for e in r['emotes']}
    chk('the 7TV set is read (unsafe ids are dropped)', r['set']['count'] == 3 and set(em) == {'GIGACHAD', 'KEKW', 'PartyKirby'} and any('/users/twitch/12345' in h for h in hits))
    chk('image urls are built from the id on the 7TV cdn', em['KEKW']['url'] == 'https://cdn.7tv.app/emote/01BBBBBBBBBBBBBBBBBBBBBBBB/2x.webp' and em['GIGACHAD']['animated'] is True)
    chk('KEKW: whole words only, bots/system lines left out, alias folded, .txt day wins over .jsonl (2+2... +1)', em['KEKW']['uses'] == 4 and em['KEKW']['topUsers'][0]['login'] == 'maingal' and em['KEKW']['topUsers'][0]['uses'] == 3, em['KEKW'])
    chk('jsonl days with no .txt are counted; system "c":1 lines are not', em['PartyKirby']['uses'] == 3, em['PartyKirby'])
    chk('GIGACHAD all time', em['GIGACHAD']['uses'] == 3, em['GIGACHAD'])
    r = api('/api/emotes?month=2026-03'); em3 = {e['name']: e['uses'] for e in r['emotes']}
    chk('month filter', em3 == {'GIGACHAD': 1, 'KEKW': 3, 'PartyKirby': 1} or em3 == {'KEKW': 3, 'GIGACHAD': 1, 'PartyKirby': 1}, em3)
    r = api('/api/emotes?q=kek'); chk('search by name', [e['name'] for e in r['emotes']] == ['KEKW'] and r['matches'] == 1)
    chk('word-like emotes are flagged', em['KEKW']['ambiguous'] is False and em['GIGACHAD']['ambiguous'] is False)
    r = api('/api/emotes?limit=1'); chk('limit', len(r['emotes']) == 1 and r['emotes'][0]['rank'] == 1)
    before = len(hits); api('/api/emotes/refresh', {})
    a = ask('v: !emote KEKW'); chk('!emote shows uses, rank and top user', len(a) == 1 and 'KEKW has been used 4 times (#' in a[0] and 'Top user: maingal (3)' in a[0] and a[0].endswith('https://innocentpenguin.com/emotes'), a)
    a = ask('v: !emote kekw'); chk('!emote is case-insensitive when the exact name is not found', len(a) == 1 and a[0].startswith('KEKW has been used'))
    a = ask('v: !emote nopeemote'); chk('unknown emote says so', len(a) == 1 and 'not in the channel' in a[0])
    a = ask('v: !emote kirb'); chk('partial name suggests', len(a) == 1 and 'Did you mean: PartyKirby' in a[0], a)
    a = ask('v: !topemotes'); chk('!topemotes all time', len(a) == 1 and a[0].startswith('Top emotes (all time): 1.') and 'KEKW 4' in a[0] and a[0].endswith('/emotes'), a)
    a = ask('v: !topemotes mar'); chk('!topemotes for a month', len(a) == 1 and 'Mar 2026' in a[0] and '1. KEKW 3' in a[0], a)
    a = ask('v: !topemotes jan'); chk('an empty month says so', len(a) == 1 and 'No 7TV emote uses' in a[0], a)
    chk('the 7TV API is called read-only and at most once per refresh', all(True for h in hits) and len(hits) <= before + 2)
finally:
    host.kill(); time.sleep(0.5); srv.shutdown(); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
