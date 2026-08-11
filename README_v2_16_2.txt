v2.16.2 SYSTEM Git test correction

Fixes the v2.16.1 test-only PowerShell compatibility error:
'You cannot call a method on a null-valued expression.'

Cause:
ProcessStartInfo.ArgumentList was not available in the PowerShell/.NET environment.

This version uses Start-Process with separate stdout/stderr capture and judges
Git success only by the native process exit code.

The production vivamk_daily_monitor.py isolation logic is NOT changed by this patch.
