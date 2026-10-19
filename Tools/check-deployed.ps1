# Read-only: compares the C# pasted into Streamer.bot actions with the repo sources.
# Usage: powershell -File Tools\check-deployed.ps1 [-ActionsJson <path>]
param([string]$ActionsJson = 'C:\Users\ivanm\Documents\PinguinoB0t\data\actions.json')
$suite = Split-Path $PSScriptRoot -Parent
$sources = [ordered]@{
  'PinguinoBot'    = "$suite\PinguinoB0t\PinguinoBotCore.cs"
  'PinguinoChat'   = "$suite\PinguinoChat\PinguinoChat.cs"
  'PinguinoHelper' = "$suite\HelperPinguino\PinguinoHelper.cs"
  'PinguinoRouter' = "$suite\Shared\PinguinoRouter.cs"
}
function Norm($t) { ($t -replace "`r`n", "`n").Trim() }
function Sha($t) { $b=[Text.Encoding]::UTF8.GetBytes((Norm $t)); -join ([Security.Cryptography.SHA256]::Create().ComputeHash($b)[0..5] | % { $_.ToString('x2') }) }
$repo = @{}; foreach ($k in $sources.Keys) { if (Test-Path $sources[$k]) { $repo[$k] = Sha (Get-Content $sources[$k] -Raw -Encoding UTF8) } }
$j = Get-Content $ActionsJson -Raw | ConvertFrom-Json
foreach ($a in $j.actions) {
  foreach ($s in @($a.subActions | ? { $_.type -eq 99999 -and $_.byteCode })) {
    $t = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($s.byteCode)); $h = Sha $t
    $match = ($repo.GetEnumerator() | ? { $_.Value -eq $h } | % { $_.Key }) -join ','
    $guess = foreach ($k in $sources.Keys) { if ($t -match ('class CPHInline') -and $t.Length -gt 0) { } }
    '{0,-28} enabled={1,-5} bytes={2,7} sha={3} identicalTo={4}' -f $a.name, $a.enabled, $t.Length, $h, $(if ($match) { $match } else { '(none - old/other copy)' })
  }
}
'--- repo hashes'; $repo.GetEnumerator() | % { '{0,-16} {1}' -f $_.Key, $_.Value }
'--- expected actions missing in Streamer.bot'
$names = @($j.actions | % { $_.name }); $sources.Keys | ? { $names -notcontains $_ } | % { "MISSING: $_" }
