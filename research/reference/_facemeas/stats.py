import json, numpy as np, math
from scipy.stats import mannwhitneyu, spearmanr, fisher_exact

OUT = "C:/Users/natha/Projects/boyd-clips/research/reference/_facemeas"
R = json.load(open(OUT + "/metrics.json", encoding="utf-8"))
for r in R:
    r["big"] = r["faces"][0] if r["faces"] else None
    fs = [f for f in r["faces"] if f["conf"] >= 0.70]
    r["hi"] = fs
    r["big2"] = sorted(fs, key=lambda f: -f["area_frac"])[:2]


def get(r, key):
    b = r["big"]
    if key == "big_h":            return b["h_frac"]
    if key == "big_area":         return b["area_frac"]
    if key == "big_cx":           return b["cx"]
    if key == "big_cy":           return b["cy"]
    if key == "big_thirds_d":     return b["thirds_d"]
    if key == "big_eyed":         return b.get("eyed_frac")
    if key == "n_faces_hi":       return r["n_faces_hi"]
    if key == "sum_face_area":    return sum(f["area_frac"] for f in r["hi"])
    if key == "face2_ratio":
        return (r["big2"][1]["area_frac"] / r["big2"][0]["area_frac"]) if len(r["big2"]) > 1 else 0.0
    if key == "big_yaw":          return abs(b["pose"]["yaw"]) if b.get("pose") else None
    if key == "big_yaw_signed":   return b["pose"]["yaw"] if b.get("pose") else None
    if key == "big_roll":         return abs(b["pose"]["roll"]) if b.get("pose") else None
    if key == "big_pitch":        return b["pose"]["pitch"] if b.get("pose") else None
    if key.startswith("expr_"):
        k = key[5:]
        return b["expr"][k] if b.get("expr") else None
    if key.startswith("maxexpr_"):
        k = key[8:]
        v = [f["expr"][k] for f in r["hi"] if f.get("expr")]
        return max(v) if v else None
    if key.startswith("fg_"):
        return r["fg"][key[3:]] if r.get("fg") else None
    if key.startswith("s210_"):   return r["surv"]["210"][key[5:]]
    if key.startswith("s120_"):   return r["surv"]["120"][key[5:]]
    return r.get(key)


KEYS = ["big_h", "big_area", "big_cx", "big_cy", "big_thirds_d", "big_eyed",
        "n_faces_hi", "sum_face_area", "face2_ratio",
        "big_yaw", "big_roll", "big_pitch",
        "expr_gape_h", "expr_gape_w", "expr_mouth_dark_frac", "expr_teeth_frac", "expr_brow_energy",
        "maxexpr_gape_h", "maxexpr_teeth_frac", "maxexpr_brow_energy",
        "mser_regions", "png512_kb", "uniq5bit", "colors_for_90pct", "col_entropy",
        "edge_otsu", "edge_fixed", "sobel_mean", "hi_freq_frac", "sal_top10",
        "skin_generic", "skin_calibrated", "L_mean", "L_std",
        "fg_dL", "fg_dE", "fg_bg_edge_behind", "fg_outer_L_std",
        "s210_ssim", "s210_edge_retained", "s210_faces_found", "s210_big_face_px",
        "s120_ssim", "s120_edge_retained", "s120_faces_found", "s120_big_face_px"]


def cliffs(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    gt = sum((x > y) for x in a for y in b)
    lt = sum((x < y) for x in a for y in b)
    return (gt - lt) / float(len(a) * len(b))


def cmp(name, A, B, la, lb):
    print("\n" + "=" * 108)
    print("%s   n(%s)=%d  n(%s)=%d" % (name, la, len(A), lb, len(B)))
    print("=" * 108)
    print("%-24s %11s %11s %11s %11s  %7s %7s  %s" %
          ("metric", la + " med", lb + " med", la + " rng", lb + " rng", "delta", "p", "read"))
    res = []
    for k in KEYS:
        a = [get(r, k) for r in A]; b = [get(r, k) for r in B]
        a = [x for x in a if x is not None]; b = [x for x in b if x is not None]
        if len(a) < 3 or len(b) < 3:
            continue
        try:
            u, p = mannwhitneyu(a, b, alternative="two-sided")
        except ValueError:
            continue
        d = cliffs(a, b)
        res.append((abs(d), p, k, np.median(a), np.median(b), min(a), max(a), min(b), max(b), d))
    res.sort(key=lambda t: (t[1], -t[0]))
    for ad, p, k, ma, mb, amin, amax, bmin, bmax, d in res:
        star = "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.10 else ""))
        sep = "SEPARATES" if (amax < bmin or bmax < amin) else ""
        print("%-24s %11.4g %11.4g %5.3g-%-5.3g %5.3g-%-5.3g  %+7.2f %7.4f  %s %s" %
              (k, ma, mb, amin, amax, bmin, bmax, d, p, star, sep))
    return res


ATC = [r for r in R if r["grp"] == "ATC"]
TOP = [r for r in R if r["grp"] == "CT_top"]
BOT = [r for r in R if r["grp"] == "CT_bot"]
CT = TOP + BOT

cmp("A. AUDIT-THE-COURT vs COURTROOMTIME  (cross-channel: different construction)",
    ATC, CT, "ATC", "CT")
cmp("B. CT TOP vs CT BOT  (within-channel, controls creator/audience/niche)",
    TOP, BOT, "top", "bot")

print("\n" + "=" * 108)
print("C. SPEARMAN vs VIEWS, within each corpus")
print("=" * 108)
for nm, S in (("ATC (n=12)", ATC), ("CT all (n=25)", CT), ("CT top only (n=15)", TOP)):
    out = []
    for k in KEYS:
        v = [(get(r, k), r["views"]) for r in S]
        v = [t for t in v if t[0] is not None]
        if len(v) < 8:
            continue
        rho, p = spearmanr([t[0] for t in v], [t[1] for t in v])
        if not math.isnan(rho):
            out.append((p, rho, k))
    out.sort()
    print("\n-- %s --" % nm)
    for p, rho, k in out[:9]:
        print("   %-24s rho=%+.3f  p=%.4f %s" % (k, rho, p, "**" if p < 0.05 else ""))

# duration confound check inside CT
print("\n" + "=" * 108)
print("D. DURATION PARTIAL — does the metric still separate top/bot after matching on length?")
print("=" * 108)
from scipy.stats import kendalltau
durs = [(r, r["dur"]) for r in CT if r["dur"]]
for k in ["mser_regions", "sal_top10", "png512_kb", "maxexpr_gape_h", "big_h", "s120_ssim"]:
    x = [get(r, k) for r, d in durs]; y = [d for r, d in durs]
    z = [1 if r["grp"] == "CT_top" else 0 for r, d in durs]
    if any(v is None for v in x):
        continue
    t1, p1 = kendalltau(x, z)
    t2, p2 = kendalltau(x, y)
    print("   %-20s tau(metric,is_top)=%+.3f p=%.4f | tau(metric,duration)=%+.3f p=%.4f"
          % (k, t1, p1, t2, p2))
