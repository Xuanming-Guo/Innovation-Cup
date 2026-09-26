@echo off
cd /d "%~dp0"
node scripts\local-host.mjs start
if errorlevel 1 pause
