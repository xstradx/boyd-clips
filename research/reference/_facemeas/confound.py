"""Is the ATC-vs-CT complexity gap real design, or just softer/upscaled source?
Three independent checks:
 1. effective resolution  - radial power spectrum slope + Laplacian variance
 2. graphics load         - fraction of frame that is flat manufactured colour
                            (large uniform regions: plates, borders, text boxes)
 3. is the gap carried by the PHOTO or by the GRAPHICS? measure edge density
    inside the largest detected face only (photo region), vs whole frame.
"""
import cv2, numpy as np, json, math
from scipy.stats import mannwhitneyu

ROOT = "C:/Users/natha/Projects/boyd-clips/research/reference"
OUT = ROOT + "/_facemeas"
R = json.load(open(OUT + "/metrics.json", encoding="utf-8"))


def pathof(r):
    return (ROOT + "/competitor/thumbs/" + r["file"]) if r["grp"] == "ATC" \
        else (ROOT + "/courtroomtime/thumbs/" + r["file"])


def spectrum_slope(g):
    f = np.fft.fftshift(np.abs(np.fft.fft2(g.astype(float))))
    h, w = g.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - cy, xx - cx).astype(int)
    nb = np.bincount(r.ravel(), f.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    k = np.arange(4, min(cy, cx))
    y = nb[4:min(cy, cx)]
    m = y > 0
    return float(np.polyfit(np.log(k[m]), np.log(y[m]), 1)[0])


def flat_fraction(img):
    """Fraction of pixels inside a large region of near-constant colour
    (>=0.5% of the frame). Manufactured graphics; photographs have almost none."""
    q = (img // 12).astype(np.uint8)
    code = q[:, :, 0].astype(np.int32) * 484 + q[:, :, 1] * 22 + q[:, :, 2]
    tot = 0
    H, W = img.shape[:2]
    minA = int(0.005 * H * W)
    for c in np.unique(code):
        m = (code == c).astype(np.uint8)
        if m.sum() < minA:
            continue
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        tot += int(stats[1:, cv2.CC_STAT_AREA][stats[1:, cv2.CC_STAT_AREA] >= minA].sum())
    return tot / float(H * W)


rows = []
for r in R:
    img = cv2.imread(pathof(r))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = img.shape[:2]
    lapv = float(cv2.Laplacian(g, cv2.CV_64F).var())
    slope = spectrum_slope(cv2.resize(g, (512, 512), interpolation=cv2.INTER_AREA))
    flat = flat_fraction(cv2.resize(img, (640, 360), interpolation=cv2.INTER_AREA))
    # edge density restricted to the largest face box = the photographic region
    fe = None
    if r["faces"]:
        b = r["faces"][0]
        x0, y0 = max(0, int(b["x"])), max(0, int(b["y"]))
        x1, y1 = min(W, int(b["x"] + b["w"])), min(H, int(b["y"] + b["h"]))
        if x1 - x0 > 20 and y1 - y0 > 20:
            sub = g[y0:y1, x0:x1]
            sub = cv2.resize(sub, (128, 128), interpolation=cv2.INTER_AREA)
            fe = float(cv2.Canny(sub, 80, 180).mean() / 255.0)
            flapv = float(cv2.Laplacian(sub, cv2.CV_64F).var())
        else:
            flapv = None
    else:
        flapv = None
    rows.append(dict(grp=r["grp"], file=r["file"], views=r["views"],
                     lapvar=lapv, spec_slope=slope, flat_frac=flat,
                     face_edge=fe, face_lapvar=flapv,
                     edge_full=r["edge_fixed"], uniq=r["uniq5bit"], sal=r["sal_top10"]))

json.dump(rows, open(OUT + "/confound.json", "w"), indent=1)
ATC = [r for r in rows if r["grp"] == "ATC"]
CT = [r for r in rows if r["grp"].startswith("CT")]
TOP = [r for r in rows if r["grp"] == "CT_top"]
BOT = [r for r in rows if r["grp"] == "CT_bot"]


def cl(a, b):
    return (sum(x > y for x in a for y in b) - sum(x < y for x in a for y in b)) / float(len(a) * len(b))


def show(k, A, B, la, lb):
    a = [r[k] for r in A if r[k] is not None]
    b = [r[k] for r in B if r[k] is not None]
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    sep = "SEPARATES" if (max(a) < min(b) or max(b) < min(a)) else ""
    print("  %-12s %s med %8.4f [%7.4f-%8.4f]  %s med %8.4f [%7.4f-%8.4f]  d=%+.2f p=%.4f %s"
          % (k, la, np.median(a), min(a), max(a), lb, np.median(b), min(b), max(b), cl(a, b), p, sep))


print("ATC vs CT")
for k in ("lapvar", "spec_slope", "flat_frac", "face_edge", "face_lapvar", "edge_full"):
    show(k, ATC, CT, "ATC", "CT ")
print("\nCT top vs CT bot")
for k in ("lapvar", "spec_slope", "flat_frac", "face_edge", "face_lapvar", "edge_full"):
    show(k, TOP, BOT, "top", "bot")

print("\nper-file flat_frac (manufactured-graphics load) and face sharpness")
for lab, G in (("ATC", ATC), ("TOP", TOP), ("BOT", BOT)):
    print("[%s]" % lab)
    for r in sorted(G, key=lambda r: -r["views"]):
        print("   %-44s v=%-8d flat=%.3f faceLapVar=%-7s specSlope=%+.2f"
              % (r["file"][:44], r["views"], r["flat_frac"],
                 ("%.0f" % r["face_lapvar"]) if r["face_lapvar"] else "n/a", r["spec_slope"]))
