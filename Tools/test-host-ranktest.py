"""Sim test for the !rank source chain (fake fetcher: all fail, partial fail, stale, backoff, prefix, fuzzy). Usage: python Tools/test-host-ranktest.py [dll]"""
import os, sys, subprocess, tempfile
suite = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(suite, 'PinguinoHost', 'bin', 'Release', 'net8.0', 'PinguinoHost.dll')
p = subprocess.run(['dotnet', dll, '--sim', '--no-sync', '--data', tempfile.mkdtemp(), '--suite', suite], input="ranktest\nquit\n", capture_output=True, text=True, encoding='utf-8', timeout=120)
assert '[ranktest] ALL PASS' in p.stdout and 'FAIL' not in p.stdout, p.stdout[-2500:]
print('PASS ranktest')
