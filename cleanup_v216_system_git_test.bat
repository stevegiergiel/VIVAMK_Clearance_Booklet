@echo off
setlocal
cd /d F:\VIVAMK_Clearance_Booklet

echo Removing v2.16 SYSTEM Git dummy file only...
echo.

if exist "site\system_v216_isolation_test.txt" (
    del /q "site\system_v216_isolation_test.txt"
    echo Removed local file.
) else (
    echo Local test file is already absent.
)

git add -A -- "site/system_v216_isolation_test.txt"
echo.
echo The deletion is now staged ONLY for site/system_v216_isolation_test.txt.
echo No commit or push has been performed.
echo.
git status --short -- "site/system_v216_isolation_test.txt"
echo.
pause
