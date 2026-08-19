Set-Location "C:\Users\natha\Projects\boyd-clips"
"=== PENA oL6lV6gCyOc:3047 ===" | Out-File -Encoding utf8 logs\render_pair.log
python -u -m boydclips.cli run --case oL6lV6gCyOc:3047 *>> logs\render_pair.log
"=== BLACKBURN UXSXYgPa_bY:6900 ===" | Out-File -Append -Encoding utf8 logs\render_pair.log
python -u -m boydclips.cli run --case UXSXYgPa_bY:6900 *>> logs\render_pair.log
"=== DONE ===" | Out-File -Append -Encoding utf8 logs\render_pair.log
