"""Sim test for /api/customs/sim-say (SimSay.Say via the simsay stdin line). Usage: python Tools/test-host-simsay.py [dll]"""
import os, sys, subprocess, tempfile, json
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
d = tempfile.mkdtemp()
cases = [
 {"event":"match_start","speak":True,"match":{"id":13,"orange":["a","b"],"blue":["c","d"],"mmr":{"a":1000,"b":1200,"c":900,"d":1100}}},
 {"event":"result","speak":True,"winner":"blue","match":{"id":13},"mode":"points"},
 {"event":"result","speak":True,"winner":"orange","match":{"id":14},"mode":"koth"},
 {"event":"queue_open","speak":True},{"event":"queue_close","speak":True},{"event":"queue_clear","speak":True},
 {"event":"join","speak":True,"player":"zed","pos":3},{"event":"leave","speak":True,"player":"zed"},{"event":"kick","speak":True,"player":"zed"},
 {"event":"koth_stays","speak":True,"winner":"blue"},{"event":"koth_wait","speak":True,"winner":"orange","need":4,"have":2},
 {"event":"queue_open"},{"event":"bogus","speak":True},
]
inp = "".join("simsay " + json.dumps(c, ensure_ascii=False) + "\n" for c in cases) + "quit\n"
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], input=inp, capture_output=True, text=True, encoding='utf-8', timeout=90)
out = p.stdout
def has(t):
    assert t in out, "missing: " + t + "\n" + out[-2500:]
has('[say] #13 🔷 Blue [avg 1000]: c(900), d(1100)')
has('[say] 🔶 Orange [avg 1100]: a(1000), b(1200) | Diff: 100')
has('[say] 🔷 Blue wins match #13! (+3 pts winners, +1 pts losers)')
has('[say] 🔶 Orange wins match #14! (+1 win on the King of the Hill leaderboard)')
has('[say] The queue is now OPEN! Type !join to enter.')
has('[say] The queue is now CLOSED. No new joins accepted.')
has('[say] The queue has been cleared and closed.')
has('[say] @zed You joined the queue at position #3!')
has('[say] @zed You left the queue.')
has('[say] zed has been removed from the queue.')
has('[say] 🔷 Blue stays on! Rotating in new challengers...')
has("[say] KOTH: 🔶 Orange stays on, but there aren't enough challengers (need 4, have 2). The winners wait at the front of the queue.")
assert out.count('"spoke":false') == 1 and 'unknown event' in out, out[-1500:]
print('PASS simsay')
