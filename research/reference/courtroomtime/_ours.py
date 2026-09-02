import cv2, numpy as np, json, os, glob, importlib.util, sys
D = os.path.dirname(os.path.abspath(__file__))

# reuse the exact measurement code by exec'ing only the function/const defs
src1 = open(os.path.join(D, "_measure.py"), encoding="utf-8").read().split("\nout = []")[0]
ns1 = {"__file__": os.path.join(D, "_measure.py")}; exec(compile(src1, "_measure.py", "exec"), ns1)
src2 = open(os.path.join(D, "_measure2.py"), encoding="utf-8").read().split("out = json.load")[0]
ns2 = {"__file__": os.path.join(D, "_measure2.py")}; exec(compile(src2, "_measure2.py", "exec"), ns2)

def full(p):
    r = ns1["measure"](p); r.update(ns2["measure"](p)); return r

files = sorted(glob.glob(r"D:\Boyd Clips\BANGERS\*.jpg"))
ours = []
for f in files:
    r = full(f); r["file"] = os.path.basename(f); r["grp"] = "ours"; ours.append(r)
    print(os.path.basename(f), "cap", round(r["cap_frac_max"] or 0, 3),
          "rows", [round(x, 2) for x in r["row_cys"]], "faceH",
          round(r["face_max_hfrac"] or 0, 3), "seam", round(r["seam_x_frac"], 2))
json.dump(ours, open(os.path.join(D, "ours.json"), "w", encoding="utf-8"), indent=1)

ref = json.load(open(os.path.join(D, "measurements.json"), encoding="utf-8"))
T = [r for r in ref if r["grp"] == "top"]; B = [r for r in ref if r["grp"] == "bot"]

def hi(S, k):
    v = [r[k] for r in S if r.get(k) is not None]
    return float(np.median(v)) if v else float("nan")

def rowfrac_above(S, y):
    tot = sum(len(r["row_cys"]) for r in S)
    n = sum(1 for r in S for c in r["row_cys"] if c < y)
    return n/tot if tot else float("nan")

def rowfrac_below(S, y):
    tot = sum(len(r["row_cys"]) for r in S)
    n = sum(1 for r in S for c in r["row_cys"] if c >= y)
    return n/tot if tot else float("nan")

print("\n%-22s %9s %9s %9s" % ("metric", "TOP15", "BOT10", "OURS17"))
for k in ("cap_frac_max", "cap_frac_mainrow", "text_ink_frac", "n_text_rows",
          "face_max_hfrac", "face_max_cx", "face_max_cy", "n_faces",
          "sat_mean", "val_mean", "contrast_std", "clip_hi",
          "seam_x_frac", "seam_rowfrac", "lr_sat_diff", "flat_frac",
          "bar_height_frac", "n_bars", "text_top", "text_bot"):
    print("%-22s %9.4f %9.4f %9.4f" % (k, hi(T, k), hi(B, k), hi(ours, k)))
print("%-22s %9.4f %9.4f %9.4f" % ("textrows_above_0.20", rowfrac_above(T,.20), rowfrac_above(B,.20), rowfrac_above(ours,.20)))
print("%-22s %9.4f %9.4f %9.4f" % ("textrows_below_0.55", rowfrac_below(T,.55), rowfrac_below(B,.55), rowfrac_below(ours,.55)))
for g, S in (("TOP", T), ("BOT", B), ("OURS", ours)):
    allr = [c for r in S for c in r["row_cys"]]
    print(g, "rowcy pct[10,25,50,75,90]", [round(float(x), 3) for x in np.percentile(allr, [10,25,50,75,90])],
          "n_rows/img", round(len(allr)/len(S), 2))
# yellow vs white vs red glyph share
for g, S in (("TOP", T), ("BOT", B), ("OURS", ours)):
    gc = {k: sum(r["glyph_counts"][k] for r in S) for k in ("y", "w", "r", "g")}
    tot = sum(gc.values())
    print(g, "glyph colour share", {k: round(v/tot, 3) for k, v in gc.items()})
