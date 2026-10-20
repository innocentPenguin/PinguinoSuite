"""Channel-control commands (Plan 5) against a fake Helix: master switch, poll/predict/chat settings/announce/shield/marker/ad/vip, guarded raid, control log, live-state.  Usage: python Tools/test-host-control.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8996; B = 'http://127.0.0.1:%d' % PORT; HX = 8997
reqs = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _do(self):
        n = int(self.headers.get('Content-Length') or 0); body = json.loads(self.rfile.read(n) or b'{}') if n else {}
        (None if (self.path.startswith('/api/') or self.command == 'GET' and not self.path.startswith(('/predictions', '/users?login=patfromearth'))) else reqs.append((self.command, self.path, body))); code, out = 200, {'data': []}
        if self.path.startswith('/games'): out = {'data': [{'id': 'g1', 'name': 'Rocket League'}]}
        elif self.path.startswith('/users'): out = {'data': [{'id': '777', 'login': 'patfromearth'}]}
        elif self.path.startswith('/predictions') and self.command == 'GET': out = {'data': [{'id': 'pr1', 'status': 'ACTIVE', 'outcomes': [{'id': 'o1', 'title': 'Yes'}, {'id': 'o2', 'title': 'No'}]}]}
        elif self.command in ('PATCH', 'DELETE') or self.path.startswith('/chat/settings'): code = 204
        if code == 204:
            self.send_response(204); self.end_headers(); return
        b = json.dumps(out).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _do
srv = HTTPServer(('127.0.0.1', HX), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
d = tempfile.mkdtemp(prefix='pgctl_'); os.makedirs(os.path.join(d, 'config'))
json.dump({'Channel': 'innocentpenguin_', 'OverlayPort': PORT, 'ClientId': 'cid', 'UserToken': 'tok', 'BroadcasterId': '111', 'SenderId': '111'}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8999', 'PINGUINO_HELIX_BASE': 'http://127.0.0.1:%d' % HX, 'PINGUINO_AD_WARN_MS': '300', 'PINGUINO_CONTROL_COOL': '0', 'PINGUINO_MODULE_TOKEN': 'tok-api'})
outp = os.path.join(d, 'out.txt')
h = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outp, 'ab'), stderr=subprocess.STDOUT)
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def say(line, wait=1.6):
    n = open(outp, 'rb').read().count(b'[say] '); h.stdin.write((line + '\n').encode()); h.stdin.flush(); time.sleep(wait)
    SNAP[0] = reqs[-1] if reqs else None
    t = open(outp, 'rb').read().decode('utf-8', 'replace').split('[say] ')
    return t[-1].split('\n')[0].strip() if len(t) - 1 > n else None
SNAP = [None]
def last(): return SNAP[0]
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B, 'Authorization': 'Bearer tok-api'})
    return json.load(urllib.request.urlopen(rq, timeout=10))
def cool(): time.sleep(0.2)
try:
    for _ in range(80):
        try: urllib.request.urlopen(B + '/api/status', timeout=2); break
        except Exception: time.sleep(0.5)
    time.sleep(3); r = say('*modguy: !slow 10', 2.5); chk('switched off says so to mods', r and 'switched off' in r, r); chk('no Helix call while off', not reqs, reqs)
    r = say('viewer: !slow 10'); chk('viewer gets nothing', r is None, r)
    cfg = os.path.join(d, 'config', 'control.json'); chk('control.json seeded off', json.load(open(cfg))['enabled'] is False)
    json.dump({'enabled': True, 'predictMods': []}, open(cfg, 'w'))
    r = say('viewer: !slow 10'); chk('viewer still nothing when on', r is None and not reqs, r)
    r = say('*modguy: !slow 10'); chk('slow', r == 'Slow mode: one message every 10s.' and last()[0] == 'PATCH' and last()[1].startswith('/chat/settings?broadcaster_id=111&moderator_id=111') and last()[2] == {'slow_mode': True, 'slow_mode_wait_time': 10}, (r, last()))
    cool(); r = say('*modguy: !followers 10'); chk('followers', last()[2] == {'follower_mode': True, 'follower_mode_duration': 10}, last())
    cool(); r = say('*modguy: !emote-only off'); chk('emote off', last()[2] == {'emote_mode': False}, last())
    cool(); r = say('*modguy: !subs-only'); chk('subs on', last()[2] == {'subscriber_mode': True}, last())
    r = say('*modguy: !poll "Best map?" Mannfield|Champions|Utopia 90'); chk('poll', last()[0] == 'POST' and last()[1] == '/polls' and last()[2]['duration'] == 90 and len(last()[2]['choices']) == 3 and last()[2]['title'] == 'Best map?', last())
    r = say('*modguy: !poll "one option" only'); chk('poll needs 2 options', r and '2 to 5' in r, r)
    r = say('*modguy: !predict "Win?" Yes|No'); chk('mod not whitelisted for predictions', r and 'streamer and mods' in r, r)
    r = say('#ivan: !predict "Win?" Yes|No 60'); chk('owner predict', last()[1] == '/predictions' and last()[2]['prediction_window'] == 60 and last()[2]['outcomes'] == [{'title': 'Yes'}, {'title': 'No'}], last())
    cool(); r = say('#ivan: !lock'); chk('lock', last() and last()[0] == 'PATCH' and last()[2]['status'] == 'LOCKED' and last()[2]['id'] == 'pr1', last())
    cool(); r = say('#ivan: !resolve no'); chk('resolve by name', last()[2] == {'broadcaster_id': '111', 'id': 'pr1', 'status': 'RESOLVED', 'winning_outcome_id': 'o2'}, last())
    cool(); r = say('#ivan: !cancel'); chk('cancel', last()[2]['status'] == 'CANCELED', last())
    r = say('#ivan: !announce orange Giveaway soon'); chk('announce colour', last()[1].startswith('/chat/announcements?broadcaster_id=111&moderator_id=111') and last()[2] == {'message': 'Giveaway soon', 'color': 'orange'}, last())
    r = say('*modguy: !title New PM system tonight'); chk('mod !title', last()[0] == 'PATCH' and last()[1].startswith('/channels?broadcaster_id=111') and last()[2] == {'title': 'New PM system tonight'} and 'Title changed' in r, (last(), r))
    r = say('*modguy: !game rocket league'); chk('mod !game', last()[0] == 'PATCH' and last()[2] == {'game_id': 'g1'} and 'Rocket League' in r, (last(), r))
    n0 = len(reqs); r = say('viewer1: !title hacked'); chk('viewer !title does nothing', len(reqs) == n0 and not r, r)
    r = say('*modguy: !title'); chk('!title usage', len(reqs) == n0 and 'Use: !title' in r, r)
    r = say('#ivan: !marker nice'); chk('marker', last()[1] == '/streams/markers' and last()[2]['description'] == 'nice', last())
    n0 = len(reqs); r = say('*modguy: !shield on'); chk('shield is broadcaster only', len(reqs) == n0, r)
    r = say('#ivan: !shield on'); chk('shield', last()[0] == 'PUT' and last()[2] == {'is_active': True} and len(reqs) == n0 + 1, last())
    r = say('#ivan: !vip patfromearth'); chk('vip', reqs[-1][0] == 'POST' and reqs[-1][1] == '/channels/vips?broadcaster_id=111&user_id=777', reqs[-3:])
    n0 = len(reqs); r = say('#ivan: !ad 45'); chk('ad length checked', r and 'must be' in r and len(reqs) == n0, r)
    r = say('#ivan: !ad 60'); chk('ad warns first', r and '30 seconds' in r, r); time.sleep(1.2); chk('then starts', last()[1] == '/channels/commercial' and last()[2]['length'] == 60, last())
    n0 = len(reqs); r = say('*modguy: !raid patfromearth'); chk('mod cannot raid', r is None and len(reqs) == n0, r)
    r = say('#ivan: !raid somebodyelse'); chk('not on list', r and 'not on the raid list' in r, r)
    r = say('#ivan: !confirm raid'); chk('confirm without request', r and 'No raid waiting' in r, r)
    r = say('#ivan: !raid patfromearth'); chk('asks for confirm', r and '!confirm raid' in r and '20 seconds' in r, r); chk('no raid yet', not any(q[1].startswith('/raids') for q in reqs))
    r = say('#ivan: !unraid'); chk('unraid cancels pending', r == 'Raid cancelled.', r)
    r = say('#ivan: !confirm raid'); chk('cancelled request cannot be confirmed', r and 'No raid waiting' in r, r)
    r = say('#ivan: !raid patfromearth'); api('/api/run', {'text': '!confirm raid', 'user': 'ivan'}); time.sleep(0.8)
    t = open(outp, 'rb').read().decode('utf-8', 'replace'); chk('Stream Deck / voice cannot confirm', 'only be confirmed by typing in Twitch chat' in t and not any(q[1].startswith('/raids') for q in reqs), t[-300:])
    r = say('#ivan: !confirm raid'); chk('real chat confirm starts the raid', last()[0] == 'POST' and last()[1] == '/raids?from_broadcaster_id=111&to_broadcaster_id=777' and r and 'Raiding patfromearth' in r, (r, last()))
    r = say('#ivan: !confirm raid'); chk('cannot confirm twice', r and 'No raid waiting' in r, r)
    r = say('#ivan: !raid patfromearth'); time.sleep(20.6); r = say('#ivan: !confirm raid'); chk('expired after 20 s', r and 'No raid waiting' in r, r)
    log = [json.loads(l) for l in open(os.path.join(d, 'runtime', 'control_log.jsonl'), encoding='utf-8')]
    chk('every use logged', len(log) >= 20 and any(x['cmd'] == '!raid' for x in log) and any(x.get('synthetic') for x in log), len(log))
    raid_list = json.load(open(os.path.join(d, 'config', 'raid_list.json')))['names']; chk('raid list seeded with patfromearth', raid_list == ['patfromearth'], raid_list)
    h.stdin.write(('eventsub channel.poll.progress ' + json.dumps({'id': 'p', 'title': 'T', 'choices': [{'id': 'a', 'title': 'A', 'votes': 3}]}) + '\n').encode()); h.stdin.flush(); time.sleep(0.6)
    ls = json.load(urllib.request.urlopen(B + '/api/live-state', timeout=5)); chk('live-state poll', ls['poll'] and ls['poll']['state'] == 'progress' and ls['poll']['choices'][0]['votes'] == 3 and ls['prediction'] is None, ls)
    r = say('eventsub channel.poll.end ' + json.dumps({'id': 'p', 'title': 'T', 'status': 'completed', 'choices': [{'id': 'a', 'title': 'A', 'votes': 3}, {'id': 'b', 'title': 'B', 'votes': 1}]}))
    chk('poll result line', r and 'A wins with 3 votes' in r, r)
finally:
    h.kill(); srv.shutdown(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS channel control')
sys.exit(1 if fails else 0)
