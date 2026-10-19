# Exit 0 if Target is missing or any file under Sources is newer than it (i.e. needs rebuilding), else 1.
param([string]$Target, [string[]]$Sources)
if (-not (Test-Path $Target)) { exit 0 }
$t = (Get-Item $Target).LastWriteTimeUtc
foreach ($s in $Sources) {
  if (-not (Test-Path $s)) { continue }
  $f = Get-ChildItem $s -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\(target|node_modules|__pycache__|binaries)\' }
  if ($f | Where-Object { $_.LastWriteTimeUtc -gt $t }) { exit 0 }
}
exit 1
