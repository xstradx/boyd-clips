# The red arrow is a second directional vector in the composition.
# Does it run WITH the judge's gaze or against it? Where does its tip sit relative to the faces?
import cv2, numpy as np, json, sys, os
ROOT = "C:/Users/natha/Projects/boyd-clips"
raw = json.load(open(ROOT + "/research/gaze/gz_raw2.json", encoding="utf-8"))
DEAD = 0.08


def grp(f):
    if f.startswith("top_"): return "CT_TOP"
    if f.startswith("bot_"): return "CT_BOT"
    if f[0].isdigit(): return "AUDIT"
    return "OURS"


def arrows(bgr):
    H, W = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    red = (((Hc <= 6) | (Hc >= 174)) & (S >= 170) & (V >= 120)).astype(np.uint8)
    yel = ((Hc >= 20) & (Hc <= 34) & (S >= 170) & (V >= 170)).astype(np.uint8)
    out = []
    for cname, m in (("red", red), ("yellow", yel)):
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab, st, ce = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if a < 0.0015 * H * W or a > 0.08 * H * W: continue
            if w < 0.03 * W and h < 0.03 * H: continue
            comp = (lab == i)
            ys, xs = np.nonzero(comp)
            pts = np.stack([xs, ys], 1).astype(np.float64)
            mean = pts.mean(0)
            u, s, vt = np.linalg.svd(pts - mean, full_matrices=False)
            ax = vt[0]                                     # principal axis
            proj = (pts - mean) @ ax
            # width profile along the axis -> the TIP is the narrow end
            perp = (pts - mean) @ vt[1]
            lo, hi = proj.min(), proj.max()
            band = (hi - lo) * 0.18
            wlo = perp[proj < lo + band].std() if (proj < lo + band).sum() > 5 else 0
            whi = perp[proj > hi - band].std() if (proj > hi - band).sum() > 5 else 0
            tip_at_hi = whi < wlo
            tip = mean + ax * (hi if tip_at_hi else lo)
            tail = mean + ax * (lo if tip_at_hi else hi)
            d = tip - tail
            L = float(np.hypot(*d))
            if L < 0.05 * W: continue
            # solidity: an arrow is not a filled blob of text
            hull = cv2.convexHull(np.stack([xs, ys], 1))
            hull_a = cv2.contourArea(hull)
            sol = a / hull_a if hull_a > 0 else 1
            if sol > 0.92 or sol < 0.30: continue
            out.append(dict(colour=cname, area=int(a), area_frac=float(a / (H * W)),
                            bbox=[int(x), int(y), int(x + w), int(y + h)],
                            tip=[float(tip[0] / W), float(tip[1] / H)],
                            tail=[float(tail[0] / W), float(tail[1] / H)],
                            dx=float(d[0] / W), dy=float(d[1] / H),
                            angle_deg=float(np.degrees(np.arctan2(d[1], d[0]))),
                            len_frac=float(L / W), solidity=float(sol)))
    out.sort(key=lambda a: -a["area"])
    return out[:3]


print("%-44s %-7s %-6s %8s %8s %7s %7s  %s" %
      ("file", "grp", "col", "areafrac", "angle", "tipx", "tipy", "vs judge gaze"))
agg = {}
for rec in raw:
    bgr = cv2.imread(rec["path"])
    ars = arrows(bgr)
    fs = [f for f in rec["faces"] if f["hfrac"] >= 0.12 and f["score"] >= 0.6] or rec["faces"][:1]
    if not fs: continue
    F0 = fs[0]
    g0 = 1 if F0["nose_dev"] > DEAD else (-1 if F0["nose_dev"] < -DEAD else 0)
    for a in ars:
        ax = 1 if a["dx"] > 0 else -1
        rel = "-" if g0 == 0 else ("SAME dir" if ax == g0 else "OPPOSED")
        # does the tip land on a face box?
        on = None
        for i, F in enumerate(fs):
            if F["x"] <= a["tip"][0] * rec["W"] <= F["x"] + F["w"] and F["y"] <= a["tip"][1] * rec["H"] <= F["y"] + F["h"]:
                on = i
        print("%-44s %-7s %-6s %8.4f %8.1f %7.3f %7.3f  %-9s tip_on_face=%s" %
              (rec["file"][:44], grp(rec["file"]), a["colour"], a["area_frac"],
               a["angle_deg"], a["tip"][0], a["tip"][1], rel, on))
        agg.setdefault(grp(rec["file"]), []).append((rel, a, F0))
print()
for g, v in agg.items():
    same = sum(1 for r, _, _ in v if r == "SAME dir")
    opp = sum(1 for r, _, _ in v if r == "OPPOSED")
    af = np.array([a["area_frac"] for _, a, _ in v])
    ln = np.array([a["len_frac"] for _, a, _ in v])
    print("%-7s arrows n=%2d | runs WITH the main gaze %d, AGAINST %d | area median %.4f of frame | length median %.3f W"
          % (g, len(v), same, opp, np.median(af), np.median(ln)))
