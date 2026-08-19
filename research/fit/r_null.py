"""Null check + full surviving n-gram list."""
import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, stats_util as S
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
        pairs.append((r[1], r[lo]))
n = len(pairs)
cnt, tot = [], []
for a, b in pairs:
    for s in (a, b):
        t = features.toks(s["text"])
        c = collections.Counter()
        for N in (1, 2, 3):
            for i in range(len(t) - N + 1):
                c[" ".join(t[i:i + N])] += 1
        cnt.append(c); tot.append(float(len(t)))
df = collections.Counter()
for c in cnt:
    for g in c:
        df[g] += 1
vocab = [g for g, v in df.items() if v >= 0.4 * len(cnt)]
D = np.zeros((n, len(vocab)))
for j in range(n):
    for i, g in enumerate(vocab):
        D[j, i] = cnt[2*j].get(g, 0)*1000.0/tot[2*j] - cnt[2*j+1].get(g, 0)*1000.0/tot[2*j+1]
Dn = D / (D.std(0) + 1e-9)

def run_cv(Dm, seed):
    idx = np.random.default_rng(seed).permutation(n)
    sc = np.zeros(n)
    for f in np.array_split(idx, 10):
        tr = np.setdiff1d(idx, f)
        t = np.array([S.auc(Dm[tr, i], -Dm[tr, i]) for i in range(Dm.shape[1])])
        sel = np.argsort(-np.abs(t - 0.5))[:10]
        m = LogisticRegression(C=0.05, max_iter=2000)
        m.fit(np.vstack([Dm[tr][:, sel], -Dm[tr][:, sel]]),
              np.r_[np.ones(len(tr)), np.zeros(len(tr))])
        sc[f] = m.decision_function(Dm[f][:, sel])
    return (sc > 0).mean()

real = np.mean([run_cv(Dn, s) for s in range(5)])
nulls = []
for s in range(20):
    fl = np.random.default_rng(100 + s).choice([-1.0, 1.0], n)[:, None]
    nulls.append(run_cv(Dn * fl, s))
print("real CV acc %.3f | NULL (pair direction shuffled) mean %.3f sd %.3f max %.3f"
      % (real, np.mean(nulls), np.std(nulls), np.max(nulls)))
print("permutation p = %.3f" % ((sum(1 for x in nulls if x >= real) + 1) / 21.0))

rng = np.random.default_rng(5)
signs = rng.choice([-1.0, 1.0], size=(n, 10000))
obs = np.abs(D.mean(0))
pv = ((np.abs(signs.T @ D / n) >= obs - 1e-12).sum(0) + 1) / 10001.0
q = S.bh_fdr(pv)
keep = [(vocab[i], D[:, i].mean(), int((D[:, i] > 0).sum()), pv[i], q[i])
        for i in range(len(vocab)) if q[i] < 0.10]
keep.sort(key=lambda r: r[1])
print("\nSURVIVING q<0.10: %d" % len(keep))
print("\n--- MORE IN #3 (the WORSE case) ---")
for g, d, w, p, qq in keep[:60]:
    print("  %-26s %+7.3f  %2d/%d wins  q=%.3f" % (g, d, w, n, qq))
print("\n--- MORE IN #1 (the BEST case) ---")
for g, d, w, p, qq in keep[::-1][:40]:
    print("  %-26s %+7.3f  %2d/%d wins  q=%.3f" % (g, d, w, n, qq))
json.dump([dict(g=g, d=float(d), w=w, q=float(qq)) for g, d, _, _, qq in
           [(k[0], k[1], k[2], k[3], k[4]) for k in keep]],
          open("research/fit/keep.json", "w"), indent=1)
