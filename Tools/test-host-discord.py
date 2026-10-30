"""Discord go-live announcements (HostDiscord.cs, owner 170): a fake Discord webhook + a fake Twitch Helix on loopback, the sim Host polls Twitch every 2 s.
Checks: not configured / disabled / dry-run states, one POST per stream (never again after a Host restart while live), a Twitch blip never re-posts,
the offline edit (PATCH to "ended") once after the grace period, !discordtest status|dry|send|end for mods only (silent for viewers), the API routes,
the webhook never appears in GET /api/discord, BuildLive payload shape (ping + allowed_mentions, no ping on tests).
Usage: python Tools/test-host-discord.py [dll]   (build first: dotnet build PinguinoHost -c Release -o <scratch>)"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, WS, FAKE, TOK = 8977, 8976, 8975, 'test-module-token'
B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgdc_'); outp = os.path.join(d, 'out.txt')
# fake streamer creds so TwitchApi.Call runs (against the fake helix below), no real token anywhere
json.dump({'Channel': 'dctest', 'OverlayPort': PORT, 'UserToken': 'fake-token', 'ClientId': 'fake-client', 'BroadcasterId': '42', 'SenderId': '42'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
fails = []
def chk(n, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else ' :: ' + str(x)[:400]))
    if not ok: fails.append('%s %s' % (n, x))

# ---------------- fake Discord webhook + fake Twitch helix ----------------
fake = {'live': False, 'stream_id': '1001', 'title': 'Ranked 2s grind', 'game': 'Rocket League', 'game_id': '30921', 'posts': [], 'patches': [], 'status': 200}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/streams'):
            data = [{'id': fake['stream_id'], 'user_login': 'innocentpenguin_', 'user_name': 'innocentpenguin_', 'game_id': fake['game_id'], 'game_name': fake['game'], 'title': fake['title'], 'started_at': '2026-10-30T22:00:00Z', 'viewer_count': 7, 'thumbnail_url': 'https://x/{width}x{height}.jpg'}] if fake['live'] else []
            return self._json(200, {'data': data})
        return self._json(200, {'data': []})
    def _body(self):
        n = int(self.headers.get('Content-Length') or 0); return json.loads(self.rfile.read(n).decode() or '{}')
    def do_POST(self):
        if self.path.startswith('/webhooks/'):
            body = self._body(); fake['posts'].append({'path': self.path, 'body': body})
            if fake['status'] != 200: return self._json(fake['status'], {'message': 'nope'})
            return self._json(200, {'id': 'msg%d' % len(fake['posts']), 'content': body.get('content')})
        return self._json(404, {})
    def do_PATCH(self):
        if self.path.startswith('/webhooks/'):
            body = self._body(); fake['patches'].append({'path': self.path, 'body': body}); return self._json(200, {'id': self.path.rsplit('/', 1)[-1]})
        return self._json(404, {})
srv = HTTPServer(('127.0.0.1', FAKE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
WEBHOOK = 'http://127.0.0.1:%d/webhooks/123/abcSECRET' % FAKE

def env(extra=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
    e.update({'PINGUINO_COMPAT_WS_PORT': str(WS), 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % FAKE}); e.update(extra or {}); return e
def start(extra=None):
    return subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env(extra), stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
def get(p):
    return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, body):
    h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
    try: return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(body).encode(), headers=h), timeout=15))
    except urllib.error.HTTPError as e: return {'http': e.code}
def waitup():
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(2)
def says(host, line, wait=1.0):
    n = len(open(outp, 'rb').read()); host.stdin.write(line.encode() + chr(10).encode()); host.stdin.flush(); time.sleep(wait)
    new = open(outp, 'rb').read()[n:].decode('utf-8', 'replace')
    return [l[len('[say] '):] for l in new.splitlines() if l.startswith('[say] ')]
def wait_live(v, tries=20):
    for _ in range(tries):
        if get('/api/live').get('live') is v: return True
        time.sleep(0.5)
    return False
def wait_posts(n, tries=25):
    for _ in range(tries):
        if len(fake['posts']) >= n: return True
        time.sleep(0.4)
    return len(fake['posts']) >= n
def setp(p): return os.path.join(d, p)

host = start()
try:
    waitup()
    # 1. fresh install: not configured, nothing posted, settings file seeded with safe defaults
    a = get('/api/discord'); chk('fresh: state not configured', a.get('state') == 'not configured' and a['webhookConfigured'] is False, a)
    chk('settings seeded Enabled=false DryRun=true', a['settings']['Enabled'] is False and a['settings']['DryRun'] is True and os.path.exists(setp('discord.json')), a.get('settings'))
    r = says(host, 'viewer1: !discordtest'); chk('!discordtest is silent for viewers', r == [], r)
    r = says(host, '*mod1: !discordtest'); chk('mod status line says not configured', len(r) == 1 and 'not configured' in r[0], r)
    r = says(host, '*mod1: !discordtest send'); chk('send without a webhook explains how to add one', len(r) == 1 and 'not configured' in r[0] and 'bots_secrets' in r[0], r)
    r = says(host, '*mod1: !discordtest dry'); chk('dry run works without a webhook', len(r) == 1 and 'dry run logged' in r[0] and '[TEST]' in r[0], r)
    fake['live'] = True; chk('fake twitch says live', wait_live(True), get('/api/live'))
    time.sleep(3); chk('unconfigured: nothing posted while live', fake['posts'] == [], fake['posts'])
    # 2. secret via API: stored in bots_secrets.json, never echoed
    r = post('/api/discord/secret', {'webhook': 'https://evil.example/x'}); chk('a non-discord URL is refused', r.get('ok') is False, r)
    r = post('/api/discord/secret', {'webhook': WEBHOOK}); chk('loopback webhook accepted in sim', r.get('ok') and r['webhookConfigured'] and r['webhookSource'] == 'file' and r['state'] == 'disabled', r)
    sec = json.load(open(setp('bots_secrets.json'), encoding='utf-8-sig')); chk('webhook stored under discord.WebhookUrl', sec.get('discord', {}).get('WebhookUrl') == WEBHOOK, sec.keys())
    chk('GET /api/discord never contains the webhook', 'abcSECRET' not in json.dumps(get('/api/discord')))
    time.sleep(3); chk('disabled: nothing posted while live', fake['posts'] == [], fake['posts'])
    # 3. enabled + dry run: logged, not sent, counted as announced
    r = post('/api/discord/settings', {'Enabled': True, 'RoleId': '<@&555>'}); chk('bad RoleId refused', r.get('ok') is False, r)
    r = post('/api/discord/settings', {'Enabled': True, 'RoleId': '555'}); chk('enabled, dry-run state', r.get('ok') and r['state'] == 'dry-run' and r['settings']['RoleId'] == '555', r)
    time.sleep(4); a = get('/api/discord')
    chk('dry run: no HTTP post, state remembers the stream key', fake['posts'] == [] and a['posted']['streamKey'] == 'twitch:1001' and 'dry-run' in (a.get('lastResult') or ''), (fake['posts'], a['posted'], a.get('lastResult')))
    logtxt = open(outp, 'rb').read().decode('utf-8', 'replace'); chk('dry run payload on the console with the role ping', '[discord] dry POST' in logtxt and '<@&555>' in logtxt and 'Ranked 2s grind' in logtxt)
    # 4. armed, new stream: exactly one real POST with ?wait=true, embed shape, ping + allowed roles
    r = post('/api/discord/settings', {'DryRun': False}); chk('armed', r['state'] == 'armed', r)
    fake['live'] = False; chk('offline', wait_live(False)); time.sleep(1)
    r = post('/api/discord/settings', {'MinGapMin': 0}); fake['stream_id'] = '1002'; fake['live'] = True; chk('live again (new stream id)', wait_live(True))
    chk('one POST for the new stream', wait_posts(1) and len(fake['posts']) == 1, fake['posts'])
    p0 = fake['posts'][0]; b0 = p0['body']
    chk('POST uses ?wait=true', 'wait=true' in p0['path'], p0['path'])
    e = b0['embeds'][0]
    chk('content pings the role and names the streamer', b0['content'].startswith('<@&555> innocentpenguin_ is LIVE'), b0['content'])
    chk('allowed_mentions limited to that role', b0['allowed_mentions'] == {'parse': [], 'roles': ['555']}, b0['allowed_mentions'])
    chk('embed: title, url, game field, preview image, boxart thumbnail, orange', e['title'] == 'Ranked 2s grind' and e['url'] == 'https://twitch.tv/innocentpenguin_' and e['fields'][0]['value'] == 'Rocket League' and 'live_user_innocentpenguin_' in e['image']['url'] and '30921' in e['thumbnail']['url'] and e['color'] == 16744192, e)
    chk('username PinguinoB0t', b0.get('username') == 'PinguinoB0t', b0.get('username'))
    time.sleep(5); chk('no second post while still live', len(fake['posts']) == 1, len(fake['posts']))
    a = get('/api/discord'); chk('state: message id + stream key', a['posted']['messageId'] == 'msg1' and a['posted']['streamKey'] == 'twitch:1002', a['posted'])
    # 5. Host restart while live: no re-post
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start(); waitup(); chk('live after restart', wait_live(True)); time.sleep(5)
    chk('restart while live: still one post', len(fake['posts']) == 1, len(fake['posts']))
    # 6. blip: offline for a moment, back with a NEW stream id inside MinGapMin -> no second post, no "ended" edit
    post('/api/discord/settings', {"MinGapMin": 30, "OfflineGraceSec": 8})
    fake['live'] = False; chk('blip offline', wait_live(False)); time.sleep(1.5); fake['stream_id'] = '1003'; fake['live'] = True; chk('blip back', wait_live(True)); time.sleep(5)
    chk('a blip never re-posts', len(fake['posts']) == 1 and fake['patches'] == [], (len(fake['posts']), fake['patches']))
    # 7. real end: offline past the grace period -> one PATCH to ended (no ping, grey, no image), once
    fake['live'] = False; chk('offline for real', wait_live(False))
    for _ in range(40):
        if fake['patches']: break
        time.sleep(0.5)
    chk('ended edit PATCHes the posted message once', len(fake['patches']) == 1 and fake['patches'][0]['path'].endswith('/messages/msg1'), fake['patches'])
    pb = fake['patches'][0]['body']; chk('ended body: no ping, grey, no image, ended text', '<@&' not in pb['content'] and pb['embeds'][0]['color'] == 6710886 and 'image' not in pb['embeds'][0] and 'Stream ended' in pb['embeds'][0]['description'] and pb['allowed_mentions'] == {'parse': []}, pb)
    time.sleep(4); chk('ended edit happens once', len(fake['patches']) == 1, len(fake['patches']))
    r = says(host, '*mod1: !discordtest end'); chk('!discordtest end after an edit says already edited', len(r) == 1 and 'already' in r[0], r)
    # 8. !discordtest send: a [TEST] post, never pings, does not touch the stream state
    n = len(fake['posts']); r = says(host, '*mod1: !discordtest send', 2.0)
    chk('!discordtest send posts a test message', len(fake['posts']) == n + 1 and len(r) == 1 and 'test post sent' in r[0], (len(fake['posts']) - n, r))
    tb = fake['posts'][-1]['body']; chk('test post is marked and pings nobody', tb['content'].startswith('[TEST, ignore]') and tb['embeds'][0]['title'].startswith('[TEST]') and tb['allowed_mentions'] == {'parse': []}, tb)
    a = get('/api/discord'); chk('test post leaves the stream state alone', a['posted']['messageId'] == 'msg1', a['posted'])
    r = post('/api/discord/test', {'mode': 'status'}); chk('API test status', r.get('ok') and 'Discord go-live: armed' in r['text'], r)
    r = post('/api/discord/test', {'mode': 'dry'}); chk('API dry returns the payload', r.get('ok') and r.get('payload', {}).get('embeds'), r)
    # 9. next stream later: a new post (MinGapMin passed because postedAt is old enough? use MinGapMin 0) and status line
    post('/api/discord/settings', {'MinGapMin': 0}); fake['stream_id'] = '2001'; fake['live'] = True; chk('next day live', wait_live(True)); n = len(fake['posts'])
    chk('a later stream gets its own post', wait_posts(n + 1) and fake['posts'][-1]['body']['content'].startswith('<@&555>'), len(fake['posts']) - n)
    r = says(host, '*mod1: !discordstatus'); chk('!discordstatus line', len(r) == 1 and r[0].startswith('Discord go-live: armed') and 'live' in r[0], r)
    # 10. dead webhook: 404 is not retried every tick
    fake['live'] = False; wait_live(False); time.sleep(6); fake['status'] = 404; fake['stream_id'] = '3001'; fake['live'] = True; wait_live(True); n = len(fake['posts']); time.sleep(6)
    chk('a 404 webhook is tried once per stream, not every tick', len(fake['posts']) == n + 1 and 'not found' in (get('/api/discord').get('lastResult') or ''), (len(fake['posts']) - n, get('/api/discord').get('lastResult')))
    fake['status'] = 200
    # 11. env webhook wins over the file, and removing the file secret works
    r = post('/api/discord/secret', {'webhook': ''}); chk('secret removed', r.get('ok') and r['webhookConfigured'] is False and r['state'] == 'not configured', r)
    host.kill(); host.wait(timeout=20); time.sleep(1); host = start({'PINGUINO_DISCORD_WEBHOOK': WEBHOOK}); waitup()
    a = get('/api/discord'); chk('env webhook is used (source env)', a['webhookConfigured'] and a['webhookSource'] == 'env', a)
finally:
    try: host.kill(); host.wait(timeout=20)
    except Exception: pass
    srv.shutdown(); time.sleep(1)
    try: shutil.rmtree(d)
    except Exception: pass
print('test-host-discord:', 'PASS' if not fails else 'FAIL (%d)' % len(fails))
for f in fails: print('  ', f)
sys.exit(1 if fails else 0)
