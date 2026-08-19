"""Honest CV: can a fitted model rank the editor's #1 above #3 out of sample?

Feature selection happens INSIDE each fold. Selecting n-grams on all 93 pairs
and then cross-validating would leak the label and manufacture an AUC.
"""
import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, features2, stats_util as S
from sklearn.linear_model import LogisticRegression

segs = segfeat.build()
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)
pairs = []
for vid, g in byv.items():
    r = {s["rank"]: s for s in g}
    lo = max(k for k in r if k >= 2) if any(k >= 2 for k in r) else None
    if 1 in r and lo:
        pairs.append((r[1], r[lo], vid))
n = len(pairs)
print("pairs (#1 vs worst-available): %d" % n)

cnt, tot = [], []
for a, b, _ in pairs:
    for s in (a, b):
        t = features.toks(s["text"])
        c = collections.Counter()
        for N in (1, 2, 3):
            for i in range(len(t) - N + 1):
                c[" ".join(t[i:i + N])] += 1
        cnt.append(c)
        tot.append(float(len(t)))
df = collections.Counter()
for c in cnt:
    for g in c:
        df[g] += 1
vocab = [g for g, v in df.items() if v >= 0.4 * len(cnt)]
print("vocab (doc-freq>=40%%): %d" % len(vocab))
D = np.zeros((n, len(vocab)))
for j in range(n):
    ca, na = cnt[2 * j], tot[2 * j]
    cb, nb = cnt[2 * j + 1], tot[2 * j + 1]
    for i, g in enumerate(vocab):
        D[j, i] = ca.get(g, 0) * 1000.0 / na - cb.get(g, 0) * 1000.0 / nb
D = D / (D.std(0) + 1e-9)

def cv(K, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, 10)
    sc = np.zeros(n)
    for f in folds:
        tr = np.setdiff1d(idx, f)
        Xtr = np.vstack([D[tr], -D[tr]])
        ytr = np.r_[np.ones(len(tr)), np.zeros(len(tr))]
        t = np.array([abs(S.auc(D[tr, i][:, None].ravel(), -D[tr, i])) for i in range(D.shape[1])])
        sel = np.argsort(-np.abs(t - 0.5))[:K]
        m = LogisticRegression(C=0.05, max_iter=2000)
        m.fit(Xtr[:, sel], ytr)
        sc[f] = m.decision_function(D[f][:, sel])
    return (sc > 0).mean(), sc

print("\nLEAVE-FOLD-OUT accuracy at ranking #1 above #worst (chance = 0.500):")
for K in (5, 10, 20, 40, 80):
    accs = [cv(K, s)[0] for s in range(5)]
    print("   top-%-3d n-grams: acc %.3f  (sd %.3f over 5 shuffles)" %
          (K, np.mean(accs), np.std(accs)))

Fk = sorted(features2.build(pairs[0][0]).keys())
H = np.array([[a["Fv"][k] - b["Fv"][k] for k in Fk]
              for a, b, _ in [(dict(Fv=features2.build(a)), dict(Fv=features2.build(b)), v)
                              for a, b, v in pairs]])
H = H / (H.std(0) + 1e-9)
rng = np.random.default_rng(0)
accs = []
for s in range(5):
    idx = np.random.default_rng(s).permutation(n)
    sc = np.zeros(n)
    for f in np.array_split(idx, 10):
        tr = np.setdiff1d(idx, f)
        m = LogisticRegression(C=0.1, max_iter=2000)
        m.fit(np.vstack([H[tr], -H[tr]]), np.r_[np.ones(len(tr)), np.zeros(len(tr))])
        sc[f] = m.decision_function(H[f])
    accs.append((sc > 0).mean())
print("   hand-family features: acc %.3f (sd %.3f)" % (np.mean(accs), np.std(accs)))
