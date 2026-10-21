@echo off
rem Builds PinguinoUpdater.exe and the Installer exe with plain rustc (std only, no crates, no downloads). Run from anywhere; does not launch or touch the Suite.
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin"
pushd "%~dp0"
rustc -O --edition 2021 pinguino_updater.rs -o PinguinoUpdater.exe || goto :fail
cd ..\..\..\Installer
rustc -O --edition 2021 pinguino_installer.rs -o PinguinoInstaller.exe || goto :fail
del /q *.pdb "%~dp0*.pdb" 2>nul
popd & echo built & exit /b 0
:fail
popd & echo FAILED & exit /b 1
