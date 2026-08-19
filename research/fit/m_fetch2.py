import os, json, time, random, subprocess, sys
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
SUB = "research/reference/courtroomtime/subs"
segs = json.load(open("research/fit/segments.json"))
have = {f.split(".")[0] for f in os.listdir(SUB) if f.endswith(".vtt")}
want = sorted({s["vid"] for s in segs} - have)
print("need", len(want), flush=True)
ok = err = 0
for i, vid in enumerate(want):
    cmd = [sys.executable, "-m", "yt_dlp", "--write-auto-subs", "--sub-lang", "en",
           "--skip-download", "--sub-format", "vtt", "--no-warnings", "-q",
           "-o", SUB + "/%(id)s.%(ext)s",
           "https://www.youtube.com/watch?v=" + vid]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        got = any(f.startswith(vid) and f.endswith(".vtt") for f in os.listdir(SUB))
        ok, err = (ok + 1, err) if got else (ok, err + 1)
        print("[%d/%d] %s %s" % (i + 1, len(want), "OK  " if got else "MISS", vid), flush=True)
    except Exception as e:
        err += 1
        print("[%d/%d] FAIL %s %s" % (i + 1, len(want), vid, e), flush=True)
    time.sleep(random.uniform(5.0, 9.0))
print("DONE ok", ok, "err", err, flush=True)
