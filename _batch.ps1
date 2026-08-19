Set-Location "C:\Users\natha\Projects\boyd-clips"
$keys = @("SPSHGzlOe8c:753","SPSHGzlOe8c:4540","SPSHGzlOe8c:2623","0siAjhcOQF8:2658","UtydTa4kZhk:4072","UtydTa4kZhk:10098")
"START $(Get-Date -f HH:mm:ss)" | Out-File -Encoding utf8 logs\batch.log
foreach ($k in $keys) {
  $safe = $k -replace ':','_'
  "--- $k  $(Get-Date -f HH:mm:ss)" | Out-File -Append -Encoding utf8 logs\batch.log
  $p = Start-Process python -ArgumentList "-u","-m","boydclips.cli","run","--case",$k `
        -RedirectStandardOutput "logs\r_$safe.log" -RedirectStandardError "logs\r_$safe.err" `
        -NoNewWindow -PassThru
  $p | Wait-Process -Timeout 1200 -ErrorAction SilentlyContinue
  if (-not $p.HasExited) {
    $p.Kill(); Start-Sleep 2
    Get-Process yt-dlp,ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    "    TIMEOUT killed after 20m" | Out-File -Append -Encoding utf8 logs\batch.log
  } else {
    "    exit $($p.ExitCode)  $(Get-Date -f HH:mm:ss)" | Out-File -Append -Encoding utf8 logs\batch.log
  }
}
"DONE $(Get-Date -f HH:mm:ss)" | Out-File -Append -Encoding utf8 logs\batch.log
