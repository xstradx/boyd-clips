# Gaze / eyeline measurement over the reference corpora.
# Detector: YuNet (models/yunet2023.onnx) -> bbox + 5 landmarks
#   landmark order (opencv_zoo face_detection_yunet): 0=right eye,1=left eye,2=nose tip,
#   3=right mouth corner,4=left mouth corner. "right" = SUBJECT's right = image-LEFT when frontal.
# Yaw proxies are computed AFTER de-rolling (rotate so the eye line is horizontal).
import cv2, numpy as np, json, os, sys, math, glob

ROOT = "C:/Users/natha/Projects/boyd-clips"
MODEL = os.path.join(ROOT, "models/yunet2023.onnx")
PROF = cv2.data.haarcascades + "haarcascade_profileface.xml"
prof_cc = cv2.CascadeClassifier(PROF)


def detect_faces(bgr, score=0.55, nms=0.3):
    """Multi-scale YuNet: run at 1x and 2x so small faces are found too. Dedupe by IoU."""
    H, W = bgr.shape[:2]
    out = []
    for scale in (1.0, 2.0):
        img = bgr if scale == 1.0 else cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        h, w = img.shape[:2]
        d = cv2.FaceDetectorYN.create(MODEL, "", (w, h), score, nms, 5000)
        d.setInputSize((w, h))
        n, f = d.detect(img)
        if f is None:
            continue
        for r in f:
            r = np.array(r, dtype=float).copy()
            r[:14] /= scale
            out.append(r)
    keep = []
    for r in sorted(out, key=lambda a: -a[14]):
        x, y, w, h = r[:4]
        dup = False
        for k in keep:
            X, Y, Wd, Hd = k[:4]
            ix = max(0, min(x + w, X + Wd) - max(x, X))
            iy = max(0, min(y + h, Y + Hd) - max(y, Y))
            inter = ix * iy
            union = w * h + Wd * Hd - inter
            if union > 0 and inter / union > 0.35:
                dup = True
                break
        if not dup:
            keep.append(r)
    return keep


MODEL3D = np.array([
    (-31.5, 34.0, -55.0),   # subject right eye  (image-left when frontal)
    (31.5, 34.0, -55.0),    # subject left  eye
    (0.0, 0.0, 0.0),        # nose tip
    (-22.0, -42.0, -38.0),  # subject right mouth corner
    (22.0, -42.0, -38.0),   # subject left  mouth corner
], dtype=np.float64)


def pnp_yaw(pts2d, bw):
    """Weak-perspective PnP on the face crop: principal point = landmark centroid, f = 2*face width."""
    cx = float(np.mean(pts2d[:, 0]))
    cy = float(np.mean(pts2d[:, 1]))
    f = 2.0 * bw
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], dtype=np.float64)
    try:
        ok, rvec, tvec = cv2.solvePnP(MODEL3D, pts2d.astype(np.float64), K, np.zeros(4),
                                      flags=cv2.SOLVEPNP_ITERATIVE)
    except Exception:
        return None, None, None
    if not ok:
        return None, None, None
    R, _ = cv2.Rodrigues(rvec)
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy > 1e-6:
        pitch = math.degrees(math.atan2(R[2, 1], R[2, 2]))
        yaw = math.degrees(math.atan2(-R[2, 0], sy))
        roll = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    else:
        pitch = math.degrees(math.atan2(-R[1, 2], R[1, 1]))
        yaw = math.degrees(math.atan2(-R[2, 0], sy))
        roll = 0.0
    return yaw, pitch, roll


def face_metrics(r, H, W):
    x, y, w, h, sc = r[0], r[1], r[2], r[3], r[14]
    lm = r[4:14].reshape(5, 2).astype(float)   # re, le, nose, rm, lm  (image coords)
    re, le = lm[0], lm[1]
    eyemid = (re + le) / 2.0
    v = le - re
    roll_img = math.degrees(math.atan2(v[1], v[0]))
    th = -math.radians(roll_img)
    Rm = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    P = (lm - eyemid) @ Rm.T
    RE, LE, NO, RM, LM = P
    iod = float(np.linalg.norm(LE - RE))
    mouthmid = (RM + LM) / 2.0
    dv = float(abs(mouthmid[1]))
    nose_dev = float(NO[0] / dv) if dv > 1e-6 else float("nan")
    dR = abs(NO[0] - RE[0])
    dL = abs(NO[0] - LE[0])
    asym = float((dR - dL) / (dR + dL)) if (dR + dL) > 1e-6 else float("nan")
    yaw, pitch, rollp = pnp_yaw(lm, w)
    nose_v = float(NO[1] / dv) if dv > 1e-6 else float("nan")
    return dict(
        x=float(x), y=float(y), w=float(w), h=float(h), score=float(sc),
        cx=float((x + w / 2) / W), cy=float((y + h / 2) / H),
        hfrac=float(h / H), wfrac=float(w / W),
        lm=[[float(a), float(b)] for a, b in lm],
        iod_over_dv=float(iod / dv) if dv > 1e-6 else float("nan"),
        roll_img=roll_img, nose_dev=nose_dev, asym=asym, nose_v=nose_v,
        pnp_yaw=yaw, pnp_pitch=pitch, pnp_roll=rollp,
        eyemid_x=float(eyemid[0] / W), eyemid_y=float(eyemid[1] / H),
    )


def profile_dir(bgr, box):
    """Independent check: haarcascade_profileface fires on ONE orientation only."""
    x, y, w, h = [int(v) for v in box]
    pad = int(0.35 * w)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(bgr.shape[1], x + w + pad), min(bgr.shape[0], y + h + pad)
    crop = bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    s = 200.0 / max(1, g.shape[1])
    g = cv2.resize(g, None, fx=s, fy=s)
    a = len(prof_cc.detectMultiScale(g, 1.08, 3, minSize=(50, 50)))
    b = len(prof_cc.detectMultiScale(cv2.flip(g, 1), 1.08, 3, minSize=(50, 50)))
    return dict(orig=int(a), flipped=int(b))


def glyph_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(float), hsv[:, :, 2].astype(float)
    y = (Hc >= 18) & (Hc <= 36) & (S >= 110) & (V >= 150)
    w = (S <= 45) & (V >= 215)
    r = ((Hc <= 8) | (Hc >= 170)) & (S >= 110) & (V >= 110)
    return y.astype(np.uint8), w.astype(np.uint8), r.astype(np.uint8)


def glyphs(m, H, W):
    n, lab, st, ce = cv2.connectedComponentsWithStats(
        cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if 0.03 * H <= h <= 0.30 * H and 0.004 * W <= w <= 0.35 * W and a / (w * h) >= 0.15 and 0.08 <= w / h <= 4.0:
            out.append((int(x), int(y), int(w), int(h), int(a)))
    return out


def text_boxes(bgr):
    H, W = bgr.shape[:2]
    ym, wm, rm = glyph_mask(bgr)
    allg = []
    for nm, m in (("y", ym), ("w", wm), ("r", rm)):
        for t in glyphs(m, H, W):
            allg.append((nm,) + t)
    if not allg:
        return None
    items = sorted(allg, key=lambda t: t[2] + t[4] / 2)
    rows = []
    cur = [items[0]]
    for it in items[1:]:
        if (it[2] + it[4] / 2) - (cur[-1][2] + cur[-1][4] / 2) < 0.05 * H:
            cur.append(it)
        else:
            rows.append(cur)
            cur = [it]
    rows.append(cur)
    rows = [rw for rw in rows if len(rw) >= 4]
    if not rows:
        return None
    out_rows = []
    for rw in rows:
        xs = [t[1] for t in rw]
        ws = [t[3] for t in rw]
        ys = [t[2] for t in rw]
        hs = [t[4] for t in rw]
        x0 = min(xs)
        x1 = max(a + b for a, b in zip(xs, ws))
        y0 = min(ys)
        y1 = max(a + b for a, b in zip(ys, hs))
        out_rows.append(dict(n=len(rw), x0=x0, x1=x1, y0=y0, y1=y1,
                             cx=float(((x0 + x1) / 2) / W), cy=float(((y0 + y1) / 2) / H),
                             wfrac=float((x1 - x0) / W), capfrac=float(np.percentile(hs, 75) / H)))
    X0 = min(r["x0"] for r in out_rows)
    X1 = max(r["x1"] for r in out_rows)
    Y0 = min(r["y0"] for r in out_rows)
    Y1 = max(r["y1"] for r in out_rows)
    return dict(rows=out_rows, n_rows=len(out_rows),
                bbox=[int(X0), int(Y0), int(X1), int(Y1)],
                cx=float(((X0 + X1) / 2) / W), cy=float(((Y0 + Y1) / 2) / H),
                wfrac=float((X1 - X0) / W), hfrac=float((Y1 - Y0) / H))


def run(paths, outjson):
    res = []
    for p in paths:
        bgr = cv2.imread(p)
        if bgr is None:
            print("SKIP", p)
            continue
        H, W = bgr.shape[:2]
        faces = []
        for r in detect_faces(bgr):
            m = face_metrics(r, H, W)
            m["profile"] = profile_dir(bgr, r[:4])
            faces.append(m)
        faces.sort(key=lambda d: -d["hfrac"])
        res.append(dict(file=os.path.basename(p), path=p, W=W, H=H,
                        faces=faces, text=text_boxes(bgr)))
        print(os.path.basename(p), "faces=%d" % len(faces), flush=True)
    json.dump(res, open(outjson, "w", encoding="utf-8"), indent=1)
    print("WROTE", outjson, len(res))


if __name__ == "__main__":
    comp = sorted(glob.glob(ROOT + "/research/reference/competitor/thumbs/*.jpg"))
    ct = sorted(glob.glob(ROOT + "/research/reference/courtroomtime/thumbs/*.jpg"))
    ours = sorted(glob.glob("C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/*thumbnail*.jpg"))
    run(comp + ct + ours, ROOT + "/research/gaze/gz_raw.json")
