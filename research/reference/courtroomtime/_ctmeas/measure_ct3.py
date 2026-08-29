# -*- coding: utf-8 -*-
"""Pass 3 - final. Verified detectors + debug overlays.
Pixels + thumbmeta.json only."""
import io, json, os, sys
import numpy as np, cv2

ROOT = r"C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime"
THUMBS = os.path.join(ROOT, "thumbs")
OUT = os.path.join(ROOT, "_ctmeas")
DBG = os.path.join(OUT, "dbg")
os.makedirs(DBG, exist_ok=True)
meta = {m["file"]: m for m in json.load(io.open(os.path.join(ROOT, "thumbmeta.json"), encoding="utf-8"))}


def masks(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].astype(int); S = hsv[:, :, 1].astype(int); V = hsv[:, :, 2].astype(int)
    return (dict(
        yellow=(H >= 18) & (H <= 36) & (S > 110) & (V > 140),
        red=(((H <= 8) | (H >= 172)) & (S > 120) & (V > 100)),
        white=(V > 200) & (S < 50),
        black=(V < 68)), H, S, V)


# ---------- panel boundary: content change across a 32px window ----------
def panels(bgr):
    small = cv2.resize(bgr, (320, 180), interpolation=cv2.INTER_AREA).astype(np.float32)
    Wsm = 320
    k = 8                       # 8 small px = 32 full px
    prof = np.zeros(Wsm)
    for x in range(k, Wsm - k):
        l = small[:, x - k:x].mean(axis=1)
        r = small[:, x:x + k].mean(axis=1)
        prof[x] = np.abs(l - r).mean()
    lo, hi = int(0.14 * Wsm), int(0.86 * Wsm)
    cands = []
    order = np.argsort(-prof)
    for x in order:
        if x < lo or x > hi: continue
        if prof[x] < 26.0: break
        if any(abs(x - c[0]) < 20 for c in cands): continue
        cands.append((int(x), float(prof[x])))
        if len(cands) >= 3: break
    cands.sort()
    return [dict(xf=c[0] / float(Wsm), score=c[1]) for c in cands], float(prof.max())


# ---------- bars: full-width horizontal plates of yellow / red ----------
def bars(bgr):
    m, H, S, V = masks(bgr)
    Himg, Wimg = V.shape
    out = {}
    for name in ("yellow", "red"):
        base = m[name]
        # a text plate = the plate colour OR the dark glyphs sitting on it.
        plate = base | (m["black"] & cv2.dilate(base.astype(np.uint8),
                                                np.ones((1, 61), np.uint8)).astype(bool))
        cov = plate.mean(axis=1)
        runs, cur = [], None
        for y, v in enumerate(cov):
            if v >= 0.72:
                cur = (y, y) if cur is None else (cur[0], y)
            else:
                if cur and cur[1] - cur[0] + 1 >= 22: runs.append(cur)
                cur = None
        if cur and cur[1] - cur[0] + 1 >= 22: runs.append(cur)
        out[name] = [dict(y0f=a / Himg, y1f=(b + 1) / Himg, hf=(b - a + 1) / Himg,
                          y0=int(a), y1=int(b)) for a, b in runs]
    out["bottom_yellow_hf"] = max([b["hf"] for b in out["yellow"] if b["y1f"] > 0.94], default=0.0)
    out["top_yellow_hf"] = max([b["hf"] for b in out["yellow"] if b["y0f"] < 0.06], default=0.0)
    out["any_red_plate"] = len(out["red"]) > 0
    # red plate need not be full width (JUDGE BOYD bar is ~45% wide) -> separate scan
    red = m["red"]
    cov = red.mean(axis=1)
    out["red_partial_rows"] = int((cov > 0.25).sum())
    out["red_partial_hf"] = float((cov > 0.25).mean())
    return out


def frame_border(bgr, t=9):
    """Coloured stroke around the picture. Left+right+top edges only, so a
    bottom-bleeding text bar is not miscounted as a frame."""
    m, H, S, V = masks(bgr)
    Himg, Wimg = V.shape
    ring = np.zeros((Himg, Wimg), bool)
    ring[:t, :] = True; ring[:, :t] = True; ring[:, -t:] = True     # top,left,right
    bot = np.zeros((Himg, Wimg), bool); bot[-t:, :] = True
    return dict(yellow_lrt=float(m["yellow"][ring].mean()),
                yellow_bottom=float(m["yellow"][bot].mean()),
                black_lrt=float(m["black"][ring].mean()))


# ---------- text ----------
def glyphs(bgr):
    m, Hc, S, V = masks(bgr)
    Himg, Wimg = V.shape
    Vf = V.astype(np.float32)
    out = []
    for name in ("white", "yellow", "red", "black"):
        cand = cv2.morphologyEx(m[name].astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))  # reconnect grunge type
        n, lab, st, ct = cv2.connectedComponentsWithStats(cand, 8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if h < 26 or h > 0.38 * Himg: continue
            if w < 8 or w > 0.40 * Wimg: continue
            if a < 380: continue
            ar = w / float(h)
            if ar < 0.14 or ar > 2.6: continue
            fill = a / float(w * h)
            if fill < 0.22 or fill > 0.93: continue
            pad = max(5, int(h * 0.15))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(Wimg, x + w + pad), min(Himg, y + h + pad)
            subm = (lab[y0:y1, x0:x1] == i)
            ringm = cv2.dilate(subm.astype(np.uint8),
                               np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)).astype(bool) & (~subm)
            rv = Vf[y0:y1, x0:x1][ringm]; bv = Vf[y0:y1, x0:x1][subm]
            if rv.size < 60: continue
            if abs(float(bv.mean()) - float(np.median(rv))) < 60: continue
            out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a), col=name))
    out.sort(key=lambda g: -g["a"])
    keep = []
    for g in out:
        ok = True
        for k in keep:
            ix = max(0, min(g["x"] + g["w"], k["x"] + k["w"]) - max(g["x"], k["x"]))
            iy = max(0, min(g["y"] + g["h"], k["y"] + k["h"]) - max(g["y"], k["y"]))
            if ix * iy > 0.5 * min(g["w"] * g["h"], k["w"] * k["h"]):
                ok = False; break
        if ok: keep.append(g)
    return keep


def textlines(gl, Himg, Wimg):
    """A text LINE must be >=4 glyphs of near-equal height, baseline-aligned,
    horizontally sequential with small gaps. That rejects hair / furniture blobs."""
    if not gl: return []
    gs = sorted(gl, key=lambda g: g["y"] + g["h"] / 2)
    lines, cur = [], [gs[0]]
    for g in gs[1:]:
        cy = g["y"] + g["h"] / 2
        ref = np.median([c["y"] + c["h"] / 2 for c in cur])
        refh = np.median([c["h"] for c in cur])
        if abs(cy - ref) <= 0.42 * max(refh, g["h"]):
            cur.append(g)
        else:
            lines.append(cur); cur = [g]
    lines.append(cur)
    res = []
    for L in lines:
        if len(L) < 4: continue
        L = sorted(L, key=lambda g: g["x"])
        hs = np.array([c["h"] for c in L], float)
        cap = float(np.median(hs))
        if hs.std() / cap > 0.22: continue                    # heights must match
        base = np.array([c["y"] + c["h"] for c in L], float)
        if base.std() / cap > 0.18: continue                  # baseline must align
        gaps = [L[i + 1]["x"] - (L[i]["x"] + L[i]["w"]) for i in range(len(L) - 1)]
        if len(gaps) and np.median(gaps) > 1.2 * cap: continue  # must be a run, not scatter
        if sum(1 for gp in gaps if gp < -0.5 * cap) > 0: continue  # no stacked overlap
        x0 = min(c["x"] for c in L); x1 = max(c["x"] + c["w"] for c in L)
        y0 = min(c["y"] for c in L); y1 = max(c["y"] + c["h"] for c in L)
        if (x1 - x0) < 2.2 * cap: continue
        cols = {}
        for c in L: cols[c["col"]] = cols.get(c["col"], 0) + 1
        res.append(dict(n=len(L), cap=cap, capf=cap / Himg,
                        x0=int(x0), x1=int(x1), y0=int(y0), y1=int(y1),
                        x0f=x0 / Wimg, x1f=x1 / Wimg, y0f=y0 / Himg, y1f=y1 / Himg,
                        cyf=(y0 + y1) / 2.0 / Himg, wf=(x1 - x0) / Wimg,
                        ink=int(sum(c["a"] for c in L)),
                        col=max(cols, key=cols.get), cols=cols))
    res.sort(key=lambda r: r["cyf"])
    return res


def blobs(bgr, mask, minarea=3000):
    mm = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, ct = cv2.connectedComponentsWithStats(mm, 8)
    Himg, Wimg = mm.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < minarea: continue
        out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), a=int(a),
                        af=a / float(Himg * Wimg), cxf=float(ct[i][0]) / Wimg,
                        cyf=float(ct[i][1]) / Himg, fill=a / float(w * h),
                        wf=w / float(Wimg), hf=h / float(Himg)))
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
    m, _, _, _ = masks(bgr)
    pn, pmax = panels(bgr)
    gl = glyphs(bgr)
    L = textlines(gl, Himg, Wimg)
    b = bars(bgr)
    fb = frame_border(bgr)
    tm = np.zeros((Himg, Wimg), np.uint8)
    for l in L:
        tm[l["y0"]:l["y1"] + 1, l["x0"]:l["x1"] + 1] = 1
    ys, xs = np.nonzero(tm)
    tb = None
    if ys.size:
        tb = dict(y0f=float(ys.min()) / Himg, y1f=float(ys.max()) / Himg,
                  x0f=float(xs.min()) / Wimg, x1f=float(xs.max()) / Wimg,
                  boxf=float(ys.size) / (Himg * Wimg), cyf=float(ys.mean()) / Himg,
                  above020=float((ys < 0.20 * Himg).mean()),
                  above033=float((ys < 0.3333 * Himg).mean()),
                  below060=float((ys > 0.60 * Himg).mean()),
                  below067=float((ys > 0.6667 * Himg).mean()))
    barrows = np.zeros(Himg, bool)
    for bb in b["yellow"] + b["red"]: barrows[bb["y0"]:bb["y1"] + 1] = True
    lrows = np.zeros(Himg, bool)
    for l in L: lrows[l["y0"]:l["y1"] + 1] = True
    def is_callout(bl):
        y0, y1 = bl["y"], bl["y"] + bl["h"]
        if barrows[y0:y1].mean() > 0.5: return False
        if lrows[y0:y1].mean() > 0.85 and bl["wf"] < 0.25: return False
        if bl["hf"] < 0.05 or bl["wf"] < 0.05: return False
        return True
    redb = [x for x in blobs(bgr, m["red"], 4000) if is_callout(x)]
    yelb = [x for x in blobs(bgr, m["yellow"], 4000) if is_callout(x)]
    mt = meta.get(f, {})
    r = dict(file=f, grp=mt.get("grp"), views=mt.get("views"), dur=mt.get("dur"),
             idx=mt.get("idx"), title=mt.get("title"),
             panels=pn, npanel=len(pn) + 1, panel_max=pmax,
             bars=b, border=fb, nline=len(L), lines=L, tbox=tb,
             capmax=max([l["capf"] for l in L], default=0.0),
             capmed=float(np.median([l["capf"] for l in L])) if L else 0.0,
             red_callouts=redb[:4], yellow_callouts=yelb[:4],
             colour=colour(bgr))
    rows.append(r)

    d = bgr.copy()
    for p in pn:
        x = int(p["xf"] * Wimg)
        cv2.line(d, (x, 0), (x, Himg), (255, 0, 255), 3)
    for l in L:
        cv2.rectangle(d, (l["x0"], l["y0"]), (l["x1"], l["y1"]), (0, 255, 0), 3)
        cv2.putText(d, "cap%.3f" % l["capf"], (l["x0"], max(20, l["y0"] - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    for bb in b["yellow"]:
        cv2.rectangle(d, (0, bb["y0"]), (Wimg - 1, bb["y1"]), (255, 255, 0), 2)
    for bb in b["red"]:
        cv2.rectangle(d, (0, bb["y0"]), (Wimg - 1, bb["y1"]), (0, 0, 255), 2)
    for bl in redb[:3]:
        cv2.rectangle(d, (bl["x"], bl["y"]), (bl["x"] + bl["w"], bl["y"] + bl["h"]), (0, 128, 255), 3)
    for bl in yelb[:3]:
        cv2.rectangle(d, (bl["x"], bl["y"]), (bl["x"] + bl["w"], bl["y"] + bl["h"]), (255, 200, 0), 3)
    cv2.line(d, (0, int(0.20 * Himg)), (Wimg, int(0.20 * Himg)), (255, 255, 255), 1)
    cv2.imencode(".jpg", d)[1].tofile(os.path.join(DBG, f))
    print("%-46s %s lines=%d capmax=%.3f capmed=%.3f cy=%.2f seams=%s botY=%.3f topY=%.3f frame=%.2f red=%d yel=%d"
          % (f[:46], mt.get("grp"), len(L), r["capmax"], r["capmed"],
             (tb["cyf"] if tb else -1), [round(p["xf"], 3) for p in pn],
             b["bottom_yellow_hf"], b["top_yellow_hf"], fb["yellow_lrt"],
             len(redb), len(yelb)), flush=True)

json.dump(rows, io.open(os.path.join(OUT, "ct_measure3.json"), "w", encoding="utf-8"), indent=1)
print("\nwrote ct_measure3.json", len(rows))
