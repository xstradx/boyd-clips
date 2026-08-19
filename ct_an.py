import json, re, statistics as st
from collections import defaultdict
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
    r["mo"] = r["upload_date"][:6]
rows.sort(key=lambda r: r["dt"])
print("N with dates:", len(rows), rows[0]["upload_date"], "->", rows[-1]["upload_date"])
print()
print("MONTH | uploads | med_views | med_dur_min | med_likes | tot_views")
for mo in sorted({r["mo"] for r in rows}):
    g = [r for r in rows if r["mo"] == mo]
    v = [r["views"] for r in g]
    print(f"{mo} | {len(g):>3} | {st.median(v):>9.0f} | {st.median([r['dur'] for r in g])/60:>6.1f} | "
          f"{st.median([r['likes'] or 0 for r in g]):>6.0f} | {sum(v):>9}")
