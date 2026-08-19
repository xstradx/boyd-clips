import cv2, numpy as np, json, os
D = os.path.dirname(os.path.abspath(__file__)); TH = os.path.join(D, "thumbs")
meta = json.load(open(os.path.join(D, "thumbmeta.json"), encoding="utf-8"))

# canonical Judge Boyd cutout template: left panel of the #1 video
tsrc = cv2.imread(os.path.join(TH, "top_00790000__-WRN7q01OY_maxresdefault.jpg"))
TH_, TW_ = tsrc.shape[:2]
TEMPL = cv2.cvtColor(tsrc[int(.05*TH_):int(.80*TH_), int(.03*TW_):int(.30*TW_)], cv2.COLOR_BGR2GRAY)
TEMPL = cv2.resize(TEMPL, (120, int(120*TEMPL.shape[0]/TEMPL.shape[1])))
cv2.imwrite(os.path.join(D, "_boyd_template.png"), TEMPL)

def glyph_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[:,:,0].astype(int), hsv[:,:,1].astype(float), hsv[:,:,2].astype(float)
    y = (Hc>=18)&(Hc<=36)&(S>=110)&(V>=150)
    w = (S<=45)&(V>=215)
    r = ((Hc<=8)|(Hc>=170))&(S>=110)&(V>=110)
    g = (Hc>=45)&(Hc<=85)&(S>=110)&(V>=110)
    return y.astype(np.uint8), w.astype(np.uint8), r.astype(np.uint8), g.astype(np.uint8)

def glyphs(m, H, W):
    n, lab, st, ce = cv2.connectedComponentsWithStats(
        cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8)), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if 0.02*H <= h <= 0.30*H and 0.004*W <= w <= 0.35*W and a/(w*h) >= 0.15 and 0.08 <= w/h <= 4.0:
            out.append((x, y, w, h, a))
    return out

def measure(path):
    bgr = cv2.imread(path); H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    r = {}
    ym, wm, rm, gm = glyph_mask(bgr)
    allg = []
    per = {}
    for nm, m in (("y", ym), ("w", wm), ("r", rm), ("g", gm)):
        gl = glyphs(m, H, W); per[nm] = len(gl); allg += [(nm,)+t for t in gl]
    r["glyph_counts"] = per
    r["n_glyph"] = len(allg)
    # union text bbox / band
    if allg:
        ys = [t[2] for t in allg]; hs = [t[4] for t in allg]
        tops = np.array(ys); bots = np.array(ys)+np.array(hs)
        r["text_top"] = float(tops.min()/H); r["text_bot"] = float(bots.max()/H)
        # row clustering on glyph centres
        cys = sorted([(t[2]+t[4]/2)/H for t in allg])
        rows = []; cur = [cys[0]]
        for c in cys[1:]:
            if c-cur[-1] < 0.045: cur.append(c)
            else: rows.append(cur); cur = [c]
        rows.append(cur)
        rows = [q for q in rows if len(q) >= 4]
        r["n_text_rows"] = len(rows)
        r["row_cys"] = [float(np.mean(q)) for q in rows]
        # cap height = 75th pct glyph height among glyphs in the biggest row
        if rows:
            big = max(rows, key=len); lo, hi = min(big)-0.03, max(big)+0.03
            hh = [t[4]/H for t in allg if lo <= (t[2]+t[4]/2)/H <= hi]
            r["cap_frac_mainrow"] = float(np.percentile(hh, 75)) if hh else None
        allh = [t[4]/H for t in allg]
        r["cap_frac_max"] = float(np.percentile(allh, 95))
        r["cap_frac_med"] = float(np.median(allh))
        # ink coverage (glyph pixel area / frame)
        r["text_ink_frac"] = float(sum(t[5] for t in allg)/(H*W))
        # text bbox area (union of row bands x their x-extent)
        r["text_bbox_frac"] = float(sum(
            (max(t[1]+t[3] for t in allg if lo2 <= (t[2]+t[4]/2)/H <= hi2) -
             min(t[1] for t in allg if lo2 <= (t[2]+t[4]/2)/H <= hi2)) *
            (max(t[2]+t[4] for t in allg if lo2 <= (t[2]+t[4]/2)/H <= hi2) -
             min(t[2] for t in allg if lo2 <= (t[2]+t[4]/2)/H <= hi2))
            for lo2, hi2 in [(min(q)-0.03, max(q)+0.03) for q in rows]) / (H*W)) if rows else 0.0
        r["n_text_colors"] = sum(1 for nm in per if per[nm] >= 4)
    else:
        for k in ("text_top","text_bot","cap_frac_mainrow","cap_frac_max","cap_frac_med",
                  "text_ink_frac","text_bbox_frac"): r[k] = None
        r["n_text_rows"] = 0; r["row_cys"] = []; r["n_text_colors"] = 0

    # ---- solid plate bars (long horizontal runs of uniform saturated yellow/red/black)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[:,:,0].astype(int), hsv[:,:,1].astype(float), hsv[:,:,2].astype(float)
    plate_y = ((Hc>=18)&(Hc<=36)&(S>=140)&(V>=170))
    plate_r = (((Hc<=8)|(Hc>=170))&(S>=150)&(V>=90))
    plate_k = (V<=45)
    bars = {}
    for nm, pm in (("yellow", plate_y), ("red", plate_r), ("black", plate_k)):
        rowfrac = pm.mean(axis=1)
        hit = rowfrac > 0.55           # >55% of the width is that flat colour
        runs = []; s = None
        for i, v in enumerate(hit):
            if v and s is None: s = i
            if not v and s is not None:
                if i-s >= 0.02*H: runs.append((s/H, i/H)); s = None
        if s is not None and len(hit)-s >= 0.02*H: runs.append((s/H, 1.0))
        bars[nm] = runs
    r["bars"] = bars
    r["n_bars"] = sum(len(v) for v in bars.values())
    r["bar_height_frac"] = float(sum(b-a for v in bars.values() for a, b in v))
    r["has_bottom_yellow_bar"] = any(b > 0.72 for a, b in bars["yellow"])
    r["has_red_tag_bar"] = len(bars["red"]) > 0

    # ---- Judge Boyd cutout template match (multi-scale, both halves)
    best = 0.0; bestloc = None
    for sc in np.linspace(0.55, 1.45, 19):
        t = cv2.resize(TEMPL, (int(TEMPL.shape[1]*sc*W/1280), int(TEMPL.shape[0]*sc*H/720)))
        if t.shape[0] >= H or t.shape[1] >= W: continue
        res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
        mn, mx, ml, mxl = cv2.minMaxLoc(res)
        if mx > best: best = mx; bestloc = ((mxl[0]+t.shape[1]/2)/W, (mxl[1]+t.shape[0]/2)/H, sc)
    r["boyd_match"] = float(best)
    r["boyd_cx"] = bestloc[0] if bestloc else None
    r["boyd_scale"] = bestloc[2] if bestloc else None
    return r

out = json.load(open(os.path.join(D, "measurements.json"), encoding="utf-8"))
for rec in out:
    rec.update(measure(os.path.join(TH, rec["file"])))
    print(rec["grp"], rec["views"], "rows", rec["n_text_rows"], "ink", round(rec["text_ink_frac"] or 0, 4),
          "cap", round(rec["cap_frac_max"] or 0, 3), "bars", rec["n_bars"],
          "barH", round(rec["bar_height_frac"], 3), "boyd", round(rec["boyd_match"], 3))
json.dump(out, open(os.path.join(D, "measurements.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("OK")
