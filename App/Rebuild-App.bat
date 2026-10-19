@echo off
rem Kept for compatibility: incremental build of stale pieces, no launch. See Build-All.bat.
call "%~dp0Build-All.bat" --no-launch %*
