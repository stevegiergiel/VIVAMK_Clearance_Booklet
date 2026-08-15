@echo off
cd /d "%~dp0"
echo Creating SOLD OUT overprint for the CURRENT registered Christmas booklet ID...
python booklet_identity.py --config configs\christmas.json --overprint
if errorlevel 1 (
  echo.
  echo OVERPRINT FAILED - no file was produced.
  pause
  exit /b 1
)
echo.
echo Done. Check output\christmas\overprints\
echo The PDF filename includes the exact Booklet ID it is safe to use with.
pause
