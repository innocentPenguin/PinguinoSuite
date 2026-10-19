# Usage: Stamp.ps1 <file> <startTicksUtc>. Backdates a build output to when its build STARTED, so a source edited while the
# build was running still counts as newer than the output (otherwise Stale.ps1 would call a stale build "fresh").
param([string]$File, [long]$Ticks)
if (Test-Path $File) { (Get-Item $File).LastWriteTimeUtc = [DateTime]::new($Ticks, 'Utc') }
