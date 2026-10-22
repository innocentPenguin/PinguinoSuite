"""Sim test for the recap test: text for the last stream ends with the best clip link; no clip -> no link. Usage: python Tools/test-host-recap.py [dll]"""
import os, sys, subprocess, tempfile, json
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
d = tempfile.mkdtemp()
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], input="recap-test\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
r = {l.split(']')[0][1:]: json.loads(l.split('] ', 1)[1]) for l in p.stdout.splitlines() if l.startswith('[recap') and '{' in l}
assert 'recap' in r and 'recap2' in r, p.stdout[-2000:]
a, b = r['recap'], r['recap2']
assert a['ok'] and a['text'].startswith('Thanks for tuning in!') and a['text'].endswith('https://clips.twitch.tv/x') and a['clip']['views'] == 9, a
assert b['ok'] and b['clip'] is None and 'clips.twitch' not in b['text'], b
assert a['window']['start'] <= a['window']['end']
print('PASS recap')
