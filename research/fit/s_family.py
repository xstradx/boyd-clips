"""Group the FDR-surviving n-grams into interpretable families, fit, CV.

Families are named groupings of n-grams that ALREADY passed BH-FDR on the
within-video rank label -- the grouping is interpretation applied after
discovery, not a hypothesis imposed before it.
"""
import os, sys, json, re, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, stats_util as S
from sklearn.linear_model import LogisticRegression

FAMILIES = {
    # --- negative: the scripted guilty-plea colloquy ---
    "plea_script": r"\b(plea bargain|did you review|you review|did you understand|"
                   r"you understand it|understand it|with your attorney|your attorney did|"
                   r"attorney did|is there anything|there anything else|your plea|"
                   r"you guilty|find you|entitled|sign)\b",
    "appeal_rights": r"\b(right to appeal|to appeal|appeal|certification|"
                     r"trial court certification|court certification|waive)\b",
    "sentence_admin": r"\b(sentence you|sentence you to|the court will|court will|"
                      r"agreement|the state|community|up to|fine|years in the)\b",
    "discourse_reset": r"\b(all right so|all right and|right so|right and|"
                       r"all right thank|right thank you)\b",
    # --- positive: live, contested, liberty-in-play proceedings ---
    "bond_live": r"\b(bond|set|on your|got|out of|put)\b",
    "direct_address": r"\b(you are|another|based|also|which)\b",
}
PATS = {k: re.compile(v) for k, v in FAMILIES.items()}

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
print("pairs %d" % n)


def fam(text):
    t = " ".join(features.toks(text))
    nw = max(len(t.split()), 1)
    return {k: len(p.findall(t)) * 1000.0 / nw for k, p in PATS.items()}


keys = list(FAMILIES)
D = np.array([[fam(a["text"])[k] - fam(b["text"])[k] for k in keys] for a, b in pairs])
print("\n%-17s %9s %8s %8s %7s" % ("FAMILY", "#1 wins", "mean d", "dz", "p"))
rows = []
rng = np.random.default_rng(1)
signs = rng.choice([-1.0, 1.0], size=(n, 20000))
for i, k in enumerate(keys):
    d = D[:, i]
    p = ((np.abs(d @ signs / n) >= abs(d.mean()) - 1e-12).sum() + 1) / 20001.0
    rows.append((k, int((d > 0).sum()), d.mean(), d.mean() / d.std(ddof=1), p))
q = S.bh_fdr([r[4] for r in rows])
for (k, w, m, dz, p), qq in zip(rows, q):
    print("%-17s %4d/%-3d %8.3f %8.2f %7.4f  q=%.3f%s" %
          (k, w, n, m, dz, p, qq, "  <-- SURVIVES" if qq < 0.10 else ""))

Dn = D / (D.std(0) + 1e-9)
accs = []
for s in range(10):
    idx = np.random.default_rng(s).permutation(n)
    sc = np.zeros(n)
    for f in np.array_split(idx, 10):
        tr = np.setdiff1d(idx, f)
        m = LogisticRegression(C=0.3, max_iter=3000)
        m.fit(np.vstack([Dn[tr], -Dn[tr]]), np.r_[np.ones(len(tr)), np.zeros(len(tr))])
        sc[f] = m.decision_function(Dn[f])
    accs.append((sc > 0).mean())
print("\n6-family model, 10-fold CV acc: %.3f (sd %.3f)" % (np.mean(accs), np.std(accs)))

m = LogisticRegression(C=0.3, max_iter=3000)
m.fit(np.vstack([Dn, -Dn]), np.r_[np.ones(n), np.zeros(n)])
sd = D.std(0)
print("\nFITTED WEIGHTS (per 1 unit of per-1000-word rate):")
raw = {}
for k, c, s_ in zip(keys, m.coef_[0], sd):
    raw[k] = float(c / s_)
    print("   %-17s standardised %+6.3f -> per-rate %+7.3f" % (k, c, c / s_))
mx = max(abs(v) for v in raw.values())
scaled = {k: round(v / mx * 25.0, 1) for k, v in raw.items()}
print("\nSCALED TO +/-25 FOR banger.py:")
for k, v in sorted(scaled.items(), key=lambda x: -abs(x[1])):
    print("   %-17s %+6.1f" % (k, v))
json.dump(dict(weights=scaled, n_pairs=n, cv=float(np.mean(accs)),
               patterns=FAMILIES), open("research/fit/fitted.json", "w"), indent=1)
