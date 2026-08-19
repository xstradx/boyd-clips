# =============================================================================
#  BOYD TRAY  --  a live on/off switch in the system tray, next to Bluetooth.
#
#  GREEN dot  = RUNNING   (the pipeline may work, download, encode)
#  RED dot    = PAUSED    (everything frozen; GPU and CPU are yours)
#
#  LEFT-CLICK the icon to flip it. That is the whole interface.
#  RIGHT-CLICK for a menu (open the finished-clips folder, quit).
#
#  Work is SUSPENDED, never killed, so a half-finished download or a
#  half-finished encode resumes from exactly where it stopped.
#
#  Start it: tools\install-tray.ps1  (installs it to run at every login)
# =============================================================================

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Root      = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StateFile = Join-Path $Root 'state\paused.flag'
$ReviewDir = Join-Path $Root 'out\review'
$TaskName  = 'BoydClips'

# --- Win32 suspend/resume -----------------------------------------------------
# NtSuspendProcess freezes every thread in a process and leaves its memory
# intact. This is the primitive Process Explorer's "Suspend" uses.
if (-not ('BoydNative' -as [type])) {
    Add-Type -Namespace '' -Name 'BoydNative' -MemberDefinition @'
[DllImport("ntdll.dll", SetLastError=true)] public static extern uint NtSuspendProcess(IntPtr h);
[DllImport("ntdll.dll", SetLastError=true)] public static extern uint NtResumeProcess(IntPtr h);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint a, bool i, int pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
'@
}
$PROCESS_SUSPEND_RESUME = 0x0800

# Only these are ever frozen. See the safety note in Get-BoydProcesses.
$SAFE_NAMES = @('python.exe','pythonw.exe','ffmpeg.exe','ffprobe.exe',
                'yt-dlp.exe','claude.exe','node.exe')

function Invoke-OnProcess {
    # Not $Pid — that is a PowerShell automatic variable and binding a
    # parameter to it is a hard parse error.
    param([int]$TargetPid, [ValidateSet('Suspend','Resume')][string]$Action)
    $h = [BoydNative]::OpenProcess($PROCESS_SUSPEND_RESUME, $false, $TargetPid)
    if ($h -eq [IntPtr]::Zero) { return $false }
    try {
        if ($Action -eq 'Suspend') { [void][BoydNative]::NtSuspendProcess($h) }
        else                       { [void][BoydNative]::NtResumeProcess($h)  }
        return $true
    } finally { [void][BoydNative]::CloseHandle($h) }
}

function Get-SelfAndAncestors {
    param($AllProcs)
    $map = @{}
    foreach ($p in $AllProcs) { $map[[int]$p.ProcessId] = [int]$p.ParentProcessId }
    $protected = @{}
    $cur = $PID
    for ($i = 0; $i -lt 64 -and $cur -and $map.ContainsKey($cur); $i++) {
        $protected[$cur] = $true
        $cur = $map[$cur]
    }
    if ($cur) { $protected[$cur] = $true }
    return $protected
}

function Get-BoydProcesses {
    # TWO HARD SAFETY RULES, both learned by breaking this on 2026-08-14:
    #
    #   1. Never suspend this process or any ancestor of it. The first
    #      version matched "command line contains the boyd-clips path" —
    #      and this script's own path contains it, so the toggle froze
    #      ITSELF mid-flip and had to be thawed by hand.
    #   2. Only suspend process NAMES the pipeline actually uses. Matching
    #      on path alone also caught unrelated shells that merely had the
    #      folder open. With an allowlist the worst case is "missed one",
    #      never "froze his desktop".
    $all = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,CommandLine
    $protected = Get-SelfAndAncestors -AllProcs $all

    $roots = $all | Where-Object {
        $_.CommandLine -and
        ($SAFE_NAMES -contains $_.Name) -and
        -not $protected.ContainsKey([int]$_.ProcessId) -and
        ($_.CommandLine -match 'boydclips' -or $_.CommandLine -match [regex]::Escape($Root))
    }

    $found = @{}
    foreach ($r in $roots) { $found[[int]$r.ProcessId] = $r }

    # Walk down the tree until nothing new appears. ffmpeg is usually a
    # grandchild (python -> yt-dlp -> ffmpeg), so one pass is not enough.
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $all) {
            $ppid  = [int]$p.ParentProcessId
            $mypid = [int]$p.ProcessId
            if ($found.ContainsKey($ppid) -and -not $found.ContainsKey($mypid) `
                -and -not $protected.ContainsKey($mypid)) {
                $found[$mypid] = $p
                $changed = $true
            }
        }
    }
    return @($found.Values)
}

# --- Icon: a coloured dot drawn at runtime, so there are no icon files -------
function New-DotIcon {
    param([System.Drawing.Color]$Fill)
    $bmp = New-Object System.Drawing.Bitmap 32,32
    $g   = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)
    $brush = New-Object System.Drawing.SolidBrush $Fill
    $g.FillEllipse($brush, 3, 3, 26, 26)
    # A dark rim keeps the dot legible on a light taskbar.
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(190,15,15,15)), 2.5
    $g.DrawEllipse($pen, 3, 3, 26, 26)
    $g.Dispose(); $brush.Dispose(); $pen.Dispose()
    $h = $bmp.GetHicon()
    $ico = [System.Drawing.Icon]::FromHandle($h).Clone()
    $bmp.Dispose()
    return $ico
}

$IconRunning = New-DotIcon ([System.Drawing.Color]::FromArgb(255, 46, 204, 90))
$IconPaused  = New-DotIcon ([System.Drawing.Color]::FromArgb(255, 235, 64,  52))

# --- The switch itself --------------------------------------------------------
$script:Notify = New-Object System.Windows.Forms.NotifyIcon

function Update-Ui {
    param([switch]$Announce)
    $paused = Test-Path $StateFile
    if ($paused) {
        $script:Notify.Icon = $IconPaused
        $script:Notify.Text = "Boyd Clips: PAUSED - click to resume"
        $script:MenuToggle.Text = "Resume Boyd Clips"
    } else {
        $script:Notify.Icon = $IconRunning
        $script:Notify.Text = "Boyd Clips: RUNNING - click to pause"
        $script:MenuToggle.Text = "Pause Boyd Clips (free the GPU)"
    }
    if ($Announce) {
        $script:Notify.BalloonTipTitle = if ($paused) { "Boyd Clips PAUSED" } else { "Boyd Clips RUNNING" }
        $script:Notify.BalloonTipText  = $script:LastMessage
        $script:Notify.ShowBalloonTip(3000)
    }
}

function Invoke-Toggle {
    $paused = Test-Path $StateFile
    $procs  = Get-BoydProcesses
    $n = 0

    if (-not $paused) {
        # Children first: suspending a parent first can leave a child
        # briefly writing into a pipe nobody is reading.
        foreach ($p in ($procs | Sort-Object ParentProcessId -Descending)) {
            if (Invoke-OnProcess -TargetPid ([int]$p.ProcessId) -Action 'Suspend') { $n++ }
        }
        try { Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch {}
        New-Item -ItemType File -Path $StateFile -Force | Out-Null
        Set-Content -Path $StateFile -Value (Get-Date -Format 'o')
        $script:LastMessage = "$n frozen. Nothing lost - it resumes where it stopped."
    }
    else {
        # Parents first on the way back up, so a resumed child always has a
        # live parent reading its output.
        foreach ($p in ($procs | Sort-Object ParentProcessId)) {
            if (Invoke-OnProcess -TargetPid ([int]$p.ProcessId) -Action 'Resume') { $n++ }
        }
        try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch {}
        Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
        $script:LastMessage = "$n resumed from exactly where they stopped."
    }
    Update-Ui -Announce
}

# --- Menu ---------------------------------------------------------------------
$menu = New-Object System.Windows.Forms.ContextMenuStrip

$script:MenuToggle = $menu.Items.Add("Pause Boyd Clips (free the GPU)")
$script:MenuToggle.Add_Click({ Invoke-Toggle })

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$mOpen = $menu.Items.Add("Open finished clips folder")
$mOpen.Add_Click({
    if (-not (Test-Path $ReviewDir)) { New-Item -ItemType Directory -Force -Path $ReviewDir | Out-Null }
    Start-Process explorer.exe $ReviewDir
})

$mStatus = $menu.Items.Add("Show what is running")
$mStatus.Add_Click({
    $p = Get-BoydProcesses
    $body = if ($p.Count -eq 0) { "Nothing is running right now." }
            else { ($p | ForEach-Object { "$($_.Name)  (pid $($_.ProcessId))" }) -join "`n" }
    [System.Windows.Forms.MessageBox]::Show($body, "Boyd Clips - running processes") | Out-Null
})

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$mExit = $menu.Items.Add("Quit this switch")
$mExit.Add_Click({
    # Never leave the pipeline frozen with no way to unfreeze it from the UI.
    if (Test-Path $StateFile) {
        foreach ($p in (Get-BoydProcesses | Sort-Object ParentProcessId)) {
            [void](Invoke-OnProcess -TargetPid ([int]$p.ProcessId) -Action 'Resume')
        }
        try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch {}
        Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    }
    $script:Notify.Visible = $false
    $script:Notify.Dispose()
    [System.Windows.Forms.Application]::Exit()
})

$script:Notify.ContextMenuStrip = $menu
$script:Notify.Visible = $true
$script:LastMessage = ""

# Left-click anywhere on the icon flips it. Right-click opens the menu.
$script:Notify.Add_MouseClick({
    param($sender, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Invoke-Toggle }
})

# Re-sync the icon periodically so it stays truthful if the flag file is
# changed by something other than this switch.
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.Add_Tick({ Update-Ui })
$timer.Start()

Update-Ui
[System.Windows.Forms.Application]::Run((New-Object System.Windows.Forms.ApplicationContext))
