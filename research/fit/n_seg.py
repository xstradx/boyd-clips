"""Within-video paired test: does any feature rank the editor's #1 above #3+?

Every comparison is inside one upload, so thumbnail, title, channel state and
calendar time are held constant by construction. Sign/Wilcoxon on the paired
differences; no length confound because segment lengths are balanced by rank.
"""
import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, stats_util as S

segs = segfeat.build()
print("segments with transcript: %d across %d videos" %
      (len(segs), len({s['vid'] for s in segs})))
print("rank dist:", dict(sorted(collections.Counter(s["rank"] for s in segs).items())))
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)

pairs = []   # (best_seg, worst_seg) within a video
for vid, g in byv.items():
    g.sort(key=lambda s: s["rank"])
    if len(g) < 2 or g[0]["rank"] != 1:
        continue
    pairs.append((g[0], g[-1]))
print("within-video #1-vs-worst pairs: %d" % len(pairs))
dl = [p[0]["dur"] - p[1]["dur"] for p in pairs]
print("length check: mean dur diff (#1 - worst) = %+.0fs  (sign test p=%.3f)" %
      (np.mean(dl), S.perm_p([1 if x > 0 else 0 for x in dl], [0.5] * len(dl), 2000)))

for s in segs:
    s["F"] = segfeat.feats(s)
keys = sorted(pairs[0][0]["F"].keys()) if pairs else []
res = []
for k in keys:
    d = np.array([p[0]["F"][k] - p[1]["F"][k] for p in pairs])
    wins = int((d > 0).sum())
    n = len(d)
    rng = np.random.default_rng(3)
    obs = abs(np.median(d))
    cnt = sum(1 for _ in range(10000)
              if abs(np.median(d * rng.choice([-1, 1], n))) >= obs - 1e-12)
    p = (cnt + 1) / 10001.0
    res.append(dict(f=k, wins=wins, n=n, frac=wins / float(n),
                    med=float(np.median(d)), p=p))
q = S.bh_fdr([r["p"] for r in res])
for r, qq in zip(res, q):
    r["q"] = qq
res.sort(key=lambda r: r["p"])
print("\n%-16s %8s %10s %9s %8s" % ("FEATURE", "#1 wins", "median d", "p", "q"))
for r in res:
    tag = "  <-- SURVIVES" if r["q"] < 0.10 else ""
    print("%-16s %4d/%-3d %10.3f %9.4f %8.3f%s" %
          (r["f"], r["wins"], r["n"], r["med"], r["p"], r["q"], tag))
json.dump(res, open("research/fit/seg_stats.json", "w"), indent=1)
