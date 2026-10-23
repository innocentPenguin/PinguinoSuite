"""IDEAS #36 unit test: compiles PinguinoHost/HostWelcomeBack.cs alone with Tools/welcomeback-test/Test.cs into a temp dir (deleted afterwards) and runs it.
Usage: python Tools/test-welcomeback.py   -> prints PASS welcomeback or the failures."""
import os, shutil, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__)); proj = os.path.join(here, 'welcomeback-test', 'wb.csproj')
tmp = tempfile.mkdtemp(prefix='pgwb_')
try:
    b = subprocess.run(['dotnet', 'build', proj, '-c', 'Release', '-o', os.path.join(tmp, 'out'), '-v', 'q', '--property:BaseIntermediateOutputPath=' + os.path.join(tmp, 'obj') + os.sep], capture_output=True, text=True)
    if b.returncode: print('FAIL build\n' + b.stdout[-1500:]); sys.exit(1)
    r = subprocess.run(['dotnet', os.path.join(tmp, 'out', 'wb.dll')], capture_output=True, text=True); print(r.stdout.strip()); sys.exit(r.returncode)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
