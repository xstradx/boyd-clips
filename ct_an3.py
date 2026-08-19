import json, re, statistics as st
from datetime import datetime
BASE = r"C:\Users\natha\Projects\boyd-clips"
R = {}
for fn in [BASE+r"\ct_meta.jsonl", BASE+r"\ct_meta2.jsonl"]:
    try:
        for l in open(fn, encoding="utf-8"):
            try: d = json.loads(l)
            except Exception: continue
            if d.get("error") or not d.get("upload_date"): continue
            R[d["id"]] = d
    except FileNotFoundError: pass
rows = list(R.values())
for r in rows:
    r["dt"] = datetime.strptime(r["upload_date"], "%Y%m%d")
    r["t"] = r["title"] or ""; r["d"] = r.get("desc") or ""; r["m"] = r["dur"]/60.0
    r["chaps"] = len(re.findall(r"\d?\d:\d\d(?::\d\d)?", r["d"]))
    r["segs"] = len(re.findall(r"#\s*\d", r["d"]))
    r["hasTS"] = "imestamp" in r["d"] or r["chaps"] >= 3
    r["fairuse"] = "fair use" in r["d"].lower()
    r["update"] = bool(re.search(r"\bupdate\b|backstory", r["t"]+" "+r["d"], re.I))
    r["multijudge"] = len(set(re.findall(r"Judge\s+([A-Z][a-z]+)", r["t"]+" "+r["d"]))) > 1
era = lambda r: "PRE" if r["dt"] < datetime(2025,10,1) else "POST"

print("=== FORMAT ADOPTION BY QUARTER ===")
print("qtr   n   %chaptered  %countdown(segs>=3)  med_segs  med_min  med_views")
def q(r): return f'{r["upload_date"][:4]}Q{(int(r["upload_date"][4:6])-1)//3+1}'
for k in sorted({q(r) for r in rows}):
    g=[r for r in rows if q(r)==k]
    print(f"{k} {len(g):>3}   {100*sum(r['hasTS'] for r in g)/len(g):>5.0f}%   {100*sum(r['segs']>=3 for r in g)/len(g):>10.0f}%   "
          f"{st.median([r['segs'] for r in g]):>6.0f}  {st.median([r['m'] for r in g]):>6.1f}  {st.median([r['views'] for r in g]):>8.0f}")

print("\n=== SEGMENT COUNT vs VIEWS (post-Oct-2025, n controls era) ===")
g=[r for r in rows if era(r)=="POST"]
med=st.median([r["views"] for r in g])
for lo,hi,lab in [(0,1,"0 (single case)"),(1,3,"1-2"),(3,4,"3"),(4,6,"4-5"),(6,20,"6+")]:
    b=[r["views"] for r in g if lo<=r["segs"]<hi]
    if len(b)>=6: print(f"  segs {lab:<16} n={len(b):<3} med={st.median(b):<8.0f} lift={st.median(b)/med:.2f}x")

print("\n=== PRE-Oct-2025 era: countdown vs not (the switch itself) ===")
g=[r for r in rows if era(r)=="PRE"]
a=[r["views"] for r in g if r["segs"]>=3]; b=[r["views"] for r in g if r["segs"]<3]
print(f"  countdown n={len(a)} med={st.median(a) if a else 0:.0f} | non-countdown n={len(b)} med={st.median(b) if b else 0:.0f}")

print("\n=== OTHER FEATURES (post-Oct-2025) ===")
g=[r for r in rows if era(r)=="POST"]
for lab,f in [("chaptered desc",lambda r:r["hasTS"]),("update/backstory",lambda r:r["update"]),
              ("multi-judge",lambda r:r["multijudge"]),("fair-use notice",lambda r:r["fairuse"])]:
    a=[r["views"] for r in g if f(r)]; b=[r["views"] for r in g if not f(r)]
    if len(a)>=6 and len(b)>=6:
        print(f"  {lab:<18} WITH n={len(a):<3} med={st.median(a):<8.0f} | WITHOUT n={len(b):<3} med={st.median(b):<8.0f} | {st.median(a)/st.median(b):.2f}x")
    else:
        print(f"  {lab:<18} WITH n={len(a)} WITHOUT n={len(b)} (too few to split)")

print("\n=== JUDGE MIX across all dated videos ===")
from collections import Counter
c=Counter()
for r in rows:
    for j in set(re.findall(r"Judge\s+([A-Z][a-z]+)", r["t"])): c[j]+=1
print("  ", c.most_common(12))
print("\n=== VIEWS by judge named in title (post-Oct) ===")
g=[r for r in rows if era(r)=="POST"]
for j,_ in c.most_common(8):
    b=[r["views"] for r in g if re.search(r"Judge\s+"+j, r["t"])]
    if len(b)>=5: print(f"  Judge {j:<12} n={len(b):<3} med={st.median(b):.0f}")
