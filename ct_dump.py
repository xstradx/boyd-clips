import json, glob
BASE = r"C:\Users\natha\Projects\boyd-clips"
seen = {}
for fn in [BASE+r"\ct_meta.jsonl", BASE+r"\ct_meta2.jsonl"]:
    try:
        for l in open(fn, encoding="utf-8"):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("error") or not d.get("upload_date"):
                continue
            seen[d["id"]] = d
    except FileNotFoundError:
        pass
with open(BASE+r"\ct_compact.tsv", "w", encoding="utf-8") as f:
    for d in seen.values():
        f.write("\t".join(str(x) for x in [d["id"], d["upload_date"], d["views"],
                d["dur"], d.get("likes"), d.get("comments")])+"\n")
print("compact rows:", len(seen))
