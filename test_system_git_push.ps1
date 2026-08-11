$ErrorActionPreference = "Continue"
$ProjectDir = "F:\VIVAMK_Clearance_Booklet"
$LogDir = Join-Path $ProjectDir "monitor_logs"
$TestFile = Join-Path $ProjectDir "site\system_git_test.txt"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir ("system_git_test_" + $stamp + ".log")

function Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
  $line | Tee-Object -FilePath $LogFile -Append
}

Log "VivaMK SYSTEM Git test started."
Log ("Identity: " + [System.Security.Principal.WindowsIdentity]::GetCurrent().Name)

if (-not (Test-Path $ProjectDir)) { Log "FAIL: project folder not found."; exit 10 }
Set-Location $ProjectDir

$git = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $git) { Log "FAIL: git.exe not available in SYSTEM PATH."; exit 11 }
Log ("Git executable: " + $git.Source)

$payload = @"
VivaMK SYSTEM Git publishing test
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Machine: $env:COMPUTERNAME
Account: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
"@
$payload | Out-File -FilePath $TestFile -Encoding utf8 -Force
Log "Created site/system_git_test.txt"

& git add -- "site/system_git_test.txt" 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "FAIL: git add failed."; exit 13 }

if (-not (& git config user.name 2>$null)) { & git config user.name "VivaMK Catalogue Monitor" }
if (-not (& git config user.email 2>$null)) { & git config user.email "admin@ezeget.com" }

& git commit -m "Test SYSTEM GitHub publishing" -- "site/system_git_test.txt" 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "FAIL: git commit failed."; exit 15 }

Log "Commit succeeded. Attempting git push under SYSTEM..."
& git push 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
  Log ("FAIL: git push failed with exit code " + $LASTEXITCODE + ".")
  exit 16
}

Log "SUCCESS: SYSTEM committed and pushed the dummy file to GitHub."
exit 0
