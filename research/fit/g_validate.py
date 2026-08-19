import os, sys
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import corpus, features
import numpy as np
docs = corpus.load()
rich = [d for d in docs if d["text"].count(">>") > 5]
print("rich docs", len(rich))
rows = []
for d in rich:
    n = len(d["words"])
    tm = d["text"].count(">>") * 1000.0 / max(n, 1)
    f = features.structural(d)
    rows.append((tm, f["pause_rate_05"], f["pause_rate_10"], f["pause_rate_20"], f["mean_run"]))
a = np.array(rows)
names = ["pause>0.5", "pause>1.0", "pause>2.0", "mean_run"]
print("corr of '>>' rate per 1k words vs pause features (n=%d):" % len(rows))
for i, nm in enumerate(names):
    r = np.corrcoef(a[:, 0], a[:, i + 1])[0, 1]
    print(f"   {nm:10s} pearson r = {r:+.3f}")
print("\n'>>' per 1k: mean %.1f sd %.1f" % (a[:, 0].mean(), a[:, 0].std()))
print("pause>1.0 per 1k: mean %.1f sd %.1f" % (a[:, 2].mean(), a[:, 2].std()))
