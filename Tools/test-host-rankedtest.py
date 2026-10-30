"""Sim test for the ranked activity logic (marks, undo, limit, reset, day / week boundaries, week answer). Usage: python Tools/test-host-rankedtest.py [dll]"""
import os, sys, subprocess, tempfile
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', tempfile.mkdtemp(), '--suite', suite], input="rankedtest\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
assert '[rankedtest] ALL PASS' in p.stdout and 'FAIL' not in p.stdout, p.stdout[-3000:]
print('PASS rankedtest')
