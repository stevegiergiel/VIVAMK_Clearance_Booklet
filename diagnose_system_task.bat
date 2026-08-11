@echo off
setlocal
set "TASK=VivaMK Daily Catalogue Check"
echo VivaMK scheduled task diagnostic
echo ================================
echo.
schtasks /Query /TN "%TASK%" /V /FO LIST
echo.
echo Exported XML:
schtasks /Query /TN "%TASK%" /XML
echo.
pause
