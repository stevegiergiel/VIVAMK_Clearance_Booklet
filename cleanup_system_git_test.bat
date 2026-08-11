@echo off
setlocal
cd /d "%~dp0"
if not exist "site\system_git_test.txt" (
  echo Test file is already absent.
  pause
  exit /b 0
)
del /q "site\system_git_test.txt"
git add -- "site/system_git_test.txt"
git commit -m "Remove SYSTEM Git publishing test file"
if errorlevel 1 (
  echo Cleanup commit failed.
  pause
  exit /b 1
)
git push
if errorlevel 1 (
  echo Cleanup push failed.
  pause
  exit /b 2
)
echo Cleanup pushed successfully.
pause
