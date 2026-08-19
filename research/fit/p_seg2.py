import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features2, stats_util as S

segs = segfeat.build()
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)
pairs = []
for vid, g in byv.items():
    r = {s["rank"]: s for s in g}
    if 1 in r and 3 in r:
        pairs.append((r[1], r[3]))
print("strict #1-vs-#3 pairs: %d videos" % len(pairs))
for s in segs:
    s["F"] = features2.build(s)

sp1 = np.array([features2.span(p[0]["words"]) for p in pairs])
sp3 = np.array([features2.span(p[1]["words"]) for p in pairs])
print("speech-span check: #1 mean %.0fs, #3 mean %.0fs, mean diff %+.0fs" %
      (sp1.mean(), sp3.mean(), (sp1 - sp3).mean()))
nw1 = np.array([p[0]["nwords"] for p in pairs], float)
nw3 = np.array([p[1]["nwords"] for p in pairs], float)
print("word-count check: #1 %.0f, #3 %.0f" % (nw1.mean(), nw3.mean()))

keys = sorted(pairs[0][0]["F"].keys())
n = len(pairs)
rng = np.random.default_rng(3)
res = []
for k in keys:
    d = np.array([p[0]["F"][k] - p[1]["F"][k] for p in pairs])
    obs = abs(d.mean())
    signs = rng.choice([-1.0, 1.0], size=(n, 4000))
    p_ = ((np.abs(d @ signs / n) >= obs - 1e-12).sum() + 1) / 4001.0
    sd = d.std(ddof=1)
    res.append(dict(f=k, wins=int((d > 0).sum()), n=n, mean=float(d.mean()),
                    dz=float(d.mean() / sd) if sd else 0.0, p=float(p_)))
q = S.bh_fdr([r["p"] for r in res])
for r, qq in zip(res, q):
    r["q"] = qq
res.sort(key=lambda r: r["p"])
print("\n%-15s %8s %9s %7s %8s %7s" % ("FEATURE", "#1 wins", "mean d", "dz", "p", "q"))
for r in res:
    tag = "  <-- SURVIVES" if r["q"] < 0.10 else ""
    print("%-15s %4d/%-3d %9.3f %7.2f %8.4f %7.3f%s" %
          (r["f"], r["wins"], r["n"], r["mean"], r["dz"], r["p"], r["q"], tag))
json.dump(res, open("research/fit/seg_stats2.json", "w"), indent=1)
