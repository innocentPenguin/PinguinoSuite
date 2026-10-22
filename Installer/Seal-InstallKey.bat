@echo off
rem One-time: seal the read-only GitHub token into Installer\install.key.enc. Asks for the token and a passphrase (hidden).
node "%~dp0Seal-InstallKey.mjs"
pause
