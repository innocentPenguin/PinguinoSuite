# PinguinoHost vs a MOCK Twitch helix: sign-in token resolve, helix chat send (Bearer + Client-Id), /api/run (Stream Deck).
$dll = Join-Path $PSScriptRoot "..\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll"
$d = Join-Path $env:TEMP ("pghosttw_" + [guid]::NewGuid().ToString("N")); New-Item -ItemType Directory $d | Out-Null
$log = Join-Path $d "mock.log"
'{"Channel":"mockstreamer","ClientId":"mockcid","UserToken":"mocktoken","SenderId":"4242","BroadcasterId":"4242"}' | Set-Content (Join-Path $d "host_secrets.json")
$mock = Start-Process (Join-Path $PSScriptRoot "..\Suite\.venv\Scripts\python.exe") -ArgumentList @((Join-Path $PSScriptRoot "mock-twitch.py"), "8771", $log) -PassThru -WindowStyle Hidden
$env:PINGUINO_HELIX_BASE = "http://127.0.0.1:8771"
$p = Start-Process dotnet -ArgumentList @($dll, "--no-sync", "--data", $d) -PassThru -WindowStyle Hidden
$u = "http://127.0.0.1:8770"; $fail = @()
try {
  for ($i = 0; $i -lt 30; $i++) { try { Invoke-RestMethod "$u/api/status" -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }
  $t = Invoke-RestMethod "$u/api/token" -Method Post -Body '{"token":"mocktoken"}'
  if (-not $t.ok -or $t.login -ne "mockstreamer") { $fail += "token resolve" }
  $r = Invoke-RestMethod "$u/api/run" -Method Post -Body '{"text":"!queue","user":"deck"}'
  if (-not $r.ok) { $fail += "run" }
  Start-Sleep -Seconds 4
  $l = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
  if ($l -notmatch "GET /users auth=OK") { $fail += "users call" }
  if ($l -notmatch "POST /chat/messages auth=OK") { $fail += "chat send" }
  if ($l -match "auth=BAD") { $fail += "bad auth header" }
} finally { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; Stop-Process -Id $mock.Id -Force -ErrorAction SilentlyContinue; Remove-Item Env:PINGUINO_HELIX_BASE }
if ($fail.Count) { "HOST TWITCH(mock): FAIL - " + ($fail -join ", "); if (Test-Path $log) { Get-Content $log }; exit 1 } else { "HOST TWITCH(mock): PASS" }
