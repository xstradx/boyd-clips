"""Paired n-gram discovery on the within-video rank label, FDR over ALL candidates."""
import os, sys, json, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, stats_util as S

segs = segfeat.build()
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)
pairs = []
for vid, g in byv.items():
    g.sort(key=lambda s: s["rank"])
    if len(g) >= 2 and g[0]["rank"] == 1:
        pairs.append((g[0], g[-1]))
n = len(pairs)
print("pairs: %d" % n)

toks = {}
for p in pairs:
    for s in p:
        toks[id(s)] = features.toks(s["text"])
cnt = {}
for p in pairs:
    for s in p:
        t = toks[id(s)]
        c = collections.Counter()
        for N in (1, 2, 3):
            for i in range(len(t) - N + 1):
                c[" ".join(t[i:i + N])] += 1
        cnt[id(s)] = (c, float(len(t)))

df = collections.Counter()
for p in pairs:
    for s in p:
        for g in cnt[id(s)][0]:
            df[g] += 1
cand = [g for g, v in df.items() if v >= max(6, 0.4 * 2 * n)]
print("candidates (in >=40%% of segments): %d  (from %d)" % (len(cand), len(df)))

D = np.zeros((len(cand), n))
for j, p in enumerate(pairs):
    (ca, na), (cb, nb) = cnt[id(p[0])], cnt[id(p[1])]
    for i, g in enumerate(cand):
        D[i, j] = ca.get(g, 0) * 1000.0 / na - cb.get(g, 0) * 1000.0 / nb
rng = np.random.default_rng(5)
NP = 10000
signs = rng.choice([-1.0, 1.0], size=(n, NP))
obs = np.abs(D.mean(1))
perm = np.abs(D @ signs / n)
pv = ((perm >= obs[:, None] - 1e-12).sum(1) + 1) / float(NP + 1)
q = S.bh_fdr(pv)
print("min p %.5f | min q %.4f | q<0.10: %d | p<.05 obs %d vs expected %.0f"
      % (pv.min(), q.min(), (q < 0.10).sum(), (pv < 0.05).sum(), 0.05 * len(cand)))
order = np.argsort(pv)
print("\n%-24s %9s %8s %8s %7s" % ("NGRAM", "mean diff", "#1 wins", "p", "q"))
for i in order[:25]:
    print("%-24s %9.3f %5d/%-3d %8.4f %7.3f" %
          (cand[i][:24], D[i].mean(), int((D[i] > 0).sum()), n, pv[i], q[i]))
json.dump([dict(g=cand[i], diff=float(D[i].mean()), p=float(pv[i]), q=float(q[i]))
           for i in order[:300]], open("research/fit/seg_ngrams.json", "w"), indent=1)
