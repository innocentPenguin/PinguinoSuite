"""Sim test for the one-time cheer back-pay (40% of the current cheer curve). Usage: python Tools/test-host-backpay.py [dll]"""
import os, sys, subprocess, tempfile, json
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'boards'))
ev = [{"at": 1771467408, "type": "cheer", "user": "alice", "amount": 100, "to": ""},
      {"at": 1771472218, "type": "cheer", "user": "alice", "amount": 500, "to": ""},
      {"at": 1772508541, "type": "cheer", "user": "bob", "amount": 1000, "to": ""},
      {"at": 1772508999, "type": "gift", "user": "bob", "amount": 5, "to": ""}]
json.dump(ev, open(os.path.join(d, 'boards', 'events.json'), 'w'))
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], input="backpay-dry\nbackpay-apply\nbackpay-apply\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
rs = [json.loads(l.split('[backpay] ', 1)[1]) for l in p.stdout.splitlines() if l.startswith('[backpay] {')]
assert len(rs) == 3, p.stdout[-2000:]
dry, ap, again = rs
assert not dry['applied'] and dry['people'] == 2 and dry['bits'] == 1600 and dry['points'] == 400 + 2200 + 6000, dry
assert ap['applied'] and ap['points'] == 8600 and ap['people'] == 2, ap
assert again['people'] == 0 and again['points'] == 0 and again['already_paid_events'] == 3, again
pts = json.load(open(os.path.join(d, 'economy', 'points.json'), encoding='utf-8-sig'))
assert pts['adjust']['alice'] == 2600 and pts['adjust']['bob'] == 6000, pts['adjust']
print('PASS backpay')
