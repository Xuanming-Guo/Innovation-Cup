@echo off
cd /d "%~dp0"
node scripts\local-host.mjs stop
if errorlevel 1 pause
