"""The YouTube-only shop: !shop lists guess + 1v1 + casual on YouTube (one line), Twitch never sees 1v1 / casual; !shop 1v1 / casual from a YouTube viewer takes the points, creates an order (Data/yt_orders.json),
pings the mods in chat, GET /api/ytorders lists it for Master View; a mod marks it done (chat or POST /api/ytorders), cancel refunds automatically (once); the buyer is told on YouTube. Fake Multi: no real chat.
Usage: python Tools/test-host-ytorders.py [dll]"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT, MX, TOK = 8977, 8978, 'test-module-token'
sends = []
class Mx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'); sends.append(b)
        r = json.dumps({'ok': True, 'id': 'm1'}).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(r))); self.end_headers(); self.wfile.write(r)
threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', MX), Mx).serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgyo_'); outp = os.path.join(d, 'out.txt')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Url': 'http://127.0.0.1:%d' % MX, 'Token': 'multi-test'}, open(os.path.join(d, 'alert_bridge.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8976', 'PINGUINO_MODULE_TOKEN': TOK, 'PINGUINO_DUP_SECONDS': '1', 'PINGUINO_YT_SPACING_MS': '100'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'wb'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def http_(p, body=None, tok=TOK):
    h = {'Content-Type': 'application/json'}
    if body is not None and tok: h['Authorization'] = 'Bearer ' + tok
    try: r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, p), data=None if body is None else json.dumps(body).encode(), headers=h), timeout=20); return json.load(r)
    except urllib.error.HTTPError as e: return {'http': e.code}
def cin(user, text, uid, mid):
    sends[:] = []; http_('/api/chat-in', {'platform': 'youtube', 'user': user, 'userId': uid, 'text': text, 'msgId': mid}); time.sleep(1.2); return [s['text'] for s in sends if 'text' in s and 'Welcome' not in s['text']]
def out(): return open(outp, 'rb').read().decode('utf-8', 'replace')
def stdin(line, wait=0.8):
    n = len(out()); host.stdin.write(line.encode() + chr(10).encode()); host.stdin.flush(); time.sleep(wait)
    return [l[6:] for l in out()[n:].splitlines() if l.startswith('[say] ')]
def bal(login): return http_('/api/economy/user?login=' + login).get('points')
try:
    for _ in range(60):
        try: urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=3); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    cin('Dana', 'hello', 'UCdana', 'd0'); cin('Eve', 'hello', 'UCeve', 'e0')
    stdin('#trial: !addpoints yt:ucdana 400000'); time.sleep(0.5)
    d0 = bal('yt:ucdana'); chk('Dana got her points', d0 is not None and d0 >= 400000, d0)
    # the list
    r = cin('Dana', '!shop', 'UCdana', 'd1')
    chk('YouTube !shop is ONE line with guess, 1v1 and casual and the prices', len(r) == 1 and r[0].startswith('@Dana ') and 'guess' in r[0] and '1v1' in r[0] and 'casual' in r[0] and '150,000' in r[0] and '300,000' in r[0] and len(r[0]) <= 200 and 'yt:' not in r[0], r)
    r = stdin('twitchy: !shop'); chk('the Twitch !shop never mentions 1v1 / casual', len(r) == 1 and '1v1' not in r[0] and 'casual' not in r[0].lower() and 'Peng' not in r[0], r)
    stdin('#trial: !addpoints twitchy 500000'); tb = bal('twitchy')
    r = stdin('twitchy: !shop 1v1'); chk('a Twitch viewer cannot buy 1v1 (no such item), no points taken', bal('twitchy') == tb and not any('order' in x.lower() for x in r), (r, bal('twitchy'), tb))
    # no money
    r = cin('Eve', '!shop 1v1', 'UCeve', 'e1'); chk('too poor: told what it costs, nothing created', len(r) == 1 and '150,000' in r[0] and r[0].startswith('@Eve '), r)
    chk('no orders yet', http_('/api/ytorders')['pending'] == 0)
    # buy 1v1
    sends[:] = []; n = len(out()); r = cin('Dana', '!shop 1v1', 'UCdana', 'd2'); log = out()[n:]
    chk('buy 1v1: one line to Dana with the item, price, place and order number', len(r) == 1 and r[0].startswith('@Dana ') and '1v1 vs Peng' in r[0] and '150,000' in r[0] and '#1' in r[0] and len(r[0]) <= 200, r)
    chk('the mods are pinged in chat', '[say] YouTube order #1: Dana bought 1v1 vs Peng' in log and '!ytorder done 1' in log, log[-500:])
    chk('the points were taken', bal('yt:ucdana') == d0 - 150000, (bal('yt:ucdana'), d0))
    o = http_('/api/ytorders'); chk('Master View list: 1 pending order with the card fields', o['pending'] == 1 and len(o['orders']) == 1 and o['orders'][0]['id'] == 1 and o['orders'][0]['display'] == 'Dana' and o['orders'][0]['label'] == '1v1 vs Peng' and o['orders'][0]['price'] == 150000 and o['orders'][0]['status'] == 'pending' and o['orders'][0]['place'] == 1 and o['orders'][0]['platform'] == 'youtube' and len(o['items']) == 2, o)
    r = cin('Dana', '!shop 1v1', 'UCdana', 'd3'); chk('a second order while one waits is refused, nothing taken', len(r) == 1 and 'already' in r[0] and bal('yt:ucdana') == d0 - 150000, (r, bal('yt:ucdana')))
    r = cin('Dana', '!shop casual', 'UCdana', 'd3b'); chk('one waiting order per buyer, for either item', len(r) == 1 and 'already' in r[0], r)
    # viewers cannot resolve
    r = cin('Dana', '!ytorder cancel 1', 'UCdana', 'd4'); chk('a viewer cannot cancel (silent)', r == [] and http_('/api/ytorders')['pending'] == 1, r)
    chk('POST needs the module token', http_('/api/ytorders', {'action': 'done', 'id': 1}, tok=None).get('http') in (401, 403), http_('/api/ytorders', {'action': 'done', 'id': 1}, tok=None))
    # mod list + cancel -> refund
    r = stdin('*modman: !ytorders'); chk('mod list in chat', len(r) == 1 and '#1' in r[0] and 'Dana' in r[0], r)
    sends[:] = []; r = stdin('*modman: !ytorder cancel 1', 1.5); said = [s['text'] for s in sends if 'text' in s]
    chk('cancel confirms to the mod', len(r) == 1 and 'cancelled and refunded' in r[0], r)
    chk('the points are back in full', bal('yt:ucdana') == d0, (bal('yt:ucdana'), d0))
    chk('the buyer is told on YouTube', any('@Dana' in s and 'refunded' in s and '150,000' in s for s in said), said)
    r = stdin('*modman: !ytorder cancel 1'); chk('a second cancel is refused and refunds nothing', len(r) == 1 and 'already' in r[0] and bal('yt:ucdana') == d0, (r, bal('yt:ucdana')))
    chk('pending is 0, history keeps it as cancelled', http_('/api/ytorders')['pending'] == 0 and http_('/api/ytorders?status=all')['orders'][0]['status'] == 'cancelled', http_('/api/ytorders?status=all'))
    # casual + done by chat
    r = cin('Dana', '!shop casual', 'UCdana', 'd5'); chk('buy casual', len(r) == 1 and 'Casual game with Peng' in r[0] and '300,000' in r[0] and '#1' in r[0] and '#2' in r[0], r)
    chk('300,000 taken', bal('yt:ucdana') == d0 - 300000, bal('yt:ucdana'))
    sends[:] = []; r = stdin('*modman: !ytorder done 2', 1.5); said = [s['text'] for s in sends if 'text' in s]
    chk('done confirms to the mod', len(r) == 1 and 'marked done' in r[0], r); chk('the buyer is told it is done', any('@Dana' in s and 'done' in s for s in said), said)
    chk('done keeps the points spent', bal('yt:ucdana') == d0 - 300000)
    o = http_('/api/ytorders?status=all'); chk('history: cancelled #1, done #2', [(x['id'], x['status']) for x in o['orders']] == [(1, 'cancelled'), (2, 'done')], o)
    r = stdin('*modman: !ytorder cancel 2'); chk('a done order cannot be cancelled / refunded', len(r) == 1 and 'already done' in r[0] and bal('yt:ucdana') == d0 - 300000, (r, bal('yt:ucdana')))
    # Master View POST path: buy again, cancel through the API
    stdin('#trial: !addpoints yt:ucdana 200000'); d1 = bal('yt:ucdana')
    r = cin('Dana', '!shop 1v1', 'UCdana', 'd6'); time.sleep(0.5)
    res = http_('/api/ytorders', {'action': 'cancel', 'id': 3, 'by': 'master view'}); chk('POST cancel refunds', res.get('ok') is True and res['order']['status'] == 'cancelled' and bal('yt:ucdana') == d1, (res, bal('yt:ucdana'), d1))
    res = http_('/api/ytorders', {'action': 'done', 'id': 3}); chk('POST on a resolved order is refused', res.get('ok') is False, res)
    res = http_('/api/ytorders', {'action': 'nope', 'id': 3}); chk('POST bad action refused', res.get('ok') is False, res)
    res = http_('/api/ytorders', {'action': 'done', 'id': 99}); chk('POST unknown id refused', res.get('ok') is False, res)
    chk('orders survive on disk', os.path.exists(os.path.join(d, 'yt_orders.json')) and len(json.load(open(os.path.join(d, 'yt_orders.json')))['orders']) == 3)
finally:
    host.kill(); time.sleep(0.5); print(out()[-1500:]) if fails else None; shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS ytorders'); sys.exit(1 if fails else 0)
