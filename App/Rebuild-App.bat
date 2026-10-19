@echo off
rem Fast, incremental rebuild of the PinguinoSuite app. Close the running app first (tray -> Quit).
rem   Rebuild-App.bat              rebuild only what changed (core sidecar and/or shell), no installer
rem   Rebuild-App.bat --installer  also build the NSIS installer
rem   Rebuild-App.bat --force      rebuild everything
rem Module code (Multi/Listen/Link/Host) never needs this: just restart that module from the app.
setlocal
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
set "APP=%~dp0"
set "INSTALLER=0" & set "FORCE=0"
for %%A in (%*) do (
  if /i "%%A"=="--installer" set "INSTALLER=1"
  if /i "%%A"=="--force" set "FORCE=1"
)
set "CORE=%APP%src-tauri\binaries\pinguino-core.exe"
set "EXE=%APP%src-tauri\target\release\pinguino-suite.exe"
set "STALE=powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%Stale.ps1""

rem 1) Core sidecar: only if Suite python / modules.json changed
%STALE% "%CORE%" "%APP%..\Suite\suite" "%APP%..\Suite\modules.json"
if errorlevel 1 if "%FORCE%"=="0" ( echo [core] up to date, skipped & goto shell )
if not exist "%APP%..\Suite\.venv\Scripts\python.exe" ( echo Suite venv missing - run PinguinoApp.bat once first. & exit /b 1 )
pushd "%APP%..\Suite"
.venv\Scripts\python.exe -c "import PyInstaller" 2>nul || .venv\Scripts\python.exe -m pip install -q pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --name pinguino-core --distpath ..\App\src-tauri\binaries --workpath "%TEMP%\pi_work" --specpath "%TEMP%\pi_spec" suite\suite.py || ( popd & exit /b 1 )
popd
set "CORE_BUILT=1"

:shell
rem 2) Shell: only if UI / Rust sources / tauri config changed (or the core was rebuilt, since it is bundled as a resource)
%STALE% "%EXE%" "%APP%src" "%APP%src-tauri\src" "%APP%src-tauri\tauri.conf.json" "%APP%src-tauri\Cargo.toml" "%APP%src-tauri\capabilities"
set "SHELLSTALE=%errorlevel%"
if "%SHELLSTALE%"=="1" if not defined CORE_BUILT if "%FORCE%"=="0" if "%INSTALLER%"=="0" ( echo [shell] up to date, skipped - just relaunch & goto done )
cd /d "%APP%"
if not exist node_modules ( call npm install --no-audit --no-fund || exit /b 1 ) else %STALE% "%APP%node_modules\.package-lock.json" "%APP%package.json" "%APP%package-lock.json" && ( call npm install --no-audit --no-fund || exit /b 1 )
if "%INSTALLER%"=="1" ( call npx tauri build --bundles nsis || exit /b 1 ) else ( call npx tauri build --no-bundle || exit /b 1 )
:done
echo Done: %EXE%
