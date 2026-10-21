@echo off
rem PinguinoSuite Installer. Needs Node 22+. Example:
rem   Install-PinguinoSuite.cmd --target "%LOCALAPPDATA%\PinguinoSuite" --local D:\release --shortcuts
rem Sources are tried in this order: --repo (git), --url (network), --local (folder / zip / USB). Nothing sensitive is asked.
node "%~dp0install.mjs" %*
