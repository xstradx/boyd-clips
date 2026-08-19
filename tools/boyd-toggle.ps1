# =============================================================================
#  BOYD TOGGLE  --  one switch that pauses everything, and resumes it exactly
#  where it left off.
#
#  Double-click the Desktop shortcut. It flips:
#     RUNNING  ->  PAUSED   (freezes work, frees the GPU/CPU for games)
#     PAUSED   ->  RUNNING  (unfreezes, picks up mid-download / mid-encode)
#
#  It SUSPENDS processes rather than killing them, so a half-finished
#  download or a half-finished ffmpeg encode is not thrown away. Windows
#  keeps them in memory, using no CPU, until resumed.
#
#  It only ever touches processes that belong to boyd-clips. Nathan has a
#  dozen unrelated python.exe running; those are matched by command line and
#  left alone.
# =============================================================================

$ErrorActionPreference = 'Stop'
$Root      = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StateFile = Join-Path $Root 'state\paused.flag'
$TaskName  = 'BoydClips'

# --- Win32: suspend/resume a whole process, not just a thread -----------------
# NtSuspendProcess is the same primitive Process Explorer's "Suspend" uses.
if (-not ('BoydNative' -as [type])) {
    Add-Type -Namespace '' -Name 'BoydNative' -MemberDefinition @'
[DllImport("ntdll.dll", SetLastError=true)] public static extern uint NtSuspendProcess(IntPtr h);
[DllImport("ntdll.dll", SetLastError=true)] public static extern uint NtResumeProcess(IntPtr h);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint a, bool i, int pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
'@
}
$PROCESS_SUSPEND_RESUME = 0x0800

function Invoke-OnProcess {
    # NOTE: not $Pid — that is a PowerShell automatic variable and binding a
    # parameter to it is a hard error at parse time.
    param([int]$TargetPid, [ValidateSet('Suspend','Resume')][string]$Action)
    $h = [BoydNative]::OpenProcess($PROCESS_SUSPEND_RESUME, $false, $TargetPid)
    if ($h -eq [IntPtr]::Zero) { return $false }
    try {
        if ($Action -eq 'Suspend') { [void][BoydNative]::NtSuspendProcess($h) }
        else                       { [void][BoydNative]::NtResumeProcess($h)  }
        return $true
    } finally { [void][BoydNative]::CloseHandle($h) }
}

# --- Find only OUR processes --------------------------------------------------
# Two passes: python running boydclips, then anything it spawned (yt-dlp,
# ffmpeg, the claude CLI) found by walking ParentProcessId.
#
# TWO HARD SAFETY RULES, both learned by breaking it on 2026-08-14:
#
#   1. NEVER suspend this script's own process or any of its ancestors.
#      The first version matched on "command line contains the boyd-clips
#      path" — and this script's own path contains it, so the toggle froze
#      ITSELF mid-run and had to be thawed by hand. It also caught the
#      terminal that launched it.
#
#   2. Only ever suspend process names the pipeline actually uses. Matching
#      on path alone caught unrelated shells that merely had the folder open.
#      An allowlist means the worst case is "missed something", never
#      "froze his desktop".
$SAFE_NAMES = @('python.exe','pythonw.exe','ffmpeg.exe','ffprobe.exe',
                'yt-dlp.exe','claude.exe','node.exe')

function Get-SelfAndAncestors {
    param($AllProcs)
    $map = @{}
    foreach ($p in $AllProcs) { $map[[int]$p.ProcessId] = [int]$p.ParentProcessId }
    $protected = @{}
    $cur = $PID
    # Bounded walk — a corrupt parent chain must not spin forever.
    for ($i = 0; $i -lt 64 -and $cur -and $map.ContainsKey($cur); $i++) {
        $protected[$cur] = $true
        $cur = $map[$cur]
    }
    if ($cur) { $protected[$cur] = $true }
    return $protected
}

function Get-BoydProcesses {
    $all = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,CommandLine
    $protected = Get-SelfAndAncestors -AllProcs $all

    $roots = $all | Where-Object {
        $_.CommandLine -and
        ($SAFE_NAMES -contains $_.Name) -and
        -not $protected.ContainsKey([int]$_.ProcessId) -and (
            $_.CommandLine -match 'boydclips' -or
            $_.CommandLine -match [regex]::Escape($Root)
        )
    }

    $found = @{}
    foreach ($r in $roots) { $found[[int]$r.ProcessId] = $r }

    # Walk down the tree until nothing new appears — ffmpeg is often a
    # grandchild (python -> yt-dlp -> ffmpeg), so one pass is not enough.
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $all) {
            $ppid = [int]$p.ParentProcessId
            $mypid = [int]$p.ProcessId
            if ($found.ContainsKey($ppid) -and -not $found.ContainsKey($mypid)) {
                $found[$mypid] = $p
                $changed = $true
            }
        }
    }
    return $found.Values
}

# --- Decide which way we are flipping ----------------------------------------
$isPaused = Test-Path $StateFile

if (-not $isPaused) {
    # ---------------- PAUSE ----------------
    $procs = @(Get-BoydProcesses)
    $n = 0
    # Children first, parents last: suspending the parent first can leave a
    # child briefly hammering the disk with no one reading its output.
    foreach ($p in ($procs | Sort-Object ParentProcessId -Descending)) {
        if (Invoke-OnProcess -TargetPid ([int]$p.ProcessId) -Action 'Suspend') { $n++ }
    }

    # Stop tonight's scheduled run from starting while he's mid-game.
    try { Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch {}

    New-Item -ItemType File -Path $StateFile -Force | Out-Null
    Set-Content -Path $StateFile -Value (Get-Date -Format 'o')

    $state = 'PAUSED'
    $msg   = "$n process(es) frozen. GPU and CPU are yours. Nothing was lost."
    $color = 'Yellow'
}
else {
    # ---------------- RESUME ----------------
    $procs = @(Get-BoydProcesses)
    $n = 0
    # Parents first on the way back up, so a resumed child always has a
    # live parent reading its pipe.
    foreach ($p in ($procs | Sort-Object ParentProcessId)) {
        if (Invoke-OnProcess -TargetPid ([int]$p.ProcessId) -Action 'Resume') { $n++ }
    }

    try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch {}

    Remove-Item $StateFile -Force -ErrorAction SilentlyContinue

    $state = 'RUNNING'
    $msg   = "$n process(es) resumed from exactly where they stopped."
    $color = 'Green'
}

# --- Tell him, unmissably ----------------------------------------------------
Write-Host ""
Write-Host "  ############################################" -ForegroundColor $color
Write-Host "  #                                          #" -ForegroundColor $color
Write-Host ("  #        BOYD CLIPS IS {0,-8}           #" -f $state) -ForegroundColor $color
Write-Host "  #                                          #" -ForegroundColor $color
Write-Host "  ############################################" -ForegroundColor $color
Write-Host ""
Write-Host "  $msg"
Write-Host ""
Write-Host "  Run this again to flip it back."
Write-Host ""

# A tray notification too, so it is obvious even if the window is behind a game.
try {
    Add-Type -AssemblyName System.Windows.Forms
    $ni = New-Object System.Windows.Forms.NotifyIcon
    $ni.Icon = [System.Drawing.SystemIcons]::Information
    $ni.BalloonTipTitle = "Boyd Clips - $state"
    $ni.BalloonTipText  = $msg
    $ni.Visible = $true
    $ni.ShowBalloonTip(4000)
    Start-Sleep -Milliseconds 4200
    $ni.Dispose()
} catch {}

Start-Sleep -Seconds 2
