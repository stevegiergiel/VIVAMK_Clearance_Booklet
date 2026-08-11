@echo off
setlocal
cd /d "%~dp0"
echo Installing VivaMK daily task under Windows SYSTEM...
echo Administrator rights are required.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_daily_task_SYSTEM.ps1"
echo.
pause
