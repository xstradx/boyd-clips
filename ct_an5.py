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
NOW = datetime(2026, 8, 18)
for r in rows:
    r["age"] = max(1, (NOW - datetime.strptime(r["upload_date"], "%Y%m%d")).days)
    r["vpd"] = r["views"]/r["age"]
print("MONTH | n | med_views/day (age-normalised) | med_likes/1k")
for mo in sorted({r["upload_date"][:6] for r in rows}):
    g = [r for r in rows if r["upload_date"][:6] == mo]
    lr = [1000*(r["likes"] or 0)/r["views"] for r in g if r["views"]]
    print(f"{mo} | {len(g):>3} | {st.median([r['vpd'] for r in g]):>8.1f} | {st.median(lr):>5.1f}")
print("\n=== TITLE LENGTH, post-Oct-2025, raw views ===")
g = [r for r in rows if r["upload_date"] >= "20251001"]
med = st.median([r["views"] for r in g])
for lo, hi in [(0,70),(70,80),(80,90),(90,120)]:
    b = [r["views"] for r in g if lo <= len(r["title"] or "") < hi]
    if len(b) >= 10:
        print(f"  {lo}-{hi} chars n={len(b):<3} med={st.median(b):<8.0f} lift={st.median(b)/med:.2f}x")
print("\n=== FULL DESCRIPTION of #1 video (sourcing/credit) ===")
top = max(rows, key=lambda r: r["views"])
print(top["title"], "|", top["views"], "views")
print(top.get("desc"))
