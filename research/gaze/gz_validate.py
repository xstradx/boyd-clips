# Does nose_dev actually measure head yaw, or is it a detector artefact?
# Mirror test: flip each thumbnail, re-detect, and check nose_dev flips sign with equal magnitude.
# A real yaw measure must be antisymmetric under reflection.
import cv2, numpy as np, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_measure import detect_faces, face_metrics
from scipy import stats

ROOT = "C:/Users/natha/Projects/boyd-clips"
raw = json.load(open(ROOT + "/research/gaze/gz_raw2.json", encoding="utf-8"))
pairs = []
for rec in raw:
    bgr = cv2.imread(rec["path"])
    H, W = bgr.shape[:2]
    flip = cv2.flip(bgr, 1)
    ff = [face_metrics(r, H, W) for r in detect_faces(flip)]
    for F in rec["faces"]:
        if F["hfrac"] < 0.12 or F["score"] < 0.6: continue
        cxm = 1.0 - F["cx"]                       # where it should land in the mirrored image
        cand = [g for g in ff if abs(g["cx"] - cxm) < 0.05 and abs(g["hfrac"] - F["hfrac"]) < 0.06]
        if not cand: continue
        g = min(cand, key=lambda g: abs(g["cx"] - cxm))
        pairs.append((F["nose_dev"], g["nose_dev"], F["asym"], g["asym"], rec["file"]))

a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
c = np.array([p[2] for p in pairs]); d = np.array([p[3] for p in pairs])
print("matched face pairs (original vs mirrored): n=%d" % len(pairs))
r, p = stats.pearsonr(a, -b)
print("nose_dev(original) vs -nose_dev(mirrored):  r=%+.4f  p=%.3g   slope=%.3f" %
      (r, p, np.polyfit(a, -b, 1)[0]))
r2, p2 = stats.pearsonr(c, -d)
print("asym    (original) vs -asym   (mirrored):  r=%+.4f  p=%.3g   slope=%.3f" %
      (r2, p2, np.polyfit(c, -d, 1)[0]))
print("sign agreement (both outside the +-0.08 deadband): %d/%d" % (
    sum(1 for x, y in zip(a, b) if abs(x) > .08 and abs(y) > .08 and np.sign(x) == -np.sign(y)),
    sum(1 for x, y in zip(a, b) if abs(x) > .08 and abs(y) > .08)))
print("median |nose_dev_orig| %.3f   median |nose_dev_mirr| %.3f   median abs residual %.3f" %
      (np.median(np.abs(a)), np.median(np.abs(b)), np.median(np.abs(a + b))))
print()
r3, p3 = stats.pearsonr(a, c)
print("agreement of the two independent proxies on the SAME image: nose_dev vs asym  r=%+.4f p=%.3g" % (r3, p3))
worst = sorted(pairs, key=lambda t: -abs(t[0] + t[1]))[:5]
print("largest disagreements:")
for w in worst:
    print("   %-44s orig %+.3f  mirrored %+.3f  (sum %+.3f)" % (w[4][:44], w[0], w[1], w[0] + w[1]))
