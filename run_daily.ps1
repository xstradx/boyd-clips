# Daily driver. Register with Task Scheduler:
#
#   schtasks /create /tn "BoydClips" /sc daily /st 19:40 /f `
#     /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\natha\Projects\boyd-clips\run_daily.ps1"
#
# 19:40 is deliberate: afternoon dockets finish and YouTube's auto-captions
# usually land within a few hours of the stream ending. Running earlier means
# processing a docket whose captions are not ready yet.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("run_{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

function Write-Log { param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
    $line | Tee-Object -FilePath $Log -Append
}

Write-Log "=== boyd-clips daily run ==="

# Keep yt-dlp current. YouTube changes extraction regularly and a stale
# yt-dlp is by far the most common cause of a silent overnight failure.
try {
    python -m pip install --quiet --upgrade yt-dlp 2>&1 | Out-Null
    Write-Log "yt-dlp updated"
} catch {
    Write-Log "WARN: yt-dlp update failed: $_"
}

try {
    python -m boydclips.cli doctor 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { throw "doctor reported an unhealthy environment" }

    python -m boydclips.cli run 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { throw "pipeline exited $LASTEXITCODE" }

    Write-Log "=== run complete ==="
    exit 0
} catch {
    Write-Log "FAILED: $_"
    exit 1
}
