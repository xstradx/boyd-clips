"""Re-measure expression on high-confidence faces only, with a teeth metric that is
spatially constrained to the oral cavity so a beard or a beige wall cannot score."""
import cv2, numpy as np, json, math
from scipy.stats import mannwhitneyu, fisher_exact, spearmanr

ROOT = "C:/Users/natha/Projects/boyd-clips/research/reference"
OUT = ROOT + "/_facemeas"
R = json.load(open(OUT + "/metrics.json", encoding="utf-8"))
CONF = 0.90


def pathof(r):
    return (ROOT + "/competitor/thumbs/" + r["file"]) if r["grp"] == "ATC" \
        else (ROOT + "/courtroomtime/thumbs/" + r["file"])


def measure(img, p):
    eyed = p["eyed"]
    mmid = np.array(p["mmid"]); emid = np.array(p["emid"])
    ev = np.array(p["ev"]); perp = np.array(p["perp"])
    N = 96

    def sample(c, hw, hh, n=N):
        u = np.linspace(-hw, hw, n); v = np.linspace(-hh, hh, n)
        UU, VV = np.meshgrid(u, v)
        X = c[0] + UU * ev[0] + VV * perp[0]
        Y = c[1] + UU * ev[1] + VV * perp[1]
        return cv2.remap(img, X.astype(np.float32), Y.astype(np.float32),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    ch = np.concatenate([
        sample(emid + ev * (0.45 * eyed) + perp * (0.55 * eyed), 0.15 * eyed, 0.15 * eyed, 20).reshape(-1, 3),
        sample(emid - ev * (0.45 * eyed) + perp * (0.55 * eyed), 0.15 * eyed, 0.15 * eyed, 20).reshape(-1, 3)])
    hsvc = cv2.cvtColor(ch.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV)
    skinV = float(np.median(hsvc[:, 0, 2])); skinS = float(np.median(hsvc[:, 0, 1]))

    m = sample(mmid, 0.62 * eyed, 0.62 * eyed)
    hsv = cv2.cvtColor(m.astype(np.uint8), cv2.COLOR_BGR2HSV)
    V = hsv[:, :, 2].astype(float); S = hsv[:, :, 1].astype(float)
    dark = V < max(28.0, 0.40 * skinV)

    rd = dark.mean(axis=1); rows = np.where(rd > 0.18)[0]
    gape = (rows[-1] - rows[0] + 1) / N * 1.24 if len(rows) else 0.0

    # cavity = the dark blob, dilated; teeth must sit INSIDE or touching it
    cav = cv2.dilate(dark.astype(np.uint8), np.ones((9, 9), np.uint8))
    teeth = (V > max(skinV * 1.02, 120.0)) & (S < max(40.0, 0.50 * skinS)) & (cav > 0)
    # and must be a contiguous horizontal band, not scattered speckle
    tb = cv2.morphologyEx(teeth.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 7), np.uint8))
    return dict(gape=float(gape), teeth=float(tb.mean()), dark=float(dark.mean()),
                cavity_dark=float((dark & (cav > 0)).mean()))


rows = []
for r in R:
    img = cv2.imread(pathof(r))
    fs = [f for f in r["faces"] if f["conf"] >= CONF and f.get("pose")]
    per = []
    for f in fs:
        e = measure(img, f["pose"])
        e["cx"] = f["cx"]; e["area"] = f["area_frac"]; e["conf"] = f["conf"]
        per.append(e)
    rows.append(dict(grp=r["grp"], file=r["file"], views=r["views"], dur=r["dur"],
                     n=len(per), faces=per,
                     max_gape=max([p["gape"] for p in per], default=None),
                     max_teeth=max([p["teeth"] for p in per], default=None),
                     big_gape=(max(per, key=lambda p: p["area"])["gape"] if per else None),
                     any_scream=(1 if any(p["gape"] > 0.55 for p in per) else 0),
                     n_scream=sum(1 for p in per if p["gape"] > 0.55)))

json.dump(rows, open(OUT + "/expr2.json", "w"), indent=1)

TOP = [r for r in rows if r["grp"] == "CT_top"]
BOT = [r for r in rows if r["grp"] == "CT_bot"]
ATC = [r for r in rows if r["grp"] == "ATC"]

print("conf threshold >= %.2f ; faces kept: ATC=%d TOP=%d BOT=%d"
      % (CONF, sum(r["n"] for r in ATC), sum(r["n"] for r in TOP), sum(r["n"] for r in BOT)))

print("\n--- per-file: max gape over high-confidence faces (gape>0.55 = wide open mouth) ---")
for lab, G in (("ATC", ATC), ("TOP", TOP), ("BOT", BOT)):
    print("\n[%s]" % lab)
    for r in sorted(G, key=lambda r: -r["views"]):
        mg = r["max_gape"]
        print("  %-44s v=%-8d n=%d maxgape=%-6s scream=%d"
              % (r["file"][:44], r["views"], r["n"],
                 ("%.2f" % mg) if mg is not None else "n/a", r["n_scream"]))


def cliffs(a, b):
    return (sum(x > y for x in a for y in b) - sum(x < y for x in a for y in b)) / float(len(a) * len(b))


print("\n--- SCREAM (any high-conf face with gape>0.55) : 2x2 Fisher ---")
for lab, A, B, la, lb in (("TOP vs BOT", TOP, BOT, "top", "bot"),
                          ("ATC vs CT", ATC, TOP + BOT, "ATC", "CT")):
    a1 = sum(r["any_scream"] for r in A); a0 = len(A) - a1
    b1 = sum(r["any_scream"] for r in B); b0 = len(B) - b1
    odds, p = fisher_exact([[a1, a0], [b1, b0]])
    print("  %-12s %s %d/%d scream   %s %d/%d scream   OR=%.3g  p=%.4f"
          % (lab, la, a1, len(A), lb, b1, len(B), odds, p))

print("\n--- continuous ---")
for key in ("max_gape", "big_gape", "max_teeth", "n_scream"):
    for lab, A, B in (("top vs bot", TOP, BOT), ("ATC vs CT", ATC, TOP + BOT)):
        a = [r[key] for r in A if r[key] is not None]
        b = [r[key] for r in B if r[key] is not None]
        if len(a) < 3 or len(b) < 3:
            continue
        u, p = mannwhitneyu(a, b, alternative="two-sided")
        print("  %-10s %-12s med %.3f vs %.3f   delta=%+.2f p=%.4f"
              % (key, lab, np.median(a), np.median(b), cliffs(a, b), p))

print("\n--- gape vs views (spearman) ---")
for lab, G in (("ATC", ATC), ("CT all", TOP + BOT), ("all 37", rows)):
    v = [(r["max_gape"], r["views"]) for r in G if r["max_gape"] is not None]
    rho, p = spearmanr([t[0] for t in v], [t[1] for t in v])
    print("  %-8s n=%d  rho=%+.3f p=%.4f" % (lab, len(v), rho, p))
