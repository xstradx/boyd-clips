# -*- coding: utf-8 -*-
"""Measure @courtroomtime thumbs: top_ (winners) vs bot_ (losers), same channel, same judge docket.
Pixels + thumbmeta.json only. No derived docs."""
import io, json, os, sys, math
import numpy as np, cv2

ROOT = r"C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime"
THUMBS = os.path.join(ROOT, "thumbs")
OUT = os.path.join(ROOT, "_ctmeas")
os.makedirs(OUT, exist_ok=True)

meta = json.load(io.open(os.path.join(ROOT, "thumbmeta.json"), encoding="utf-8"))
metaby = {m["file"]: m for m in meta}


# ---------- seams ----------
def seams(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = g.shape
    d = np.abs(g[:, 1:] - g[:, :-1])                 # H x (W-1)
    frac = (d > 28).mean(axis=0)                     # fraction of rows discontinuous
    mean = d.mean(axis=0)
    cands = []
    lo, hi = int(0.10 * W), int(0.90 * W)
    order = np.argsort(-frac)
    for x in order:
        if x < lo or x > hi:
            continue
        if frac[x] < 0.55:
            break
        if any(abs(x - c[0]) < 30 for c in cands):
            continue
        cands.append((int(x), float(frac[x]), float(mean[x])))
        if len(cands) >= 4:
            break
    cands.sort()
    return cands, frac, mean


# ---------- faces ----------
CASCS = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
         ("haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml",
          "haarcascade_profileface.xml")]


def faces(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.equalizeHist(g)
    boxes = []
    for c in CASCS:
        for sf in (1.05, 1.12):
            r = c.detectMultiScale(g, scaleFactor=sf, minNeighbors=6, minSize=(48, 48))
            for (x, y, w, h) in r:
                boxes.append([int(x), int(y), int(w), int(h)])
    gm = cv2.flip(g, 1)
    Wg = g.shape[1]
    for sf in (1.05, 1.12):
        for (x, y, w, h) in CASCS[2].detectMultiScale(gm, scaleFactor=sf, minNeighbors=6, minSize=(48, 48)):
            boxes.append([int(Wg - x - w), int(y), int(w), int(h)])
    if not boxes:
        return []
    scores = [1.0] * len(boxes)
    idx = cv2.dnn.NMSBoxes(boxes, scores, 0.0, 0.3)
    idx = np.array(idx).ravel()
    return [boxes[i] for i in idx]


# ---------- text ----------
def text_mask(bgr):
    """White or yellow glyph body ringed by much darker pixels (heavy stroke)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc = hsv[:, :, 0].astype(int)
    S = hsv[:, :, 1].astype(int)
    V = hsv[:, :, 2].astype(int)
    white = (V > 205) & (S < 60)
    yellow = (Hc >= 18) & (Hc <= 38) & (S > 120) & (V > 175)
    cand = (white | yellow).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(cand, 8)
    Himg, Wimg = cand.shape
    keep = np.zeros_like(cand)
    glyphs = []
    Vf = V.astype(np.float32)
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if h < 12 or h > 0.45 * Himg:
            continue
        if w < 3 or w > 0.75 * Wimg:
            continue
        if a < 40:
            continue
        ar = w / float(h)
        if ar > 6.0:
            continue
        fill = a / float(w * h)
        if fill < 0.10 or fill > 0.97:
            continue
        pad = max(3, int(h * 0.18))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(Wimg, x + w + pad), min(Himg, y + h + pad)
        sub = (lab[y0:y1, x0:x1] == i)
        ring = cv2.dilate(sub.astype(np.uint8), np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)) & (~sub)
        rv = Vf[y0:y1, x0:x1][ring.astype(bool)]
        bv = Vf[y0:y1, x0:x1][sub]
        if rv.size < 20:
            continue
        dark = float((rv < 90).mean())
        contrast = float(bv.mean() - np.median(rv))
        if dark < 0.35 or contrast < 70:
            continue
        keep[lab == i] = 1
        glyphs.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a),
                           yellow=bool(yellow[lab == i].mean() > 0.5)))
    return keep, glyphs


def lines_from_glyphs(glyphs, H):
    if not glyphs:
        return []
    gs = sorted(glyphs, key=lambda g: g["y"] + g["h"] / 2)
    lines, cur = [], [gs[0]]
    for g in gs[1:]:
        cy = g["y"] + g["h"] / 2
        ref = np.median([c["y"] + c["h"] / 2 for c in cur])
        refh = np.median([c["h"] for c in cur])
        if abs(cy - ref) <= 0.62 * max(refh, g["h"]):
            cur.append(g)
        else:
            lines.append(cur)
            cur = [g]
    lines.append(cur)
    out = []
    for L in lines:
        if len(L) < 2:
            continue
        hs = sorted(c["h"] for c in L)
        cap = float(np.percentile(hs, 75))
        x0 = min(c["x"] for c in L)
        x1 = max(c["x"] + c["w"] for c in L)
        y0 = min(c["y"] for c in L)
        y1 = max(c["y"] + c["h"] for c in L)
        out.append(dict(n=len(L), cap=cap, cap_frac=cap / H,
                        x0=int(x0), x1=int(x1), y0=int(y0), y1=int(y1),
                        x0f=x0 / float(W_REF), x1f=x1 / float(W_REF),
                        y0f=y0 / float(H), y1f=y1 / float(H),
                        yellow=sum(1 for c in L if c["yellow"])))
    return out


# ---------- red callouts ----------
def red_blobs(bgr):
    b = bgr[:, :, 0].astype(int)
    g = bgr[:, :, 1].astype(int)
    r = bgr[:, :, 2].astype(int)
    m = ((r > 130) & (r - g > 60) & (r - b > 60)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    H, W = m.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 400:
            continue
        out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a),
                        af=a / float(H * W), cx=float(cent[i][0] / W), cy=float(cent[i][1] / H)))
    out.sort(key=lambda d: -d["a"])
    return out[:6]


# ---------- colour ----------
def colour(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1].astype(np.float32) / 255.0
    V = hsv[:, :, 2].astype(np.float32) / 255.0
    mx = bgr.max(axis=2)
    lum = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return dict(sat=float(S.mean()), val=float(V.mean()),
                clip250=float((mx >= 250).mean()), clip240=float((mx >= 240).mean()),
                lum=float(lum.mean()), lum_sd=float(lum.std()),
                dark=float((lum < 40).mean()))


rows = []
W_REF = 1280
for f in sorted(os.listdir(THUMBS)):
    if not f.lower().endswith(".jpg"):
        continue
    p = os.path.join(THUMBS, f)
    bgr = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
    H, W = bgr.shape[:2]
    W_REF = W
    sm, frac, mean = seams(bgr)
    fb = faces(bgr)
    tm, glyphs = text_mask(bgr)
    L = lines_from_glyphs(glyphs, H)
    ys, xs = np.nonzero(tm)
    if ys.size:
        tb = dict(x0=float(xs.min()) / W, x1=float(xs.max()) / W,
                  y0=float(ys.min()) / H, y1=float(ys.max()) / H,
                  px=int(ys.size), pxf=float(ys.size) / (H * W),
                  above020=float((ys < 0.20 * H).mean()),
                  above033=float((ys < 0.3333 * H).mean()),
                  below067=float((ys > 0.6667 * H).mean()))
    else:
        tb = None
    onface = 0.0
    if ys.size and fb:
        fm = np.zeros((H, W), np.uint8)
        for (x, y, w, h) in fb:
            fm[y:y + h, x:x + w] = 1
        onface = float(fm[ys, xs].mean())
    m = metaby.get(f, {})
    rows.append(dict(file=f, grp=m.get("grp"), views=m.get("views"), dur=m.get("dur"),
                     idx=m.get("idx"), title=m.get("title"), W=W, H=H,
                     seams=[dict(x=s[0], xf=s[0] / W, frac=s[1], mean=s[2]) for s in sm],
                     nseam=len(sm),
                     faces=[dict(x=b[0], y=b[1], w=b[2], h=b[3],
                                 areaf=b[2] * b[3] / float(W * H),
                                 hf=b[3] / float(H),
                                 cx=(b[0] + b[2] / 2) / W, cy=(b[1] + b[3] / 2) / H) for b in fb],
                     nface=len(fb),
                     maxface=max([b[2] * b[3] / float(W * H) for b in fb], default=0.0),
                     maxfaceh=max([b[3] / float(H) for b in fb], default=0.0),
                     nline=len(L), lines=L,
                     cap_max=max([l["cap_frac"] for l in L], default=0.0),
                     cap_med=float(np.median([l["cap_frac"] for l in L])) if L else 0.0,
                     nyellow=sum(l["yellow"] for l in L),
                     tbox=tb, text_on_face=onface,
                     red=red_blobs(bgr), colour=colour(bgr)))
    print(f, "seams", [round(s[0] / W, 3) for s in sm], "faces", len(fb),
          "lines", len(L), "cap", round(max([l["cap_frac"] for l in L], default=0), 3), flush=True)

json.dump(rows, io.open(os.path.join(OUT, "ct_measure.json"), "w", encoding="utf-8"), indent=1)
print("\nwrote", os.path.join(OUT, "ct_measure.json"), len(rows), "rows")
