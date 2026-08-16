@echo off
setlocal
cd /d F:\VIVAMK_Clearance_Booklet

echo Rebuilding all VivaMK iframe pages locally with monitor state where available...
echo.

for %%S in (christmas mega_sale pets personalised winter_warmers) do (
    if exist "monitor_state\%%S.json" (
        echo [%%S] using monitor_state\%%S.json
        python vivamk_clearance_iframe.py --config "configs\%%S.json" --state-file "monitor_state\%%S.json"
    ) else (
        echo [%%S] no monitor state yet - rebuilding from current source only
        python vivamk_clearance_iframe.py --config "configs\%%S.json"
    )
    if errorlevel 1 (
        echo.
        echo FAILED while rebuilding %%S.
        exit /b 1
    )
)

echo.
echo All iframe pages rebuilt locally.
echo Review with:
echo     git status --short -- site
echo.
echo Then stage only the intended site pages before committing.
pause
