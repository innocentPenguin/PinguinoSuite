@echo off
rem Build the Tauri shell only if App\src, src-tauri\src, tauri.conf.json, Cargo.toml or capabilities changed
rem (or the core sidecar is newer than the exe). Flags: --force  --installer (also NSIS setup)
setlocal
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
set "APP=%~dp0..\"
set "EXE=%APP%src-tauri\target\release\pinguino-suite.exe"
set "STALE=powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%Stale.ps1""
set "FORCE=0" & set "INSTALLER=0"
for %%A in (%*) do (
  if /i "%%A"=="--force" set "FORCE=1"
  if /i "%%A"=="--installer" set "INSTALLER=1"
)
set "NEED=%FORCE%"
if "%INSTALLER%"=="1" set "NEED=1"
%STALE% "%EXE%" "%APP%src" "%APP%src-tauri\src" "%APP%src-tauri\tauri.conf.json" "%APP%src-tauri\Cargo.toml" "%APP%src-tauri\capabilities" "%APP%src-tauri\binaries"
if not errorlevel 1 set "NEED=1"
if "%NEED%"=="0" ( echo [shell] up to date, skipped & exit /b 0 )
cd /d "%APP%"
set "NPM=0"
if not exist node_modules set "NPM=1"
%STALE% "%APP%node_modules\.package-lock.json" "%APP%package.json" "%APP%package-lock.json"
if not errorlevel 1 set "NPM=1"
if "%NPM%"=="1" ( echo [shell] npm install... & call npm install --no-audit --no-fund || ( echo [shell] FAILED & exit /b 1 ) )
echo [shell] building...
for /f %%T in ('powershell -NoProfile -Command "[DateTime]::UtcNow.Ticks"') do set "T0=%%T"
if "%INSTALLER%"=="1" ( call npx tauri build --bundles nsis ) else ( call npx tauri build --no-bundle )
if errorlevel 1 ( echo [shell] FAILED & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\Stamp.ps1" "%EXE%" %T0%
echo [shell] built
