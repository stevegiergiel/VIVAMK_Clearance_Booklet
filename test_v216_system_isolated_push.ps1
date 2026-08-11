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

function Quote-NativeArg {
    param([string]$Arg)

    if ($Arg -match '[\s"]') {
        # Windows command-line quoting suitable for git.exe arguments here.
        $escaped = $Arg -replace '(\\*)"', '$1$1\"'
        $escaped = $escaped -replace '(\\+)$', '$1$1'
        return '"' + $escaped + '"'
    }
    return $Arg
}

function Run-Git {
    param(
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [string]$GitSshCommand = ""
    )

    $outFile = Join-Path $env:TEMP ("vivamk_git_stdout_" + [guid]::NewGuid().ToString("N") + ".txt")
    $errFile = Join-Path $env:TEMP ("vivamk_git_stderr_" + [guid]::NewGuid().ToString("N") + ".txt")
    $oldSsh = $env:GIT_SSH_COMMAND

    try {
        if ($GitSshCommand) {
            $env:GIT_SSH_COMMAND = $GitSshCommand
        } else {
            Remove-Item Env:\GIT_SSH_COMMAND -ErrorAction SilentlyContinue
        }

        # PowerShell 5.1 Start-Process flattens ArgumentList. Build one correctly
        # quoted command-line string so multi-word commit messages stay one argument.
        $argLine = (($Arguments | ForEach-Object { Quote-NativeArg $_ }) -join ' ')

        $proc = Start-Process `
            -FilePath "git.exe" `
            -ArgumentList $argLine `
            -WorkingDirectory $Root `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $outFile `
            -RedirectStandardError $errFile

        if (Test-Path $outFile) {
            Get-Content $outFile | ForEach-Object { if ($_ -ne "") { Log "$_" } }
        }
        if (Test-Path $errFile) {
            # Git normally writes push progress to stderr. Exit code decides success.
            Get-Content $errFile | ForEach-Object { if ($_ -ne "") { Log "$_" } }
        }

        return $proc.ExitCode
    }
    finally {
        if ($null -eq $oldSsh) {
            Remove-Item Env:\GIT_SSH_COMMAND -ErrorAction SilentlyContinue
        } else {
            $env:GIT_SSH_COMMAND = $oldSsh
        }
        Remove-Item $outFile,$errFile -Force -ErrorAction SilentlyContinue
    }
}

try {
    Set-Location $Root
    Log "v2.16.3 isolated SYSTEM Git test started."
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
    "v2.16.3 SYSTEM isolated push test $(Get-Date -Format o)" |
        Set-Content -Path $testFile -Encoding ASCII
    Log "Created $testRel"

    $code = Run-Git @("add", "--", $testRel)
    if ($code -ne 0) { throw "git add failed with exit code $code" }

    $changes = (& git status --porcelain -- $testRel 2>&1 | Out-String).Trim()
    if (-not $changes) {
        throw "No Git change detected for test file."
    }

    $code = Run-Git @(
        "commit",
        "-m", "Test v2.16.3 isolated SYSTEM Git publishing",
        "--", $testRel
    )
    if ($code -ne 0) { throw "git commit failed with exit code $code" }

    $ssh = 'C:\Windows\System32\OpenSSH\ssh.exe'
    $key = 'C:\ProgramData\VivaMK\ssh\github_deploy_ed25519'
    $known = 'C:\ProgramData\VivaMK\ssh\known_hosts'
    $sshCommand = "`"$ssh`" -i `"$key`" -o IdentitiesOnly=yes -o UserKnownHostsFile=`"$known`" -o StrictHostKeyChecking=yes"

    Log "Attempting push with process-local SYSTEM deploy key..."
    $code = Run-Git @(
        "push",
        "git@github.com:stevegiergiel/VIVAMK_Clearance_Booklet.git",
        "HEAD:main"
    ) $sshCommand

    if ($code -ne 0) { throw "git push failed with exit code $code" }

    Log "SUCCESS: v2.16.3 SYSTEM isolated SSH push works while normal origin remains HTTPS."
    exit 0
}
catch {
    Log "FAIL: $($_.Exception.Message)"
    exit 1
}
