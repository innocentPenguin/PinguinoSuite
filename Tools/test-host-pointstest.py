"""Sim test for the points rework (calculator, 5-minute watch, tier change, extension bits, follow once, raid threshold, idempotency, hot reload). Usage: python Tools/test-host-pointstest.py [dll]"""
import os, sys, subprocess, tempfile
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', tempfile.mkdtemp(), '--suite', suite], input="pointstest\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
assert '[pointstest] ALL PASS' in p.stdout and 'FAIL' not in p.stdout, p.stdout[-2500:]
print('PASS pointstest')
