"""Chat feed colours + badges (sim Host, fake Helix): a raw IRC PRIVMSG with color=#FF4500 and badges=subscriber/12,moderator/1 shows both in /api/chat/recent
(color "#FF4500", badges names kept, badgeSets [{set_id,version,url}]); an empty colour tag uses the Helix /chat/color fallback (fake) once per user (cached);
both failing leaves color empty; YouTube lines (via /api/chat-in) are in the feed as plain lines (platform, name, empty colour and badges) and never ask Helix; /api/chat/badges serves global + channel badge images (channel overrides global).
Usage: python Tools/test-host-chatmeta.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, HX, TOK = 9181, 9182, 'test-module-token'; B = 'http://127.0.0.1:%d' % PORT
colour_calls = []; badge_calls = []
COLORS = {'101': '#1E90FF', '102': ''}
def reply(h, o, code=200):
    b = json.dumps(o).encode(); h.send_response(code); h.send_header('Content-Type', 'application/json'); h.send_header('Content-Length', str(len(b))); h.end_headers(); h.wfile.write(b)
class Hx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith('/chat/color'):
            uid = self.path.split('user_id=')[1].split('&')[0]; colour_calls.append(uid)
            if uid == '103': return reply(self, {'message': 'boom'}, 500)
            return reply(self, {'data': [{'user_id': uid, 'color': COLORS.get(uid, '')}]})
        if self.path.startswith('/chat/badges/global'):
            badge_calls.append('global')
            return reply(self, {'data': [{'set_id': 'moderator', 'versions': [{'id': '1', 'image_url_1x': 'https://g/mod1', 'image_url_2x': 'https://g/mod2', 'image_url_4x': 'https://g/mod4'}]},
                                        {'set_id': 'subscriber', 'versions': [{'id': '0', 'image_url_1x': 'https://g/sub0', 'image_url_2x': 'https://g/sub0b', 'image_url_4x': 'https://g/sub0c'}]}]})
        if self.path.startswith('/chat/badges'):
            badge_calls.append('channel')
            return reply(self, {'data': [{'set_id': 'subscriber', 'versions': [{'id': '12', 'image_url_1x': 'https://c/sub12a', 'image_url_2x': 'https://c/sub12b', 'image_url_4x': 'https://c/sub12c'},
                                                                              {'id': '0', 'image_url_1x': 'https://c/sub0a', 'image_url_2x': 'https://c/sub0b', 'image_url_4x': 'https://c/sub0c'}]}]})
        reply(self, {'data': []})
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0))); reply(self, {'data': [{'is_sent': True}]})
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', HX), Hx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgcm_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT, 'UserToken': 't', 'ClientId': 'c', 'BroadcasterId': 'streamer1'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_COMPAT_WS_PORT': '9183', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '0'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(os.path.join(d, 'out.txt'), 'wb'), stderr=subprocess.STDOUT)
res = []
def chk(n, ok, x=''):
    res.append((n, ok)); print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '   ' + str(x)))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=8))
def irc(nick, uid, tags, text): host.stdin.write(('@%s;display-name=%s;user-id=%s;id=m-%s-%s :%s!%s@%s.tmi.twitch.tv PRIVMSG #trial :%s\n' % (tags, nick.capitalize(), uid, nick, time.time(), nick, nick, nick, text)).encode()); host.stdin.flush()
def msgs(): return get('/api/chat/recent?limit=50')['messages']
def by(user): return [m for m in msgs() if m['user'] == user]
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    irc('alice', '100', 'color=#FF4500;badges=subscriber/12,moderator/1;mod=1;subscriber=1', 'hello chat'); time.sleep(2)
    a = by('alice')
    chk('IRC colour tag passes through', a and a[-1]['color'] == '#FF4500', a)
    chk('badges names kept (old field)', a and a[-1]['badges'] == ['moderator', 'subscriber'], a)
    chk('badgeSets carries set_id/version', a and [(b['set_id'], b['version']) for b in a[-1]['badgeSets']] == [('subscriber', '12'), ('moderator', '1')], a)
    chk('no Helix colour lookup when the tag has one', '100' not in colour_calls, colour_calls)
    irc('bob', '101', 'color=;badges=', 'no colour here'); time.sleep(2)
    b = by('bob')
    chk('empty colour tag: Helix fallback colour used', b and b[-1]['color'] == '#1E90FF', (b, colour_calls))
    irc('bob', '101', 'color=;badges=', 'second line'); time.sleep(1.5)
    chk('fallback is cached: one Helix call for two lines', colour_calls.count('101') == 1 and by('bob')[-1]['color'] == '#1E90FF', colour_calls)
    irc('carl', '102', 'color=;badges=', 'helix has none either'); time.sleep(2)
    chk('both empty: color stays empty', by('carl') and by('carl')[-1]['color'] == '', by('carl'))
    irc('dan', '103', 'color=;badges=', 'helix errors'); time.sleep(2)
    chk('Helix error: color empty, line still in the feed', by('dan') and by('dan')[-1]['color'] == '', by('dan'))
    irc('eve', '104', 'color=notacolour;badges=bits/100', 'bad tag'); time.sleep(2)
    chk('a malformed colour tag is not passed through', by('eve') and by('eve')[-1]['color'] in ('', ), by('eve'))
    api = get('/api/chat/badges'); s = api.get('sets', {})
    chk('/api/chat/badges: global + channel badges, channel overrides', api.get('ok') and s['moderator']['1']['2x'] == 'https://g/mod2' and s['subscriber']['12']['2x'] == 'https://c/sub12b' and s['subscriber']['0']['2x'] == 'https://c/sub0b', api)
    chk('badge sets fetched once (cached)', badge_calls.count('global') == 1 and badge_calls.count('channel') == 1, badge_calls)
    irc('fay', '105', 'color=#00FF7F;badges=subscriber/12', 'after the cache is warm'); time.sleep(2)
    f = by('fay')
    chk('badgeSets get the image url once the cache is warm', f and f[-1]['badgeSets'][0].get('url') == 'https://c/sub12b', f)
    rq = urllib.request.Request(B + '/api/chat-in', data=json.dumps({'platform': 'youtube', 'user': 'Yt Viewer', 'userId': 'UCyt1', 'text': 'hi from youtube', 'msgId': 'y1'}).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK})
    urllib.request.urlopen(rq, timeout=20); time.sleep(2)
    yl = [m for m in msgs() if 'youtube' in m['text']]
    chk('YouTube lines are in the feed as plain lines (platform, name, no colour, no badges) and never ask Helix', len(yl) == 1 and yl[0].get('platform') == 'youtube' and yl[0].get('name') == 'Yt Viewer' and yl[0]['color'] == '' and yl[0]['badges'] == [] and 'UCyt1' not in colour_calls, yl)
    sim = [m for m in msgs() if m['user'] == 'zed']; host.stdin.write(b'zed: plain sim line\n'); host.stdin.flush(); time.sleep(1.5)
    z = by('zed'); chk('plain sim chat line: unchanged shape (color empty, badgeSets empty)', z and z[-1]['color'] == '' and z[-1]['badgeSets'] == [], z)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
bad = [n for n, ok in res if not ok]; print('FAILS: %d' % len(bad)); sys.exit(1 if bad else 0)
