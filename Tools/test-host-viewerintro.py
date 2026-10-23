"""Viewer intros: filters, pending -> approve/reject, edit goes back to pending, remove, Multi's GET /api/intro (approved only, 404 otherwise), mod audit.
Usage: python Tools/test-host-viewerintro.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8986; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgvi_'); outf = os.path.join(d, 'out.txt')
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8987'})
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'ab'), stderr=subprocess.STDOUT)
def get(p):
    try: return urllib.request.urlopen(B + p, timeout=10).status, json.load(urllib.request.urlopen(B + p, timeout=10))
    except urllib.error.HTTPError as e: return e.code, None
def post(p, o): return json.load(urllib.request.urlopen(urllib.request.Request(B + p, data=json.dumps(o).encode(), headers={'Content-Type': 'application/json', 'Origin': B}), timeout=10))
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def sub(text, uid='111', sound='bell', login='alice'): return post('/api/intros', {'action': 'submit', 'platform': 'twitch', 'user_id': uid, 'login': login, 'text': text, 'sound_id': sound})
try:
    for _ in range(120):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    chk('none yet 404', get('/api/intro?platform=twitch&user_id=111')[0] == 404)
    for bad in ['visit www.evil.com now', 'go to http://x.y', 'check me.gg', 'f u c k this', 'sh1t happens', '!so someone', '', 'x' * 81, 'two\nlines']:
        r = sub(bad); chk('rejects ' + repr(bad[:20]), r['ok'] is False, r)
    for good in ['Penguin incoming! Say hi', 'The document is here', 'cocktail time', 'Skyscraper vibes']:
        r = sub(good, uid='9' + str(len(good)), login='ok' + str(len(good))); chk('allows ' + good, r['ok'] is True, r)
    r = sub('The legend arrives!'); chk('submit pending', r['ok'] and r['intro']['status'] == 'pending', r)
    chk('pending is not served', get('/api/intro?platform=twitch&user_id=111')[0] == 404)
    r = post('/api/intros', {'action': 'approve', 'platform': 'twitch', 'user_id': '111', 'by': 'modguy'}); chk('approve', r['ok'] and r['intro']['status'] == 'approved' and r['intro']['approved_by'] == 'modguy', r)
    c, j = get('/api/intro?platform=twitch&user_id=111'); chk('served after approval', c == 200 and j == {'text': 'The legend arrives!', 'sound_id': 'bell', 'status': 'approved'}, (c, j))
    c, j = get('/api/intro/viewer?login=Alice'); chk('/api/intro/viewer finds the approved intro by login', c == 200 and j['text'] == 'The legend arrives!', (c, j))
    chk('unknown login is 404', get('/api/intro/viewer?login=nobody')[0] == 404)
    r = sub('Edited intro'); chk('edit back to pending', r['intro']['status'] == 'pending', r)
    chk('edit not served', get('/api/intro?platform=twitch&user_id=111')[0] == 404)
    r = post('/api/intros', {'action': 'reject', 'platform': 'twitch', 'user_id': '111', 'by': 'modguy'}); chk('reject', r['intro']['status'] == 'rejected', r)
    r = post('/api/intros', {'action': 'approve', 'platform': 'twitch', 'user_id': '111', 'by': 'modguy'}); chk('cannot approve twice', r['ok'] is False, r)
    sub('Back again'); post('/api/intros', {'action': 'approve', 'platform': 'twitch', 'user_id': '111', 'by': 'modguy'})
    chk('pending list', get('/api/intros?status=pending')[1]['pending'] >= 4)
    r = post('/api/intros', {'action': 'remove', 'platform': 'twitch', 'user_id': '111'}); chk('remove', r['ok'], r)
    chk('removed not served', get('/api/intro?platform=twitch&user_id=111')[0] == 404)
    chk('mine', get('/api/intros?platform=twitch&user_id=111')[1]['intro']['status'] == 'removed')
    r = post('/api/intros', {'action': 'settings', 'requireApproval': False}); sub('Auto live', uid='222', login='bob')
    c, j = get('/api/intro?platform=twitch&user_id=222'); chk('auto approve setting', c == 200 and j['text'] == 'Auto live', (c, j))
    r = sub('hi', sound='../x'); chk('bad sound id', r['ok'] is False, r)
    log = get('/api/modaudit?limit=100')[1]; txt = json.dumps(log)
    chk('mod audit', 'intro approved' in txt and 'intro rejected' in txt and 'intro removed' in txt and 'intro submitted' in txt)
finally:
    h.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS viewerintro'); sys.exit(1 if fails else 0)
