import os, sys, statistics as st
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import corpus
docs = corpus.load()
print("docs", len(docs))
for d in docs:
    t = d["text"]
    d["style"] = "rich" if (t.count(">>") > 5 and t.count(".") > 50) else "plain"
for s in ("rich", "plain"):
    g = [d for d in docs if d["style"] == s]
    if not g:
        continue
    vs = sorted(x["views"] for x in g)
    ds = [x["dur"] for x in g]
    print(f"{s:6s} n={len(g):3d} med_views={int(st.median(vs)):8d} "
          f"min={vs[0]} max={vs[-1]} med_dur={int(st.median(ds))}")
band = [d for d in docs if 2700 <= d["dur"] <= 4200]
print("\nIN 45-70m BAND n =", len(band))
for s in ("rich", "plain"):
    g = [d for d in band if d["style"] == s]
    if g:
        vs = sorted(x["views"] for x in g)
        print(f"  {s:6s} n={len(g):3d} med_views={int(st.median(vs)):8d} min={vs[0]} max={vs[-1]}")
print("\nper-doc:")
for d in sorted(band, key=lambda x: -x["views"]):
    print(f"  {d['id']} {d['views']:>7} dur={d['dur']} nw={d['nwords']:>6} "
          f"turns={d['text'].count('>>'):>4} dots={d['text'].count('.'):>5} {d['style']}")
