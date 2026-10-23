@echo off
rem PinguinoSuite Installer. Needs Node 22+. Example:
rem   Install-PinguinoSuite.cmd --target "%LOCALAPPDATA%\PinguinoSuite" --local D:\release --shortcuts
rem Sources are tried in this order: --repo (git), --url (network), --local (folder / zip / USB). Nothing sensitive is asked.
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found on this PC. Install Node.js LTS 22 or newer from https://nodejs.org ^(or run: winget install OpenJS.NodeJS.LTS^), open a NEW window and run this again.
  exit /b 3
)
for /f "delims=" %%v in ('node -p "process.versions.node.split('.')[0]"') do set "NODEMAJOR=%%v"
if %NODEMAJOR% LSS 22 (
  echo Node.js %NODEMAJOR% is too old; PinguinoSuite needs Node 22 or newer. Install the current LTS from https://nodejs.org and try again.
  exit /b 3
)
node "%~dp0install.mjs" %*
