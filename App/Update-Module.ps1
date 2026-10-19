# Update one module without touching the app or other modules: stop it, rebuild it (if its manifest has a
# "build" command), start it again and wait until it answers. Usage: Update-Module.bat <id> [--no-build]
# Talks to the core through the control folder (Data\runtime\control), so no API token is needed.
param([Parameter(Mandatory)][string]$Id, [switch]$NoBuild)
$ErrorActionPreference = 'Stop'
$suite = Join-Path $PSScriptRoot '..\Suite'
# PS 5.1 ConvertFrom-Json returns a JSON array as ONE object; ForEach-Object unrolls it into separate specs
$specs = @(Get-Content (Join-Path $suite 'modules.json') -Raw | ConvertFrom-Json | ForEach-Object { $_ })
Get-ChildItem (Join-Path $suite 'modules') -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $mf = Join-Path $_.FullName 'module.json'
  if (Test-Path $mf) { $j = Get-Content $mf -Raw | ConvertFrom-Json; if (-not ($specs | Where-Object id -eq $j.id)) { if (-not $j.cwd) { $j | Add-Member cwd "modules/$($_.Name)" }; $specs += $j } }
}
$m = $specs | Where-Object id -eq $Id
if (-not $m) { Write-Host "[update] unknown module '$Id'. Known: $(($specs.id) -join ', ')"; exit 1 }
$dataDir = if ($env:PINGUINO_DATA_DIR) { $env:PINGUINO_DATA_DIR } else { Join-Path $PSScriptRoot '..\Data\runtime' }
$ctl = Join-Path $dataDir 'control'
$health = $m.url + $(if ($m.health) { $m.health } else { '/' })
function Up { try { (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2).StatusCode -lt 400 } catch { $false } }
function Wait-For([bool]$want, [int]$secs) { for ($i = 0; $i -lt $secs; $i++) { if ((Up) -eq $want) { return $true }; Start-Sleep 1 }; $false }
function Send($action) { New-Item -ItemType Directory -Force $ctl | Out-Null; New-Item -ItemType File -Force (Join-Path $ctl "$action-$Id") | Out-Null }

Write-Host "[update] $Id : stopping"
if (Up) {
  Send 'stop'
  if (-not (Wait-For $false 30)) { Write-Host "[update] FAILED: $Id still answers after 30s (is the core running? it consumes $ctl)"; exit 1 }
  Start-Sleep 2  # let the OS release file locks (dll)
}
if ($m.build -and -not $NoBuild) {
  Write-Host "[update] $Id : building ($($m.build -join ' '))"
  Push-Location (Join-Path $suite $m.cwd)
  try { & $m.build[0] $m.build[1..($m.build.Count - 1)]; $rc = $LASTEXITCODE } finally { Pop-Location }
  if ($rc -ne 0) { Write-Host "[update] BUILD FAILED - $Id left stopped (previous build, if any, still on disk). Fix and rerun."; exit 1 }
}
Write-Host "[update] $Id : starting"
Send 'start'
if (-not (Wait-For $true 60)) { Write-Host "[update] FAILED: $Id did not answer on $health within 60s. See Suite\logs\$Id.log"; exit 1 }
Write-Host "[update] OK: $Id is up again. App and other modules untouched."
