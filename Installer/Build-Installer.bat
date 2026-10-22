@echo off
rem Builds Installer\dist\PinguinoSuiteSetup.exe (ONE file for another PC) from the CURRENT built Suite. Run App\Build-All.bat --no-launch first so it packs fresh builds.
rem Does not launch, stop or touch anything. Optional: --version 1.2.3   --no-key (leave the sealed repo key out)
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
node "%~dp0Build-Installer.mjs" %*
