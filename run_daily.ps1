# Daily driver for the existing Codex Boyd Daily Production automation.
# Keep one scheduler. -PreflightOnly checks recovered structure without production.
#
# 19:40 is deliberate: afternoon dockets finish and YouTube's auto-captions
# usually land within a few hours of the stream ending. Running earlier means
# processing a docket whose captions are not ready yet.

param([switch]$PreflightOnly)

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

$Mutex = [System.Threading.Mutex]::new($false, 'Global\BoydClipsDaily')
$HasLock = $false

try {
    $HasLock = $Mutex.WaitOne(0)
    if (-not $HasLock) { throw "another Boyd daily run is already active" }

    $ErrorActionPreference = 'Continue'
    python tools/check_recovery_structure.py 2>&1 | Tee-Object -FilePath $Log -Append
    $StructureExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($StructureExit -ne 0) { throw "recovery structure check failed; resolve reported drift before production" }
    if ($PreflightOnly) {
        Write-Log "=== structure preflight complete; no production requested ==="
        exit 0
    }

    # Python logging writes normal INFO lines to stderr. Windows PowerShell
    # turns redirected native stderr into ErrorRecord objects, and with Stop
    # that used to abort a healthy run on its first INFO line.
    $ErrorActionPreference = 'Continue'
    python -m boydclips.cli doctor 2>&1 | Tee-Object -FilePath $Log -Append
    $DoctorExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($DoctorExit -ne 0) { throw "doctor reported an unhealthy environment" }

    $ErrorActionPreference = 'Continue'
    python -m boydclips.cli run 2>&1 | Tee-Object -FilePath $Log -Append
    $PipelineExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($PipelineExit -ne 0) { throw "pipeline exited $PipelineExit" }

    Write-Log "=== run complete ==="
    exit 0
} catch {
    Write-Log "FAILED: $_"
    exit 1
} finally {
    if ($HasLock) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
