import cv2, numpy as np, json, os, math
D = os.path.dirname(os.path.abspath(__file__))
TH = os.path.join(D, "thumbs")
meta = json.load(open(os.path.join(D, "thumbmeta.json"), encoding="utf-8"))

CAS = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
       ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
        "haarcascade_profileface.xml")]

def nms(boxes, thr=0.35):
    if not boxes: return []
    b = np.array(boxes, float)
    x1, y1 = b[:,0], b[:,1]; x2, y2 = b[:,0]+b[:,2], b[:,1]+b[:,3]
    a = b[:,2]*b[:,3]; order = a.argsort()[::-1]; keep = []
    while order.size:
        i = order[0]; keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]]); yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]]); yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2-xx1)*np.maximum(0, yy2-yy1)
        iou = inter/np.minimum(a[i], a[order[1:]])
        order = order[1:][iou < thr]
    return [boxes[i] for i in keep]

def detect_faces(gray, H, W):
    out = []
    for c in CAS:
        for sf in (1.06, 1.12):
            f = c.detectMultiScale(gray, sf, 6, minSize=(int(H*0.06), int(H*0.06)))
            out += [tuple(map(int, r)) for r in f]
    return nms(out)

def comps(mask, H, W):
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    g = []
    for i in range(1, n):
        x, y, w, h, ar = stats[i]
        if not (0.018*H <= h <= 0.34*H): continue
        if not (0.003*W <= w <= 0.40*W): continue
        if h == 0 or w == 0: continue
        asp = w/h
        if not (0.08 <= asp <= 5.0): continue
        if ar/(w*h) < 0.12: continue
        g.append((x, y, w, h, ar))
    return g

def rows_from(g, H):
    g = sorted(g, key=lambda c: c[1]+c[3]/2)
    rows = []
    for c in g:
        cy = c[1]+c[3]/2
        placed = False
        for r in rows:
            rcy = np.mean([q[1]+q[3]/2 for q in r]); rh = np.mean([q[3] for q in r])
            if abs(cy-rcy) < 0.6*max(rh, c[3]):
                r.append(c); placed = True; break
        if not placed: rows.append([c])
    return [r for r in rows if len(r) >= 3]

def words_in(row):
    row = sorted(row, key=lambda c: c[0])
    mw = np.median([c[2] for c in row])
    n = 1
    for a, b in zip(row, row[1:]):
        if b[0]-(a[0]+a[2]) > 0.85*mw: n += 1
    return n

def measure(path):
    bgr = cv2.imread(path); H, W = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    Hc, S, V = hsv[:,:,0].astype(int), hsv[:,:,1].astype(float), hsv[:,:,2].astype(float)
    r = {"W": W, "H": H}
    r["sat_mean"] = float(S.mean()/255); r["sat_p90"] = float(np.percentile(S, 90)/255)
    r["val_mean"] = float(V.mean()/255)
    r["contrast_std"] = float(gray.std()/255)
    r["clip_hi"] = float((V >= 250).mean()); r["clip_lo"] = float((V <= 8).mean())
    r["p01"] = float(np.percentile(gray,1)); r["p99"] = float(np.percentile(gray,99))

    # ---- vertical seam / 2-panel split
    small = cv2.resize(gray, (320, 180))
    dx = np.abs(cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3))
    colscore = dx.mean(axis=0)
    inner = colscore[32:288]
    si = int(np.argmax(inner)) + 32
    r["seam_x_frac"] = si/320.0
    r["seam_strength"] = float(colscore[si]/(np.median(colscore)+1e-6))
    # full-height continuity of that seam
    colfull = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    xf = int(r["seam_x_frac"]*W)
    band = colfull[:, max(0,xf-3):xf+4].max(axis=1)
    r["seam_rowfrac"] = float((band > 40).mean())
    r["seam_color"] = [int(v) for v in rgb[:, min(W-1,xf)].mean(axis=0)]
    # horizontal seam
    dy = np.abs(cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)).mean(axis=1)
    inn = dy[18:162]; hi = int(np.argmax(inn))+18
    r["hseam_y_frac"] = hi/180.0
    r["hseam_strength"] = float(dy[hi]/(np.median(dy)+1e-6))
    rowfull = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    yf = int(r["hseam_y_frac"]*H)
    b2 = rowfull[max(0,yf-3):yf+4, :].max(axis=0)
    r["hseam_colfrac"] = float((b2 > 40).mean())

    # ---- border ring
    t = max(2, int(0.012*H))
    ring = np.concatenate([rgb[:t].reshape(-1,3), rgb[-t:].reshape(-1,3),
                           rgb[:, :t].reshape(-1,3), rgb[:, -t:].reshape(-1,3)])
    r["border_rgb"] = [int(v) for v in ring.mean(axis=0)]
    r["border_std"] = float(ring.std(axis=0).mean())
    ctr = rgb[int(.2*H):int(.8*H), int(.2*W):int(.8*W)].reshape(-1,3).mean(axis=0)
    r["border_vs_center"] = float(np.abs(ring.mean(axis=0)-ctr).mean())

    # ---- faces
    fs = detect_faces(gray, H, W)
    r["n_faces"] = len(fs)
    r["faces"] = [{"h_frac": h/H, "w_frac": w/W, "cx": (x+w/2)/W, "cy": (y+h/2)/H}
                  for (x,y,w,h) in fs]
    if fs:
        big = max(fs, key=lambda f: f[3])
        r["face_max_hfrac"] = big[3]/H
        r["face_max_cx"] = (big[0]+big[2]/2)/W
        r["face_max_cy"] = (big[1]+big[3]/2)/H
    else:
        r["face_max_hfrac"] = r["face_max_cx"] = r["face_max_cy"] = None

    # ---- text (colour-keyed glyphs)
    yellow = ((Hc>=18)&(Hc<=36)&(S>=110)&(V>=150)).astype(np.uint8)
    white  = ((S<=45)&(V>=215)).astype(np.uint8)
    red    = (((Hc<=8)|(Hc>=170))&(S>=110)&(V>=110)).astype(np.uint8)
    k = np.ones((3,3), np.uint8)
    res = {}
    for nm, m in (("yellow", yellow), ("white", white), ("red", red)):
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        g = comps(m, H, W)
        rws = rows_from(g, H)
        res[nm] = {"px_frac": float(m.mean()), "n_glyph": len(g), "n_rows": len(rws),
                   "rows": [{"cy": float(np.mean([q[1]+q[3]/2 for q in rr])/H),
                             "cap": float(np.percentile([q[3] for q in rr], 75)/H),
                             "x0": float(min(q[0] for q in rr)/W),
                             "x1": float(max(q[0]+q[2] for q in rr)/W),
                             "nglyph": len(rr), "nword": words_in(rr)} for rr in rws]}
    r["text"] = res
    allrows = [(nm, rr) for nm in res for rr in res[nm]["rows"]]
    r["has_text"] = len(allrows) > 0
    if allrows:
        best = max(allrows, key=lambda t: t[1]["cap"]*t[1]["nglyph"])
        r["text_color"] = best[0]; r["text_cap_frac"] = best[1]["cap"]
        r["text_cy"] = best[1]["cy"]; r["text_nword"] = best[1]["nword"]
        r["text_x0"] = best[1]["x0"]; r["text_x1"] = best[1]["x1"]
        r["text_nrows"] = sum(res[n]["n_rows"] for n in res)
        r["text_rows_all"] = sorted([rr["cy"] for _, rr in allrows])
    else:
        for kk in ("text_color","text_cap_frac","text_cy","text_nword","text_x0","text_x1","text_rows_all"):
            r[kk] = None
        r["text_nrows"] = 0
    r["text_px_frac"] = float(max(res[n]["px_frac"] for n in res))

    # ---- big saturated non-text graphics (arrows / circles / emoji)
    strong = ((S>=140)&(V>=120)).astype(np.uint8)
    strong = cv2.morphologyEx(strong, cv2.MORPH_OPEN, np.ones((5,5),np.uint8))
    n, lab, st, ce = cv2.connectedComponentsWithStats(strong, 8)
    big = [st[i] for i in range(1,n) if st[i][4] > 0.004*H*W and st[i][3] > 0.10*H]
    r["n_big_graphic"] = len(big)
    r["graphic_area_frac"] = float(sum(b[4] for b in big)/(H*W))
    circ = cv2.HoughCircles(cv2.medianBlur(gray,5), cv2.HOUGH_GRADIENT, 1, int(H*0.2),
                            param1=120, param2=90, minRadius=int(H*0.06), maxRadius=int(H*0.45))
    r["n_circles"] = 0 if circ is None else int(circ.shape[1])

    # ---- flat-plate fraction (cutout-over-plate signal)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    flat = cv2.blur((lap < 4).astype(np.float32), (25,25))
    r["flat_frac"] = float((flat > 0.9).mean())
    # left/right half colour difference (panel signal)
    lh = rgb[:, :W//2].reshape(-1,3).mean(axis=0); rh = rgb[:, W//2:].reshape(-1,3).mean(axis=0)
    r["lr_rgb_diff"] = float(np.abs(lh-rh).mean())
    r["lr_sat_diff"] = float(abs(S[:, :W//2].mean()-S[:, W//2:].mean())/255)
    return r

out = []
for m in meta:
    r = measure(os.path.join(TH, m["file"]))
    r.update({kk: m[kk] for kk in ("grp","file","id","views","dur","idx","title")})
    out.append(r)
    print(m["grp"], m["views"], "faces", r["n_faces"], "cap", r["text_cap_frac"],
          "seam", round(r["seam_x_frac"],3), round(r["seam_rowfrac"],2))
json.dump(out, open(os.path.join(D, "measurements.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("OK", len(out))
