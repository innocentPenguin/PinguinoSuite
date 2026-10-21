@echo off
rem Starts PinguinoLite. Build: cd src-tauri && cargo build --release --features custom-protocol
rem Starts the bundled PinguinoLink; no Host/OBS/go-live actions.
start "" "%~dp0src-tauri\target\release\pinguino-lite.exe"
