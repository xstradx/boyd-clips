Set-Location "C:\Users\natha\Projects\boyd-clips"
$keys = @("MiNisjOh61c:2309","JjRfzudxY1w:4468","H_hXwF2dl7E:5383","qSyaR2dc_WU:8644","JjRfzudxY1w:345","JjRfzudxY1w:6142","X4fifbLpvYs:10421","UtydTa4kZhk:4072","m9CleqGwqKk:8346")
"RESTYLE START $(Get-Date -f 'HH:mm:ss')" | Out-File -Encoding utf8 logs\restyle.log
foreach ($k in $keys) {
  $safe = $k -replace ':','_'
  "--- $k $(Get-Date -f 'HH:mm:ss')" | Out-File -Append -Encoding utf8 logs\restyle.log
  $p = Start-Process python -ArgumentList "-u","-m","boydclips.cli","run","--case",$k -RedirectStandardOutput "logs\rs_$safe.log" -RedirectStandardError "logs\rs_$safe.err" -NoNewWindow -PassThru
  $p | Wait-Process -Timeout 1500 -ErrorAction SilentlyContinue
  if (-not $p.HasExited) { $p.Kill(); Start-Sleep 2; Get-Process yt-dlp,ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "    TIMEOUT" | Out-File -Append -Encoding utf8 logs\restyle.log }
}
python scripts\collect_bangers.py *>> logs\restyle.log
"RESTYLE DONE $(Get-Date -f 'HH:mm:ss')" | Out-File -Append -Encoding utf8 logs\restyle.log
