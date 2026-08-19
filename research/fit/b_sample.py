import os, json, statistics as st
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
R = "research/reference/courtroomtime"
have = {f.split(".")[0] for f in os.listdir(R + "/subs") if f.endswith(".vtt")}
rows = []
for l in open("ct_flat.txt", encoding="utf-8-sig"):
    p = l.rstrip("\n").split("|")
    if len(p) < 4 or not p[1].isdigit():
        continue
    rows.append(dict(id=p[0], views=int(p[1]), dur=int(p[2]), title=p[3]))
print("catalog", len(rows), "already have vtt", len(have))
print("have but not in flat:", sorted(have - {r["id"] for r in rows}))

band = [r for r in rows if 2700 <= r["dur"] <= 4200]          # the 45-70min compilation format
print("45-70m band n =", len(band))
bv = sorted(r["views"] for r in band)
print("band view deciles", [bv[int(len(bv) * q / 10)] for q in range(10)], bv[-1])
print("band dur mean %.0f sd %.0f" % (st.mean([r["dur"] for r in band]), st.pstdev([r["dur"] for r in band])))

band.sort(key=lambda r: -r["views"])
HI = [r for r in band[:40] if r["id"] not in have]
LO = [r for r in band[-40:] if r["id"] not in have]
MID = [r for r in band[len(band)//2 - 20: len(band)//2 + 20] if r["id"] not in have]
plan = HI[:22] + LO[:22] + MID[:14]
seen, out = set(), []
for r in plan:
    if r["id"] not in seen:
        seen.add(r["id"]); out.append(r)
json.dump(out, open("research/fit/plan.json", "w"), indent=0)
json.dump(rows, open("research/fit/flat.json", "w"), indent=0)
print("to download", len(out))
print("  HI views", [r["views"] for r in HI[:22]])
print("  LO views", [r["views"] for r in LO[:22]])
print("  MID views", [r["views"] for r in MID[:14]])
