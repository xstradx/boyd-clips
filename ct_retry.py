import json, time, os
from yt_dlp import YoutubeDL
BASE = r"C:\Users\natha\Projects\boyd-clips"
ids = [l.split("|")[0] for l in open(BASE+r"\ct_flat.txt", encoding="utf-8-sig") if "|" in l]
have = set()
if os.path.exists(BASE+r"\ct_meta.jsonl"):
    for l in open(BASE+r"\ct_meta.jsonl", encoding="utf-8"):
        try:
            d = json.loads(l)
        except Exception:
            continue
        if not d.get("error"):
            have.add(d["id"])
todo = [i for i in ids if i not in have]
print("todo:", len(todo), flush=True)
OPTS = {"quiet": True, "no_warnings": True, "skip_download": True,
        "retries": 2, "socket_timeout": 30}
out = open(BASE+r"\ct_meta2.jsonl", "a", encoding="utf-8")
ok = 0
for n, vid in enumerate(todo):
    try:
        with YoutubeDL(OPTS) as y:
            i = y.extract_info("https://www.youtube.com/watch?v="+vid, download=False)
        out.write(json.dumps({"id": vid, "upload_date": i.get("upload_date"),
            "views": i.get("view_count"), "dur": i.get("duration"),
            "likes": i.get("like_count"), "comments": i.get("comment_count"),
            "title": i.get("title"), "desc": (i.get("description") or "")[:1200]},
            ensure_ascii=False)+"\n")
        ok += 1
        out.flush()
    except Exception:
        time.sleep(8)
    time.sleep(3)
    if n % 25 == 0:
        print("at", n, "ok", ok, flush=True)
print("DONE ok", ok, flush=True)
