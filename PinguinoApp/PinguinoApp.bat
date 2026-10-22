@echo off
rem PinguinoApp - opens PinguinoSuite. Prefers the Tauri shell (one window, tray, single-instance; it starts the core itself).
rem Falls back to the standalone core (tray + Edge app window) only if the shell has not been built.
rem Update check (silent no-op unless install.json names a source; capped at 10 s; never blocks the app).
if exist "%~dp0..\Suite\updater\exe\PinguinoUpdater.exe" start "" /wait "%~dp0..\Suite\updater\exe\PinguinoUpdater.exe"
rem Release installs only (install.json exists): no exe, so use node. Applies staged app parts / staged rollbacks while nothing is running. A dev tree has no install.json, so this does nothing.
if not exist "%~dp0..\Suite\updater\exe\PinguinoUpdater.exe" if exist "%~dp0..\install.json" if exist "%~dp0..\Suite\updater\updater.mjs" where node >nul 2>nul && node "%~dp0..\Suite\updater\updater.mjs" launch --install "%~dp0.." >nul 2>nul
set "SHELL_EXE=%~dp0..\App\src-tauri\target\release\pinguino-suite.exe"
if exist "%SHELL_EXE%" (
  start "" "%SHELL_EXE%"
  exit /b 0
)
cd /d "%~dp0..\Suite"
if not exist .venv\Scripts\pythonw.exe (
  echo First run: creating the Suite environment ^(a few minutes^)...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe suite\suite.py
