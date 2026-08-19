"""Two honesty checks the family model must pass.

(1) TRANSFER: the families were derived from the #1-vs-worst contrast. Score
    contrasts they were never fitted on (#1 vs #2, #2 vs #3). If the grouping
    were an artifact of the fitting contrast it would not transfer.
(2) DEPLOYMENT SCALE: we deploy on ~45-60s windows (~150 words), not on
    940s segments (~2400 words). Re-run the ranking with a single random
    150-word window per segment.
"""
import os, sys, json, re, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, segfeat, features, stats_util as S

fit = json.load(open("research/fit/fitted.json"))
W = fit["weights"]
PATS = {k: re.compile(v) for k, v in fit["patterns"].items()}


def score_text(text):
    t = " ".join(features.toks(text))
    nw = max(len(t.split()), 1)
    return sum(W[k] * len(p.findall(t)) * 1000.0 / nw for k, p in PATS.items())


segs = segfeat.build()
byv = collections.defaultdict(list)
for s in segs:
    byv[s["vid"]].append(s)
for s in segs:
    s["sc"] = score_text(s["text"])

print("TRANSFER TO UNFITTED CONTRASTS (accuracy, chance=0.500):")
for a, b in [(1, 3), (1, 2), (2, 3), (1, 4), (2, 4), (3, 4)]:
    w = t = 0
    for vid, g in byv.items():
        r = {s["rank"]: s for s in g}
        if a in r and b in r:
            t += 1
            w += r[a]["sc"] > r[b]["sc"]
    if t >= 12:
        se = (0.25 / t) ** 0.5
        star = "  <- FITTED ON THIS" if (a, b) == (1, 3) else ""
        print("   #%d vs #%d   %3d/%-3d = %.3f  (+/-%.3f)%s" % (a, b, w, t, w / t, 1.96 * se, star))

print("\nRANK CORRELATION (score vs editorial rank, within video):")
rs = []
for vid, g in byv.items():
    if len(g) >= 3:
        rs.append(S.spearman([s["sc"] for s in g], [-s["rank"] for s in g]))
print("   mean within-video spearman = %+.3f  (n=%d videos, sd %.2f)"
      % (np.mean(rs), len(rs), np.std(rs)))
print("   videos with positive correlation: %d/%d" % (sum(1 for x in rs if x > 0), len(rs)))

print("\nDEPLOYMENT SCALE - single random window per segment:")
for WIN in (150, 300, 600, 1200):
    accs = []
    for trial in range(40):
        rng = np.random.default_rng(trial)
        w = t = 0
        for vid, g in byv.items():
            r = {s["rank"]: s for s in g}
            if 1 in r and 3 in r:
                ss = []
                for k in (1, 3):
                    tk = features.toks(r[k]["text"])
                    if len(tk) <= WIN:
                        ss.append(score_text(" ".join(tk)))
                    else:
                        i = rng.integers(0, len(tk) - WIN)
                        ss.append(score_text(" ".join(tk[i:i + WIN])))
                t += 1
                w += ss[0] > ss[1]
        accs.append(w / t)
    print("   %4d-word window (~%3ds): acc %.3f (sd %.3f)"
          % (WIN, WIN / 2.6, np.mean(accs), np.std(accs)))
