v2.16.3 SYSTEM Git test correction

Fixes the v2.16.2 test-only pathspec error caused by Windows PowerShell 5.1
flattening Start-Process -ArgumentList and losing the quoting around the
multi-word git commit message.

v2.16.3 explicitly quotes native arguments that contain whitespace before
passing them to Start-Process.

Production vivamk_daily_monitor.py remains unchanged.
