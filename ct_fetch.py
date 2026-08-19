import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from yt_dlp import YoutubeDL

BASE = r"C:\Users\natha\Projects\boyd-clips"
ids = []
with open(BASE + r"\ct_flat.txt", encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if "|" in line:
            ids.append(line.split("|")[0])
print("ids:", len(ids), flush=True)

OPTS = {"quiet": True, "no_warnings": True, "skip_download": True,
        "extractor_args": {"youtube": {"player_skip": ["configs"]}},
        "retries": 3, "socket_timeout": 30}

def grab(vid):
    for attempt in range(3):
        try:
            with YoutubeDL(OPTS) as y:
                i = y.extract_info("https://www.youtube.com/watch?v=" + vid, download=False)
            return {"id": vid, "upload_date": i.get("upload_date"),
                    "views": i.get("view_count"), "dur": i.get("duration"),
                    "likes": i.get("like_count"), "comments": i.get("comment_count"),
                    "title": i.get("title"), "desc": (i.get("description") or "")[:1200]}
        except Exception as e:
            if attempt == 2:
                return {"id": vid, "error": str(e)[:150]}
            time.sleep(3 * (attempt + 1))

out = open(BASE + r"\ct_meta.jsonl", "w", encoding="utf-8")
done = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(grab, ids):
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
        done += 1
        if done % 50 == 0:
            out.flush(); print("done", done, flush=True)
out.close()
print("COMPLETE", done, flush=True)
