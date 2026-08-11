@echo off
setlocal
set "TASK=VivaMK Daily Catalogue Check"

echo Starting "%TASK%" now under SYSTEM...
schtasks /Run /TN "%TASK%"
if errorlevel 1 (
  echo.
  echo FAILED to start the scheduled task.
  pause
  exit /b 1
)

echo.
echo The task has been launched.
echo The full catalogue scan can take several minutes.
echo Wait for the normal heartbeat email to confirm completion.
echo.
echo Current Task Scheduler status:
schtasks /Query /TN "%TASK%" /V /FO LIST
echo.
echo After the heartbeat arrives, check monitor_logs if it reports a Git push error.
echo That would indicate GitHub credentials need separate setup for SYSTEM.
echo.
pause
