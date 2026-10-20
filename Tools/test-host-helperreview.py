"""Helper review log browser: GET /api/helper/review (merge of trigger + after rows, filters, notes), POST a note, the page, local-only. Usage: python Tools/test-host-helperreview.py [dll]"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8995; B = 'http://127.0.0.1:%d' % PORT
d = tempfile.mkdtemp(prefix='pghr_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
os.makedirs(os.path.join(d, 'helper'))
rows = [{'type': 'trigger', 'id': 'a1', 'at': 1792000000, 'user': 'ana', 'text': 'what commands are there?', 'kind': 'answered', 'intent': 'site_commands', 'reply': '@Ana Every chat command: https://innocentpenguin.com/help#commands', 'reason': '', 'window': [{'at': 1791999990, 'u': 'bob', 't': 'hi'}, {'at': 1792000000, 'u': 'ana', 't': 'what commands are there?'}]},
        {'type': 'after', 'id': 'a1', 'at': 1792000005, 'u': 'bob', 't': 'thanks bot'},
        {'type': 'trigger', 'id': 'm1', 'at': 1792000100, 'user': 'cy', 'text': 'how do i get points refunded?', 'kind': 'missed', 'intent': '', 'reply': '', 'reason': 'no pattern or AI intent matched', 'window': [{'at': 1792000100, 'u': 'cy', 't': 'how do i get points refunded?'}]}]
open(os.path.join(d, 'helper', 'review.jsonl'), 'w', encoding='utf-8').write('\n'.join(json.dumps(r) for r in rows) + '\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8996'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def api(path, body=None):
    rq = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(rq, timeout=15))
res = []
def chk(n, ok): res.append((n, bool(ok)))
try:
    for _ in range(60):
        try: api('/api/status'); break
        except Exception: time.sleep(0.5)
    r = api('/api/helper/review')
    chk('newest first, counts, private flag', r['ok'] and r['private'] and r['total'] == 2 and r['answered'] == 1 and r['missed'] == 1 and r['entries'][0]['id'] == 'm1')
    a = [e for e in r['entries'] if e['id'] == 'a1'][0]
    chk('the after lines are merged into their trigger', len(a['after']) == 1 and a['after'][0]['t'] == 'thanks bot' and len(a['window']) == 2)
    chk('kind filter', [e['id'] for e in api('/api/helper/review?kind=missed')['entries']] == ['m1'])
    chk('search filter', [e['id'] for e in api('/api/helper/review?q=refunded')['entries']] == ['m1'])
    n = api('/api/helper/review', {'id': 'm1', 'note': 'should have pointed at /faq'})
    chk('a note is saved and comes back', n['ok'] and api('/api/helper/review?kind=missed')['entries'][0]['note'] == 'should have pointed at /faq' and os.path.exists(os.path.join(d, 'helper', 'review_notes.json')))
    html = urllib.request.urlopen(B + '/helper-review', timeout=15).read().decode()
    chk('the page is served', 'Helper review' in html and '/api/helper/review' in html)
finally:
    host.kill(); time.sleep(0.5); shutil.rmtree(d, True)
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
