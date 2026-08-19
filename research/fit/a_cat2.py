import os, json
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
R = "research/reference/courtroomtime"
have = {f.split(".")[0] for f in os.listdir(R+"/txt")}
allr = {}
for fn in ("ct_meta.jsonl", "ct_meta2.jsonl"):
    if not os.path.exists(fn):
        continue
    n = 0
    for l in open(fn, encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            j = json.loads(l)
        except Exception:
            continue
        if "views" in j and "dur" in j:
            i = j["id"].lstrip("\ufeff")
            allr[i] = dict(id=i, views=j["views"], dur=j["dur"], title=j.get("title", ""))
            n += 1
    print(fn, "usable", n, "rawlines", sum(1 for _ in open(fn, encoding="utf-8")))
print("union meta", len(allr))
txt = open("ct_flat.txt", encoding="utf-8-sig").read()
print("flat lines", txt.count("\n"), "| head:", repr(txt[:200]))
print("have in meta", len(have & set(allr)))
for h in sorted(have):
    r = allr.get(h)
    print("  ", h, r["views"] if r else "?", r["dur"] if r else "?", (r["title"][:55] if r else "NOT IN META"))
json.dump(list(allr.values()), open("research/fit/meta.json", "w"), indent=0)
