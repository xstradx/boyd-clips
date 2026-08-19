import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, corpus, features, stats_util as S

docs = corpus.load()
band = sorted([d for d in docs if 2700 <= d["dur"] <= 4200], key=lambda d: -d["views"])
k = len(band) // 3
HI, LO = band[:k], band[-k:]
grp = {d["id"]: "HI" for d in HI}
grp.update({d["id"]: "LO" for d in LO})
use = HI + LO
print("n-gram discovery on HI=%d LO=%d length-matched docs" % (len(HI), len(LO)))

rate = {}   # ngram -> {docid: per-1k rate}
docfreq = collections.Counter()
for d in use:
    t = features.toks(d["text"])
    n = float(len(t))
    c = collections.Counter()
    for N in (1, 2, 3, 4):
        for i in range(len(t) - N + 1):
            c[" ".join(t[i:i + N])] += 1
    for g, v in c.items():
        rate.setdefault(g, {})[d["id"]] = v * 1000.0 / n
        docfreq[g] += 1

MIN_HI = max(3, int(len(HI) * 0.6))
MIN_LO = max(3, int(len(LO) * 0.6))
cand = []
for g, m in rate.items():
    nh = sum(1 for x in m if grp[x] == "HI")
    nl = sum(1 for x in m if grp[x] == "LO")
    if nh >= MIN_HI or nl >= MIN_LO:
        cand.append(g)
print("candidates after doc-frequency filter (>=60%% of one group): %d "
      "(from %d raw n-grams)" % (len(cand), len(rate)))

res = []
for g in cand:
    m = rate[g]
    p = [m.get(d["id"], 0.0) for d in HI]
    q = [m.get(d["id"], 0.0) for d in LO]
    a = S.auc(p, q)
    if abs(a - 0.5) < 0.25:
        continue
    res.append(dict(g=g, auc=a, d=S.cohen_d(p, q),
                    hi=float(np.mean(p)), lo=float(np.mean(q)),
                    p=S.perm_p(p, q, 2000, seed=abs(hash(g)) % 9999)))
print("tested (|AUC-0.5|>=0.25): %d" % len(res))
qs = S.bh_fdr([r["p"] for r in res]) if res else []
for r, qq in zip(res, qs):
    r["q"] = qq
res.sort(key=lambda r: (r["q"], -abs(r["auc"] - 0.5)))
sig = [r for r in res if r["q"] < 0.10]
print("SURVIVING BH-FDR q<0.10: %d" % len(sig))
print("\n%-28s %6s %7s %8s %8s %7s %7s" % ("NGRAM", "AUC", "d", "HI/1k", "LO/1k", "p", "q"))
for r in (sig if sig else res)[:45]:
    print("%-28s %6.3f %7.2f %8.2f %8.2f %7.4f %7.3f" %
          (r["g"][:28], r["auc"], r["d"], r["hi"], r["lo"], r["p"], r["q"]))
json.dump(res[:400], open("research/fit/ngrams.json", "w"), indent=1)
