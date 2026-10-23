"""Player-to-player loans through the site queue (request / offer / accept / decline / cancel / repay / default), limits, ledger rows for both sides, the checkbook activity view and the market push.
A fake innocentpenguin.com runs locally.  Usage: python Tools/test-host-p2p.py [dll]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
def _free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); n = s.getsockname()[1]; s.close(); return n
PORT, SITE, WSPORT = _free(), _free(), _free(); B = 'http://127.0.0.1:%d' % PORT; KEY = 'test-key-123'
d = tempfile.mkdtemp(prefix='pgp2p_'); out = os.path.join(d, 'out.txt'); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 40, 'minutes': 600}, 'amy': {'points': 7, 'minutes': 5}, 'bob': {'points': 1000, 'minutes': 600}, 'cat': {'points': 500, 'minutes': 600}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
S = {'reqs': {}, 'users': [], 'answers': []}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def auth(self):
        if self.headers.get('Authorization') != 'Bearer ' + KEY: self.send(401, {'error': 'unauthorized'}); return False
        return True
    def do_GET(self):
        if not self.auth(): return
        if self.path.startswith('/api/bot/economy/requests'): return self.send(200, {'requests': [r for r in S['reqs'].values() if r['status'] == 'pending']})
        self.send(404, {})
    def do_POST(self):
        if not self.auth(): return
        b = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/bot/economy/users': S['users'].append(b); return self.send(200, {'ok': True})
        if self.path == '/api/bot/economy/answers':
            S['answers'].append(b); S['reqs'][b['id']]['status'] = 'answered'; return self.send(200, {'ok': True})
        self.send(404, {})
srv = HTTPServer(('127.0.0.1', SITE), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': str(WSPORT), 'PINGUINO_SITE_BASE': 'http://127.0.0.1:%d' % SITE, 'BOT_API_KEY': KEY, 'PINGUINO_SITE_POLL_SEC': '1', 'PINGUINO_ECONOMY_PUSH_SEC': '1', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '600'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def bal(u): return get('/api/economy/me?login=' + u)['balance']
def q(i, login, action, **kw):
    r = {'id': i, 'login': login, 'action': action, 'status': 'pending'}; r.update(kw); S['reqs'][i] = r
def ans(i, t=10):
    e = time.time() + t
    while time.time() < e:
        for a in S['answers']:
            if a['id'] == i: return a
        time.sleep(0.3)
    return {}
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)
    q('r1', 'zed', 'loan_request', amount=100, interestPct=10, days=7); a = ans('r1')
    chk('request posted, id returned', a.get('status') == 'done' and a.get('data', {}).get('requestId') == 'rq-site-r1', a)
    q('r2', 'bob', 'loan_offer', requestId='rq-site-r1', amount=100, interestPct=10, days=7); a = ans('r2')
    chk('offer sent', a.get('status') == 'done' and a['data']['offerId'] == 'of-site-r2', a)
    q('r2b', 'zed', 'loan_offer', toLogin='zed', amount=50, interestPct=0, days=3); a = ans('r2b'); chk('no lending to yourself', a.get('status') == 'rejected' and 'yourself' in a['message'], a)
    q('r2c', 'amy', 'loan_offer', toLogin='zed', amount=100, interestPct=0, days=3); a = ans('r2c'); chk('lender needs the points', a.get('status') == 'rejected' and 'only have' in a['message'], a)
    q('r2d', 'cat', 'loan_accept', offerId='of-site-r2'); a = ans('r2d'); chk('only the borrower can accept', a.get('status') == 'rejected' and 'not for you' in a['message'], a)
    time.sleep(2)
    v = get('/api/economy/me?login=zed')
    chk('borrower sees the incoming offer', any(o['id'] == 'of-site-r2' and o['lender'] == 'bob' for o in v['p2p']['incoming']) and v['p2p']['myRequests'][0]['offers'] == 1, v['p2p'])
    q('r3', 'zed', 'loan_accept', offerId='of-site-r2'); a = ans('r3')
    chk('accepted: loan id, owed = principal + 10%', a.get('status') == 'done' and a['data']['loanId'] == 'ln-of-site-r2' and a['data']['owed'] == 110, a)
    chk('points moved both ways', bal('zed') == 140 and bal('bob') == 900, (bal('zed'), bal('bob')))
    q('r3b', 'zed', 'loan_accept', offerId='of-site-r2'); a = ans('r3b'); chk('accepting twice does not pay twice', a.get('status') == 'done' and bal('zed') == 140 and bal('bob') == 900, (a, bal('zed')))
    v = get('/api/economy/me?login=zed'); b = get('/api/economy/me?login=bob')
    chk('loan shows on both sides', v['p2p']['loans']['asBorrower'][0]['owed'] == 110 and b['p2p']['loans']['asLender'][0]['borrower'] == 'zed' and v['p2p']['myRequests'][0]['status'] == 'filled', (v['p2p'], b['p2p']['loans']))
    q('r4', 'zed', 'loan_repay', loanId='ln-of-site-r2', amount=50); a = ans('r4')
    chk('part repay', a.get('status') == 'done' and a['data']['owed'] == 60 and bal('zed') == 90 and bal('bob') == 950, a)
    q('r4b', 'cat', 'loan_repay', loanId='ln-of-site-r2', amount=10); a = ans('r4b'); chk('only the borrower repays', a.get('status') == 'rejected', a)
    q('r5', 'zed', 'loan_repay', loanId='ln-of-site-r2', amount=0); a = ans('r5')
    chk('repay all closes the loan', a.get('status') == 'done' and a['data']['owed'] == 0 and bal('zed') == 30 and bal('bob') == 1010, a)
    z = get('/api/economy/me?login=zed')
    chk('status repaid', z['p2p']['loans']['asBorrower'][0]['status'] == 'repaid', z['p2p']['loans'])
    # ---- limits
    q('l1', 'zed', 'loan_request', amount=5, interestPct=10, days=7); q('l2', 'zed', 'loan_request', amount=100, interestPct=80, days=7); q('l3', 'zed', 'loan_request', amount=100, interestPct=5, days=99)
    chk('amount, interest and days limits', all(ans(i).get('status') == 'rejected' for i in ('l1', 'l2', 'l3')), [ans(i) for i in ('l1', 'l2', 'l3')])
    q('l4', 'cat', 'loan_request', amount=50, interestPct=5, days=2); a4 = ans('l4'); q('l5', 'cat', 'loan_request', amount=60, interestPct=5, days=2); a5 = ans('l5')
    chk('one open request at a time', a4.get('status') == 'done' and a5.get('status') == 'rejected' and 'open request' in a5['message'], (a4, a5))
    # ---- decline and cancel
    q('d1', 'bob', 'loan_offer', requestId='rq-site-l4', amount=50, interestPct=5, days=2); ans('d1')
    q('d2', 'bob', 'loan_offer', requestId='rq-site-l4', amount=60, interestPct=5, days=2); chk('a second open offer to the same request is refused', ans('d2').get('status') == 'rejected', ans('d2'))
    q('d3', 'cat', 'loan_decline', offerId='of-site-d1'); chk('decline', ans('d3').get('status') == 'done', ans('d3'))
    q('d4', 'bob', 'loan_offer', requestId='rq-site-l4', amount=55, interestPct=5, days=2); ans('d4')
    q('d5', 'bob', 'loan_cancel', targetId='of-site-d4'); chk('lender cancels own offer', ans('d5').get('status') == 'done', ans('d5'))
    q('d6', 'bob', 'loan_offer', requestId='rq-site-l4', amount=56, interestPct=5, days=2); ans('d6')
    q('d7', 'cat', 'loan_cancel', targetId='rq-site-l4'); chk('borrower cancels the request', ans('d7').get('status') == 'done', ans('d7'))
    q('d8', 'cat', 'loan_accept', offerId='of-site-d6'); chk('offers on a cancelled request cannot be accepted', ans('d8').get('status') == 'rejected', ans('d8'))
    # ---- the market rides on the push
    q('m1', 'cat', 'loan_request', amount=70, interestPct=5, days=2); ans('m1'); time.sleep(5)
    chk('open requests are in the pushed market', any(x['id'] == 'rq-site-m1' and x['borrower'] == 'cat' and x['amount'] == 70 for x in S['users'][-1].get('market', [])), S['users'][-1].get('market') if S['users'] else None)
    chk('p2p limits travel in the public settings', S['users'][-1]['settings'].get('p2p', {}).get('MaxDays') == 30, S['users'][-1]['settings'].get('p2p'))
    # ---- default: a loan that is already due
    json.dump({'MinDays': 0}, open(os.path.join(d, 'economy', 'p2p_settings.json'), 'w')); time.sleep(1.5)
    q('f1', 'cat', 'loan_cancel', targetId='rq-site-m1'); ans('f1')
    q('f2', 'bob', 'loan_offer', toLogin='cat', amount=40, interestPct=0, days=0); ans('f2')
    q('f3', 'cat', 'loan_accept', offerId='of-site-f2'); chk('a 0 day loan starts when MinDays allows it', ans('f3').get('status') == 'done', ans('f3'))
    time.sleep(2)
    c = get('/api/economy/me?login=cat')
    chk('overdue loan is defaulted', c['p2p']['loans']['asBorrower'][0]['status'] == 'defaulted', c['p2p']['loans'])
    q('f4', 'cat', 'loan_request', amount=50, interestPct=0, days=2); chk('a defaulter cannot ask again', ans('f4').get('status') == 'rejected' and 'overdue' in ans('f4')['message'], ans('f4'))
    q('f5', 'cat', 'loan_take', amount=100); chk('nor take a house loan', ans('f5').get('status') == 'rejected' and 'overdue' in ans('f5')['message'], ans('f5'))
    q('f6', 'cat', 'loan_repay', loanId='ln-of-site-f2', amount=0); chk('a late repay clears it', ans('f6').get('status') == 'done', ans('f6'))
    q('f7', 'cat', 'loan_request', amount=50, interestPct=0, days=2); chk('and they can ask again', ans('f7').get('status') == 'done', ans('f7'))
    # ---- ledger on both sides, friendly labels
    zl = get('/api/economy/me?login=bob')
    chk('lender ledger rows exist with friendly labels', any(x['label'].startswith('Loan to') for x in zl['activity']) and any(x['label'].startswith('Repayment from') for x in zl['activity']), [x['label'] for x in zl['activity']])
    # ---- the checkbook: newest first, every balance follows from the next row
    for who in ('zed', 'bob', 'cat'):
        act = get('/api/economy/me?login=' + who)['activity']; cur = bal(who)
        ok = len(act) > 0 and act[0]['balance'] == cur and all(act[i]['balance'] - act[i]['delta'] == act[i + 1]['balance'] for i in range(len(act) - 1)) and all(act[i]['at'] >= act[i + 1]['at'] for i in range(len(act) - 1))
        chk('activity runs unbroken for ' + who, ok, [(x['label'], x['delta'], x['balance']) for x in act])
    chk('activityTotal present', get('/api/economy/me?login=zed')['activityTotal'] >= 4)
    # ---- replay of a request id never repeats it
    n0 = bal('bob'); S['reqs']['r4']['status'] = 'pending'; time.sleep(3)
    chk('a replayed request id is not applied again', bal('bob') == n0, (n0, bal('bob')))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS p2p'); sys.exit(1 if fails else 0)
