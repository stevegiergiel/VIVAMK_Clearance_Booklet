@echo off
setlocal
cd /d "%~dp0"
echo Installing corrected VivaMK daily task under Windows SYSTEM...
echo.
echo IMPORTANT: Right-click this BAT and choose "Run as administrator".
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_daily_task_SYSTEM_XML.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo INSTALLER FAILED with exit code %RC%.
) else (
  echo Installer completed.
)
echo.
pause
exit /b %RC%
