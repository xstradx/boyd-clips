"""Surface-quality metrics for thumbnails / key art.
Every metric is defined here so it is reproducible. No opinions, only numbers.
"""
import sys, os, glob, json, math
import numpy as np, cv2
from skimage import color as skcolor


def load(path, norm_w=None, crop=None):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    if crop:
        x0, y0, x1, y1 = crop
        H, W = bgr.shape[:2]
        bgr = bgr[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]
    if norm_w and bgr.shape[1] != norm_w:
        h = int(round(bgr.shape[0] * norm_w / bgr.shape[1]))
        interp = cv2.INTER_AREA if bgr.shape[1] > norm_w else cv2.INTER_LANCZOS4
        bgr = cv2.resize(bgr, (norm_w, h), interpolation=interp)
    return bgr


def luma(bgr):
    b, g, r = [bgr[:, :, i].astype(np.float64) for i in range(3)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------- 1. tone / rolloff ----------
def tone(Y):
    h = np.histogram(Y, bins=256, range=(0, 256))[0].astype(np.float64)
    out = {}
    out['Y_mean'] = float(Y.mean())
    out['Y_std'] = float(Y.std())
    for p in (0.5, 1, 5, 50, 95, 99, 99.5):
        out['Y_p%s' % p] = float(np.percentile(Y, p))
    out['pct_below_16'] = float((Y < 16).mean() * 100)
    out['pct_below_4'] = float((Y < 4).mean() * 100)
    out['pct_above_235'] = float((Y >= 235).mean() * 100)
    out['pct_above_250'] = float((Y >= 250).mean() * 100)
    out['pct_at_255'] = float((Y >= 254.5).mean() * 100)
    hi = (Y >= 235).sum()
    out['clip_ratio'] = float((Y >= 254.5).sum() / hi) if hi > 50 else None
    seg = h[200:253] + 1
    x = np.arange(len(seg))
    out['shoulder_slope'] = float(np.polyfit(x, np.log(seg), 1)[0])
    return out


# ---------- 2. multiscale local contrast ----------
def bandpass_rms(Y, sigmas=(1, 2, 4, 8, 16, 32, 64)):
    prev = cv2.GaussianBlur(Y, (0, 0), 0.5)
    out = {}
    for s in sigmas:
        cur = cv2.GaussianBlur(Y, (0, 0), s)
        band = prev - cur
        out['band_s%d' % s] = float(np.sqrt((band ** 2).mean()))
        prev = cur
    return out


# ---------- 3. acutance ----------
def acutance(Y):
    gx = cv2.Sobel(Y, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(Y, cv2.CV_64F, 0, 1, ksize=3)
    g = np.hypot(gx, gy) / 4.0
    out = {'grad_mean': float(g.mean())}
    thr = np.percentile(g, 90)
    out['grad_p90'] = float(thr)
    out['grad_top10_mean'] = float(g[g >= thr].mean())
    out['grad_p99'] = float(np.percentile(g, 99))
    return out


# ---------- 4. halo / oversharpening ----------
def halo(Y):
    Yf = Y.astype(np.float32)
    gx = cv2.Sobel(Yf, cv2.CV_32F, 1, 0, 3)
    gy = cv2.Sobel(Yf, cv2.CV_32F, 0, 1, 3)
    g = np.hypot(gx, gy) / 4.0
    thr = np.percentile(g, 99)
    mask = g >= thr
    if mask.sum() < 200:
        return {'halo_overshoot': None, 'halo_undershoot': None, 'halo_pct': None}
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    k11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (23, 23))
    near_max = cv2.dilate(Yf, k3)
    far_max = cv2.dilate(Yf, k11)
    near_min = cv2.erode(Yf, k3)
    far_min = cv2.erode(Yf, k11)
    base = cv2.GaussianBlur(Yf, (0, 0), 8)
    amp = np.maximum((far_max - far_min)[mask], 1e-3)
    ov = np.clip((near_max - base)[mask] / amp, 0, 3)
    un = np.clip((base - near_min)[mask] / amp, 0, 3)
    return {'halo_overshoot': float(np.median(ov)),
            'halo_undershoot': float(np.median(un)),
            'halo_pct': float(((ov > 0.55) & (un > 0.55)).mean() * 100)}


# ---------- 5. grain / noise ----------
def noise_immerkaer(Y):
    """J. Immerkaer, Fast Noise Variance Estimation, CVGIP:IU 64(2) 1996."""
    M = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    H, W = Y.shape
    conv = cv2.filter2D(Y, cv2.CV_64F, M)
    return float(math.sqrt(math.pi / 2) / (6 * (W - 2) * (H - 2)) * np.abs(conv).sum())


def flat_noise(Y):
    loc = cv2.GaussianBlur(Y, (0, 0), 8)
    var = cv2.GaussianBlur(Y * Y, (0, 0), 8) - loc * loc
    sd = np.sqrt(np.maximum(var, 0))
    q = np.percentile(sd, 25)
    m = sd <= q
    M = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    conv = np.abs(cv2.filter2D(Y, cv2.CV_64F, M))
    if m.sum() < 500:
        return None
    return float(math.sqrt(math.pi / 2) / 6 * conv[m].mean())


def radial_spectrum(Y):
    h, w = Y.shape
    n = min(h, w)
    n -= n % 2
    p = Y[(h - n) // 2:(h - n) // 2 + n, (w - n) // 2:(w - n) // 2 + n].astype(np.float64)
    p = p - p.mean()
    win = np.outer(np.hanning(n), np.hanning(n))
    F = np.fft.fftshift(np.fft.fft2(p * win))
    P = np.abs(F) ** 2
    yy, xx = np.indices((n, n))
    c = n // 2
    r = np.hypot(yy - c, xx - c).astype(int)
    tb = np.bincount(r.ravel(), P.ravel())
    cnt = np.bincount(r.ravel())
    prof = tb[:c] / np.maximum(cnt[:c], 1)
    f = np.arange(c) / n
    L = 10 * np.log10(prof + 1e-12)
    ref_i = max(1, int(0.02 * n))
    ref = L[ref_i]
    cut = None
    for i in range(ref_i, c):
        if L[i] < ref - 40:
            cut = f[i]
            break
    out = {'spec_cutoff_cpp': (float(cut) if cut else 0.5)}
    i0, i1 = int(0.05 * n), int(0.35 * n)
    if i1 > i0 + 5:
        out['spec_slope'] = float(np.polyfit(np.log10(f[i0:i1]), L[i0:i1], 1)[0])

    def band(a, b):
        ia, ib = int(a * n), int(b * n)
        return float(prof[ia:ib].mean())

    out['spec_hi_over_mid'] = float(band(0.25, 0.5) / max(band(0.06, 0.125), 1e-9))
    return out


# ---------- 6. colour ----------
def colour(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lab = skcolor.rgb2lab(rgb)
    L, a, b = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    C = np.hypot(a, b)
    hdeg = (np.degrees(np.arctan2(b, a)) + 360) % 360
    hist = np.histogram(hdeg, bins=36, range=(0, 360), weights=(C > 12).astype(float))[0]
    s = max(hist.sum(), 1)
    hist = hist / s
    nz = hist[hist > 0]
    ent = float(-(nz * np.log2(nz)).sum())
    return {'L_mean': float(L.mean()), 'L_std': float(L.std()),
            'C_mean': float(C.mean()), 'C_p95': float(np.percentile(C, 95)),
            'pct_C_gt60': float((C > 60).mean() * 100),
            'pct_C_lt10': float((C < 10).mean() * 100),
            'hue_entropy_bits': ent}


# ---------- 7. blockiness ----------
def blockiness(Y):
    d = np.abs(np.diff(Y, axis=1))
    cols = np.arange(d.shape[1])
    on = d[:, (cols % 8) == 7].mean()
    off = d[:, (cols % 8) != 7].mean()
    dv = np.abs(np.diff(Y, axis=0))
    rows = np.arange(dv.shape[0])
    onv = dv[(rows % 8) == 7, :].mean()
    offv = dv[(rows % 8) != 7, :].mean()
    return {'block_h': float(on - off), 'block_v': float(onv - offv)}


def measure(path, norm_w=None, tag='', crop=None):
    bgr = load(path, norm_w, crop)
    if bgr is None:
        return None
    Y = luma(bgr)
    d = {'file': os.path.basename(path), 'tag': tag, 'w': bgr.shape[1], 'h': bgr.shape[0]}
    d.update(tone(Y))
    d.update(bandpass_rms(Y))
    d.update(acutance(Y))
    d.update(halo(Y))
    d.update(radial_spectrum(Y))
    d.update(colour(bgr))
    d.update(blockiness(Y))
    d['noise_global'] = noise_immerkaer(Y)
    d['noise_flat'] = flat_noise(Y)
    return d


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--norm', type=int, default=None)
    ap.add_argument('--tag', default='')
    ap.add_argument('--out', default=None)
    ap.add_argument('--crop', default=None)
    a = ap.parse_args()
    rows = []
    for pat in a.paths:
        for f in sorted(glob.glob(pat)):
            cr = tuple(float(v) for v in a.crop.split(',')) if a.crop else None
            r = measure(f, a.norm, a.tag, cr)
            if r:
                rows.append(r)
    if a.out:
        open(a.out, 'w').write(json.dumps(rows, indent=1))
    print(json.dumps(rows, indent=1)[:400])
    print('rows', len(rows))
