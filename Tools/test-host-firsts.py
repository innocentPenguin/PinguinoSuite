"""Sim test for the First 5 rebuild from chat logs. Usage: python Tools/test-host-firsts.py [dll]"""
import os, sys, subprocess, tempfile, json, datetime as dt
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
d = tempfile.mkdtemp(); ld = os.path.join(d, 'chat_logs', '2026', '03'); os.makedirs(ld)
def L(day, hms, user, msg='hi'): return '[2026-03-%s %s] #innocentpenguin_ %s: %s\n' % (day, hms, user, msg)
b = 'pinguinob0t'
day1 = [L('01', '01:00:00', 'early'), L('01', '01:05:00', b, 'Stream is live! Today we are streaming Rocket League.'),   # chat before the live line does not count
        L('01', '01:05:10', 'ann'), L('01', '01:05:11', 'sery_bot'), L('01', '01:05:12', 'bob'), L('01', '01:05:13', 'ann'), L('01', '01:05:14', 'innocentpenguin_'),
        L('01', '01:05:15', 'cy'), L('01', '01:05:16', 'dee'), L('01', '01:05:17', 'eve'), L('01', '01:05:18', 'fay'),
        L('01', '03:00:00', b, 'Stream offline. Goodnight everybody. Thanks for tuning in!'), L('01', '03:01:00', 'late')]
# second stream next day, a repeated live line (restart) must not start a new stream
day2 = [L('02', '01:00:00', b, 'Stream is live! Today we are streaming Rocket League.'), L('02', '01:00:05', 'bob'), L('02', '01:00:06', 'ann'), L('02', '01:00:07', 'bob'),
        L('02', '01:20:00', b, 'Stream is live! Today we are streaming Rocket League.'), L('02', '01:21:00', 'zed'), L('02', '01:22:00', b, 'Stream offline. Goodnight everybody. Thanks for tuning in!')]
# offline chatter without markers: not a stream
day3 = [L('03', '12:00:00', 'solo', 'x'), L('03', '12:01:00', 'solo', 'y')]
open(os.path.join(ld, '2026-03-01.txt'), 'w', encoding='utf-8').write(''.join(day1))
open(os.path.join(ld, '2026-03-02.txt'), 'w', encoding='utf-8').write(''.join(day2))
open(os.path.join(ld, '2026-03-03.txt'), 'w', encoding='utf-8').write(''.join(day3))
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], input="firsts-dry\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
r = [json.loads(l.split('] ', 1)[1]) for l in p.stdout.splitlines() if l.startswith('[firsts] {')]
assert r, p.stdout[-2000:]
r = r[0]
assert r['streams'] == 2, r
# stream 1: ann, bob, cy, dee, eve (early/late/bot/streamer excluded); stream 2: bob, ann, zed
top = {x['login']: x for x in r['top10']}
assert top['ann']['firsts'] == 1 and top['ann']['score'] == 5 + 3, top['ann']
assert top['bob']['firsts'] == 1 and top['bob']['top3'] == 2 and top['bob']['score'] == 3 + 5, top['bob']
assert top['zed']['top3'] == 1 and top['zed']['top5'] == 1 and top['zed']['score'] == 3, top['zed']
print(list(top), r['streams'], r['people'])
assert top['eve']['top5'] == 1 and 'early' not in top and 'late' not in top and 'sery_bot' not in top and 'fay' not in top, list(top)
assert r['found_by'] == {'marker': 2}, r['found_by']
site = [json.loads(l.split('] ', 1)[1]) for l in p.stdout.splitlines() if l.startswith('[firstssite] {')][0]
al = site['all']; assert al['current'] == 'all' and al['keys'] == ['all'], al
rows = al['boards']['all']['rows']; assert rows[0]['value'] == 8 and {'login', 'name', 'value', 'firsts', 'top3', 'top5'} <= set(rows[0]) and al['boards']['all']['total'] == 6, rows
assert '2026-03-01' in site['day']['keys'] and site['day']['boards']['2026-03-01']['rows'][0]['login'] == 'bob' and site['month']['boards']['2026-03']['total'] == 3, site['day']['keys']
print('PASS firsts')
