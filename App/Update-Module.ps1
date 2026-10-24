# Update one module without touching the app or other modules.
#
#   Update-Module.bat <id> [--no-build]        stop it, rebuild it (if its manifest has a "build" command), start it, wait until it answers
#   Update-Module.ps1 <id> -StopOnly           stop it and HOLD it (the core will not relaunch it) so files can be replaced by hand
#   Update-Module.ps1 <id> -Start              release the hold, start it, wait until it answers
#   Update-Module.ps1 <id> -InstallFrom <dir>  stop + hold, copy the prebuilt contents of <dir> (e.g. ...\bin\Release\net8.0) into the module's
#                                              own bin folder with retries and a lock check on each file, verify size/hash/timestamp of every copied
#                                              file, then release + start. On any failure the hold is released (the module stays stopped, nothing relaunches
#                                              a half-copied folder) and the message says what to do.
#
# Talks to the core through the control folder (Data\runtime\control), so no API token is needed. Nothing here prompts, beeps or needs a visible console.
# HOLD needs a core built with the hold feature (control files hold-<id> / release-<id>; the core confirms in Data\runtime\holds.json). With an OLDER core
# the hold is not confirmed: the script warns and falls back to "stop, then copy at once" - a module killed from outside (not through the core) can be
# relaunched by an old core within ~2 s, which is exactly the race the hold removes.
param([Parameter(Mandatory)][string]$Id, [switch]$NoBuild, [switch]$StopOnly, [switch]$Start, [string]$InstallFrom, [int]$HoldMinutes = 10)
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
$holdsFile = Join-Path $dataDir 'holds.json'
$health = $m.url + $(if ($m.health) { $m.health } else { '/' })
function Up { try { (Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2).StatusCode -lt 400 } catch { $false } }
function Wait-For([bool]$want, [int]$secs) { for ($i = 0; $i -lt $secs; $i++) { if ((Up) -eq $want) { return $true }; Start-Sleep 1 }; $false }
function Send($action, $text = '') { New-Item -ItemType Directory -Force $ctl | Out-Null; Set-Content -Path (Join-Path $ctl "$action-$Id") -Value $text -NoNewline }
# True when the core wrote a hold for this module that has not ended yet (it consumes hold-<id> within ~1 s)
function Held { try { $h = (Get-Content $holdsFile -Raw | ConvertFrom-Json).holds.$Id; [bool]($h -and $h -gt [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) } catch { $false } }
function Hold {
  Send 'hold' ([string]([Math]::Max(1, [Math]::Min(30, $HoldMinutes))))
  for ($i = 0; $i -lt 6; $i++) { Start-Sleep -Milliseconds 700; if (Held) { Write-Host "[update] $Id : held for $HoldMinutes min (the core will not relaunch it)"; return $true } }
  Write-Host "[update] WARNING: the core did not confirm the hold (older core, or the core is not running). Falling back to stop + immediate copy; an old core may relaunch a module killed from outside within ~2 s."
  $false
}
function Release { Send 'release'; Start-Sleep -Milliseconds 800 }
function Stop-Module {
  if (Up) {
    Send 'stop'
    if (-not (Wait-For $false 30)) { Write-Host "[update] FAILED: $Id still answers after 30s (is the core running? it consumes $ctl)"; Release; exit 1 }
    Start-Sleep 2  # let the OS release file locks (dll)
  }
}
function Start-Module {
  Write-Host "[update] $Id : starting"
  Send 'start'   # a start also ends any hold in the core
  if (-not (Wait-For $true 60)) { Write-Host "[update] FAILED: $Id did not answer on $health within 60s. See Suite\logs\$Id.log"; exit 1 }
  Write-Host "[update] OK: $Id is up. App and other modules untouched."
}

if ($Start) { Release; Start-Module; exit 0 }

if ($StopOnly) {
  $held = Hold
  Write-Host "[update] $Id : stopping"
  Stop-Module
  Write-Host "[update] OK: $Id is stopped$(if ($held) { " and held for $HoldMinutes min" } else { ' (NOT held: old core)' }). Replace its files, then run: Update-Module.ps1 $Id -Start"
  exit 0
}

if ($InstallFrom) {
  $src = (Resolve-Path -LiteralPath $InstallFrom -ErrorAction SilentlyContinue).Path
  if (-not $src -or -not (Test-Path -LiteralPath $src -PathType Container)) { Write-Host "[update] FAILED: -InstallFrom folder not found: $InstallFrom"; exit 1 }
  $files = @(Get-ChildItem -LiteralPath $src -Recurse -File)
  if ($files.Count -eq 0) { Write-Host "[update] FAILED: $src is empty"; exit 1 }
  # destination: the folder of the file the module's command runs (Host: bin\Release\net8.0), else the module folder itself
  $modDir = [IO.Path]::GetFullPath((Join-Path $suite $m.cwd))
  $dest = $modDir
  foreach ($c in @($m.cmd)) { if ($c -match '[\\/]' -and $c -notmatch '^\{') { $dest = Split-Path ([IO.Path]::GetFullPath((Join-Path $modDir $c))) -Parent; break } }
  $dest = [IO.Path]::GetFullPath($dest)
  if (-not $dest.StartsWith($modDir, [StringComparison]::OrdinalIgnoreCase)) { Write-Host "[update] FAILED: destination $dest is outside the module folder $modDir"; exit 1 }
  Write-Host "[update] $Id : installing $($files.Count) files from $src into $dest"
  $null = Hold
  Stop-Module
  try {
    New-Item -ItemType Directory -Force $dest | Out-Null
    # lock check: every file that already exists must be openable for writing, else something (the old process, an antivirus scan) still holds it
    foreach ($f in $files) {
      $t = Join-Path $dest $f.FullName.Substring($src.Length).TrimStart('\', '/')
      if (-not (Test-Path -LiteralPath $t)) { continue }
      $ok = $false
      for ($i = 0; $i -lt 20 -and -not $ok; $i++) {
        try { $fs = [IO.File]::Open($t, 'Open', 'ReadWrite', 'None'); $fs.Close(); $ok = $true } catch { Start-Sleep -Milliseconds 750 }
      }
      if (-not $ok) { throw "locked: $t is still in use by another process (is the old $Id still running?)" }
    }
    foreach ($f in $files) {
      $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/')
      $t = Join-Path $dest $rel
      New-Item -ItemType Directory -Force (Split-Path $t -Parent) | Out-Null
      $done = $false
      for ($i = 0; $i -lt 5 -and -not $done; $i++) {
        try { Copy-Item -LiteralPath $f.FullName -Destination $t -Force; $done = $true } catch { Start-Sleep -Seconds 1 }
      }
      if (-not $done) { throw "could not copy $rel" }
    }
    # verify what is on disk now: size, SHA-256 and last-write time of every file
    foreach ($f in $files) {
      $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/')
      $t = Get-Item -LiteralPath (Join-Path $dest $rel)
      if ($t.Length -ne $f.Length) { throw "verify failed (size) for $rel" }
      if ($t.LastWriteTimeUtc -ne $f.LastWriteTimeUtc) { throw "verify failed (timestamp) for $rel" }
      if ((Get-FileHash -LiteralPath $t.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash) { throw "verify failed (hash) for $rel" }
    }
    Write-Host "[update] $Id : $($files.Count) files copied and verified (size, hash, timestamp)"
  } catch {
    Write-Host "[update] INSTALL FAILED: $($_.Exception.Message)"
    Release
    Write-Host "[update] $Id is left STOPPED and the hold is released (nothing will relaunch a half-copied folder). Fix the cause and rerun -InstallFrom, or run -Start to launch what is there."
    exit 1
  }
  Release
  Start-Module
  exit 0
}

Write-Host "[update] $Id : stopping"
$null = Hold
Stop-Module
if ($m.build -and -not $NoBuild) {
  Write-Host "[update] $Id : building ($($m.build -join ' '))"
  Push-Location (Join-Path $suite $m.cwd)
  try { & $m.build[0] $m.build[1..($m.build.Count - 1)]; $rc = $LASTEXITCODE } finally { Pop-Location }
  if ($rc -ne 0) { Release; Write-Host "[update] BUILD FAILED - $Id left stopped (previous build, if any, still on disk). Fix and rerun."; exit 1 }
}
Start-Module
