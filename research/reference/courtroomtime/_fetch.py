import json, os, urllib.request, ssl
D = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(D, "catalog.json"), encoding="utf-8"))
for i, r in enumerate(rows):
    r["idx"] = i           # 0 = newest on the /videos tab
    r["n"] = len(rows)
srt = sorted(rows, key=lambda r: r["views"], reverse=True)
top, bot = srt[:15], srt[-10:]
print("TOP idx(age-rank):", [r["idx"] for r in top])
print("BOT idx(age-rank):", [r["idx"] for r in bot])
outd = os.path.join(D, "thumbs"); os.makedirs(outd, exist_ok=True)
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
meta = []
for grp, lst in (("top", top), ("bot", bot)):
    for r in lst:
        got = None
        for q in ("maxresdefault", "hqdefault"):
            url = f"https://i.ytimg.com/vi/{r['id']}/{q}.jpg"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                data = urllib.request.urlopen(req, timeout=30, context=ctx).read()
                if len(data) > 3000:
                    fn = f"{grp}_{r['views']:08d}_{r['id']}_{q}.jpg"
                    open(os.path.join(outd, fn), "wb").write(data)
                    got = (fn, q, len(data)); break
            except Exception as e:
                print("ERR", r["id"], q, e)
        print(grp, r["views"], r["idx"], got)
        if got:
            meta.append({"grp": grp, "file": got[0], "q": got[1], "bytes": got[2],
                         "id": r["id"], "views": r["views"], "dur": r["dur"],
                         "idx": r["idx"], "title": r["title"]})
json.dump(meta, open(os.path.join(D, "thumbmeta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("saved", len(meta))
