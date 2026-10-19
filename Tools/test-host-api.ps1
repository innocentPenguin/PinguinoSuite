# Setup-interface test for PinguinoHost: status/config API, secret masking, localhost-only guard. Uses a temp data dir.
$dll = Join-Path $PSScriptRoot "..\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll"
$d = Join-Path $env:TEMP ("pghostapi_" + [guid]::NewGuid().ToString("N")); New-Item -ItemType Directory $d | Out-Null
$p = Start-Process dotnet -ArgumentList @($dll, "--no-sync", "--data", $d) -PassThru -WindowStyle Hidden
$u = "http://127.0.0.1:8770"; $fail = @()
try {
  for ($i = 0; $i -lt 30; $i++) { try { Invoke-RestMethod "$u/api/status" -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }
  $s = Invoke-RestMethod "$u/api/status"; if ($s.name -ne "PinguinoHost") { $fail += "status" }
  Invoke-RestMethod "$u/api/config" -Method Post -Body '{"Channel":"mychan","ClientId":"abc","UserToken":"SECRETTOKEN123"}' | Out-Null
  $raw = Invoke-WebRequest "$u/api/config" -UseBasicParsing | Select-Object -ExpandProperty Content
  if ($raw -match "SECRETTOKEN123") { $fail += "secret leaked" }
  if ((ConvertFrom-Json $raw).hasUserToken -ne $true) { $fail += "hasUserToken" }
  if ((Get-Content "$d\host_secrets.json" -Raw) -notmatch "SECRETTOKEN123") { $fail += "not saved" }
  try { Invoke-WebRequest "$u/api/config" -Headers @{ Origin = "http://evil.com" } -UseBasicParsing | Out-Null; $fail += "origin not blocked" } catch { }
  if ((Invoke-WebRequest "$u/setup" -UseBasicParsing).Content -notmatch "PinguinoHost") { $fail += "page" }
} finally { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
if ($fail.Count) { "HOST API: FAIL - " + ($fail -join ", "); exit 1 } else { "HOST API: PASS" }
