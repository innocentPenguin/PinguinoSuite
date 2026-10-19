# Finishes moving the website into the suite.
# Right now D:\PinguinoSuite\PinguinoSite is a LINK to the real folder D:\InnocentPenguinSite (some editor / Claude session has
# that folder open, so Windows will not let it be renamed). Close every window/session whose folder is D:\InnocentPenguinSite
# (VS Code, Claude sessions, terminals), then run this script. Afterwards D:\InnocentPenguinSite becomes the link instead.
$link = 'D:\PinguinoSuite\PinguinoSite'
$old  = 'D:\InnocentPenguinSite'
if (-not ((Get-Item $link -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { Write-Host 'Already moved.'; return }
(Get-Item $link -Force).Delete()                       # removes only the link
try {
    Move-Item -LiteralPath $old -Destination $link -ErrorAction Stop
} catch {
    New-Item -ItemType Junction -Path $link -Target $old | Out-Null   # put the link back, nothing lost
    Write-Host "Still in use, nothing changed: $($_.Exception.Message)"; return
}
New-Item -ItemType Junction -Path $old -Target $link | Out-Null     # old path keeps working
Write-Host 'Site moved to D:\PinguinoSuite\PinguinoSite (old path is now a link).'
Set-Location $link; git status -sb | Select-Object -First 3
