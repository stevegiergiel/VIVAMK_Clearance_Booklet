#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$TaskName = "VivaMK Daily Catalogue Check"
$ProjectDir = "F:\VIVAMK_Clearance_Booklet"
$Runner = Join-Path $ProjectDir "run_daily_catalogue_check.bat"

Write-Host ""
Write-Host "VivaMK Daily Catalogue Check - SYSTEM Task Installer" -ForegroundColor Cyan
Write-Host "----------------------------------------------------"

if (-not (Test-Path $ProjectDir)) {
    throw "Project folder not found: $ProjectDir`nMake sure the USB drive is connected and mounted as F:."
}
if (-not (Test-Path $Runner)) {
    throw "Runner not found: $Runner"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "C:\Windows\System32\cmd.exe" `
    -Argument "/d /c `"$Runner`"" `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Checks VivaMK clearance catalogues daily, sends heartbeat email, updates SOLD OUT status, rebuilds affected booklets/iframes, and publishes changes when Git credentials are available." `
    -Force | Out-Null

Write-Host ""
Write-Host "SUCCESS: $TaskName created under NT AUTHORITY\SYSTEM." -ForegroundColor Green
Write-Host "Time: 09:00 daily"
Write-Host "Wake from sleep/hibernate: enabled"
Write-Host "Catch up after missed start: enabled"
Write-Host "Retry on failure: 15 minutes, up to 3 retries"
Write-Host "Highest privileges: enabled"
Write-Host ""

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host ("Run account: " + $task.Principal.UserId)
Write-Host ("WakeToRun: " + $task.Settings.WakeToRun)
Write-Host ("StartWhenAvailable: " + $task.Settings.StartWhenAvailable)
Write-Host ("Next run: " + $info.NextRunTime)
Write-Host ""

Write-Host "IMPORTANT:" -ForegroundColor Yellow
Write-Host "SYSTEM can access F: only while the USB drive is connected and mounted as F:."
Write-Host "Email should work under SYSTEM because the config is local."
Write-Host "GitHub publishing may need a SYSTEM-accessible Git credential; your normal user Git credential may not be visible to SYSTEM."
Write-Host ""
Write-Host "Next: run test_system_task.bat as Administrator."
