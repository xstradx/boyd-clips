# -*- coding: utf-8 -*-
import os, sys, time, subprocess, random
TOP = "ERPX6JpX5OU _-WRN7q01OY rcub_Jev9NE 6Tp2eiBjGB8 urZza-9kdP0 ePdAxp1Zs8Y aH0fnO4w-dg lfAlCDsEQZ4".split()
BOT = "q1Fo7x_0ItI bQjZEqsESqE xUmB4XrFi3g 9ab4YTSQI-8 RfF0ouKeE0w 79nw7lP0jm0".split()
OUT = r"research/reference/courtroomtime/subs"
os.makedirs(OUT, exist_ok=True)
ids = TOP + BOT
for i, vid in enumerate(ids):
    done = [f for f in os.listdir(OUT) if f.startswith(vid)]
    if done:
        print("SKIP", vid, done); sys.stdout.flush(); continue
    cmd = [sys.executable, "-m", "yt_dlp", "--write-auto-subs", "--sub-lang", "en",
           "--skip-download", "--sub-format", "vtt", "--no-warnings",
           "-o", OUT + "/%(id)s.%(ext)s",
           "https://www.youtube.com/watch?v=" + vid]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(vid, "rc=", r.returncode)
    print((r.stdout or "")[-500:])
    print((r.stderr or "")[-500:])
    sys.stdout.flush()
    time.sleep(random.uniform(8, 14))
print("FILES:", sorted(os.listdir(OUT)))
