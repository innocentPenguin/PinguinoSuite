# Runs PinguinoHost. Usage: Tools\run-host.ps1 [-Sim] [-Channel name]
param([switch]$Sim, [string]$Channel = "")
$dll = Join-Path $PSScriptRoot "..\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll"
if (-not (Test-Path $dll)) { dotnet build (Join-Path $PSScriptRoot "..\PinguinoHost") -c Release --nologo }
$a = @($dll); if ($Sim) { $a += "--sim" }; if ($Channel) { $a += @("--channel", $Channel) }
dotnet @a
