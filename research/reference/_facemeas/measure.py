import cv2, numpy as np, json, os, glob, math
from skimage.metrics import structural_similarity as ssim

ROOT = "C:/Users/natha/Projects/boyd-clips/research/reference"
OUT = ROOT + "/_facemeas"
MODEL = "C:/Users/natha/Projects/boyd-clips/models/yunet2023.onnx"
CT_META = {m["file"]: m for m in json.load(open(ROOT + "/courtroomtime/thumbmeta.json", encoding="utf-8"))}


def files():
    out = []
    for f in sorted(glob.glob(ROOT + "/competitor/thumbs/*.jpg")):
        b = os.path.basename(f)
        out.append(dict(grp="ATC", file=b, path=f, views=int(b.split("_")[0]), dur=None, title=None))
    for f in sorted(glob.glob(ROOT + "/courtroomtime/thumbs/*.jpg")):
        b = os.path.basename(f)
        m = CT_META.get(b, {})
        out.append(dict(grp="CT_" + b[:3], file=b, path=f, views=int(b.split("_")[1]),
                        dur=m.get("dur"), title=m.get("title")))
    return out


def _ov(a, b):
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0, 0.0
    inter = (x2 - x1) * (y2 - y1)
    return inter / float(aw * ah + bw * bh - inter), inter / float(min(aw * ah, bw * bh))


def detect(img, conf=0.55):
    H, W = img.shape[:2]
    allf = []
    for s in (0.5, 1.0, 1.6, 2.4):
        w, h = int(W * s), int(H * s)
        if w < 64 or w > 4200:
            continue
        im = cv2.resize(img, (w, h), interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        det = cv2.FaceDetectorYN.create(MODEL, "", (w, h), conf, 0.3, 5000)
        det.setInputSize((w, h))
        n, fs = det.detect(im)
        if fs is None:
            continue
        for f in fs:
            f = f.astype(float).copy()
            f[:14] /= s
            allf.append(f)
    allf.sort(key=lambda f: -f[14])
    kept = []
    for f in allf:
        dup = False
        for k in kept:
            i, c = _ov(f, k)
            if i > 0.20 or c > 0.55:
                dup = True
                break
        if not dup:
            kept.append(f)
    return kept


def pose(f):
    re = np.array(f[4:6]); le = np.array(f[6:8]); no = np.array(f[8:10])
    rm = np.array(f[10:12]); lm = np.array(f[12:14])
    eyed = float(np.linalg.norm(le - re))
    if eyed < 2:
        return None
    emid = (le + re) / 2.0
    mmid = (lm + rm) / 2.0
    ev = (le - re) / eyed
    perp = np.array([-ev[1], ev[0]])
    roll = math.degrees(math.atan2(le[1] - re[1], le[0] - re[0]))
    yaw = float(np.dot(no - emid, ev)) / eyed
    d_e = float(np.dot(no - emid, perp))
    d_m = float(np.dot(mmid - emid, perp))
    pitch = d_e / d_m if abs(d_m) > 1e-6 else float("nan")
    return dict(eyed=eyed, roll=roll, yaw=yaw, pitch=pitch,
                mouthw_over_eyed=float(np.linalg.norm(lm - rm)) / eyed,
                emid=[float(emid[0]), float(emid[1])],
                mmid=[float(mmid[0]), float(mmid[1])],
                ev=[float(ev[0]), float(ev[1])],
                perp=[float(perp[0]), float(perp[1])])


def expression(img, f, p):
    eyed = p["eyed"]
    mmid = np.array(p["mmid"]); emid = np.array(p["emid"])
    ev = np.array(p["ev"]); perp = np.array(p["perp"])

    def sample(center, hw, hh, N=48):
        u = np.linspace(-hw, hw, N)
        v = np.linspace(-hh, hh, N)
        UU, VV = np.meshgrid(u, v)
        X = center[0] + UU * ev[0] + VV * perp[0]
        Y = center[1] + UU * ev[1] + VV * perp[1]
        return cv2.remap(img, X.astype(np.float32), Y.astype(np.float32),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    cheekL = sample(emid + ev * (0.45 * eyed) + perp * (0.55 * eyed), 0.16 * eyed, 0.16 * eyed, 20)
    cheekR = sample(emid - ev * (0.45 * eyed) + perp * (0.55 * eyed), 0.16 * eyed, 0.16 * eyed, 20)
    skin = np.concatenate([cheekL.reshape(-1, 3), cheekR.reshape(-1, 3)])
    skin_hsv = cv2.cvtColor(skin.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV)
    skinV = float(np.median(skin_hsv[:, 0, 2]))
    skinS = float(np.median(skin_hsv[:, 0, 1]))

    mouth = sample(mmid, 0.62 * eyed, 0.62 * eyed)
    hsv = cv2.cvtColor(mouth.astype(np.uint8), cv2.COLOR_BGR2HSV)
    V = hsv[:, :, 2].astype(float)
    S = hsv[:, :, 1].astype(float)
    dark = V < max(28.0, 0.40 * skinV)
    bright_desat = (V > max(skinV * 1.05, 130.0)) & (S < max(45.0, 0.55 * skinS))

    rowdark = dark.mean(axis=1)
    rows = np.where(rowdark > 0.18)[0]
    gape_h = (rows[-1] - rows[0] + 1) / dark.shape[0] * 1.24 if len(rows) else 0.0
    coldark = dark.mean(axis=0)
    cols = np.where(coldark > 0.18)[0]
    gape_w = (cols[-1] - cols[0] + 1) / dark.shape[1] * 1.24 if len(cols) else 0.0

    brow = sample(emid - perp * (0.42 * eyed), 0.95 * eyed, 0.26 * eyed)
    bg = cv2.cvtColor(brow.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(float)
    brow_h = float(np.abs(np.diff(bg, axis=0)).mean())

    return dict(mouth_dark_frac=float(dark.mean()), teeth_frac=float(bright_desat.mean()),
                gape_h=float(gape_h), gape_w=float(gape_w), brow_energy=brow_h,
                skinV=skinV, skinS=skinS)


def globals_(img):
    H, W = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    t, _ = cv2.threshold(cv2.GaussianBlur(g, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    e_otsu = cv2.Canny(g, int(0.5 * t), int(t)).mean() / 255.0
    e_fixed = cv2.Canny(g, 80, 180).mean() / 255.0
    sob = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3),
                        cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    q = (img // 8).astype(np.int32)
    codes = q[:, :, 0] * 4096 + q[:, :, 1] * 64 + q[:, :, 2]
    uniq = int(len(np.unique(codes)))
    hist = np.bincount(codes.ravel(), minlength=262144).astype(float)
    hist /= hist.sum()
    nz = hist[hist > 0]
    col_entropy = float(-(nz * np.log2(nz)).sum())
    srt = np.sort(nz)[::-1]
    cum = np.cumsum(srt)
    n90 = int(np.searchsorted(cum, 0.90) + 1)
    small = cv2.resize(img, (512, 288), interpolation=cv2.INTER_AREA)
    png = len(cv2.imencode(".png", small)[1])
    mser = cv2.MSER_create()
    mser.setMinArea(int(0.0004 * 640 * 360))
    mser.setMaxArea(int(0.25 * 640 * 360))
    regs, _ = mser.detectRegions(cv2.resize(g, (640, 360), interpolation=cv2.INTER_AREA))
    fm = np.fft.fftshift(np.abs(np.fft.fft2(
        cv2.resize(g, (512, 512), interpolation=cv2.INTER_AREA).astype(float))))
    yy, xx = np.mgrid[0:512, 0:512]
    r = np.hypot(yy - 256, xx - 256)
    hi = float(fm[r > 64].sum() / fm.sum())
    # log-spectrum residual saliency, implemented inline (cv2.saliency is an empty
    # stub in opencv-python 4.14.0 on this machine). Operations, in order:
    # FFT -> log amplitude -> subtract 3x3 box-mean of log amplitude -> inverse FFT
    # -> squared magnitude -> gaussian blur. See globals_() for the exact code.
    gs = cv2.resize(g, (128, 72), interpolation=cv2.INTER_AREA).astype(float)
    F = np.fft.fft2(gs)
    logA = np.log(np.abs(F) + 1e-9)
    resid = logA - cv2.blur(logA, (3, 3))
    smap = np.abs(np.fft.ifft2(np.exp(resid + 1j * np.angle(F)))) ** 2
    smap = cv2.GaussianBlur(smap, (0, 0), 2.5)
    smap /= (smap.sum() + 1e-9)
    ssort = np.sort(smap.ravel())[::-1]
    sal_top10 = float(ssort[:int(0.10 * len(ssort))].sum())
    return dict(edge_otsu=float(e_otsu), edge_fixed=float(e_fixed), sobel_mean=float(sob.mean()),
                uniq5bit=uniq, col_entropy=col_entropy, colors_for_90pct=n90,
                png512_kb=png / 1024.0, mser_regions=int(len(regs)), hi_freq_frac=hi,
                sal_top10=sal_top10,
                L_mean=float(lab[:, :, 0].mean()), L_std=float(lab[:, :, 0].std()))


def skin_frac(img, faces):
    ycc = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    Cr = ycc[:, :, 1].astype(float)
    Cb = ycc[:, :, 2].astype(float)
    generic = (Cr >= 133) & (Cr <= 176) & (Cb >= 77) & (Cb <= 127)
    samples = []
    for f in faces:
        x, y, w, h = [int(v) for v in f[:4]]
        x0, y0 = max(0, x + int(0.2 * w)), max(0, y + int(0.25 * h))
        x1, y1 = min(img.shape[1], x + int(0.8 * w)), min(img.shape[0], y + int(0.85 * h))
        if x1 > x0 and y1 > y0:
            m = generic[y0:y1, x0:x1]
            if m.sum() > 50:
                samples.append(np.stack([Cr[y0:y1, x0:x1][m], Cb[y0:y1, x0:x1][m]], 1))
    if samples:
        S = np.concatenate(samples)
        mu = S.mean(0)
        cov = np.cov(S.T) + np.eye(2) * 4.0
        inv = np.linalg.inv(cov)
        d = np.stack([Cr - mu[0], Cb - mu[1]], -1)
        md = np.einsum("...i,ij,...j->...", d, inv, d)
        cal = (md < 9.0) & generic
    else:
        cal = generic
    return float(generic.mean()), float(cal.mean())


def figure_ground(img, f):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(float)
    H, W = img.shape[:2]
    x, y, w, h = [float(v) for v in f[:4]]
    cx, cy = x + w / 2, y + h / 2
    Y, X = np.mgrid[0:H, 0:W]
    rin = ((X - cx) / (w * 0.55)) ** 2 + ((Y - cy) / (h * 0.55)) ** 2
    rmid = ((X - cx) / (w * 0.95)) ** 2 + ((Y - cy) / (h * 0.95)) ** 2
    rout = ((X - cx) / (w * 1.35)) ** 2 + ((Y - cy) / (h * 1.35)) ** 2
    inner = rin < 1.0
    outer = (rout < 1.0) & (rmid >= 1.0)
    if inner.sum() < 50 or outer.sum() < 50:
        return None
    dL = abs(lab[:, :, 0][inner].mean() - lab[:, :, 0][outer].mean())
    da = lab[:, :, 1][inner].mean() - lab[:, :, 1][outer].mean()
    db = lab[:, :, 2][inner].mean() - lab[:, :, 2][outer].mean()
    dE = float(math.sqrt(dL * dL + da * da + db * db))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bg_edge = float(cv2.Canny(g, 80, 180)[outer].mean() / 255.0)
    return dict(dL=float(dL), dE=dE, bg_edge_behind=bg_edge,
                inner_L=float(lab[:, :, 0][inner].mean()),
                outer_L=float(lab[:, :, 0][outer].mean()),
                outer_L_std=float(lab[:, :, 0][outer].std()))


def survival(img, faces, W, H):
    res = {}
    orig = cv2.resize(img, (512, 288), interpolation=cv2.INTER_AREA)
    og = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    e_o = cv2.Canny(og, 80, 180).mean()
    for tag, (tw, th) in {"210": (210, 118), "168": (168, 94), "120": (120, 68)}.items():
        small = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
        up = cv2.resize(small, (tw * 4, th * 4), interpolation=cv2.INTER_CUBIC)
        det = cv2.FaceDetectorYN.create(MODEL, "", (tw * 4, th * 4), 0.6, 0.3, 5000)
        det.setInputSize((tw * 4, th * 4))
        n, fs = det.detect(up)
        nfound = 0 if fs is None else int(len(fs))
        rt = cv2.resize(small, (512, 288), interpolation=cv2.INTER_CUBIC)
        rg = cv2.cvtColor(rt, cv2.COLOR_BGR2GRAY)
        s = float(ssim(og, rg))
        e_r = cv2.Canny(rg, 80, 180).mean()
        d = dict(faces_found=nfound, ssim=s, edge_retained=float(e_r / (e_o + 1e-9)))
        if faces:
            big = max(faces, key=lambda f: f[2] * f[3])
            d["big_face_px"] = float(big[3] * th / H)
        res[tag] = d
    return res


def thirds(cx, cy, W, H):
    pts = [(W / 3, H / 3), (2 * W / 3, H / 3), (W / 3, 2 * H / 3), (2 * W / 3, 2 * H / 3)]
    return min(math.hypot(cx - px, cy - py) for px, py in pts) / math.hypot(W, H)


rows = []
for it in files():
    img = cv2.imread(it["path"])
    H, W = img.shape[:2]
    fs = detect(img)
    fs_hi = [f for f in fs if f[14] >= 0.70]
    faces = []
    for f in fs:
        p = pose(f)
        d = dict(x=float(f[0]), y=float(f[1]), w=float(f[2]), h=float(f[3]), conf=float(f[14]),
                 cx=float(f[0] + f[2] / 2) / W, cy=float(f[1] + f[3] / 2) / H,
                 h_frac=float(f[3]) / H, area_frac=float(f[2] * f[3]) / (W * H),
                 thirds_d=thirds(f[0] + f[2] / 2, f[1] + f[3] / 2, W, H), pose=p)
        if p:
            d["expr"] = expression(img, f, p)
            d["eyed_frac"] = p["eyed"] / W
        faces.append(d)
    faces.sort(key=lambda d: -d["area_frac"])
    r = dict(**{k: it[k] for k in ("grp", "file", "views", "dur", "title")}, W=W, H=H,
             n_faces_all=len(fs), n_faces_hi=len(fs_hi), faces=faces)
    r.update(globals_(img))
    gs, cs = skin_frac(img, fs_hi if fs_hi else fs)
    r["skin_generic"] = gs
    r["skin_calibrated"] = cs
    if fs:
        r["fg"] = figure_ground(img, max(fs, key=lambda f: f[2] * f[3]))
    r["surv"] = survival(img, fs, W, H)
    rows.append(r)
    print("%-46s n=%d/%d bigh=%.3f skin=%.3f mser=%3d png=%3.0fkb sal=%.3f"
          % (it["file"][:46], len(fs), len(fs_hi), faces[0]["h_frac"], cs,
             r["mser_regions"], r["png512_kb"], r["sal_top10"]))

json.dump(rows, open(OUT + "/metrics.json", "w", encoding="utf-8"), indent=1, default=float)
print("\nwrote", OUT + "/metrics.json")
