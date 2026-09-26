@echo off
cd /d "%~dp0"
node scripts\local-host.mjs status
if errorlevel 1 pause
