@echo off
setlocal
cd /d "%~dp0"

if not exist "data\Petals_amp_Paws_Sale_GBP.pdf" (
  echo ERROR: Missing data\Petals_amp_Paws_Sale_GBP.pdf
  echo Copy the supplied Petals ^& Paws sale PDF into the data folder, then run this again.
  exit /b 1
)

python build_booklet_with_id.py --config configs\petals_paws_specials.json --state-file monitor_state\petals_paws_specials.json
if errorlevel 1 exit /b %errorlevel%

python vivamk_clearance_iframe.py --config configs\petals_paws_specials.json --state-file monitor_state\petals_paws_specials.json
if errorlevel 1 exit /b %errorlevel%

echo.
echo Petals ^& Paws specials booklet and iframe complete.
echo Booklets: output\petals_paws_specials\
echo Iframe:   site\petals-paws-specials\index.html
endlocal
