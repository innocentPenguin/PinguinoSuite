@echo off
rem Starts PinguinoLite. Build: cd src-tauri && cargo build --release --features custom-protocol
rem Starts the bundled PinguinoLink; no Host/OBS/go-live actions.
rem If an update was staged from Lite's Parts card (release install only), the shared updater swaps it in now, while Lite is not running.
if exist "%~dp0..\install.json" if exist "%~dp0..\Suite\updater\updater.mjs" node "%~dp0..\Suite\updater\updater.mjs" launch --install "%~dp0.." >nul 2>&1
start "" "%~dp0src-tauri\target\release\pinguino-lite.exe"
