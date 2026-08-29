"""Remaining territory: face dominance, gaze convergence, side placement,
and exactly what survives the downscale to feed size."""
import cv2, numpy as np, json, math
from scipy.stats import mannwhitneyu, spearmanr, fisher_exact

ROOT = "C:/Users/natha/Projects/boyd-clips/research/reference"
OUT = ROOT + "/_facemeas"
R = json.load(open(OUT + "/metrics.json", encoding="utf-8"))
CONF = 0.90


def pathof(r):
    return (ROOT + "/competitor/thumbs/" + r["file"]) if r["grp"] == "ATC" \
        else (ROOT + "/courtroomtime/thumbs/" + r["file"])


def cl(a, b):
    return (sum(x > y for x in a for y in b) - sum(x < y for x in a for y in b)) / float(len(a) * len(b))


rows = []
for r in R:
    fs = sorted([f for f in r["faces"] if f["conf"] >= CONF], key=lambda f: -f["area_frac"])
    d = dict(grp=r["grp"], file=r["file"], views=r["views"], n=len(fs))
    if fs:
        b = fs[0]
        d["dom_area"] = b["area_frac"]
        d["dom_h"] = b["h_frac"]
        d["dom_cx"] = b["cx"]
        d["dom_cy"] = b["cy"]
        d["dom_side"] = "R" if b["cx"] > 0.5 else "L"
        d["dom_yaw"] = b["pose"]["yaw"] if b.get("pose") else None
        # dominance = how much bigger the biggest face is than the second
        d["ratio21"] = fs[1]["area_frac"] / fs[0]["area_frac"] if len(fs) > 1 else 0.0
        d["dominant_single"] = 1 if d["ratio21"] < 0.5 else 0
        # share of total face area held by the biggest face
        tot = sum(f["area_frac"] for f in fs)
        d["dom_share"] = b["area_frac"] / tot
        # gaze convergence: for the two biggest faces, does each face turn toward
        # the other?  yaw>0 means the nose is offset toward the subject's own left
        # in image terms the sign of yaw tells which way the head is turned.
        if len(fs) > 1 and fs[0].get("pose") and fs[1].get("pose"):
            f0, f1 = (fs[0], fs[1]) if fs[0]["cx"] < fs[1]["cx"] else (fs[1], fs[0])
            y0 = f0["pose"]["yaw"]; y1 = f1["pose"]["yaw"]
            d["converge"] = 1 if (y0 > 0.03 and y1 < -0.03) else 0
            d["diverge"] = 1 if (y0 < -0.03 and y1 > 0.03) else 0
            d["both_camera"] = 1 if (abs(y0) < 0.12 and abs(y1) < 0.12) else 0
            d["yaw_gap"] = abs(f0["cx"] - f1["cx"])
    rows.append(d)

ATC = [r for r in rows if r["grp"] == "ATC" and r["n"]]
TOP = [r for r in rows if r["grp"] == "CT_top" and r["n"]]
BOT = [r for r in rows if r["grp"] == "CT_bot" and r["n"]]
CT = TOP + BOT

print("=== FACE DOMINANCE (conf>=%.2f) ===" % CONF)
print("%-46s %8s %3s %6s %6s %6s %4s %5s" %
      ("file", "views", "n", "domH", "r2/1", "share", "side", "yaw"))
for lab, G in (("ATC", ATC), ("TOP", TOP), ("BOT", BOT)):
    print("[%s]" % lab)
    for r in sorted(G, key=lambda r: -r["views"]):
        print("  %-44s %8d %3d %6.3f %6.3f %6.3f %4s %+5.2f" %
              (r["file"][:44], r["views"], r["n"], r["dom_h"], r["ratio21"],
               r["dom_share"], r["dom_side"], r["dom_yaw"] if r["dom_yaw"] is not None else 0))

print("\n=== ratio21 (2nd face area / 1st face area) vs views ===")
for lab, G in (("ATC n=12", ATC), ("CT all", CT), ("TOP", TOP)):
    v = [(r["ratio21"], r["views"]) for r in G]
    rho, p = spearmanr([t[0] for t in v], [t[1] for t in v])
    print("  %-9s rho=%+.3f p=%.4f  median ratio21=%.3f" % (lab, rho, p, np.median([t[0] for t in v])))

print("\n=== dom_share (biggest face's share of all face area) vs views ===")
for lab, G in (("ATC n=12", ATC), ("CT all", CT)):
    v = [(r["dom_share"], r["views"]) for r in G]
    rho, p = spearmanr([t[0] for t in v], [t[1] for t in v])
    print("  %-9s rho=%+.3f p=%.4f" % (lab, rho, p))

print("\n=== single-dominant-face (ratio21<0.5) : Fisher ===")
for lab, A, B in (("ATC vs CT", ATC, CT), ("TOP vs BOT", TOP, BOT)):
    a1 = sum(r["dominant_single"] for r in A); b1 = sum(r["dominant_single"] for r in B)
    od, p = fisher_exact([[a1, len(A) - a1], [b1, len(B) - b1]])
    print("  %-11s %d/%d vs %d/%d  OR=%.3g p=%.4f" % (lab, a1, len(A), b1, len(B), od, p))

print("\n=== ATC split at the median view count (n=6 vs n=6) ===")
med = np.median([r["views"] for r in ATC])
hi = [r for r in ATC if r["views"] > med]; lo = [r for r in ATC if r["views"] <= med]
for k in ("ratio21", "dom_share", "dom_h", "n"):
    a = [r[k] for r in hi]; b = [r[k] for r in lo]
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    print("  %-10s hi med %.3f  lo med %.3f  d=%+.2f p=%.4f" % (k, np.median(a), np.median(b), cl(a, b), p))

print("\n=== gaze ===")
for lab, G in (("ATC", ATC), ("TOP", TOP), ("BOT", BOT)):
    c = sum(r.get("converge", 0) for r in G)
    dv = sum(r.get("diverge", 0) for r in G)
    bc = sum(r.get("both_camera", 0) for r in G)
    nn = sum(1 for r in G if "converge" in r)
    print("  %-4s of %d two-face images: converge(face each other)=%d diverge=%d both-to-camera=%d"
          % (lab, nn, c, dv, bc))

print("\n=== dominant face side ===")
for lab, G in (("ATC", ATC), ("TOP", TOP), ("BOT", BOT)):
    rr = sum(1 for r in G if r["dom_side"] == "R")
    print("  %-4s right=%d/%d  median dom_cx=%.3f" % (lab, rr, len(G), np.median([r["dom_cx"] for r in G])))

# ---- what survives the downscale, measured per region ----
print("\n=== 210px SURVIVAL: per-region detail retention (SSIM of 210->upscale vs original) ===")
from skimage.metrics import structural_similarity as ssim
surv = []
for r in R:
    img = cv2.imread(pathof(r))
    H, W = img.shape[:2]
    small = cv2.resize(img, (210, 118), interpolation=cv2.INTER_AREA)
    rt = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
    g0 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g1 = cv2.cvtColor(rt, cv2.COLOR_BGR2GRAY)
    _, smap = ssim(g0, g1, full=True)
    fs = sorted([f for f in r["faces"] if f["conf"] >= CONF], key=lambda f: -f["area_frac"])
    e = dict(grp=r["grp"], file=r["file"], views=r["views"], whole=float(smap.mean()))
    if fs:
        b = fs[0]
        x0, y0 = max(0, int(b["x"])), max(0, int(b["y"]))
        x1, y1 = min(W, int(b["x"] + b["w"])), min(H, int(b["y"] + b["h"]))
        e["face"] = float(smap[y0:y1, x0:x1].mean())
        # eye region only - the part that carries identity/emotion
        p = b.get("pose")
        if p:
            ex, ey = p["emid"]; ed = p["eyed"]
            a0, b0 = max(0, int(ey - 0.4 * ed)), max(0, int(ex - 1.0 * ed))
            a1, b1 = min(H, int(ey + 0.4 * ed)), min(W, int(ex + 1.0 * ed))
            if a1 > a0 and b1 > b0:
                e["eyes"] = float(smap[a0:a1, b0:b1].mean())
                e["eyed_px_at210"] = float(ed * 210.0 / W)
    surv.append(e)

for lab, key in (("whole frame", "whole"), ("dominant face box", "face"), ("eye band", "eyes")):
    a = [r[key] for r in surv if r["grp"] == "ATC" and key in r]
    b = [r[key] for r in surv if r["grp"].startswith("CT") and key in r]
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    print("  %-18s ATC %.3f [%.3f-%.3f]  CT %.3f [%.3f-%.3f]  d=%+.2f p=%.4f"
          % (lab, np.median(a), min(a), max(a), np.median(b), min(b), max(b), cl(a, b), p))

print("\n  eye separation in px at 210px-wide render:")
for lab, g in (("ATC", "ATC"), ("TOP", "CT_top"), ("BOT", "CT_bot")):
    v = [r["eyed_px_at210"] for r in surv if r["grp"] == g and "eyed_px_at210" in r]
    print("    %-4s median %.1f px  range %.1f-%.1f  (n=%d)" % (lab, np.median(v), min(v), max(v), len(v)))

json.dump(dict(dom=rows, surv=surv), open(OUT + "/final.json", "w"), indent=1)
