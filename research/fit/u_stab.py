"""Are the fitted weights stable, or is the solver splitting correlated families?"""
import os, sys, json, re, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, stats_util as S
from sklearn.linear_model import LogisticRegression

fit = json.load(open("research/fit/fitted.json"))
PATS = {k: re.compile(v) for k, v in fit["patterns"].items()}
keys = list(PATS)
segs = segfeat.build()
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)
pairs = []
for vid, g in byv.items():
    r = {s["rank"]: s for s in g}
    lo = max(k for k in r if k >= 2) if any(k >= 2 for k in r) else None
    if 1 in r and lo:
        pairs.append((r[1], r[lo]))
n = len(pairs)

def fam(text):
    t = " ".join(features.toks(text))
    nw = max(len(t.split()), 1)
    return [len(PATS[k].findall(t)) * 1000.0 / nw for k in keys]

D = np.array([np.array(fam(a["text"])) - np.array(fam(b["text"])) for a, b in pairs])
print("family correlation matrix (paired differences):")
C = np.corrcoef(D.T)
print("      " + " ".join("%7s" % k[:7] for k in keys))
for i, k in enumerate(keys):
    print("%-14s" % k[:14] + " ".join("%7.2f" % C[i, j] for j in range(len(keys))))

Dn = D / (D.std(0) + 1e-9)
B = []
for b in range(400):
    idx = np.random.default_rng(b).integers(0, n, n)
    m = LogisticRegression(C=0.3, max_iter=3000)
    m.fit(np.vstack([Dn[idx], -Dn[idx]]), np.r_[np.ones(n), np.zeros(n)])
    B.append(m.coef_[0])
B = np.array(B)
print("\nBOOTSTRAP (400 resamples) standardised weights:")
print("%-17s %8s %16s %12s" % ("FAMILY", "median", "95% CI", "sign stable"))
for i, k in enumerate(keys):
    lo, hi = np.percentile(B[:, i], [2.5, 97.5])
    frac = max((B[:, i] > 0).mean(), (B[:, i] < 0).mean())
    print("%-17s %8.3f  [%6.3f,%6.3f] %11.0f%%%s" %
          (k, np.median(B[:, i]), lo, hi, 100 * frac,
           "" if frac > 0.95 else "   <-- UNSTABLE"))

print("\nUNIVARIATE dz (stable alternative):")
dz = {}
for i, k in enumerate(keys):
    dz[k] = D[:, i].mean() / D[:, i].std(ddof=1)
    print("   %-17s dz %+6.3f" % (k, dz[k]))

# compare CV: multivariate vs dz-proportional weights
def cvacc(wvec):
    sc = Dn @ wvec
    return (sc > 0).mean()
print("\nin-sample acc, dz-proportional weights: %.3f" %
      cvacc(np.array([dz[k] for k in keys])))
accs = []
for s in range(10):
    idx = np.random.default_rng(s).permutation(n)
    sc = np.zeros(n)
    for f in np.array_split(idx, 10):
        tr = np.setdiff1d(idx, f)
        d2 = np.array([Dn[tr][:, i].mean() / Dn[tr][:, i].std(ddof=1) for i in range(len(keys))])
        sc[f] = Dn[f] @ d2
    accs.append((sc > 0).mean())
print("10-fold CV acc, dz-proportional weights refit per fold: %.3f (sd %.3f)"
      % (np.mean(accs), np.std(accs)))
