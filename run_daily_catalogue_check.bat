@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo EzeGet Daily Catalogue Monitor
echo %date% %time%
echo ============================================================

python run_daily_monitor_with_petals_paws.py
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% EQU 0 (
  echo Daily monitor completed successfully.
) else (
  echo Daily monitor finished with an error/attention code: %EXITCODE%
  echo Check monitor_logs and the heartbeat email.
)

exit /b %EXITCODE%
