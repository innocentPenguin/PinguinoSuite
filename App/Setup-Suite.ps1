# Set up PinguinoSuite on a clean Windows PC from any folder (no drive letters assumed).
# Usage: powershell -ExecutionPolicy Bypass -File App\Setup-Suite.ps1 [-SkipHost] [-SkipApp]
# Checks Python/Node/.NET, creates the Suite venv, installs module dependencies, builds Host and (unless -SkipApp) the app.
param([switch]$SkipHost, [switch]$SkipApp)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Write-Host "[setup] Suite folder: $root"
function Need($cmd, $hint) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Host "[setup] MISSING $cmd. Install it: $hint"; $script:missing = $true } }
$missing = $false
Need python 'winget install Python.Python.3.12'
Need node 'winget install OpenJS.NodeJS.LTS   (Node 22 or newer, for Link)'
if (-not $SkipHost) { Need dotnet 'winget install Microsoft.DotNet.SDK.8   (for the bot Host)' }
if (-not $SkipApp) { Need cargo 'winget install Rustlang.Rustup   (and the Visual Studio Build Tools C++ workload, for the app shell)' }
if ($missing) { Write-Host '[setup] Install the missing tools, open a NEW terminal, and run this again.'; exit 1 }

$venv = Join-Path $root 'Suite\.venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { Write-Host '[setup] creating Python venv'; python -m venv $venv }
Write-Host '[setup] installing Python dependencies (the first run downloads a few hundred MB)'
& (Join-Path $venv 'Scripts\python.exe') -m pip install -q --upgrade pip
& (Join-Path $venv 'Scripts\python.exe') -m pip install -q -r (Join-Path $root 'Suite\requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Host '[setup] pip failed'; exit 1 }
$link = Join-Path $root 'Suite\modules\link'
if (Test-Path (Join-Path $link 'package.json')) { Write-Host '[setup] Link dependencies'; Push-Location $link; npm install --no-audit --no-fund; Pop-Location }
New-Item -ItemType Directory -Force (Join-Path $root 'Data\runtime') | Out-Null
if (-not $SkipHost) { Write-Host '[setup] building Host'; & (Join-Path $root 'App\build\Build-Host.bat'); if ($LASTEXITCODE -ne 0) { exit 1 } }
if (-not $SkipApp) { Write-Host '[setup] building the app'; & (Join-Path $root 'App\Build-All.bat') --no-launch; if ($LASTEXITCODE -ne 0) { exit 1 } }
Write-Host '[setup] done. Start the app: App\src-tauri\target\release\pinguino-suite.exe  (first launch shows the setup wizard)'
Write-Host '[setup] Optional: set PINGUINO_DATA_DIR to keep your data somewhere else.'
