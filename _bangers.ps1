Set-Location "C:\Users\natha\Projects\boyd-clips"
$dest = "D:\Boyd Clips\BANGERS"
$picks = @(
 @("RzjGikNbHMA:8485","01_McCaskill_smell_like_marijuana"),
 @("MiNisjOh61c:2309","02_JoeGarcia_2yrs"),
 @("JjRfzudxY1w:4468","03_Terry_71yo"),
 @("H_hXwF2dl7E:5383","04_DiamondGarcia"),
 @("qSyaR2dc_WU:8644","05_Aguilar_5yrs"),
 @("JjRfzudxY1w:345","06_Wilson_1.4TB"),
 @("JjRfzudxY1w:6142","07_Carvajal_4th_revoke"),
 @("X4fifbLpvYs:10421","08_Escobar_wrong_charge"),
 @("UtydTa4kZhk:4072","09_Ganal_custody"),
 @("m9CleqGwqKk:8346","10_JoeGonzalezIV")
)
"START $(Get-Date -f 'HH:mm:ss')  (intro + watermark + graded thumb)" | Out-File -Encoding utf8 logs\bangers.log
foreach ($pk in $picks) {
  $k=$pk[0]; $label=$pk[1]; $safe=$k -replace ':','_'
  "--- $label ($k) $(Get-Date -f 'HH:mm:ss')" | Out-File -Append -Encoding utf8 logs\bangers.log
  $before = Get-ChildItem out\review -Directory -ErrorAction SilentlyContinue | Select-Object -Expand FullName
  $p = Start-Process python -ArgumentList "-u","-m","boydclips.cli","run","--case",$k -RedirectStandardOutput "logs\b_$safe.log" -RedirectStandardError "logs\b_$safe.err" -NoNewWindow -PassThru
  $p | Wait-Process -Timeout 1500 -ErrorAction SilentlyContinue
  if (-not $p.HasExited) {
    $p.Kill(); Start-Sleep 2
    Get-Process yt-dlp,ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    "    TIMEOUT skipped" | Out-File -Append -Encoding utf8 logs\bangers.log; continue
  }
  $new = Get-ChildItem out\review -Directory | Where-Object { $before -notcontains $_.FullName }
  foreach ($d in $new) {
    if (Test-Path (Join-Path $d.FullName "longform.mp4")) { Copy-Item (Join-Path $d.FullName "longform.mp4") (Join-Path $dest "$label.mp4") -Force }
    if (Test-Path (Join-Path $d.FullName "short.mp4")) { Copy-Item (Join-Path $d.FullName "short.mp4") (Join-Path $dest ($label + "_SHORT.mp4")) -Force }
    if (Test-Path (Join-Path $d.FullName "thumbnail_quote.jpg")) { Copy-Item (Join-Path $d.FullName "thumbnail_quote.jpg") (Join-Path $dest "$label.jpg") -Force }
    "    copied $label" | Out-File -Append -Encoding utf8 logs\bangers.log
  }
}
"DONE $(Get-Date -f 'HH:mm:ss')" | Out-File -Append -Encoding utf8 logs\bangers.log
