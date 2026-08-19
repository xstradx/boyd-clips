import os, json, statistics as st
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
R = "research/reference/courtroomtime"
have = {f.split(".")[0] for f in os.listdir(R+"/txt")}
rows = []
for l in open("ct_compact.tsv", encoding="utf-8"):
    p = l.rstrip("\n").split("\t")
    if len(p) < 4 or not p[2].isdigit():
        continue
    rows.append(dict(id=p[0], date=p[1], views=int(p[2]), dur=int(p[3])))
print("rows", len(rows), "have txt", len(have & {r['id'] for r in rows}))
v = sorted(r["views"] for r in rows)
d = sorted(r["dur"] for r in rows)
print("views deciles", [v[int(len(v)*q/10)] for q in range(10)], v[-1])
print("dur   deciles", [d[int(len(d)*q/10)] for q in range(10)], d[-1])
for lo, hi, lab in [(0,900,"<15m"),(900,1800,"15-30m"),(1800,2700,"30-45m"),(2700,4200,"45-70m"),(4200,99999,">70m")]:
    b = [r for r in rows if lo <= r["dur"] < hi]
    if b:
        print(f"{lab:8s} n={len(b):4d} med_views={int(st.median([x['views'] for x in b])):8d} min={min(x['views'] for x in b)} max={max(x['views'] for x in b)}")
json.dump(rows, open("research/fit/catalog.json","w"), indent=0)
print("have ids:", sorted(have))
