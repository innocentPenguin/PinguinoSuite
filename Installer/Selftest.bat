@echo off
rem Release self-test: builds two signed fake releases in a temp folder and exercises install/update/rollback/tamper/repair/uninstall. See Docs\RELEASE_DRYRUN.md.
node "%~dp0Selftest.mjs" %*
