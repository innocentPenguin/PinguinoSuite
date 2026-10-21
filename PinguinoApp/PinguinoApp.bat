@echo off
rem PinguinoApp - opens PinguinoSuite (starts it hidden with a tray icon, or just brings up the window if it is already running).
rem Update check (silent no-op unless install.json names a source; capped at 10 s; never blocks the app).
if exist "%~dp0..\Suite\updater\exe\PinguinoUpdater.exe" start "" /wait "%~dp0..\Suite\updater\exe\PinguinoUpdater.exe"
cd /d "%~dp0..\Suite"
if not exist .venv\Scripts\pythonw.exe (
  echo First run: creating the Suite environment ^(a few minutes^)...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe suite\suite.py
