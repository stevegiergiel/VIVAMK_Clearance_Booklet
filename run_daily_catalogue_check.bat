@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo VivaMK Daily Catalogue Monitor
echo %date% %time%
echo ============================================================

python vivamk_daily_monitor.py
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% EQU 0 (
  echo Daily monitor completed successfully.
) else (
  echo Daily monitor finished with an error/attention code: %EXITCODE%
  echo Check monitor_logs and the heartbeat email.
)

exit /b %EXITCODE%
