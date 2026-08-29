# Text-box detection with a BLACK-STROKE RING test.
# Every thumbnail in both corpora (and ours) uses heavy black-stroked display type.
# A candidate glyph is kept only if the 5px ring just outside it is much darker
# than the glyph itself -> kills bright ceilings, walls, shirts, paper.
import cv2, numpy as np, json, os, glob

ROOT = "C:/Users/natha/Projects/boyd-clips"


def glyph_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(float), hsv[:, :, 2].astype(float)
    y = (Hc >= 18) & (Hc <= 36) & (S >= 110) & (V >= 150)
    w = (S <= 45) & (V >= 215)
    r = ((Hc <= 8) | (Hc >= 170)) & (S >= 110) & (V >= 110)
    g = (Hc >= 45) & (Hc <= 85) & (S >= 90) & (V >= 130)
    c = (Hc >= 86) & (Hc <= 100) & (S >= 90) & (V >= 150)
    m = (Hc >= 140) & (Hc <= 165) & (S >= 90) & (V >= 130)
    return dict(y=y, w=w, r=r, g=g, c=c, m=m)


def stroked_glyphs(bgr, mask, H, W, ring=5, dark_gap=55):
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, st, ce = cv2.connectedComponentsWithStats(m, 8)
    V = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2].astype(float)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (0.030 * H <= h <= 0.32 * H):  continue
        if not (0.004 * W <= w <= 0.40 * W):  continue
        if a / float(w * h) < 0.15:           continue
        if not (0.06 <= w / float(h) <= 4.5): continue
        x0, y0 = max(0, x - ring), max(0, y - ring)
        x1, y1 = min(W, x + w + ring), min(H, y + h + ring)
        sub = (lab[y0:y1, x0:x1] == i)
        if sub.sum() < 20: continue
        dil = cv2.dilate(sub.astype(np.uint8), np.ones((2 * ring + 1, 2 * ring + 1), np.uint8))
        rng = (dil > 0) & (~sub)
        if rng.sum() < 20: continue
        vin = float(V[y0:y1, x0:x1][sub].mean())
        vrg = float(np.percentile(V[y0:y1, x0:x1][rng], 60))
        if vin - vrg < dark_gap: continue          # <- the black-stroke test
        out.append((int(x), int(y), int(w), int(h), int(a), vin - vrg))
    return out


def text_boxes(path):
    bgr = cv2.imread(path)
    H, W = bgr.shape[:2]
    masks = glyph_mask(bgr)
    allg = []
    for nm, mk in masks.items():
        for t in stroked_glyphs(bgr, mk, H, W):
            allg.append((nm,) + t)
    if len(allg) < 4:
        return None
    items = sorted(allg, key=lambda t: t[2] + t[4] / 2.0)
    rows, cur = [], [items[0]]
    for it in items[1:]:
        if (it[2] + it[4] / 2.0) - (cur[-1][2] + cur[-1][4] / 2.0) < 0.055 * H:
            cur.append(it)
        else:
            rows.append(cur); cur = [it]
    rows.append(cur)
    rows = [rw for rw in rows if len(rw) >= 4]
    if not rows:
        return None
    orows = []
    for rw in rows:
        xs = [t[1] for t in rw]; ws = [t[3] for t in rw]
        ys = [t[2] for t in rw]; hs = [t[4] for t in rw]
        x0 = min(xs); x1 = max(a + b for a, b in zip(xs, ws))
        y0 = min(ys); y1 = max(a + b for a, b in zip(ys, hs))
        orows.append(dict(n=len(rw), x0=int(x0), x1=int(x1), y0=int(y0), y1=int(y1),
                          cx=float(((x0 + x1) / 2.0) / W), cy=float(((y0 + y1) / 2.0) / H),
                          wfrac=float((x1 - x0) / W), capfrac=float(np.percentile(hs, 75) / H),
                          cols=sorted({t[0] for t in rw})))
    X0 = min(r["x0"] for r in orows); X1 = max(r["x1"] for r in orows)
    Y0 = min(r["y0"] for r in orows); Y1 = max(r["y1"] for r in orows)
    return dict(rows=orows, n_rows=len(orows), bbox=[int(X0), int(Y0), int(X1), int(Y1)],
                cx=float(((X0 + X1) / 2.0) / W), cy=float(((Y0 + Y1) / 2.0) / H),
                wfrac=float((X1 - X0) / W), hfrac=float((Y1 - Y0) / H),
                left_edge=float(X0 / W), right_edge=float(X1 / W),
                top_edge=float(Y0 / H), bot_edge=float(Y1 / H))


if __name__ == "__main__":
    raw = json.load(open(ROOT + "/research/gaze/gz_raw.json", encoding="utf-8"))
    for rec in raw:
        rec["text"] = text_boxes(rec["path"])
        t = rec["text"]
        print("%-52s rows=%s bbox=%s" % (rec["file"][:52],
              t["n_rows"] if t else "-", t["bbox"] if t else "-"), flush=True)
    json.dump(raw, open(ROOT + "/research/gaze/gz_raw2.json", "w", encoding="utf-8"), indent=1)
    print("WROTE gz_raw2.json")
