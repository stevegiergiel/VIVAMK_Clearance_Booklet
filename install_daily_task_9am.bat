@echo off
setlocal
cd /d "%~dp0"

set TASKNAME=VivaMK Daily Catalogue Check
set BAT=%~dp0run_daily_catalogue_check.bat

echo This installs a Windows Scheduled Task to run every day at 09:00.
echo.
schtasks /Create /TN "%TASKNAME%" /TR "\"%BAT%\"" /SC DAILY /ST 09:00 /F

if errorlevel 1 (
  echo.
  echo Could not create the task. Try right-clicking this file and choosing Run as administrator.
  pause
  exit /b 1
)

echo.
echo Installed successfully.
echo Task: %TASKNAME%
echo Time: 09:00 daily
echo.
echo You can change the time later in Windows Task Scheduler.
pause
