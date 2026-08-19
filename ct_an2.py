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
    r["dt"] = datetime.strptime(r["upload_date"], "%Y%m%d")
    r["age"] = max(1, (NOW - r["dt"]).days)
    r["t"] = r["title"] or ""
    r["m"] = r["dur"]/60.0
era = lambda r: "A_pre_Oct25" if r["dt"] < datetime(2025,10,1) else "B_post_Oct25"

print("=== DURATION vs VIEWS WITHIN ERA (median views) ===")
for e in ["A_pre_Oct25","B_post_Oct25"]:
    g = [r for r in rows if era(r)==e]
    med = st.median([r["views"] for r in g])
    print(f"\n{e}  n={len(g)}  era median views={med:.0f}")
    for lo,hi in [(0,20),(20,35),(35,50),(50,58),(58,200)]:
        b=[r["views"] for r in g if lo<=r["m"]<hi]
        if len(b)>=5:
            print(f"   {lo:>2}-{hi:<3}min n={len(b):<3} med={st.median(b):<8.0f} lift={st.median(b)/med:.2f}x")

print("\n=== ENGAGEMENT RATE (likes per 1k views) by era ===")
for e in ["A_pre_Oct25","B_post_Oct25"]:
    g=[r for r in rows if era(r)==e and r["views"] and r["likes"]]
    print(f"  {e}: median {st.median([1000*r['likes']/r['views'] for r in g]):.1f} likes/1k views  n={len(g)}")

print("\n=== TITLE FEATURES, post-Oct-2025 only (controls for era) ===")
g=[r for r in rows if era(r)=="B_post_Oct25"]
med=st.median([r["views"] for r in g])
caps=lambda t:[w for w in re.findall(r"[A-Za-z']{3,}",t) if w.isupper()]
pats={
 "names Boyd": lambda t:"boyd" in t.lower(),
 "2 judges named": lambda t:len(re.findall(r"judge\s+[A-Z]",t))>1,
 "ALLCAPS word": lambda t:len(caps(t))>0,
 "Top N listicle": lambda t:bool(re.search(r"\btop\s*\d",t,re.I)),
 "quoted phrase": lambda t:bool(re.search(r"[\u2018\u2019\u201c\u201d'\"]",t)),
 "SHUTS DOWN/OWNS/DESTROYS": lambda t:bool(re.search(r"shuts? down|owns?\b|destroy|snaps|loses it|exposes",t,re.I)),
 "craz/wild/shock": lambda t:bool(re.search(r"craz|wild|shock|insane|unbeliev",t,re.I)),
 "mom/mother": lambda t:bool(re.search(r"\bmom\b|mother",t,re.I)),
 "karen/punk/brat/entitled": lambda t:bool(re.search(r"karen|punk|brat|entitled|smug",t,re.I)),
 "attorney/lawyer": lambda t:bool(re.search(r"attorney|lawyer|defense",t,re.I)),
 "sentence/years": lambda t:bool(re.search(r"sentenc|\d+\s*year",t,re.I)),
 "drug/high": lambda t:bool(re.search(r"\bhigh\b|drug|meth|weed",t,re.I)),
}
for k,f in pats.items():
    a=[r["views"] for r in g if f(r["t"])]; b=[r["views"] for r in g if not f(r["t"])]
    if len(a)>=8 and len(b)>=8:
        print(f"  {k:<26} WITH n={len(a):<3} med={st.median(a):<8.0f} | WITHOUT n={len(b):<3} med={st.median(b):<8.0f} | {st.median(a)/st.median(b):.2f}x")

print("\n=== TOP 10 DESCRIPTIONS ===")
for r in sorted(rows,key=lambda r:-r["views"])[:10]:
    print(f"\n--- {r['views']} views | {r['m']:.0f}min | {r['upload_date']} | {r['t'][:70]}")
    print((r.get("desc") or "")[:600].replace("\n"," | "))
