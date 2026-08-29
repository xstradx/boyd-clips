import json, math, numpy as np
from scipy import stats
ROOT = "C:/Users/natha/Projects/boyd-clips"
raw = json.load(open(ROOT + "/research/gaze/gz_raw2.json", encoding="utf-8"))
DEAD = 0.08


def grp(f):
    if f.startswith("top_"): return "CT_TOP"
    if f.startswith("bot_"): return "CT_BOT"
    if f[0].isdigit(): return "AUDIT"
    return "OURS"


print("=" * 104)
print("A) VERTICAL EYELINE of the largest face  (craft rule: eyes on the UPPER THIRD, y ~ 0.333 H)")
print("=" * 104)
G = {}
for rec in raw:
    fs = [f for f in rec["faces"] if f["hfrac"] >= 0.12 and f["score"] >= 0.6] or rec["faces"][:1]
    if not fs: continue
    G.setdefault(grp(rec["file"]), []).append((rec, fs))
for g, items in G.items():
    ey = np.array([fs[0]["eyemid_y"] for _, fs in items])
    print("%-7s n=%2d  eye_y median %.3f  IQR %.3f-%.3f  mean %.3f" %
          (g, len(ey), np.median(ey), np.percentile(ey, 25), np.percentile(ey, 75), ey.mean()))
allitems = [it for v in G.values() for it in v]
ey = np.array([fs[0]["eyemid_y"] for _, fs in allitems])
print("ALL     n=%2d  eye_y median %.3f  |  film-school upper-third target = 0.333" % (len(ey), np.median(ey)))

print()
print("=" * 104)
print("B) TEXT vs THE EYELINE and THE GAZE CORRIDOR")
print("=" * 104)
for g, items in G.items():
    above, below, inside_corr, tot = 0, 0, 0, 0
    caps = []
    for rec, fs in items:
        t = rec.get("text")
        if not t: continue
        tot += 1
        e0 = fs[0]["eyemid_y"]
        if t["cy"] < e0: above += 1
        else: below += 1
        caps.append(max(r["capfrac"] for r in t["rows"]))
        if len(fs) > 1:
            lo = min(fs[0]["eyemid_x"], fs[1]["eyemid_x"]); hi = max(fs[0]["eyemid_x"], fs[1]["eyemid_x"])
            if lo <= t["cx"] <= hi: inside_corr += 1
    print("%-7s n=%2d  text centre ABOVE the main eyeline %d/%d | inside the eye-to-eye corridor %d/%d | cap height median %.3f H"
          % (g, tot, above, tot, inside_corr, tot, np.median(caps) if caps else float("nan")))

print()
print("=" * 104)
print("C) TEXT OVERLAPPING FACES - per image (Nathan's rule: never on a face or body)")
print("=" * 104)
for g, items in G.items():
    print("--", g)
    for rec, fs in items:
        t = rec.get("text")
        if not t: continue
        X0, Y0, X1, Y1 = t["bbox"]
        worst = []
        for i, F in enumerate(fs[:3]):
            x0, y0, x1, y1 = F["x"], F["y"], F["x"] + F["w"], F["y"] + F["h"]
            ix = max(0, min(X1, x1) - max(X0, x0)); iy = max(0, min(Y1, y1) - max(Y0, y0))
            if ix * iy > 0:
                worst.append((i, int(ix * iy), 100.0 * ix * iy / (F["w"] * F["h"])))
        if worst:
            print("   %-44s %s" % (rec["file"][:44],
                  " ".join("face%d %dpx (%.0f%% of that face box)" % w for w in worst)))
        else:
            print("   %-44s clean" % rec["file"][:44])

print()
print("=" * 104)
print("D) COURTROOMTIME'S FIXED JUDGE CUTOUT - is it one repeated asset?")
print("=" * 104)
sig = {}
for rec, fs in G.get("CT_TOP", []) + G.get("CT_BOT", []):
    for F in fs:
        k = (round(F["cx"], 2), round(F["hfrac"], 2), round(F["nose_dev"], 2))
        sig.setdefault(k, []).append(rec["file"])
for k, v in sorted(sig.items(), key=lambda kv: -len(kv[1])):
    if len(v) >= 3:
        print("   cx=%.2f hfrac=%.2f nose_dev=%+.2f  -> %d images: %s" %
              (k[0], k[1], k[2], len(v), ", ".join(f[:22] for f in v)))
