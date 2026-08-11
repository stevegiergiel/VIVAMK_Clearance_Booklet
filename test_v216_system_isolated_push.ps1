$ErrorActionPreference = "Stop"

$Root = "F:\VIVAMK_Clearance_Booklet"
$LogDir = Join-Path $Root "monitor_logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $LogDir "v216_system_isolated_git_test_$Stamp.log"

function Log($Message) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Message"
    Add-Content -Path $Log -Value $line
}

function Run-Native {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [hashtable]$Environment = @{}
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    foreach ($arg in $Arguments) {
        [void]$psi.ArgumentList.Add($arg)
    }

    foreach ($key in $Environment.Keys) {
        $psi.Environment[$key] = [string]$Environment[$key]
    }

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($stdout) {
        $stdout.TrimEnd() -split "`r?`n" | ForEach-Object { Log "$_" }
    }
    if ($stderr) {
        # Git normally writes push progress ("To github.com...") to stderr.
        # Log it as information; do not treat stderr itself as failure.
        $stderr.TrimEnd() -split "`r?`n" | ForEach-Object { Log "$_" }
    }

    return $proc.ExitCode
}

try {
    Set-Location $Root
    Log "v2.16.1 isolated SYSTEM Git test started."
    Log "Identity: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

    $origin = (& git remote get-url origin 2>&1 | Out-String).Trim()
    Log "Normal origin remains: $origin"

    if ($origin -notlike "https://github.com/*") {
        throw "Normal origin is not HTTPS: $origin"
    }

    $repoSsh = (& git config --get core.sshCommand 2>$null | Out-String).Trim()
    if ($repoSsh) {
        throw "Repo-wide core.sshCommand is still set: $repoSsh"
    }
    Log "Repo-wide core.sshCommand: NOT SET (correct)"

    $testRel = "site/system_v216_isolation_test.txt"
    $testFile = Join-Path $Root $testRel
    "v2.16.1 SYSTEM isolated push test $(Get-Date -Format o)" |
        Set-Content -Path $testFile -Encoding ASCII
    Log "Created $testRel"

    $code = Run-Native "git.exe" @("add", "--", $testRel)
    if ($code -ne 0) { throw "git add failed with exit code $code" }

    $changes = (& git status --porcelain -- $testRel 2>&1 | Out-String).Trim()
    if (-not $changes) {
        throw "No Git change detected for test file."
    }

    $code = Run-Native "git.exe" @(
        "commit",
        "-m", "Test v2.16.1 isolated SYSTEM Git publishing",
        "--", $testRel
    )
    if ($code -ne 0) { throw "git commit failed with exit code $code" }

    $ssh = 'C:\Windows\System32\OpenSSH\ssh.exe'
    $key = 'C:\ProgramData\VivaMK\ssh\github_deploy_ed25519'
    $known = 'C:\ProgramData\VivaMK\ssh\known_hosts'
    $sshCommand = "`"$ssh`" -i `"$key`" -o IdentitiesOnly=yes -o UserKnownHostsFile=`"$known`" -o StrictHostKeyChecking=yes"

    Log "Attempting push with process-local SYSTEM deploy key..."
    $code = Run-Native "git.exe" @(
        "push",
        "git@github.com:stevegiergiel/VIVAMK_Clearance_Booklet.git",
        "HEAD:main"
    ) @{ "GIT_SSH_COMMAND" = $sshCommand }

    if ($code -ne 0) { throw "git push failed with exit code $code" }

    Log "SUCCESS: v2.16.1 SYSTEM isolated SSH push works while normal origin remains HTTPS."
    exit 0
}
catch {
    Log "FAIL: $($_.Exception.Message)"
    exit 1
}
