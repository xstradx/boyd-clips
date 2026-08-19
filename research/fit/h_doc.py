import os, sys, json
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, corpus, features, stats_util as S

docs = corpus.load()
band = [d for d in docs if 2700 <= d["dur"] <= 4200]
band.sort(key=lambda d: -d["views"])
print("ALL docs %d | length-matched band (45-70m) %d" % (len(docs), len(band)))
dur = np.array([d["dur"] for d in band], float)
lv = np.array([np.log10(d["views"]) for d in band])
print("band dur mean %.0f sd %.0f | views %d..%d" %
      (dur.mean(), dur.std(), band[-1]["views"], band[0]["views"]))
print("CONFOUND CHECK  spearman(dur, log views) in band = %+.3f" % S.spearman(dur, lv))
print("CONFOUND CHECK  spearman(nwords, log views)      = %+.3f" %
      S.spearman([d["nwords"] for d in band], lv))
k = len(band) // 3
HI, LO = band[:k], band[-k:]
print("HI n=%d (%d..%d)  LO n=%d (%d..%d)" %
      (len(HI), HI[-1]["views"], HI[0]["views"], len(LO), LO[-1]["views"], LO[0]["views"]))
print("  HI dur mean %.0f  LO dur mean %.0f  (t-gap in minutes: %.1f)" %
      (np.mean([d["dur"] for d in HI]), np.mean([d["dur"] for d in LO]),
       (np.mean([d["dur"] for d in HI]) - np.mean([d["dur"] for d in LO])) / 60.0))

F = {d["id"]: features.all_feats(d) for d in band}
keys = sorted(F[band[0]["id"]].keys())
rows = []
for k_ in keys:
    p = [F[d["id"]][k_] for d in HI]
    n = [F[d["id"]][k_] for d in LO]
    a = S.auc(p, n)
    lo, hi = S.boot_auc_ci(p, n)
    rows.append(dict(f=k_, auc=a, lo=lo, hi=hi, d=S.cohen_d(p, n),
                     rho=S.spearman([F[d["id"]][k_] for d in band], lv),
                     p=S.perm_p(p, n, 3000)))
q = S.bh_fdr([r["p"] for r in rows])
for r, qq in zip(rows, q):
    r["q"] = qq
rows.sort(key=lambda r: -abs(r["auc"] - 0.5))
print("\n%-16s %6s %-14s %7s %7s %7s %7s" % ("FEATURE", "AUC", "95% CI", "d", "rho", "p", "q"))
for r in rows:
    flag = "  <-- survives FDR" if r["q"] < 0.10 else ("" if r["p"] < 0.05 else "   NOISE")
    print("%-16s %6.3f [%.2f,%.2f] %7.2f %7.2f %7.3f %7.3f%s" %
          (r["f"], r["auc"], r["lo"], r["hi"], r["d"], r["rho"], r["p"], r["q"], flag))
json.dump({"band": [d["id"] for d in band], "rows": rows}, open("research/fit/doc_stats.json", "w"), indent=1)
