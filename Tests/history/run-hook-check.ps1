# Compiles PinguinoChat\HistoryHook.cs.txt inside a wrapper class (C# 7.3, like Streamer.bot) and runs checks against sample summary files.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$hook = Join-Path $here 'hook'
New-Item -ItemType Directory -Force "$hook\build" | Out-Null
$snippet = Get-Content -Raw -Encoding UTF8 "$here\..\..\PinguinoChat\HistoryHook.cs.txt"
$wrapper = Get-Content -Raw -Encoding UTF8 "$hook\wrapper.cs.in"
$wrapper.Replace('//SNIPPET', $snippet) | Set-Content -Encoding UTF8 "$hook\build\hook.cs"
Push-Location $hook
dotnet run -c Release --nologo 2>&1
Pop-Location
