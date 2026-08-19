# sting_04_contact.ps1 -- extract contact frames from the DELIVERED mp4 and build sheets.
$ErrorActionPreference = "Stop"
$FF = "C:\ffmpeg\ffmpeg.exe"
$R  = "C:\Users\natha\Projects\boyd-clips\research\blender\renders"
$C  = "$R\contact"
$T  = "$R\contact\_tiles"
$FONT = "C\:/Users/natha/Projects/boyd-clips/assets/fonts/BebasNeue-Regular.ttf"
New-Item -ItemType Directory -Force $C | Out-Null
New-Item -ItemType Directory -Force $T | Out-Null
Get-ChildItem "$T\*.png" -ErrorAction SilentlyContinue | Remove-Item -Force

# --- SET A: 6 evenly spaced frames across the 84-frame piece (as briefed) -----------
# round(1 + i*83/5) for i=0..5
$even = @(1, 18, 34, 51, 67, 84)
# --- SET B: 6 beat-aligned frames, because evenly-spaced puts 4 of 6 inside the
#            35-frame dead hold and shows almost none of the build.
$beats = @(24, 25, 30, 36, 42, 49)
$beatlabels = @{24="f24 BEAT A end - ground+grain only"; 25="f25 BEAT B1 star hard-cut on";
                30="f30 B2/B3 fade + shear"; 36="f36 B2 end - alpha 1.0";
                42="f42 B3 settling"; 49="f49 BEAT C - LOCK"}

function Extract($frames, $prefix) {
  foreach ($f in $frames) {
    $n = $f - 1
    & $FF -v error -y -i "$R\sting.mp4" -vf "select=eq(n\,$n)" -vframes 1 `
        "$C\$prefix`_f$('{0:d4}' -f $f).png"
    if ($LASTEXITCODE -ne 0) { throw "extract failed f$f" }
  }
}

function BuildSheet($frames, $labels, $out, $title) {
  Get-ChildItem "$T\*.png" -ErrorAction SilentlyContinue | Remove-Item -Force
  $i = 1
  foreach ($f in $frames) {
    $lab = $labels[$f]
    $src = Get-ChildItem "$C\*_f$('{0:d4}' -f $f).png" | Select-Object -First 1
    # 620x349 image inside a 640x400 tile: 1px rule, label bar underneath
    & $FF -v error -y -i $src.FullName -vf `
      "scale=620:349,pad=640:400:10:6:0x0A0C10,drawbox=x=10:y=6:w=620:h=349:color=0x2A2F38:t=1,drawtext=fontfile='$FONT':text='$lab':fontcolor=0xF2EEE3:fontsize=26:x=12:y=364" `
      "$T\t_$('{0:d3}' -f $i).png"
    if ($LASTEXITCODE -ne 0) { throw "tile failed f$f" }
    $i++
  }
  # 3 x 2 grid -> 1920 x 800, then a 70px title bar on top
  & $FF -v error -y -i "$T\t_%03d.png" -vf "tile=3x2" -frames:v 1 "$T\grid.png"
  if ($LASTEXITCODE -ne 0) { throw "tile filter failed" }
  & $FF -v error -y -i "$T\grid.png" -vf `
    "pad=1920:872:0:72:0x0A0C10,drawtext=fontfile='$FONT':text='$title':fontcolor=0xF2EEE3:fontsize=40:x=16:y=14,drawbox=x=0:y=68:w=1920:h=3:color=0xD42B2B:t=fill" `
    $out
  if ($LASTEXITCODE -ne 0) { throw "title failed" }
  Write-Host "wrote $out"
}

Extract $even  "even"
Extract $beats "beat"

$evenlabels = @{}
foreach ($f in $even) {
  $ms = [math]::Round(($f - 1) / 60.0 * 1000)
  $evenlabels[$f] = "f$f   $ms ms"
}
BuildSheet $even  $evenlabels "$R\contact\contact_sheet.png" `
  "TEXAS TRIAL TRACKER - STING T2 - 6 EVENLY SPACED FRAMES - 1920x1080 60fps 84f 1.400s"
BuildSheet $beats $beatlabels "$R\contact\contact_sheet_beats.png" `
  "TEXAS TRIAL TRACKER - STING T2 - BEAT-ALIGNED FRAMES (the build, which even spacing misses)"

Remove-Item -Recurse -Force $T
Get-ChildItem "$C" | Select-Object Name, Length | Format-Table -AutoSize
