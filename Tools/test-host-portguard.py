"""Port guard: --sim without OverlayPort takes a free port (never 8770); non-sim with a foreign --data and no OverlayPort refuses to start."""
import subprocess, sys, tempfile, os, re
dll = sys.argv[1] if len(sys.argv) > 1 else r'D:\PinguinoSuite\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll'
suite = r'D:\PinguinoSuite'
def run(args, inp, to=120):
    d = tempfile.mkdtemp(prefix='pgport')
    return subprocess.run(['dotnet', dll] + args + ['--no-sync', '--data', d, '--suite', suite], input=inp, capture_output=True, text=True, encoding='utf-8', timeout=to)
ok = True
def chk(n, c):
    global ok
    print(('PASS ' if c else 'FAIL ') + n); ok = ok and c
p = run(['--sim'], 'quit\n')
m = re.search(r'free port (\d+)', p.stdout)
chk('sim picks a free port', bool(m) and m.group(1) != '8770')
p = run([], 'quit\n', 60)
chk('non-sim foreign data refuses', p.returncode == 3 and 'refusing to start' in p.stdout)
print('ALL PASS' if ok else 'FAILED'); sys.exit(0 if ok else 1)
