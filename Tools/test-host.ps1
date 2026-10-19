# Sim smoke test for PinguinoHost: pipes chat lines, expects bot replies and a routing.log.
$dll = Join-Path $PSScriptRoot "..\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll"
$d = Join-Path $env:TEMP ("pghost_" + [guid]::NewGuid().ToString("N")); New-Item -ItemType Directory $d | Out-Null
$out = "ivan: !queue`n*mod: !help`nviewer: hello PinguinoB0t" | dotnet $dll --sim --no-sync --data $d 2>&1 | Out-String
$ok = ($out -match "\[say\] Queue is") -and ($out -match "\[say\] @viewer") -and (Test-Path "$d\routing.log")
if ($ok) { "HOST SIM: PASS" } else { $out; "HOST SIM: FAIL"; exit 1 }
