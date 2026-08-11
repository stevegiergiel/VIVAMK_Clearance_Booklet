#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$TaskName   = "VivaMK Daily Catalogue Check"
$ProjectDir = "F:\VIVAMK_Clearance_Booklet"
$Runner     = Join-Path $ProjectDir "run_daily_catalogue_check.bat"
$XmlFile    = Join-Path $env:TEMP "VivaMK_Daily_Catalogue_Check.xml"

Write-Host ""
Write-Host "VivaMK Daily Catalogue Check - SYSTEM/XML Installer" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------"

if (-not (Test-Path $ProjectDir)) {
    throw "Project folder not found: $ProjectDir`nMake sure the USB drive is connected and mounted as F:."
}
if (-not (Test-Path $Runner)) {
    throw "Runner not found: $Runner"
}

# Start tomorrow at 09:00 so installing after 09:00 does not accidentally trigger
# an immediate missed-start run. The separate test BAT can launch it immediately.
$StartBoundary = (Get-Date).Date.AddDays(1).AddHours(9).ToString("yyyy-MM-dd'T'HH:mm:ss")

# Task Scheduler schema values are written explicitly, including ISO-8601 durations.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Checks VivaMK clearance catalogues daily, sends heartbeat email, updates SOLD OUT status, rebuilds affected booklets/iframes, and publishes changes when Git credentials are available.</Description>
    <URI>\VivaMK Daily Catalogue Check</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$StartBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT15M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\Windows\System32\cmd.exe</Command>
      <Arguments>/d /c "&quot;$Runner&quot;"</Arguments>
      <WorkingDirectory>$ProjectDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Write the file in UTF-16 because the XML declaration explicitly says UTF-16.
$xml | Out-File -FilePath $XmlFile -Encoding Unicode -Force

Write-Host "Registering/replacing task directly..." -ForegroundColor Cyan
$createOutput = & cmd.exe /d /c "schtasks.exe /Create /TN `"$TaskName`" /XML `"$XmlFile`" /F 2>&1"
$createExit = $LASTEXITCODE
$createOutput | ForEach-Object { Write-Host $_ }

if ($createExit -ne 0) {
    throw "schtasks failed to create the task. XML retained at: $XmlFile"
}

Write-Host ""
Write-Host "SUCCESS: SYSTEM task registered and ready for verification." -ForegroundColor Green
Write-Host ""

# Verify with schtasks rather than Get-ScheduledTask, so a CIM/XML parser issue
# cannot falsely make the installer itself fail.
$queryOutput = & cmd.exe /d /c "schtasks.exe /Query /TN `"$TaskName`" /V /FO LIST 2>&1"
$queryExit = $LASTEXITCODE
$queryOutput | ForEach-Object { Write-Host $_ }

if ($queryExit -ne 0) {
    throw "Task was created but schtasks could not query it."
}

Write-Host ""
Write-Host "Configured:" -ForegroundColor Cyan
Write-Host "  Account: NT AUTHORITY\SYSTEM"
Write-Host "  Time: 09:00 daily"
Write-Host "  Wake from sleep/hibernate: enabled"
Write-Host "  Catch up after a missed start: enabled"
Write-Host "  Retry: every 15 minutes, maximum 3 retries"
Write-Host "  Maximum single run: 4 hours"
Write-Host "  Highest privileges: enabled"
Write-Host "  Overlapping runs: prevented"
Write-Host ""
Write-Host "The task starts its normal schedule tomorrow at 09:00."
Write-Host "Run test_system_task.bat now to test it immediately under SYSTEM."
Write-Host ""
Write-Host "NOTE: F: must be connected and mounted with the same drive letter."
Write-Host "GitHub publishing still needs to be verified under SYSTEM because Git credentials may be user-specific."

Remove-Item $XmlFile -Force -ErrorAction SilentlyContinue
