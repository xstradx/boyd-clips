# -*- coding: utf-8 -*-
"""Layout geometry of reference thumbnails, measured from pixels."""
import os, glob, json, math, sys
import numpy as np, cv2

ROOT = 'C:/Users/natha/Projects/boyd-clips/research/reference'
GEO = ROOT + '/_geom'
MODEL = 'C:/Users/natha/Projects/boyd-clips/models/yunet2023.onnx'  # YuNet 2023mar, opencv_zoo, Apache-2.0


# ---------- FACES ----------
def faces(img, conf=0.80):
    H, W = img.shape[:2]
    out = []
    for sc in (1.0, 1.5, 2.0, 3.0):
        w, h = int(W * sc), int(H * sc)
        im = cv2.resize(img, (w, h), interpolation=cv2.INTER_CUBIC) if sc != 1.0 else img
        d = cv2.FaceDetectorYN.create(MODEL, '', (w, h), conf, 0.3, 5000)
        _, f = d.detect(im)
        if f is None:
            continue
        for r in f:
            x, y, bw, bh = [float(v) / sc for v in r[:4]]
            lm = [[float(r[4 + 2 * i]) / sc, float(r[5 + 2 * i]) / sc] for i in range(5)]
            (ex1, ey1), (ex2, ey2), (nx, ny), (m1x, m1y), (m2x, m2y) = lm
            if abs(ex2 - ex1) < 1:
                continue
            ang = abs(math.degrees(math.atan2(ey2 - ey1, ex2 - ex1)))
            if ang > 40:
                continue
            if (m1y + m2y) / 2 <= (ey1 + ey2) / 2:
                continue
            out.append(dict(x=x, y=y, w=bw, h=bh, conf=float(r[-1]), lm=lm))
    out.sort(key=lambda r: -(r['w'] * r['h']))
    keep = []
    for r in out:
        ok = True
        for k in keep:
            ix = max(0, min(r['x'] + r['w'], k['x'] + k['w']) - max(r['x'], k['x']))
            iy = max(0, min(r['y'] + r['h'], k['y'] + k['h']) - max(r['y'], k['y']))
            if ix * iy / (min(r['w'] * r['h'], k['w'] * k['h']) + 1e-9) > 0.45:
                ok = False
                break
        if ok:
            keep.append(r)
    return keep


# ---------- TEXT ----------
_ocr = None


def ocr_lines(path):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    res, _ = _ocr(path)
    if not res:
        return []
    return [dict(poly=np.array(it[0], float).tolist(), txt=it[1], conf=float(it[2])) for it in res]


def fillmask(bgr):
    """bright glyph fill: white / yellow / red"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hh = hsv[:, :, 0].astype(int)
    S = hsv[:, :, 1].astype(int)
    V = hsv[:, :, 2].astype(int)
    white = (V > 185) & (S < 70)
    yellow = (Hh >= 18) & (Hh <= 38) & (S > 110) & (V > 150)
    red = ((Hh <= 9) | (Hh >= 171)) & (S > 110) & (V > 110)
    return white, yellow, red


def refine_text(img, lines):
    H, W = img.shape[:2]
    white, yellow, red = fillmask(img)
    any_fill = white | yellow | red
    out = []
    for L in lines:
        p = np.array(L['poly'])
        x0, x1 = p[:, 0].min(), p[:, 0].max()
        y0, y1 = p[:, 1].min(), p[:, 1].max()
        pad = 0.18 * (y1 - y0)
        X0, X1 = int(max(0, x0 - pad)), int(min(W, x1 + pad))
        Y0, Y1 = int(max(0, y0 - pad)), int(min(H, y1 + pad))
        sub = any_fill[Y0:Y1, X0:X1].astype(np.uint8)
        if sub.sum() < 30:
            continue
        n, lab, st, cen = cv2.connectedComponentsWithStats(sub, 8)
        comps = []
        for i in range(1, n):
            a = st[i, cv2.CC_STAT_AREA]
            hh = st[i, cv2.CC_STAT_HEIGHT]
            ww = st[i, cv2.CC_STAT_WIDTH]
            if a < 40:
                continue
            if hh < 0.25 * (y1 - y0):
                continue
            comps.append((st[i, cv2.CC_STAT_LEFT], st[i, cv2.CC_STAT_TOP], ww, hh, a, i))
        if not comps:
            continue
        gx0 = min(c[0] for c in comps) + X0
        gx1 = max(c[0] + c[2] for c in comps) + X0
        gy0 = min(c[1] for c in comps) + Y0
        gy1 = max(c[1] + c[3] for c in comps) + Y0
        hs = sorted(c[3] for c in comps)
        cap = float(np.median([h for h in hs if h >= 0.80 * hs[-1]]))
        runs = []
        for c in sorted(comps, key=lambda c: c[0]):
            m = (lab[c[1]:c[1] + c[3], c[0]:c[0] + c[2]] == c[5])
            wy = white[Y0 + c[1]:Y0 + c[1] + c[3], X0 + c[0]:X0 + c[0] + c[2]][m].sum()
            yy = yellow[Y0 + c[1]:Y0 + c[1] + c[3], X0 + c[0]:X0 + c[0] + c[2]][m].sum()
            rr = red[Y0 + c[1]:Y0 + c[1] + c[3], X0 + c[0]:X0 + c[0] + c[2]][m].sum()
            col = ['white', 'yellow', 'red'][int(np.argmax([wy, yy, rr]))]
            if runs and runs[-1][0] == col:
                runs[-1][2] = c[0] + c[2] + X0
            else:
                runs.append([col, c[0] + X0, c[0] + c[2] + X0])
        out.append(dict(txt=L['txt'], conf=L['conf'], x0=float(gx0), x1=float(gx1),
                        y0=float(gy0), y1=float(gy1), cap=cap,
                        runs=[[r[0], float(r[1]), float(r[2])] for r in runs], ncomp=len(comps)))
    out.sort(key=lambda d: d['y0'])
    return out


# ---------- ACCENT SHAPES ----------
def graphic_masks(bgr):
    """flat, high-chroma GRAPHIC fills only - excludes wood/skin (textured, mid-sat)"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hh = hsv[:, :, 0].astype(int)
    S = hsv[:, :, 1].astype(int)
    V = hsv[:, :, 2].astype(int)
    red = (((Hh <= 8) | (Hh >= 172)) & (S > 165) & (V > 130))
    yellow = ((Hh >= 20) & (Hh <= 36) & (S > 150) & (V > 175))
    return dict(red=red, yellow=yellow)


def head_tail(comp):
    """arrow head/tail from the distance transform along the principal axis"""
    ys, xs = np.nonzero(comp)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    mu = pts.mean(0)
    u, s, vt = np.linalg.svd(pts - mu, full_matrices=False)
    ax = vt[0]
    t = (pts - mu) @ ax
    dt = cv2.distanceTransform(comp.astype(np.uint8), cv2.DIST_L2, 5)[ys, xs]
    lo, hi = t.min(), t.max()
    band = 0.25 * (hi - lo)
    dneg = dt[t < lo + band].mean() if (t < lo + band).any() else 0
    dpos = dt[t > hi - band].mean() if (t > hi - band).any() else 0
    sign = 1.0 if dpos > dneg else -1.0
    sel = (t * sign) > (max(abs(lo), abs(hi)) * 0 + (hi if sign > 0 else -lo) - band)
    cand = pts[(t * sign) >= (t * sign).max() - 2]
    tip = cand.mean(0) if len(cand) else pts[int((t * sign).argmax())]
    return ax * sign, tip, float(hi - lo), float(dt.max())


def accents(img, textmask):
    H, W = img.shape[:2]
    res = []
    for name, m in graphic_masks(img).items():
        mm = cv2.morphologyEx((m.astype(np.uint8)) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab, st, cen = cv2.connectedComponentsWithStats((mm > 0).astype(np.uint8), 8)
        for i in range(1, n):
            a = int(st[i, cv2.CC_STAT_AREA])
            if a < 900:
                continue
            x, y = int(st[i, cv2.CC_STAT_LEFT]), int(st[i, cv2.CC_STAT_TOP])
            w, h = int(st[i, cv2.CC_STAT_WIDTH]), int(st[i, cv2.CC_STAT_HEIGHT])
            comp = (lab == i)
            # graphic-uniformity: flat fill, not textured scene content
            px = img[comp].astype(float)
            if px[:, 0].std() + px[:, 1].std() + px[:, 2].std() > 90:
                continue
            fill = a / float(w * h)
            ov = float((comp & textmask).sum()) / a
            cnt, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            c = max(cnt, key=cv2.contourArea)
            sol = float(cv2.contourArea(c) / (cv2.contourArea(cv2.convexHull(c)) + 1e-9))
            if fill > 0.85 and w > 3 * h and a > 12000:
                kind = 'bar'
            elif ov > 0.30:
                continue
            else:
                kind = 'shape'
            d, tip, length, thick = head_tail(comp)
            M = cv2.moments(c)
            cx = M['m10'] / (M['m00'] + 1e-9)
            cy = M['m01'] / (M['m00'] + 1e-9)
            # arrow-likeness: elongated, non-convex, one thick end one thin end
            arrowish = (kind == 'shape' and sol < 0.90 and length > 2.2 * thick and a > 1500)
            res.append(dict(colour=name, kind=('arrow' if arrowish else kind), x=x, y=y, w=w, h=h,
                            area=a, solidity=sol, fill=float(fill), cx=float(cx), cy=float(cy),
                            tip=[float(tip[0]), float(tip[1])],
                            ang=float(math.degrees(math.atan2(d[1], d[0]))),
                            length=length, thick=thick, textov=ov))
    res.sort(key=lambda r: -r['area'])
    return res


# ---------- EMPTY SPACE ----------
def max_rect(free):
    H, W = free.shape
    hgt = np.zeros(W, int)
    best = (0, 0, 0, 0, 0)
    for r in range(H):
        hgt = np.where(free[r], hgt + 1, 0)
        st = []
        ext = np.append(hgt, 0)
        for i in range(W + 1):
            start = i
            while st and st[-1][1] >= ext[i]:
                s, hh = st.pop()
                area = hh * (i - s)
                if area > best[0]:
                    best = (int(area), int(s), int(r - hh + 1), int(i - s), int(hh))
                start = s
            st.append((start, ext[i]))
    return best


def occupancy(shape, faces_, texts, accs, mat=None):
    H, W = shape
    occ = np.zeros((H, W), bool)
    for f in faces_:
        x0, y0 = max(0, int(f['x'])), max(0, int(f['y']))
        x1, y1 = min(W, int(f['x'] + f['w'])), min(H, int(f['y'] + f['h']))
        occ[y0:y1, x0:x1] = True
    for t in texts:
        occ[max(0, int(t['y0'])):min(H, int(t['y1'])), max(0, int(t['x0'])):min(W, int(t['x1']))] = True
    for a in accs:
        occ[a['y']:a['y'] + a['h'], a['x']:a['x'] + a['w']] = True
    if mat is not None:
        occ |= mat
    return occ


def run():
    fs = sorted(glob.glob(ROOT + '/competitor/thumbs/*.jpg')) + sorted(glob.glob(ROOT + '/courtroomtime/thumbs/*.jpg'))
    all_ = {}
    for f in fs:
        base = os.path.basename(f)
        img = cv2.imread(f)
        H, W = img.shape[:2]
        F = faces(img)
        L = ocr_lines(f)
        T = refine_text(img, L)
        tm = np.zeros((H, W), bool)
        for t in T:
            tm[max(0, int(t['y0']) - 4):int(t['y1']) + 4, max(0, int(t['x0']) - 4):int(t['x1']) + 4] = True
        A = accents(img, tm)
        mpath = GEO + '/mattes/' + base[:-4] + '.png'
        mat = None
        if os.path.exists(mpath):
            mk = cv2.imread(mpath, 0)
            if mk is not None and mk.shape == (H, W):
                mat = mk > 128
        er = max_rect(~occupancy((H, W), F, T, A, mat))
        er2 = max_rect(~occupancy((H, W), F, T, A, None))
        all_[base] = dict(W=W, H=H, faces=F, text=T, accents=A,
                          empty_all=dict(area=er[0], x=er[1], y=er[2], w=er[3], h=er[4]),
                          empty_elem=dict(area=er2[0], x=er2[1], y=er2[2], w=er2[3], h=er2[4]),
                          has_matte=mat is not None)
        print(base, 'faces', len(F), 'text', len(T), 'acc', len(A), flush=True)
    json.dump(all_, open(GEO + '/geom.json', 'w'), indent=1)
    print('WROTE', GEO + '/geom.json')


if __name__ == '__main__':
    run()
