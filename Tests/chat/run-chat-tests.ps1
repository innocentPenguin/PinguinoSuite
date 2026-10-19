# Compiles PinguinoChat\PinguinoChat.cs (as C# 7.3, like Streamer.bot) with a stub Streamer.bot and runs harness.cs.
# Uses a throwaway data folder (PINGUINO_DATA_DIR), never %AppData%\BVQ, and a fake AI (no network, no cost).
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force "$here\build" | Out-Null
(Get-Content -Raw -Encoding UTF8 "$here\..\..\PinguinoChat\PinguinoChat.cs") -replace '(?m)^public class CPHInline\s*$', 'public class CPHInline : CPHStubBase' |
  Set-Content -Encoding UTF8 "$here\build\chat.cs"
Push-Location $here
dotnet run -c Release --nologo 2>&1 | Where-Object { $_ -notmatch '^INFO' }
Pop-Location
