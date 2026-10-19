@echo off
rem Update ONE module without restarting the app: Update-Module.bat <id> [-NoBuild]. See Update-Module.ps1.
if "%1"=="" ( echo usage: Update-Module.bat ^<listen^|multi^|host^|link^> [-NoBuild] & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Module.ps1" %*
exit /b %errorlevel%
