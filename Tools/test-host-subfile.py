"""SubsImport.WriteAtomic/ReadShared: a concurrent read/write loop never throws and never shows a half file. Usage: python Tools/test-host-subfile.py [dll]"""
import os, subprocess, sys, tempfile, time
here = os.path.dirname(os.path.abspath(__file__)); suite = os.path.dirname(here)
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
d = tempfile.mkdtemp(prefix='pgsf_'); outf = os.path.join(d, 'out.txt')
env = {k: v for k, v in os.environ.items() if not k.startswith('PINGUINO_')}; env.update({'PINGUINO_COMPAT_WS_PORT': '8996'})
host = subprocess.Popen(['dotnet', dll, '--sim', '--no-sync', '--data', d, '--suite', suite], env=env, stdin=subprocess.PIPE, stdout=open(outf, 'wb'), stderr=subprocess.STDOUT)
try:
    time.sleep(6); host.stdin.write(b'subfiletest\n'); host.stdin.flush()
    for _ in range(120):
        time.sleep(0.5)
        t = open(outf, 'rb').read().decode('utf-8', 'replace')
        if '[subfiletest]' in t: break
finally:
    try: host.stdin.write(b'quit\n'); host.stdin.flush(); host.wait(timeout=10)
    except Exception: host.kill()
lines = [l for l in t.splitlines() if l.startswith(('PASS', 'FAIL')) or '[subfiletest]' in l]
print('\n'.join(lines))
ok = '[subfiletest] ALL PASS' in t
print('PASS test-host-subfile' if ok else 'FAIL test-host-subfile'); sys.exit(0 if ok else 1)
