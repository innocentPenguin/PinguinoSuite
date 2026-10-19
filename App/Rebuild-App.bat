@echo off
rem One step: rebuild the PinguinoSuite app (core sidecar + Tauri shell). Close the running app first (tray -> Quit).
setlocal
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
cd /d "%~dp0..\Suite"
if not exist .venv\Scripts\python.exe ( echo Suite venv missing - run PinguinoApp.bat once first. & exit /b 1 )
.venv\Scripts\python.exe -m pip install -q pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --name pinguino-core --distpath ..\App\src-tauri\binaries --workpath "%TEMP%\pi_work" --specpath "%TEMP%\pi_spec" suite\suite.py || exit /b 1
cd /d "%~dp0"
call npm install --no-audit --no-fund || exit /b 1
call npx tauri build --bundles nsis || exit /b 1
echo Done: src-tauri\target\release\pinguino-suite.exe  and  src-tauri\target\release\bundle\nsis\
