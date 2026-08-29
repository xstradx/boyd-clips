"""Grain / texture character of the reference set.

Isolates the residual (image minus an edge-preserving base) inside the flattest
areas, then reports:
  sigma      : residual std in ADU (8-bit)
  acf_fwhm   : full width at half max of the residual autocorrelation, in px
               -> the physical GRAIN SIZE
  iso        : how isotropic the residual is (1.0 = round grain, <1 = directional)
  lum_slope  : how residual sigma varies with local luminance (film grain peaks
               in the midtones and dies in the highlights; digital noise is flat
               or rises in shadows)
  chroma_frac: chroma residual sigma / luma residual sigma
               (film grain is largely monochromatic in a scan; sensor noise is not)
"""
import sys, glob, os, json
import numpy as np, cv2


def residual(Y):
    base = cv2.medianBlur(Y.astype(np.float32), 5)
    base = cv2.GaussianBlur(base, (0, 0), 1.0)
    return Y.astype(np.float32) - base


def flatmask(Y, pct=35):
    loc = cv2.GaussianBlur(Y, (0, 0), 6)
    var = cv2.GaussianBlur(Y * Y, (0, 0), 6) - loc * loc
    sd = np.sqrt(np.maximum(var, 0))
    return sd <= np.percentile(sd, pct), loc


def acf(R, m, half=8):
    n = m.sum()
    if n < 2000:
        return None
    out = np.zeros((2 * half + 1, 2 * half + 1))
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            mm = m & np.roll(np.roll(m, dy, 0), dx, 1)
            k = mm.sum()
            if k < 500:
                out[dy + half, dx + half] = 0
            else:
                out[dy + half, dx + half] = float((R * np.roll(np.roll(R, dy, 0), dx, 1))[mm].sum() / k)
    c = out[half, half]
    if c <= 0:
        return None
    out = out / c
    # radial FWHM
    prof = []
    for r in range(0, half + 1):
        yy, xx = np.indices(out.shape)
        d = np.hypot(yy - half, xx - half)
        sel = (d >= r - 0.5) & (d < r + 0.5)
        prof.append(out[sel].mean() if sel.sum() else 0)
    prof = np.array(prof)
    fw = half * 2.0
    for r in range(1, len(prof)):
        if prof[r] < 0.5:
            fw = 2 * ((r - 1) + (prof[r - 1] - 0.5) / max(prof[r - 1] - prof[r], 1e-9))
            break
    hor = out[half, half + 1]
    ver = out[half + 1, half]
    return {'acf_fwhm_px': float(fw), 'acf_h1': float(hor), 'acf_v1': float(ver),
            'iso': float(min(hor, ver) / max(abs(hor), abs(ver), 1e-6)),
            'sigma': float(np.sqrt(c))}


def run(path, crop=None):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    if crop:
        H, W = bgr.shape[:2]
        x0, y0, x1, y1 = crop
        bgr = bgr[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Y = ycc[:, :, 0]
    m, loc = flatmask(Y)
    R = residual(Y)
    d = {'file': os.path.basename(path)}
    a = acf(R, m)
    if a:
        d.update(a)
    Rc = residual(ycc[:, :, 1])
    Rc2 = residual(ycc[:, :, 2])
    if m.sum() > 2000:
        sl = float(np.sqrt((R[m] ** 2).mean()))
        sc = float(np.sqrt((Rc[m] ** 2).mean() + (Rc2[m] ** 2).mean()) / np.sqrt(2))
        d['chroma_frac'] = sc / max(sl, 1e-6)
        # sigma vs luminance in 5 bins
        bins = []
        for lo, hi in [(0, 51), (51, 102), (102, 153), (153, 204), (204, 256)]:
            sel = m & (loc >= lo) & (loc < hi)
            bins.append(float(np.sqrt((R[sel] ** 2).mean())) if sel.sum() > 400 else None)
        d['sigma_by_luma'] = bins
    return d


if __name__ == '__main__':
    crop = None
    args = sys.argv[1:]
    if args and args[0].startswith('--crop='):
        crop = tuple(float(v) for v in args[0].split('=')[1].split(','))
        args = args[1:]
    rows = []
    for pat in args:
        for f in sorted(glob.glob(pat)):
            r = run(f, crop)
            if r:
                rows.append(r)
                print('%-28s sig=%5.2f fwhm=%4.2fpx iso=%4.2f h1=%5.2f chroma=%4.2f byL=%s' % (
                    r['file'][:28], r.get('sigma', 0), r.get('acf_fwhm_px', 0), r.get('iso', 0),
                    r.get('acf_h1', 0), r.get('chroma_frac', 0),
                    ' '.join(('%.2f' % v if v else ' -- ') for v in r.get('sigma_by_luma', []))))
    json.dump(rows, open('grainchar.json', 'w'), indent=1)
