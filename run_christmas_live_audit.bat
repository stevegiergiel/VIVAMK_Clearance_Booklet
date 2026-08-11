@echo off
setlocal
cd /d "%~dp0"
echo Comparing Christmas PDF source with the live Christmas category...
echo.
python compare_christmas_live.py
echo.
if errorlevel 1 (
  echo Christmas live audit FAILED.
) else (
  echo Christmas live audit completed successfully.
  echo See output\christmas\live_audit\
)
pause
