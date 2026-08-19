import os, json, time, random, subprocess, sys
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
SUB = "research/reference/courtroomtime/subs"
plan = json.load(open("research/fit/plan.json"))
ok = err = skip = 0
for i, r in enumerate(plan):
    vid = r["id"]
    if any(f.startswith(vid) and f.endswith(".vtt") for f in os.listdir(SUB)):
        skip += 1
        continue
    cmd = [sys.executable, "-m", "yt_dlp", "--write-auto-subs", "--sub-lang", "en",
           "--skip-download", "--sub-format", "vtt", "--no-warnings", "-q",
           "-o", SUB + "/%(id)s.%(ext)s",
           "https://www.youtube.com/watch?v=" + vid]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        got = any(f.startswith(vid) and f.endswith(".vtt") for f in os.listdir(SUB))
        if got:
            ok += 1
            print(f"[{i+1}/{len(plan)}] OK   {vid} {r['views']}", flush=True)
        else:
            err += 1
            print(f"[{i+1}/{len(plan)}] MISS {vid} {(p.stderr or '')[:120]}", flush=True)
    except Exception as e:
        err += 1
        print(f"[{i+1}/{len(plan)}] FAIL {vid} {e}", flush=True)
    time.sleep(random.uniform(6.0, 11.0))
print("DONE ok", ok, "err", err, "skip", skip, flush=True)
