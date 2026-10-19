@echo off
rem Build PinguinoHost (dotnet) only if its sources are newer than the built dll. Flag: --force
setlocal
set "ROOT=%~dp0..\.."
set "DLL=%ROOT%\PinguinoHost\bin\Release\net8.0\PinguinoHost.dll"
set "STALE=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\Stale.ps1""
if /i not "%1"=="--force" (
  %STALE% "%DLL%" "%ROOT%\PinguinoHost"
  if errorlevel 1 ( echo [host] up to date, skipped & exit /b 0 )
)
echo [host] building...
for /f %%T in ('powershell -NoProfile -Command "[DateTime]::UtcNow.Ticks"') do set "T0=%%T"
dotnet build "%ROOT%\PinguinoHost\PinguinoHost.csproj" -c Release --nologo -v q || ( echo [host] FAILED & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\Stamp.ps1" "%DLL%" %T0%
echo [host] built
