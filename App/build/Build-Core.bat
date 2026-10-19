@echo off
rem Freeze the Python core (PyInstaller) only if Suite\suite\*.py or modules.json is newer than pinguino-core.exe. Flag: --force
setlocal
set "APP=%~dp0..\"
set "CORE=%APP%src-tauri\binaries\pinguino-core.exe"
set "STALE=powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%Stale.ps1""
if /i not "%1"=="--force" (
  %STALE% "%CORE%" "%APP%..\Suite\suite" "%APP%..\Suite\modules.json"
  if errorlevel 1 ( echo [core] up to date, skipped & exit /b 0 )
)
if not exist "%APP%..\Suite\.venv\Scripts\python.exe" ( echo [core] Suite venv missing - run PinguinoApp.bat once first. & exit /b 1 )
echo [core] freezing...
pushd "%APP%..\Suite"
.venv\Scripts\python.exe -c "import PyInstaller" 2>nul || .venv\Scripts\python.exe -m pip install -q pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --name pinguino-core --distpath ..\App\src-tauri\binaries --workpath "%TEMP%\pi_work" --specpath "%TEMP%\pi_spec" suite\suite.py
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" ( echo [core] FAILED & exit /b 1 )
echo [core] built
