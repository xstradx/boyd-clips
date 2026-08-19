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
rows = [r for r in R.values() if r["upload_date"] >= "20251001"]
for r in rows:
    r["x"] = (r["title"] or "") + " " + (r.get("desc") or "")
med = st.median([r["views"] for r in rows])
print("POST-Oct-2025 n=%d median=%d" % (len(rows), med))
print("\n=== PROCEEDING / SUBJECT TYPE (title+desc keywords) ===")
cats = {
 "sentencing":  r"sentenc|years in prison|life sentence|punishment",
 "probation/revocation": r"probation|revok|violat",
 "bond/jail":   r"\bbond\b|\bjail\b|cuff|custody|taken into",
 "plea":        r"\bplea\b|pleads?\b|guilty plea",
 "trial/jury":  r"\btrial\b|jury|verdict",
 "contempt/decorum": r"contempt|disrespect|outburst|decorum|interrupt",
 "zoom-behaviour": r"zoom|virtual court|in bed|driving|camera off",
 "drugs/sobriety": r"\bhigh\b|drug|meth|sober|positive test",
 "family/parent": r"\bmom\b|mother|father|\bdad\b|son\b|daughter|parent",
 "attorney conflict": r"attorney|lawyer|defense counsel|prosecutor",
 "sovereign citizen": r"sovereign",
 "theft/money": r"theft|steal|stole|restitution|fraud|\$",
}
for k, pat in cats.items():
    a = [r["views"] for r in rows if re.search(pat, r["x"], re.I)]
    b = [r["views"] for r in rows if not re.search(pat, r["x"], re.I)]
    if len(a) >= 8 and len(b) >= 8:
        print(f"  {k:<20} n={len(a):<3} ({100*len(a)/len(rows):>3.0f}%) med={st.median(a):<8.0f} lift={st.median(a)/med:.2f}x  (rest med={st.median(b):.0f})")
    else:
        print(f"  {k:<20} n={len(a):<3} (too few)")
print("\n=== VIEWS-PER-DAY normalised (controls for age) by duration, post-Oct ===")
NOW = datetime(2026, 8, 18)
for r in rows:
    r["age"] = max(1, (NOW - datetime.strptime(r["upload_date"], "%Y%m%d")).days)
    r["vpd"] = r["views"] / r["age"]
for lo, hi in [(0, 50), (50, 58), (58, 63), (63, 200)]:
    g = [r["vpd"] for r in rows if lo <= r["dur"]/60 < hi]
    if len(g) >= 8:
        print(f"  {lo}-{hi}min n={len(g):<3} median views/day={st.median(g):.1f}")
print("\n=== SEGMENT COUNT vs views/day (age-normalised) ===")
for lo, hi, lab in [(0,1,"single case"),(1,3,"1-2"),(3,4,"3"),(4,6,"4-5"),(6,20,"6+")]:
    g = [r["vpd"] for r in rows if lo <= len(re.findall(r"#\s*\d", r.get("desc") or "")) < hi]
    if len(g) >= 6:
        print(f"  segs {lab:<12} n={len(g):<3} median views/day={st.median(g):.1f}")
