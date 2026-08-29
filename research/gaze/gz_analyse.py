import json, math, os, re
import numpy as np
from scipy import stats

ROOT = "C:/Users/natha/Projects/boyd-clips"
raw = json.load(open(ROOT + "/research/gaze/gz_raw2.json", encoding="utf-8"))
DEAD = 0.08          # |nose_dev| below this = read as frontal, gaze direction undefined


def grp(f):
    if f.startswith("top_"): return "CT_TOP"
    if f.startswith("bot_"): return "CT_BOT"
    if f[0].isdigit():       return "AUDIT"
    return "OURS"


def views(f):
    m = re.match(r"^(?:top_|bot_)?0*(\d+)_", f)
    return int(m.group(1)) if m else None


def gaze_side(nd):
    if nd is None or math.isnan(nd): return 0
    if nd > DEAD:  return +1     # looking image-RIGHT
    if nd < -DEAD: return -1     # looking image-LEFT
    return 0


rows = []
for rec in raw:
    fs = [f for f in rec["faces"] if f["hfrac"] >= 0.12 and f["score"] >= 0.6]
    if not fs:
        fs = rec["faces"][:1]
    if not fs:
        continue
    F0 = fs[0]
    F1 = fs[1] if len(fs) > 1 else None
    d = dict(file=rec["file"], grp=grp(rec["file"]), views=views(rec["file"]),
             n_big=len(fs))
    for tag, F in (("f0", F0), ("f1", F1)):
        if F is None:
            continue
        d[tag + "_cx"] = F["cx"]; d[tag + "_ex"] = F["eyemid_x"]; d[tag + "_ey"] = F["eyemid_y"]
        d[tag + "_h"] = F["hfrac"]; d[tag + "_nd"] = F["nose_dev"]; d[tag + "_as"] = F["asym"]
        g = gaze_side(F["nose_dev"]); d[tag + "_g"] = g
        # side of frame the head sits on
        d[tag + "_side"] = 1 if F["cx"] > 0.5 else -1
        # INWARD = turned toward frame centre
        d[tag + "_inward"] = (g != 0 and g == -d[tag + "_side"])
        d[tag + "_outward"] = (g != 0 and g == d[tag + "_side"])
        # LEAD ROOM = fraction of frame width ahead of the eyes in the gaze direction
        d[tag + "_lead"] = (1.0 - F["eyemid_x"]) if g > 0 else (F["eyemid_x"] if g < 0 else None)
    # ---- two-face relationship
    if F1 is not None:
        L, R = (F0, F1) if F0["cx"] <= F1["cx"] else (F1, F0)
        gl, gr = gaze_side(L["nose_dev"]), gaze_side(R["nose_dev"])
        d["pair_dx"] = abs(F0["eyemid_x"] - F1["eyemid_x"])
        d["pair_dy"] = abs(F0["eyemid_y"] - F1["eyemid_y"])
        d["pair_eyelevel_dy"] = F0["eyemid_y"] - F1["eyemid_y"]
        if gl > 0 and gr < 0:   d["pair"] = "CONVERGE"
        elif gl < 0 and gr > 0: d["pair"] = "DIVERGE"
        elif gl == 0 or gr == 0: d["pair"] = "ONE_FRONTAL"
        elif gl == gr:          d["pair"] = "PARALLEL"
        else:                   d["pair"] = "?"
        # does F0's gaze ray sweep across F1?
        d["f0_looks_at_f1"] = (gaze_side(F0["nose_dev"]) != 0 and
                               np.sign(F1["cx"] - F0["cx"]) == gaze_side(F0["nose_dev"]))
    # ---- text
    t = rec.get("text")
    if t:
        d["tx_cx"] = t["cx"]; d["tx_cy"] = t["cy"]; d["tx_w"] = t["wfrac"]
        d["tx_l"] = t["left_edge"]; d["tx_r"] = t["right_edge"]
        d["tx_rows"] = t["n_rows"]
        g0 = gaze_side(F0["nose_dev"])
        if g0 != 0:
            d["text_on_gaze_side"] = (np.sign(t["cx"] - F0["eyemid_x"]) == g0)
        # text overlapping any big face box
        ov = 0.0
        X0, Y0, X1, Y1 = t["bbox"]
        for F in fs:
            x0, y0 = F["x"], F["y"]; x1, y1 = F["x"] + F["w"], F["y"] + F["h"]
            ix = max(0, min(X1, x1) - max(X0, x0)); iy = max(0, min(Y1, y1) - max(Y0, y0))
            ov += ix * iy
        d["text_face_overlap_px"] = ov
    rows.append(d)


def col(rs, k):
    return np.array([r[k] for r in rs if r.get(k) is not None and not (isinstance(r[k], float) and math.isnan(r[k]))])


def pct(rs, k):
    v = [r[k] for r in rs if k in r and r[k] is not None]
    return (sum(1 for x in v if x), len(v))


G = {g: [r for r in rows if r["grp"] == g] for g in ("AUDIT", "CT_TOP", "CT_BOT", "OURS")}

print("=" * 100)
print("1) IS THE HEAD TURNED INTO THE FRAME?  (nose_dev sign vs which half the head sits in)")
print("=" * 100)
for g, rs in G.items():
    a, b = pct(rs, "f0_inward"); c, dd = pct(rs, "f0_outward")
    a1, b1 = pct(rs, "f1_inward")
    print("%-7s largest face inward %2d/%-2d  outward %2d/%-2d | 2nd face inward %2d/%-2d" %
          (g, a, b, c, dd, a1, b1))
print()
allr = rows
x = col(allr, "f0_cx") - 0.5
y = col([r for r in allr if r.get("f0_cx") is not None], "f0_nd")
r_, p_ = stats.pearsonr(x, y)
rs_, ps_ = stats.spearmanr(x, y)
print("ALL n=%d  corr(cx-0.5 , nose_dev) pearson r=%+.3f p=%.4g | spearman rho=%+.3f p=%.4g"
      % (len(x), r_, p_, rs_, ps_))
for g, rs in G.items():
    xs = np.array([r["f0_cx"] - 0.5 for r in rs if "f0_nd" in r])
    ys = np.array([r["f0_nd"] for r in rs if "f0_nd" in r])
    if len(xs) > 3:
        rr, pp = stats.pearsonr(xs, ys)
        print("   %-7s n=%2d r=%+.3f p=%.4g" % (g, len(xs), rr, pp))

print()
print("=" * 100)
print("2) LEAD ROOM / LOOKING ROOM  (fraction of frame width AHEAD of the eyes, in the gaze direction)")
print("=" * 100)
for g, rs in G.items():
    v = col(rs, "f0_lead")
    v1 = col(rs, "f1_lead")
    if len(v):
        print("%-7s F0 n=%2d  median %.3f  mean %.3f  IQR %.3f-%.3f  min %.3f  >0.5: %d/%d" %
              (g, len(v), np.median(v), v.mean(), np.percentile(v, 25), np.percentile(v, 75),
               v.min(), int((v > .5).sum()), len(v)))
    if len(v1):
        print("        F1 n=%2d  median %.3f  >0.5: %d/%d" % (len(v1), np.median(v1), int((v1 > .5).sum()), len(v1)))

print()
print("=" * 100)
print("3) TWO-FACE EYELINE RELATIONSHIP")
print("=" * 100)
for g, rs in G.items():
    from collections import Counter
    c = Counter(r.get("pair") for r in rs if r.get("pair"))
    tot = sum(c.values())
    print("%-7s n=%2d  " % (g, tot) + "  ".join("%s=%d(%.0f%%)" % (k, v, 100 * v / tot) for k, v in c.most_common()))
    a, b = pct(rs, "f0_looks_at_f1")
    print("        largest face's gaze ray sweeps ACROSS the other face: %d/%d" % (a, b))
    dy = col(rs, "pair_dy"); dx = col(rs, "pair_dx")
    if len(dy):
        print("        eye-midpoint separation  dx median %.3f W   dy median %.3f H" % (np.median(dx), np.median(dy)))

print()
print("=" * 100)
print("4) TEXT vs GAZE")
print("=" * 100)
for g, rs in G.items():
    a, b = pct(rs, "text_on_gaze_side")
    ovs = col(rs, "text_face_overlap_px")
    txc = col(rs, "tx_cx")
    print("%-7s text on the LOOK side of the largest face: %d/%d | text cx median %.3f | text-over-face overlap median %.0f px" %
          (g, a, b, np.median(txc) if len(txc) else float("nan"), np.median(ovs) if len(ovs) else float("nan")))

print()
print("=" * 100)
print("5) WINNERS vs LOSERS  (courtroomtime: same judge, same docket, same channel)")
print("=" * 100)
T, B = G["CT_TOP"], G["CT_BOT"]


def mw(k, lo=None):
    a = col(T, k); b = col(B, k)
    if len(a) < 3 or len(b) < 3: return
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    print("  %-24s TOP med %+.3f (n=%2d) | BOT med %+.3f (n=%2d)  Mann-Whitney U p=%.4f" %
          (k, np.median(a), len(a), np.median(b), len(b), p))


for k in ("f0_nd", "f0_lead", "f1_lead", "pair_dx", "pair_dy", "f0_cx", "f1_cx", "tx_cx"):
    mw(k)
for k in ("f0_inward", "f1_inward", "text_on_gaze_side", "f0_looks_at_f1"):
    a, b = pct(T, k); c, d2 = pct(B, k)
    if b and d2:
        tbl = [[a, b - a], [c, d2 - c]]
        try:
            odd, p = stats.fisher_exact(tbl)
        except Exception:
            p = float("nan")
        print("  %-24s TOP %d/%-2d (%.0f%%) | BOT %d/%-2d (%.0f%%)  Fisher p=%.4f" %
              (k, a, b, 100 * a / b, c, d2, 100 * c / d2, p))
from collections import Counter
print("  pair type  TOP:", Counter(r.get("pair") for r in T if r.get("pair")))
print("  pair type  BOT:", Counter(r.get("pair") for r in B if r.get("pair")))

print()
print("=" * 100)
print("6) VIEW-COUNT CORRELATION (Audit the Court, view count is in the filename)")
print("=" * 100)
A = [r for r in G["AUDIT"] if r["views"]]
for k in ("f0_lead", "f0_nd", "f0_cx", "pair_dx", "pair_dy"):
    v = [(r["views"], r[k]) for r in A if r.get(k) is not None and not (isinstance(r[k], float) and math.isnan(r[k]))]
    if len(v) >= 6:
        rho, p = stats.spearmanr([a for a, _ in v], [b for _, b in v])
        print("  views vs %-10s n=%2d rho=%+.3f p=%.4f" % (k, len(v), rho, p))

print()
print("=" * 100)
print("7) PER-IMAGE DUMP")
print("=" * 100)
hdr = "%-44s %-7s %6s %6s %6s %6s %6s %6s %-11s %5s %5s" % (
    "file", "grp", "f0cx", "f0nd", "f0lead", "f1cx", "f1nd", "f1lead", "pair", "txcx", "gaze?")
print(hdr)
for r in sorted(rows, key=lambda r: (r["grp"], -(r["views"] or 0))):
    def g(k, f="%6.3f"):
        v = r.get(k)
        return (f % v) if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and math.isnan(v)) else "     -"
    print("%-44s %-7s %s %s %s %s %s %s %-11s %s %5s" % (
        r["file"][:44], r["grp"], g("f0_cx"), g("f0_nd"), g("f0_lead"),
        g("f1_cx"), g("f1_nd"), g("f1_lead"), r.get("pair", "-")[:11],
        g("tx_cx", "%5.2f"), str(r.get("text_on_gaze_side", "-"))[:5]))

json.dump(rows, open(ROOT + "/research/gaze/gz_rows.json", "w", encoding="utf-8"), indent=1, default=str)
