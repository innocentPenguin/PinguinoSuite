"""Host /setup page: script parses (node --check) and the chat bot lists text settings. Usage: python Tools/test-host-setuppage.py [dll]"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
PORT = 8905; d = tempfile.mkdtemp(prefix='pgpage_')
json.dump({'Channel': 'trial', 'OverlayPort': PORT}, open(os.path.join(d, 'host_secrets.json'), 'w'))
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env['PINGUINO_COMPAT_WS_PORT'] = '8906'
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d], env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
res = []
try:
    for _ in range(60):
        try: html = urllib.request.urlopen('http://127.0.0.1:%d/setup' % PORT, timeout=3).read().decode('utf-8'); break
        except Exception: time.sleep(0.5)
    js = '\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)); f = os.path.join(d, 'page.js'); open(f, 'w', encoding='utf-8').write(js)
    r = subprocess.run(['node', '--check', f], capture_output=True, text=True)
    res.append(('page script parses', r.returncode == 0))
    res.append(("text input rendered for 'text' settings", "s.type=='text'" in js))
    b = json.load(urllib.request.urlopen('http://127.0.0.1:%d/api/bots' % PORT, timeout=5))['bots'][1]['settings']
    res.append(('chat bot lists text settings', any(s['type'] == 'text' and s['key'] == 'CountdownLine' for s in b)))
    r = urllib.request.Request('http://127.0.0.1:%d/api/bots' % PORT, data=json.dumps({'id': 'chat', 'settings': {'CountdownLine': "it's {left}"}}).encode(), headers={'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:%d' % PORT})
    res.append(('saving a text setting works', json.load(urllib.request.urlopen(r, timeout=5))['ok'] and json.load(open(os.path.join(d, 'chat_settings.json')))['CountdownLine'] == "it's {left}"))
finally:
    host.kill()
for n, ok in res: print('PASS' if ok else 'FAIL', n)
sys.exit(0 if all(ok for _, ok in res) else 1)
