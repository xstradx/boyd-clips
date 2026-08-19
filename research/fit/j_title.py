"""Is the view count a property of the TRANSCRIPT or of the PACKAGING?

n=553 titles with view counts -- 8x the transcript sample. If title words
predict views where transcript words do not, then document-level view count
is mostly a thumbnail/title outcome and cannot supply clip-content weights.
"""
import os, sys, json, collections, re
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, stats_util as S

rows = []
for l in open("ct_flat.txt", encoding="utf-8-sig"):
    p = l.rstrip("\n").split("|")
    if len(p) >= 4 and p[1].isdigit() and int(p[1]) > 0:
        rows.append((p[0], int(p[1]), int(p[2]), p[3]))
band = [r for r in rows if 2700 <= r[2] <= 4200]
print("all %d | length-matched band %d" % (len(rows), len(band)))
band.sort(key=lambda r: -r[1])
k = len(band) // 3
HI, LO = band[:k], band[-k:]
n1, n2 = len(HI), len(LO)
print("HI n=%d (%d..%d)  LO n=%d (%d..%d)" %
      (n1, HI[-1][1], HI[0][1], n2, LO[-1][1], LO[0][1]))

def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", s.lower())).strip()

use = HI + LO
toks = [norm(r[3]).split() for r in use]
df_hi, df_lo = collections.Counter(), collections.Counter()
grams = []
for i, t in enumerate(toks):
    c = collections.Counter()
    for N in (1, 2):
        for j in range(len(t) - N + 1):
            c[" ".join(t[j:j + N])] += 1
    grams.append(c)
    for g in c:
        (df_hi if i < n1 else df_lo)[g] += 1
cand = [g for g in set(df_hi) | set(df_lo) if df_hi[g] + df_lo[g] >= 8]
print("title n-gram candidates (>=8 docs): %d" % len(cand))

X = np.zeros((len(cand), n1 + n2))
for j, c in enumerate(grams):
    for i, g in enumerate(cand):
        if c.get(g):
            X[i, j] = 1.0
R = np.apply_along_axis(S.rankdata, 1, X)
obs = R[:, :n1].sum(1)
rng = np.random.default_rng(11)
NP = 20000
idx = np.argsort(rng.random((NP, n1 + n2)), axis=1)[:, :n1]
M = np.zeros((n1 + n2, NP))
for p_ in range(NP):
    M[idx[p_], p_] = 1.0
perm = R @ M
centre = R.sum(1, keepdims=True) * n1 / (n1 + n2)
pv = ((np.abs(perm - centre) >= np.abs(obs - centre.ravel())[:, None] - 1e-9).sum(1) + 1) / float(NP + 1)
q = S.bh_fdr(pv)
auc = (obs - n1 * (n1 + 1) / 2.0) / (n1 * n2)
print("min q %.4f | surviving q<0.10: %d | p<.05 observed %d vs expected %.0f"
      % (q.min(), (q < 0.10).sum(), (pv < 0.05).sum(), 0.05 * len(cand)))
order = np.argsort(pv)
print("\n%-22s %6s %7s %7s %8s %7s" % ("TITLE NGRAM", "AUC", "HI%", "LO%", "p", "q"))
for i in order[:22]:
    print("%-22s %6.3f %6.0f%% %6.0f%% %8.4f %7.4f" %
          (cand[i][:22], auc[i], 100 * X[i, :n1].mean(), 100 * X[i, n1:].mean(), pv[i], q[i]))
