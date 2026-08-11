@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "TASK=VivaMK SYSTEM Git Test"
set "SCRIPT=%~dp0test_system_git_push.ps1"
set "LOGDIR=%~dp0monitor_logs"

echo VivaMK SYSTEM GitHub publishing test
echo =====================================
echo.
echo This uses a separate temporary SYSTEM task and does not alter the daily task.
echo Run this BAT as Administrator.
echo.

schtasks /Create /TN "%TASK%" /SC ONCE /ST 23:59 /RU SYSTEM /RL HIGHEST /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT%\"" /F
if errorlevel 1 (
  echo FAILED to create test task.
  pause
  exit /b 1
)

schtasks /Run /TN "%TASK%"
if errorlevel 1 (
  echo FAILED to start test task.
  pause
  exit /b 2
)

echo.
echo Waiting for completion...
:WAIT
timeout /t 3 /nobreak >nul
for /f "tokens=2 delims=:" %%A in ('schtasks /Query /TN "%TASK%" /FO LIST ^| findstr /B /C:"Status:"') do set "STATUS=%%A"
set "STATUS=!STATUS: =!"
if /I "!STATUS!"=="Running" goto WAIT

echo.
echo Latest test log:
for /f "delims=" %%F in ('dir /b /o-d "%LOGDIR%\system_git_test_*.log" 2^>nul') do (
  type "%LOGDIR%\%%F"
  goto DONELOG
)
:DONELOG
echo.
schtasks /Delete /TN "%TASK%" /F >nul 2>&1
echo Temporary test task removed.
echo.
echo If the log ends with SUCCESS, SYSTEM GitHub publishing works.
echo If it ends with FAIL, paste that log into ChatGPT.
echo.
pause
