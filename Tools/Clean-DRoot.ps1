# Clean-DRoot.ps1 - nightly tidy of the D: root (Ivan's request 2026-10-30).
# Removes ONLY build leftovers our sessions create there:
#   D:\pg-headbuild*   detached git worktrees used for Host head builds (removed via git so the repo forgets them)
#   D:\tmp*, D:\tmp_wt_*, D:\selftest-work, D:\cargo-scratch   scratch folders from sessions
# Everything else in the root is never touched (allowlist below is informational; the script only matches the patterns above).
# A folder is removed only when nothing inside it changed in the last -MinAgeHours (default 12) and no process runs from it.
# Log: D:\PinguinoSuite\Docs\log\cleanup\YYYY-MM-DD.md.  -DryRun lists without deleting.
param([switch]$DryRun, [int]$MinAgeHours = 12)

$ErrorActionPreference = 'Stop'
$root = 'D:\'
$repo = 'D:\PinguinoSuite'
$logDir = Join-Path $repo 'Docs\log\cleanup'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ((Get-Date).ToString('yyyy-MM-dd') + '.md')
$keep = @('PinguinoSuite','Archive','PinguinoBackup','PinguinoBot','InnocentPenguinSite','Recordings','Roblox Games','cargo-target','.claude','.remember','System Volume Information','$RECYCLE.BIN')
$patterns = @('pg-headbuild*','tmp*','tmp_wt_*','selftest-work','cargo-scratch')
$cutoff = (Get-Date).AddHours(-$MinAgeHours)
$lines = @("## " + (Get-Date).ToString('HH:mm') + ($(if ($DryRun) { ' (dry run)' } else { '' })))

function Newest($path) {
    $n = Get-ChildItem $path -Recurse -Force -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($n) { if ($n.LastWriteTime -gt (Get-Item $path).LastWriteTime) { return $n.LastWriteTime } }
    return (Get-Item $path).LastWriteTime
}
$busy = @{}
Get-Process -ErrorAction SilentlyContinue | ForEach-Object { try { if ($_.Path) { $busy[$_.Path] = $true } } catch {} }
function InUse($path) { foreach ($p in $busy.Keys) { if ($p -like ($path.TrimEnd('\') + '\*')) { return $true } }; return $false }

$freed = 0; $removed = 0
foreach ($d in Get-ChildItem $root -Directory -Force) {
    if ($keep -contains $d.Name) { continue }
    $match = $false; foreach ($p in $patterns) { if ($d.Name -like $p) { $match = $true } }
    if (-not $match) { continue }
    $newest = Newest $d.FullName
    if ($newest -gt $cutoff) { $lines += "- keep $($d.Name): changed $($newest.ToString('yyyy-MM-dd HH:mm'))"; continue }
    if (InUse $d.FullName) { $lines += "- keep $($d.Name): a process runs from it"; continue }
    $size = (Get-ChildItem $d.FullName -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    $mb = [math]::Round(($size / 1MB), 1)
    if ($DryRun) { $lines += "- would remove $($d.Name) ($mb MB, last change $($newest.ToString('yyyy-MM-dd HH:mm')))"; continue }
    try {
        if ($d.Name -like 'pg-headbuild*' -and (Test-Path (Join-Path $d.FullName '.git'))) {
            & git -C $repo worktree remove --force $d.FullName 2>$null | Out-Null
        }
        if (Test-Path $d.FullName) { Remove-Item $d.FullName -Recurse -Force -Confirm:$false }
        $freed += $size; $removed++
        $lines += "- removed $($d.Name) ($mb MB)"
    } catch { $lines += "- FAILED $($d.Name): $($_.Exception.Message)" }
}
if (-not $DryRun) { & git -C $repo worktree prune 2>$null | Out-Null }
$lines += "- total: $removed removed, " + [math]::Round($freed / 1MB, 1) + " MB freed"
Add-Content -Path $log -Value ($lines -join "`n") -Encoding utf8
$lines | ForEach-Object { Write-Output $_ }
