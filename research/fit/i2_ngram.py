"""N-gram discovery with an HONEST multiple-testing correction.

The first pass filtered on |AUC-0.5| and then FDR-corrected only the
survivors -- selecting on the test statistic and correcting among the
selected inflates significance. Here every candidate is tested and BH runs
over the FULL candidate set.

Permutation is exact-by-construction: pooled ranks are invariant under label
permutation, so one rank matrix is reused for all 20k shuffles.
"""
import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, corpus, features, stats_util as S

docs = corpus.load()
band = sorted([d for d in docs if 2700 <= d["dur"] <= 4200], key=lambda d: -d["views"])
k = len(band) // 3
HI, LO = band[:k], band[-k:]
use = HI + LO
n1, n2 = len(HI), len(LO)
print("HI=%d LO=%d length-matched docs" % (n1, n2))

counts, tot = [], []
for d in use:
    t = features.toks(d["text"])
    c = collections.Counter()
    for N in (1, 2, 3, 4):
        for i in range(len(t) - N + 1):
            c[" ".join(t[i:i + N])] += 1
    counts.append(c)
    tot.append(float(len(t)))

df_hi, df_lo = collections.Counter(), collections.Counter()
for i, c in enumerate(counts):
    for g in c:
        (df_hi if i < n1 else df_lo)[g] += 1
MIN = 0.6
cand = [g for g in set(df_hi) | set(df_lo)
        if df_hi[g] >= MIN * n1 or df_lo[g] >= MIN * n2]
print("candidates (doc-freq >=60%% of one group): %d" % len(cand))

X = np.zeros((len(cand), n1 + n2))
for j, c in enumerate(counts):
    for i, g in enumerate(cand):
        v = c.get(g)
        if v:
            X[i, j] = v * 1000.0 / tot[j]
R = np.apply_along_axis(S.rankdata, 1, X)
obs = R[:, :n1].sum(1)
rng = np.random.default_rng(7)
NP = 20000
idx = np.argsort(rng.random((NP, n1 + n2)), axis=1)[:, :n1]
M = np.zeros((n1 + n2, NP))
for p in range(NP):
    M[idx[p], p] = 1.0
perm = R @ M
centre = R.sum(1, keepdims=True) * n1 / (n1 + n2)
pv = (np.abs(perm - centre) >= np.abs(obs - centre.ravel())[:, None] - 1e-9).sum(1)
pv = (pv + 1) / float(NP + 1)
q = S.bh_fdr(pv)
auc = (obs - n1 * (n1 + 1) / 2.0) / (n1 * n2)
print("min p %.5f | min q %.4f | surviving q<0.10: %d | expected by chance at p<.05: %.0f"
      % (pv.min(), q.min(), (q < 0.10).sum(), 0.05 * len(cand)))
print("actually observed at p<.05: %d" % (pv < 0.05).sum())
order = np.argsort(pv)
print("\n%-26s %6s %8s %8s %8s %7s" % ("NGRAM", "AUC", "HI/1k", "LO/1k", "p", "q"))
for i in order[:25]:
    print("%-26s %6.3f %8.2f %8.2f %8.4f %7.3f" %
          (cand[i][:26], auc[i], X[i, :n1].mean(), X[i, n1:].mean(), pv[i], q[i]))
json.dump([dict(g=cand[i], auc=float(auc[i]), p=float(pv[i]), q=float(q[i]),
                hi=float(X[i, :n1].mean()), lo=float(X[i, n1:].mean()))
           for i in order[:300]], open("research/fit/ngrams2.json", "w"), indent=1)
