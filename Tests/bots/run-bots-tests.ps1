# Routing + fallback + naming checks for the three bots (Shared\PinguinoRouter.cs + Shared\PinguinoBots.cs.txt), with a stub Streamer.bot. No network, no cost.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& node "$here\..\..\Shared\sync-shared.mjs" --check
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: a copy of the shared code is out of date (run: node Shared\sync-shared.mjs)"; }
New-Item -ItemType Directory -Force "$here\build" | Out-Null
(Get-Content -Raw -Encoding UTF8 "$here\..\..\Shared\PinguinoRouter.cs") -replace '(?m)^public class CPHInline\s*$', 'public class CPHInline : CPHStubBase' |
  Set-Content -Encoding UTF8 "$here\build\router.cs"
Push-Location $here
dotnet run -c Release --nologo 2>&1
Pop-Location
