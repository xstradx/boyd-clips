' Launches the Boyd tray switch with no console window at all.
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Program Files\PowerShell\7\pwsh.exe"" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\natha\Projects\boyd-clips\tools\boyd-tray.ps1""", 0, False
