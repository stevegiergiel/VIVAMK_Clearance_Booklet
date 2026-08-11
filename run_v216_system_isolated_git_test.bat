@echo off
setlocal
cd /d F:\VIVAMK_Clearance_Booklet

echo VivaMK v2.16.3 isolated SYSTEM Git test
echo =======================================
echo.
echo Tests the production monitor's isolated SYSTEM SSH publishing path.
echo Your normal origin remains HTTPS.
echo Run this BAT as Administrator.
echo.

schtasks /Delete /TN "VivaMK v2.16 SYSTEM Git Test" /F >nul 2>&1

schtasks /Create /TN "VivaMK v2.16 SYSTEM Git Test" /SC ONCE /ST 23:59 /RU SYSTEM /RL HIGHEST /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"F:\VIVAMK_Clearance_Booklet\test_v216_system_isolated_push.ps1\"" /F
if errorlevel 1 (
  echo FAILED to create temporary SYSTEM task.
  pause
  exit /b 1
)

schtasks /Run /TN "VivaMK v2.16 SYSTEM Git Test"
if errorlevel 1 (
  echo FAILED to start temporary SYSTEM task.
  schtasks /Delete /TN "VivaMK v2.16 SYSTEM Git Test" /F >nul 2>&1
  pause
  exit /b 1
)

echo.
echo Waiting 12 seconds for completion...
timeout /t 12 /nobreak >nul

echo.
echo Latest test log:
powershell.exe -NoProfile -Command "$f=Get-ChildItem 'F:\VIVAMK_Clearance_Booklet\monitor_logs\v216_system_isolated_git_test_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){Get-Content $f.FullName}else{Write-Host 'No test log found yet.'}"

schtasks /Delete /TN "VivaMK v2.16 SYSTEM Git Test" /F >nul 2>&1

echo.
echo Temporary test task removed.
echo.
pause
