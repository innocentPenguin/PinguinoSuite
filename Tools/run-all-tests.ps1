# Run every test suite, serially and read-only. Owner: 999.
# Uses Suite\.venv python (system Python lacks numpy/requests/cryptography/windows -> false failures).
# Never touches the live ports (8770/8766/8771/8765/8772/7777). Host tests use fixed 88xx/89xx ports:
# a Host test is SKIPPED (not failed) if any 88xx/89xx port named in its source is already listening.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File Tools\run-all-tests.ps1 [-NoHost] [-TimeoutSec 240]
param([switch]$NoHost, [int]$TimeoutSec = 240)
$ErrorActionPreference = 'Continue'
$suite = Split-Path -Parent $PSScriptRoot
$py = Join-Path $suite 'Suite\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Host "Suite\.venv python missing: $py"; exit 2 }
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONIOENCODING = 'utf-8'
$live = 8770, 8766, 8771, 8765, 8772, 7777
$results = New-Object System.Collections.ArrayList

function Add-Result($name, $status, $note) {
    [void]$results.Add([pscustomobject]@{ Suite = $name; Status = $status; Note = $note })
    Write-Host ("{0,-6} {1}  {2}" -f $status, $name, $note)
}
function Run-Proc($name, $exe, $argList, $workDir) {
    $out = Join-Path $env:TEMP ("rat_" + [guid]::NewGuid().ToString('N') + '.txt')
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $workDir -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError ($out + '.err')
    $null = $p.Handle
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { try { $p.Kill() } catch {}; Add-Result $name 'FAIL' "timeout ${TimeoutSec}s"; return }
    $p.WaitForExit()
    $text = (Get-Content $out -ErrorAction SilentlyContinue) + (Get-Content ($out + '.err') -ErrorAction SilentlyContinue)
    $tail = ($text | Select-Object -Last 2) -join ' | '
    Remove-Item $out, ($out + '.err') -ErrorAction SilentlyContinue
    if ($p.ExitCode -eq 0) { Add-Result $name 'PASS' $tail } else { Add-Result $name 'FAIL' ("exit " + $p.ExitCode + ": " + $tail) }
}
function Listening-Ports { (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue).LocalPort }

# 1. C# suites (own throwaway data dirs, stub CPHInline)
foreach ($t in 'core', 'bots', 'chat', 'helper') {
    $dir = Join-Path $suite "Tests\$t"
    if (Test-Path $dir) { Run-Proc "Tests/$t" 'dotnet' 'run -c Release --nologo' $dir }
}
# 2. History (node)
$hist = Join-Path $suite 'Tests\history'
if ((Test-Path (Join-Path $hist 'test-summaries.mjs')) -and (Get-Command node -ErrorAction SilentlyContinue)) {
    Run-Proc 'Tests/history' 'node' 'test-summaries.mjs' $hist
}
# 3. Python modules via the venv, from the repo root
foreach ($m in 'spotify', 'voice', 'listen') {
    Run-Proc "module/$m" $py "-m unittest discover -s Suite/modules/$m/tests" $suite
}
Run-Proc 'Suite/tests' $py '-m unittest discover -s tests' (Join-Path $suite 'Suite')
# multi is pytest style (conftest.py); run from its own folder so `import windows` resolves
Run-Proc 'module/multi' $py '-m pytest tests/test_core.py -q -p no:cacheprovider' (Join-Path $suite 'Suite\modules\multi')

# 4. Host sim tests, one at a time
if (-not $NoHost) {
    $dll = Join-Path $suite 'PinguinoHost\bin\Release\net8.0\PinguinoHost.dll'
    if (-not (Test-Path $dll)) { Add-Result 'Host tests' 'SKIP' 'PinguinoHost.dll not built (only 00 builds)' }
    else {
        foreach ($f in Get-ChildItem (Join-Path $suite 'Tools') -Filter 'test-host-*.py' | Sort-Object Name) {
            $src = Get-Content $f.FullName -Raw
            $ports = [regex]::Matches($src, '\b(8[89]\d\d)\b') | ForEach-Object { [int]$_.Value } | Sort-Object -Unique
            if ($ports | Where-Object { $live -contains $_ }) { Add-Result $f.Name 'SKIP' 'names a live port'; continue }
            $busy = @($ports | Where-Object { (Listening-Ports) -contains $_ })
            if ($busy.Count) { Add-Result $f.Name 'SKIP' ("ports busy: " + ($busy -join ',') + " (another test is running)"); continue }
            Run-Proc $f.Name $py ('"' + $f.FullName + '"') $suite
        }
        if (Test-Path (Join-Path $suite 'Tools\test-namehistory.py')) { Run-Proc 'test-namehistory.py' $py ('"' + (Join-Path $suite 'Tools\test-namehistory.py') + '"') $suite }
    }
}

$fail = @($results | Where-Object Status -eq 'FAIL'); $skip = @($results | Where-Object Status -eq 'SKIP')
Write-Host ""; Write-Host ("TOTAL {0}: {1} pass, {2} FAIL, {3} skip" -f $results.Count, ($results.Count - $fail.Count - $skip.Count), $fail.Count, $skip.Count)
if ($fail.Count) { $fail | ForEach-Object { Write-Host ("  FAIL " + $_.Suite) }; exit 1 }
exit 0
