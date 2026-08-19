# =============================================================================
#  Installs the Boyd tray switch:
#    1. a hidden launcher (no console window ever flashes)
#    2. a Startup shortcut, so it is there after every reboot
#    3. pins it to the visible tray next to Bluetooth, rather than letting
#       Windows 11 bury it in the "^" overflow drawer
#    4. starts it now
#
#  Run once:  powershell -ExecutionPolicy Bypass -File tools\install-tray.ps1
# =============================================================================

$ErrorActionPreference = 'Stop'
$Tools   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root    = Split-Path -Parent $Tools
$Tray    = Join-Path $Tools 'boyd-tray.ps1'
$Vbs     = Join-Path $Tools 'boyd-tray-hidden.vbs'
$Startup = [Environment]::GetFolderPath('Startup')
$Link    = Join-Path $Startup 'Boyd Clips Switch.lnk'

# Prefer PowerShell 7 if present; fall back to Windows PowerShell.
$Pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $Pwsh) { $Pwsh = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe' }

# --- 1. Hidden launcher -------------------------------------------------------
# -WindowStyle Hidden still flashes a console for a split second. WScript.Shell
# with intWindowStyle 0 does not show one at all.
$vbsBody = @"
' Launches the Boyd tray switch with no console window at all.
Set sh = CreateObject("WScript.Shell")
sh.Run """$Pwsh"" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$Tray""", 0, False
"@
Set-Content -Path $Vbs -Value $vbsBody -Encoding ASCII
Write-Host "  [ok] hidden launcher  $Vbs"

# --- 2. Startup shortcut ------------------------------------------------------
$wsh = New-Object -ComObject WScript.Shell
$sc  = $wsh.CreateShortcut($Link)
$sc.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
$sc.Arguments        = """$Vbs"""
$sc.WorkingDirectory = $Root
$sc.Description      = "Pause / resume Boyd Clips from the system tray"
$sc.Save()
Write-Host "  [ok] starts at login  $Link"

# --- 3. Stop anything already running, then start fresh ----------------------
Get-CimInstance Win32_Process -Property ProcessId,CommandLine |
    Where-Object { $_.CommandLine -match 'boyd-tray\.ps1' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }
Start-Sleep -Milliseconds 500

Start-Process wscript.exe -ArgumentList """$Vbs""" -WorkingDirectory $Root
Write-Host "  [ok] switch started"

# --- 4. Promote it out of the overflow drawer --------------------------------
# Windows 11 hides new tray icons behind the "^" chevron. Each icon gets a key
# under HKCU\Control Panel\NotifyIconSettings; IsPromoted = 1 means "show on
# the taskbar itself". The key only exists once the icon has been shown, so
# this has to run after the app is up.
Write-Host "  ... waiting for the icon to register"
$promoted = $false
foreach ($attempt in 1..12) {
    Start-Sleep -Seconds 2
    $base = 'HKCU:\Control Panel\NotifyIconSettings'
    if (-not (Test-Path $base)) { continue }
    foreach ($k in Get-ChildItem $base -ErrorAction SilentlyContinue) {
        $exe = (Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue).ExecutablePath
        if ($exe -and ($exe -match 'pwsh\.exe|powershell\.exe')) {
            Set-ItemProperty -Path $k.PSPath -Name 'IsPromoted' -Value 1 -Type DWord -Force
            $promoted = $true
        }
    }
    if ($promoted) { break }
}

if ($promoted) {
    # Deliberately NOT restarting explorer.exe here — that would close every
    # File Explorer window he has open, to save one manual step. Windows
    # normally picks the setting up on its own within a few seconds.
    Write-Host "  [ok] pinned to the visible tray"
} else {
    Write-Host "  [!!] could not auto-pin it. Do this once by hand:"
    Write-Host "       Settings > Personalization > Taskbar > Other system tray icons"
    Write-Host "       and switch ON the entry for PowerShell."
}

Write-Host ""
Write-Host "  Done. Look at the bottom-right of your taskbar:"
Write-Host "     GREEN dot = running     RED dot = paused"
Write-Host "     Left-click it to flip. Right-click for the menu."
