import json, os
from yt_dlp import YoutubeDL
OUT = os.path.dirname(os.path.abspath(__file__))
opts = {"extract_flat": "in_playlist", "quiet": True, "skip_download": True,
        "ignoreerrors": True, "playlistend": 500}
with YoutubeDL(opts) as ydl:
    info = ydl.extract_info("https://www.youtube.com/@courtroomtime/videos", download=False)
ents = [e for e in (info.get("entries") or []) if e]
rows = []
for e in ents:
    rows.append({
        "id": e.get("id"),
        "views": e.get("view_count") or 0,
        "dur": e.get("duration") or 0,
        "title": (e.get("title") or "").replace("\n", " "),
    })
with open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=1, ensure_ascii=False)
print("total", len(rows))
rows.sort(key=lambda r: r["views"], reverse=True)
for r in rows:
    print(f'{r["id"]}|{r["views"]}|{r["dur"]}|{r["title"][:80]}')
