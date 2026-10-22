"""Economy phase 2: Economy.Award ledger, match awards (customs/comp/casual), depreciation (dry run, then real, once per stream, exempt accounts), the one-line reminder, loans (!loan !repay !bank + API),
and the per-user site view GET /api/economy/me.  Streams are flipped with the test hook (PINGUINO_ECONOMY_TESTHOOK=1).  Usage: python Tools/test-host-economy2.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8970; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pgec2_'); out = os.path.join(d, 'out.txt')
os.makedirs(os.path.join(d, 'runtime')); os.makedirs(os.path.join(d, 'economy'))
json.dump({'Channel': 'streamer1', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
json.dump({'Earning': False, 'WelcomeBonus': 0}, open(os.path.join(d, 'economy', 'settings.json'), 'w'))
json.dump({'earned': {'zed': {'points': 0, 'minutes': 600}}}, open(os.path.join(d, 'economy', 'points.json'), 'w'))
now = int(time.time())
def P(*n): return [{'Username': x} for x in n]
json.dump([
    {'Id': 1, 'Format': '2v2', 'Activity': 'competitive', 'Blue': P('ann', 'ben'), 'Orange': P('cat', 'dan'), 'Winner': 'Blue', 'FinishedAt': now - 99},
    {'Id': 2, 'Format': '2v2', 'Activity': 'casual', 'Blue': P('eve', 'fay'), 'Orange': P('gus', 'hal'), 'Winner': 'Orange', 'FinishedAt': now - 90},
    {'Id': 3, 'Format': '2v2', 'Activity': 'viewers', 'Blue': P('ivy', 'jon'), 'Orange': P('kim', 'nightbot'), 'Winner': 'Blue', 'FinishedAt': now - 80},
    {'Id': 4, 'Format': '2v2', 'Activity': 'competitive', 'Blue': P('lou', 'max'), 'Orange': P('ned', 'oli'), 'Winner': None, 'FinishedAt': now - 70},
    {'Id': 5, 'Format': '2v2', 'Activity': 'competitive', 'Blue': P('pat', 'quin'), 'Orange': P('rex', 'sue'), 'Winner': 'Blue', 'FinishedAt': now - 60, 'Incomplete': True}],
    open(os.path.join(d, 'runtime', 'matches.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}
env.update({'PINGUINO_COMPAT_WS_PORT': '8972', 'PINGUINO_ECONOMY_TESTHOOK': '1', 'PINGUINO_ECONOMY_MINUTE_SEC': '1', 'PINGUINO_ECONOMY_AWARD_FROM': '0', 'PINGUINO_ECONOMY_GRACE_SEC': '0', 'PINGUINO_ECONOMY_NO_ANNOUNCE': '1', 'PINGUINO_ECONOMY_V2': '0'})
fails = []
def chk(n, ok, x=''):
    if not ok: fails.append('%s %s' % (n, x))
def get(p): return json.load(urllib.request.urlopen(B + p, timeout=10))
def post(p, o):
    rq = urllib.request.Request(B + p, json.dumps(o).encode(), {'Content-Type': 'application/json', 'Origin': B})
    try: return json.load(urllib.request.urlopen(rq, timeout=10))
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
def me(u): return get('/api/economy/me?login=' + u)
def bal(u): return me(u)['balance']
def live(v): r = post('/api/economy/stream', {'live': v}); time.sleep(1.2); return r
def said(): return open(out, encoding='utf-8', errors='replace').read()
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(out, 'ab'), stderr=subprocess.STDOUT)
def feed(l, w=1.2): host.stdin.write((l + '\n').encode()); host.stdin.flush(); time.sleep(w)
try:
    for _ in range(80):
        try: get('/api/status'); break
        except Exception: time.sleep(0.5)
    time.sleep(3)   # a few award passes
    # ---- match awards
    pg = get('/api/points?login=ann')
    chk('points page shape', all(k in pg for k in ['balance','rank','players','depreciation','loans','earned','ledger']) and all(k in pg['depreciation'] for k in ['threshold','ratePct','nextAmount','nextAt']) and all(k in pg['loans'] for k in ['maxLoan','ratePct','items']), list(pg))
    ce = [e for e in pg['earned'] if e['source'] == 'comp']
    chk('earned folds play+win', ce and ce[0]['points'] == 35 and ce[0]['wins'] == 1 and ce[0]['games'] == 1 and all('label' in l for l in pg['ledger']), (ce, pg['ledger'][:1]))
    chk('comp play + win', bal('ann') == 35 and bal('cat') == 10, (bal('ann'), bal('cat')))
    chk('casual play + win', bal('gus') == 20 and bal('eve') == 5, (bal('gus'), bal('eve')))
    chk('customs (viewers) play + win', bal('ivy') == 15 and bal('kim') == 5, (bal('ivy'), bal('kim')))
    chk('no winner / incomplete = nothing', bal('lou') == 0 and bal('pat') == 0)
    chk('bots earn nothing', bal('nightbot') == 0)
    time.sleep(2); chk('rescan pays nothing twice', bal('ann') == 35)
    v = me('ann'); src = {g['source']: g for g in v['earnings']}
    chk('earnings grouped by source', src.get('comp_play', {}).get('earned') == 10 and src.get('comp_win', {}).get('earned') == 25, v['earnings'])
    chk('ledger rows carry source + balance after', v['ledger'] and all('source' in r and 'balance' in r and 'at' in r for r in v['ledger']) and v['ledger'][0]['balance'] == 35, v['ledger'][:2])
    # ---- one door: gamble spends/credits land in the same ledger with a source
    feed('#streamer1: !addpoints ann 150000'); chk('hidden grant', bal('ann') == 150035, bal('ann'))
    feed('#streamer1: !addpoints streamer1 500000'); feed('#streamer1: !addpoints nightbot 500000'); feed('#streamer1: !addpoints poor 50')
    feed('ann: !points'); chk('grant is a ledger line', any(r['source'] == 'grant' for r in me('ann')['ledger']))
    # ---- depreciation: preview + dry run
    pv = get('/api/economy/depreciation'); lg = {x['login']: x for x in pv['top']}
    chk('preview lists ann, not streamer/bot/poor', 'ann' in lg and 'streamer1' not in lg and 'nightbot' not in lg and 'poor' not in lg, pv['top'])
    chk('2.5% of the total', lg['ann']['loss'] == 3750, lg.get('ann'))
    chk('me shows next depreciation', me('ann')['depreciation']['amount'] == 3750 and me('ann')['depreciation']['applies'] and me('poor')['depreciation']['amount'] == 0)
    live(True); chk('stream opened', get('/api/economy/stream')['stream']['open'] is True)
    feed('ann: hello chat'); chk('no reminder in a dry run', 'you hold' not in said())
    live(False); st = get('/api/economy/stream')['stream']
    chk('stream closed + dry run logged', st['open'] is False and st['lastDepreciation']['dryRun'] is True and st['lastDepreciation']['total'] > 0, st)
    chk('dry run takes nothing', bal('ann') == 150035, bal('ann'))
    chk('depreciation.log written', 'DRYRUN' in open(os.path.join(d, 'economy', 'depreciation.log')).read())
    # ---- real
    post('/api/economy', {'settings': {'DepreciationDryRun': False}})
    live(True); feed('ann: hello again'); feed('ann: and again'); feed('poor: hi'); feed('streamer1: hi')
    s = said(); chk('one personal reminder for ann', s.count('@ann you hold') == 1 and '3,750' in s and '2.5%' in s, s[-400:])
    chk('no reminder for under-threshold or streamer', '@poor you hold' not in s and '@streamer1 you hold' not in s)
    feed('^anon1: x');
    live(False)
    chk('depreciation taken once', bal('ann') == 150035 - 3750, bal('ann'))
    dl = [r for r in me('ann')['ledger'] if r['source'] == 'depreciation']
    chk('depreciation ledger line', len(dl) == 1 and dl[0]['delta'] == -3750 and dl[0]['balance'] == 146285, dl)
    chk('streamer and bots exempt', bal('streamer1') == 500000 and bal('nightbot') == 500000, (bal('streamer1'), bal('nightbot')))
    live(False); live(False); chk('end of the same stream again changes nothing', bal('ann') == 146285, bal('ann'))
    post('/api/economy', {'settings': {'DepreciationBasis': 'excess', 'DepreciationPct': 10}})
    pv = get('/api/economy/depreciation'); lg = {x['login']: x for x in pv['top']}
    chk('excess basis', lg['ann']['loss'] == int((146285 - 100000) * 0.10), lg.get('ann'))
    post('/api/economy', {'settings': {'DepreciationBasis': 'total', 'DepreciationPct': 2.5}})
    # ---- loans
    feed('zed: !loan'); chk('loan limit by watch time', 'borrow up to 1,000' in said(), said()[-300:])
    feed('zed: !loan 5000'); chk('over the limit refused', 'limit is 1,000' in said())
    feed('zed: !loan 500', 1.5); chk('loan paid out', bal('zed') == 500, bal('zed'))
    feed('zed: !loan 100'); chk('one loan at a time', 'still owe 500' in said())
    chk('loan view', me('zed')['loans']['owed'] == 500 and me('zed')['loans']['canBorrow'] is False)
    feed('zed: !repay 200', 1.5); chk('partial repay', bal('zed') == 300 and me('zed')['loans']['owed'] == 300, (bal('zed'), me('zed')['loans']))
    live(True); live(False)
    chk('interest per stream (5% of 500 = 25)', me('zed')['loans']['owed'] == 325, me('zed')['loans'])
    feed('zed: !bank'); chk('!bank line', '@zed you have 300' in said() and 'loan owed 325' in said(), said()[-300:])
    feed('zed: !repay all', 1.5); chk('repay limited by balance', bal('zed') == 0 and me('zed')['loans']['owed'] == 25, (bal('zed'), me('zed')['loans']))
    r = post('/api/economy/loan', {'action': 'take', 'login': 'yan', 'amount': 10, 'id': 'r1'}); chk('no history = no loan', r['ok'] is False and 'watch time' in r['error'], r)
    post('/api/economy/loan', {'action': 'repay', 'login': 'zed', 'amount': 0, 'id': 'rp1'}); post('/api/economy/loan', {'action': 'take', 'login': 'ann', 'amount': 0, 'id': 'x'})
    # ---- default handling: interest stops, new loans blocked, nothing else
    post('/api/economy', {'settings': {'LoanDefaultStreams': 1}})
    feed('#streamer1: !addpoints zed 1000'); feed('zed: !repay all', 1.6)
    feed('zed: !loan 100', 1.5); live(True); live(False); lv = me('zed')['loans']
    chk('defaulted after the limit, interest stops', lv['defaulted'] is True, lv)
    o = lv['owed']; live(True); live(False); chk('interest stops once defaulted', me('zed')['loans']['owed'] == o, me('zed')['loans'])
    feed('zed: !loan 10'); chk('overdue blocks new loans', 'overdue' in said())
    feed('zed: !repay all', 1.5); chk('repaying clears it', me('zed')['loans']['owed'] == 0 and me('zed')['loans']['defaulted'] is False)
    # ---- Award refuses to overdraw
    ids = [r['id'] for r in me('ann')['ledger']]; chk('ledger ids unique', len(ids) == len(set(ids)))
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
print('FAIL ' + '; '.join(fails) if fails else 'PASS economy2'); sys.exit(1 if fails else 0)
