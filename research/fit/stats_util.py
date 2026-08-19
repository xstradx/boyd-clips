import numpy as np


def auc(pos, neg):
    """P(random pos > random neg). Ties count 0.5. == Mann-Whitney U / (n*m)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    allv = np.concatenate([pos, neg])
    r = rankdata(allv)
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))


def rankdata(a):
    a = np.asarray(a, float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return ranks


def cohen_d(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    n1, n2 = len(pos), len(neg)
    if n1 < 2 or n2 < 2:
        return 0.0
    sp = np.sqrt(((n1 - 1) * pos.var(ddof=1) + (n2 - 1) * neg.var(ddof=1)) / (n1 + n2 - 2))
    return 0.0 if sp == 0 else (pos.mean() - neg.mean()) / sp


def spearman(x, y):
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def perm_p(pos, neg, nperm=5000, seed=0):
    """Two-sided permutation p-value on the AUC statistic."""
    rng = np.random.default_rng(seed)
    obs = abs(auc(pos, neg) - 0.5)
    allv = np.concatenate([pos, neg])
    n = len(pos)
    c = 0
    for _ in range(nperm):
        rng.shuffle(allv)
        if abs(auc(allv[:n], allv[n:]) - 0.5) >= obs - 1e-12:
            c += 1
    return (c + 1) / float(nperm + 1)


def boot_auc_ci(pos, neg, nboot=2000, seed=0):
    rng = np.random.default_rng(seed)
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    vals = []
    for _ in range(nboot):
        p = rng.choice(pos, len(pos), replace=True)
        q = rng.choice(neg, len(neg), replace=True)
        vals.append(auc(p, q))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def bh_fdr(pvals):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(pvals, float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n, float)
    prev = 1.0
    for rank in range(n - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * n / (rank + 1))
        q[i] = prev
    return q
