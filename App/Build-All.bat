@echo off
rem One entry point: builds only what is stale (Host, core, shell), each separately, and launches the app
rem only if every needed piece succeeded. Close the running app first (tray -> Quit). Only session 00 runs this.
rem   Build-All.bat                 build stale pieces, then launch
rem   Build-All.bat --no-launch     build only
rem   Build-All.bat --force         rebuild everything
rem   Build-All.bat --installer     also build the NSIS installer
rem   Build-All.bat --only host|core|shell   build just that piece
setlocal
set "B=%~dp0build"
set "LAUNCH=1" & set "FLAGS=" & set "ONLY="
:parse
if "%~1"=="" goto run
if /i "%~1"=="--no-launch" ( set "LAUNCH=0" ) else if /i "%~1"=="--only" ( set "ONLY=%~2" & shift ) else ( set "FLAGS=%FLAGS% %~1" )
shift
goto parse
:run
set "FAIL="
if not defined ONLY goto all
call "%B%\Build-%ONLY%.bat" %FLAGS% || call :try %ONLY%
goto done
:all
call "%B%\Build-Host.bat" %FLAGS%
if errorlevel 1 set "FAIL=%FAIL% host"
call "%B%\Build-Core.bat" %FLAGS%
if errorlevel 1 set "FAIL=%FAIL% core"
if defined FAIL ( echo [all] skipping shell, earlier failure & goto done )
call "%B%\Build-Shell.bat" %FLAGS%
if errorlevel 1 set "FAIL=%FAIL% shell"
:done
if defined FAIL ( echo. & echo BUILD FAILED:%FAIL% - nothing launched. & exit /b 1 )
echo. & echo BUILD OK
if "%LAUNCH%"=="1" if not defined ONLY ( echo launching... & start "" "%~dp0..\PinguinoApp\PinguinoApp.bat" )
exit /b 0
:try
set "FAIL=%FAIL% %1"
exit /b 1
