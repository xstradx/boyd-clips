# -*- coding: utf-8 -*-
"""Pass 2. Detectors tuned to what the 25 images actually contain:
torn-paper seams (ragged white strip), hard butt seams, bottom colour bars,
border frames, arrow colour, text band geometry. Pixels + thumbmeta.json only."""
import io, json, os
import numpy as np, cv2

ROOT = r"C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime"
THUMBS = os.path.join(ROOT, "thumbs")
OUT = os.path.join(ROOT, "_ctmeas")
meta = {m["file"]: m for m in json.load(io.open(os.path.join(ROOT, "thumbmeta.json"), encoding="utf-8"))}


def masks(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].astype(int); S = hsv[:, :, 1].astype(int); V = hsv[:, :, 2].astype(int)
    yellow = (H >= 18) & (H <= 36) & (S > 120) & (V > 150)
    red = (((H <= 8) | (H >= 172)) & (S > 130) & (V > 110))
    white = (V > 200) & (S < 45)
    black = (V < 55)
    return yellow, red, white, black


def seam_scan(bgr):
    """Return best hard-butt seam and best torn-paper (white ragged strip) seam."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    Himg, Wimg = g.shape
    d = np.abs(g[:, 1:] - g[:, :-1])
    frac = (d > 28).mean(axis=0)
    lo, hi = int(0.12 * Wimg), int(0.88 * Wimg)
    sub = frac[lo:hi]
    hx = int(np.argmax(sub)) + lo
    hard = dict(x=hx, xf=hx / Wimg, frac=float(frac[hx]))

    _, _, white, _ = masks(bgr)
    colwhite = white.mean(axis=0)                      # fraction of column that is near-white
    sw = cv2.GaussianBlur(colwhite.astype(np.float32).reshape(1, -1), (1, 1), 0).ravel()
    sub2 = sw[lo:hi]
    tx = int(np.argmax(sub2)) + lo
    # width of the white strip around tx
    w = 0
    for x in range(tx, min(Wimg, tx + 80)):
        if sw[x] < 0.35: break
        w += 1
    for x in range(tx - 1, max(0, tx - 80), -1):
        if sw[x] < 0.35: break
        w += 1
    torn = dict(x=tx, xf=tx / Wimg, colwhite=float(sw[tx]), width=w)
    return hard, torn


def bars(bgr):
    """Full-width solid colour bars: per-row coverage of yellow / red."""
    yellow, red, white, black = masks(bgr)
    Himg, Wimg = yellow.shape
    yrow = yellow.mean(axis=1)
    rrow = red.mean(axis=1)
    out = {}
    # a "bar" = >=25 consecutive rows with >=0.60 coverage
    def find(rowcov, name):
        runs, cur = [], None
        for y, v in enumerate(rowcov):
            if v >= 0.60:
                cur = (y, y) if cur is None else (cur[0], y)
            else:
                if cur and cur[1] - cur[0] + 1 >= 20: runs.append(cur)
                cur = None
        if cur and cur[1] - cur[0] + 1 >= 20: runs.append(cur)
        return [dict(y0=a, y1=b, y0f=a / Himg, y1f=(b + 1) / Himg,
                     hf=(b - a + 1) / Himg) for a, b in runs]
    out["yellow_bars"] = find(yrow, "y")
    out["red_bars"] = find(rrow, "r")
    # bottom-anchored yellow bar?
    out["bottom_yellow"] = any(b["y1f"] > 0.955 for b in out["yellow_bars"])
    out["bottom_yellow_hf"] = max([b["hf"] for b in out["yellow_bars"] if b["y1f"] > 0.955], default=0.0)
    out["top_yellow"] = any(b["y0f"] < 0.045 for b in out["yellow_bars"])
    return out


def border(bgr, t=10):
    """Coloured frame stroke around the whole image?"""
    yellow, red, white, black = masks(bgr)
    Himg, Wimg = yellow.shape
    ring = np.zeros_like(yellow)
    ring[:t, :] = True; ring[-t:, :] = True; ring[:, :t] = True; ring[:, -t:] = True
    return dict(yellow=float(yellow[ring].mean()), red=float(red[ring].mean()),
                black=float(black[ring].mean()))


def glyphs(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc = hsv[:, :, 0].astype(int); S = hsv[:, :, 1].astype(int); V = hsv[:, :, 2].astype(int)
    Himg, Wimg = V.shape
    # glyph bodies used by this channel: white, yellow, red, and black-on-yellow
    white = (V > 200) & (S < 55)
    yellow = (Hc >= 18) & (Hc <= 36) & (S > 120) & (V > 160)
    red = (((Hc <= 8) | (Hc >= 172)) & (S > 140) & (V > 110))
    black = (V < 60)
    out = []
    Vf = V.astype(np.float32)
    for name, m in (("white", white), ("yellow", yellow), ("red", red), ("black", black)):
        cand = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        n, lab, st, ct = cv2.connectedComponentsWithStats(cand, 8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if h < 22 or h > 0.42 * Himg: continue
            if w < 6 or w > 0.55 * Wimg: continue
            if a < 250: continue
            ar = w / float(h)
            if ar < 0.12 or ar > 3.2: continue
            fill = a / float(w * h)
            if fill < 0.18 or fill > 0.95: continue
            pad = max(4, int(h * 0.16))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(Wimg, x + w + pad), min(Himg, y + h + pad)
            subm = (lab[y0:y1, x0:x1] == i)
            ringm = cv2.dilate(subm.astype(np.uint8), np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)).astype(bool) & (~subm)
            rv = Vf[y0:y1, x0:x1][ringm]
            bv = Vf[y0:y1, x0:x1][subm]
            if rv.size < 40: continue
            contrast = abs(float(bv.mean()) - float(np.median(rv)))
            if contrast < 55: continue
            out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a), col=name))
    # de-dup overlapping boxes from different colour masks
    out.sort(key=lambda g: -g["a"])
    keep = []
    for g in out:
        ok = True
        for k in keep:
            ix = max(0, min(g["x"] + g["w"], k["x"] + k["w"]) - max(g["x"], k["x"]))
            iy = max(0, min(g["y"] + g["h"], k["y"] + k["h"]) - max(g["y"], k["y"]))
            if ix * iy > 0.55 * min(g["w"] * g["h"], k["w"] * k["h"]):
                ok = False; break
        if ok: keep.append(g)
    return keep


def textlines(gl, Himg, Wimg):
    if not gl: return []
    gs = sorted(gl, key=lambda g: g["y"] + g["h"] / 2)
    lines, cur = [], [gs[0]]
    for g in gs[1:]:
        cy = g["y"] + g["h"] / 2
        ref = np.median([c["y"] + c["h"] / 2 for c in cur])
        refh = np.median([c["h"] for c in cur])
        if abs(cy - ref) <= 0.55 * max(refh, g["h"]):
            cur.append(g)
        else:
            lines.append(cur); cur = [g]
    lines.append(cur)
    res = []
    for L in lines:
        if len(L) < 3: continue                       # need >=3 glyphs to call it a line
        hs = [c["h"] for c in L]
        cap = float(np.median(hs))
        x0 = min(c["x"] for c in L); x1 = max(c["x"] + c["w"] for c in L)
        y0 = min(c["y"] for c in L); y1 = max(c["y"] + c["h"] for c in L)
        cols = {}
        for c in L: cols[c["col"]] = cols.get(c["col"], 0) + 1
        res.append(dict(n=len(L), cap=cap, capf=cap / Himg,
                        x0f=x0 / Wimg, x1f=x1 / Wimg, y0f=y0 / Himg, y1f=y1 / Himg,
                        cyf=(y0 + y1) / 2.0 / Himg, wf=(x1 - x0) / Wimg, cols=cols))
    res.sort(key=lambda r: r["cyf"])
    return res


def blobs(bgr, mask, minarea=2500):
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, ct = cv2.connectedComponentsWithStats(m, 8)
    Himg, Wimg = m.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < minarea: continue
        out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a),
                        af=a / float(Himg * Wimg), cxf=float(ct[i][0]) / Wimg,
                        cyf=float(ct[i][1]) / Himg, fill=a / float(w * h)))
    out.sort(key=lambda d: -d["a"])
    return out


def colour(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1].astype(np.float32) / 255.0
    V = hsv[:, :, 2].astype(np.float32) / 255.0
    mx = bgr.max(axis=2)
    lum = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return dict(sat=float(S.mean()), val=float(V.mean()),
                clip250=float((mx >= 250).mean()), clip240=float((mx >= 240).mean()),
                lum=float(lum.mean()), lum_sd=float(lum.std()),
                dark40=float((lum < 40).mean()))


rows = []
for f in sorted(os.listdir(THUMBS)):
    if not f.lower().endswith(".jpg"): continue
    bgr = cv2.imdecode(np.fromfile(os.path.join(THUMBS, f), np.uint8), cv2.IMREAD_COLOR)
    Himg, Wimg = bgr.shape[:2]
    yellow, red, white, black = masks(bgr)
    hard, torn = seam_scan(bgr)
    gl = glyphs(bgr)
    L = textlines(gl, Himg, Wimg)
    b = bars(bgr)
    # text ink mask from kept glyph boxes
    tm = np.zeros((Himg, Wimg), np.uint8)
    for g in gl: tm[g["y"]:g["y"] + g["h"], g["x"]:g["x"] + g["w"]] = 1
    ys, xs = np.nonzero(tm)
    tb = None
    if ys.size:
        tb = dict(y0f=float(ys.min()) / Himg, y1f=float(ys.max()) / Himg,
                  x0f=float(xs.min()) / Wimg, x1f=float(xs.max()) / Wimg,
                  boxf=float(ys.size) / (Himg * Wimg),
                  cyf=float(ys.mean()) / Himg,
                  above020=float((ys < 0.20 * Himg).mean()),
                  above033=float((ys < 0.3333 * Himg).mean()),
                  below060=float((ys > 0.60 * Himg).mean()),
                  below067=float((ys > 0.6667 * Himg).mean()))
    # arrows / stamps: red or yellow blobs NOT inside a text line band and not a bar
    barrows = np.zeros(Himg, bool)
    for bb in b["yellow_bars"] + b["red_bars"]: barrows[bb["y0"]:bb["y1"] + 1] = True
    txtrows = np.zeros(Himg, bool)
    for l in L: txtrows[int(l["y0f"] * Himg):int(l["y1f"] * Himg) + 1] = True
    def outside(bl):
        y0, y1 = bl["y"], bl["y"] + bl["h"]
        band = barrows[y0:y1]
        return (band.mean() < 0.5)
    redb = [x for x in blobs(bgr, red, 3000) if outside(x) and x["fill"] < 0.72]
    yelb = [x for x in blobs(bgr, yellow, 3000) if outside(x) and x["fill"] < 0.72]
    m = meta.get(f, {})
    rows.append(dict(file=f, grp=m.get("grp"), views=m.get("views"), dur=m.get("dur"),
                     idx=m.get("idx"), title=m.get("title"),
                     hard=hard, torn=torn, bars=b, border=border(bgr),
                     nline=len(L), lines=L, tbox=tb,
                     capmax=max([l["capf"] for l in L], default=0.0),
                     capmed=float(np.median([l["capf"] for l in L])) if L else 0.0,
                     red_blobs=redb[:4], yellow_blobs=yelb[:4],
                     colour=colour(bgr)))
    print("%-46s %-3s lines=%d capmax=%.3f cy=%.2f torn(x=%.2f w=%d cw=%.2f) hard(x=%.2f f=%.2f) botY=%s bord_y=%.2f"
          % (f[:46], m.get("grp"), len(L), rows[-1]["capmax"],
             (tb["cyf"] if tb else -1), torn["xf"], torn["width"], torn["colwhite"],
             hard["xf"], hard["frac"], b["bottom_yellow"], rows[-1]["border"]["yellow"]), flush=True)

json.dump(rows, io.open(os.path.join(OUT, "ct_measure2.json"), "w", encoding="utf-8"), indent=1)
print("\nwrote ct_measure2.json", len(rows))
