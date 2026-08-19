import json, os, numpy as np
from scipy.stats import mannwhitneyu, fisher_exact
D = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(D, "measurements.json"), encoding="utf-8"))
cen = json.load(open(os.path.join(D, "_census.json"), encoding="utf-8"))
for r in rows:
    c = cen.get(r["id"], {})
    r["c_boyd"] = 1 if c.get("judge") == "boyd" else 0
    r["c_judge_any"] = 0 if c.get("judge") == "none" else 1
    r["c_panels2"] = 1 if c.get("panels") == 2 else 0
    r["c_torn"] = c.get("torn", 0)
    r["c_arrow"] = 0 if c.get("arrow") == "none" else 1
    r["c_arrow_red"] = 1 if c.get("arrow") in ("red", "magenta") else 0
    r["c_arrow_yellow"] = 1 if c.get("arrow") == "yellow" else 0
    r["c_stamp"] = c.get("stamp", 0); r["c_cuffs"] = c.get("cuffs", 0)
    r["c_lines"] = c.get("lines", 0)
    r["c_yplate"] = c.get("yellow_plate", 0); r["c_rplate"] = c.get("red_plate", 0)
    r["c_judge_left"] = 1 if c.get("judge_side") == "L" else 0
    # derived
    r["face_big_hfrac"] = r["face_max_hfrac"]
    r["aspect_ok"] = r["W"]/r["H"]

T = [r for r in rows if r["grp"] == "top"]; B = [r for r in rows if r["grp"] == "bot"]
print(f"n_top={len(T)} n_bot={len(B)}")
print(f"views top median={np.median([r['views'] for r in T]):.0f} bot median={np.median([r['views'] for r in B]):.0f}")
print(f"AGE CONTROL playlist-idx mean top={np.mean([r['idx'] for r in T]):.0f} bot={np.mean([r['idx'] for r in B]):.0f} (0=newest of 500)")
print(f"DURATION s  median top={np.median([r['dur'] for r in T]):.0f} bot={np.median([r['dur'] for r in B]):.0f}")
print(f"resolution: {sorted(set((r['W'],r['H']) for r in rows))}")

CONT = ["face_big_hfrac","n_faces","face_max_cx","face_max_cy","cap_frac_max","cap_frac_mainrow",
        "cap_frac_med","text_ink_frac","text_bbox_frac","n_text_rows","n_glyph","n_text_colors",
        "text_top","text_bot","n_bars","bar_height_frac","sat_mean","sat_p90","val_mean",
        "contrast_std","clip_hi","clip_lo","seam_x_frac","seam_rowfrac","seam_strength",
        "lr_rgb_diff","lr_sat_diff","flat_frac","n_big_graphic","graphic_area_frac","n_circles",
        "border_vs_center","border_std","boyd_match","c_lines","dur"]
BIN = ["c_boyd","c_judge_any","c_panels2","c_torn","c_arrow","c_arrow_red","c_arrow_yellow",
       "c_stamp","c_cuffs","c_yplate","c_rplate","c_judge_left","has_text","has_bottom_yellow_bar",
       "has_red_tag_bar"]

print("\n=== CONTINUOUS  (AUC = P(top>bot); 0.5 = no separation) ===")
print(f"{'metric':22s} {'topMed':>9s} {'botMed':>9s} {'d':>7s} {'AUC':>6s} {'p':>7s}")
res = []
for k in CONT:
    a = [r[k] for r in T if r.get(k) is not None]; b = [r[k] for r in B if r.get(k) is not None]
    if len(a) < 5 or len(b) < 4: continue
    a = np.array(a, float); b = np.array(b, float)
    sp = np.sqrt(((len(a)-1)*a.var(ddof=1)+(len(b)-1)*b.var(ddof=1))/(len(a)+len(b)-2))
    d = (a.mean()-b.mean())/sp if sp > 0 else 0.0
    try:
        u, p = mannwhitneyu(a, b, alternative="two-sided"); auc = u/(len(a)*len(b))
    except Exception: p, auc = 1.0, 0.5
    res.append((abs(d), k, np.median(a), np.median(b), d, auc, p))
for _, k, ma, mb, d, auc, p in sorted(res, reverse=True):
    print(f"{k:22s} {ma:9.4f} {mb:9.4f} {d:7.2f} {auc:6.2f} {p:7.3f}")

print("\n=== BINARY  (rate top vs bot) ===")
print(f"{'trait':22s} {'top':>9s} {'bot':>9s} {'diff':>7s} {'p':>7s}")
rb = []
for k in BIN:
    a = sum(1 for r in T if r.get(k)); b = sum(1 for r in B if r.get(k))
    pa, pb = a/len(T), b/len(B)
    try: _, p = fisher_exact([[a, len(T)-a], [b, len(B)-b]])
    except Exception: p = 1.0
    rb.append((abs(pa-pb), k, pa, pb, pa-pb, p, a, b))
for _, k, pa, pb, dd, p, a, b in sorted(rb, reverse=True):
    print(f"{k:22s} {a:2d}/15={pa:4.2f} {b:2d}/10={pb:4.2f} {dd:+7.2f} {p:7.3f}")

print("\n=== TEXT ROW POSITIONS (cy as fraction of H) ===")
for g, S in (("top", T), ("bot", B)):
    allr = [c for r in S for c in (r["row_cys"] or [])]
    print(g, "n_rows", len(allr), "deciles", [round(float(x),3) for x in np.percentile(allr, [10,25,50,75,90])])
    print("   ", g, "text_top med", round(float(np.median([r['text_top'] for r in S if r['text_top'] is not None])),3),
          "text_bot med", round(float(np.median([r['text_bot'] for r in S if r['text_bot'] is not None])),3))

print("\n=== FACE DETAIL (all detected faces) ===")
for g, S in (("top", T), ("bot", B)):
    fh = [f["h_frac"] for r in S for f in r["faces"]]
    fx = [f["cx"] for r in S for f in r["faces"]]
    print(g, "nfaces", len(fh), "h_frac med", round(float(np.median(fh)),3),
          "p90", round(float(np.percentile(fh,90)),3),
          "cx med", round(float(np.median(fx)),3))

print("\n=== COLOUR ===")
for g, S in (("top", T), ("bot", B)):
    print(g, "sat", round(float(np.mean([r['sat_mean'] for r in S])),4),
          "val", round(float(np.mean([r['val_mean'] for r in S])),4),
          "contrast", round(float(np.mean([r['contrast_std'] for r in S])),4),
          "clip_hi", round(float(np.mean([r['clip_hi'] for r in S])),4),
          "clip_lo", round(float(np.mean([r['clip_lo'] for r in S])),4))
json.dump(rows, open(os.path.join(D, "measurements.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
