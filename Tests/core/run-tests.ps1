# Compiles PinguinoBotCore.cs with a stub Streamer.bot and runs the checks in harness.cs.
# The tests use a throwaway data folder (PINGUINO_DATA_DIR), never %AppData%\BVQ.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force "$here\build" | Out-Null
(Get-Content -Raw -Encoding UTF8 "$here\..\..\PinguinoB0t\PinguinoBotCore.cs") -replace '(?m)^public class CPHInline\s*$', 'public class CPHInline : CPHStubBase' |
  Set-Content -Encoding UTF8 "$here\build\core.cs"
Push-Location $here
dotnet run -c Release --nologo 2>&1 | Where-Object { $_ -notmatch '^INFO' }
Pop-Location
