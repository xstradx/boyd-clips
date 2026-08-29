"""Edge-profile analysis: measures the ACTUAL sharpening signature of an image.

For each strong, locally-straight step edge we sample the luma profile along the
gradient normal for +/-12 px, normalise it to the step, and report:
  rise_10_90  : distance in px from 10% to 90% of the step  (acutance / effective radius)
  overshoot   : peak excursion beyond the bright plateau, as % of step height
  undershoot  : peak excursion below the dark plateau, as % of step height
  halo_radius : distance from the edge centre to the overshoot peak (= USM radius)
Also measures alpha-matte contour quality when an RGBA cutout is supplied.
"""
import sys, glob, json, os
import numpy as np, cv2


def profiles(Y, n_target=4000, half=12, seed=0):
    Yf = Y.astype(np.float32)
    sm = cv2.GaussianBlur(Yf, (0, 0), 1.2)
    gx = cv2.Sobel(sm, cv2.CV_32F, 1, 0, 3) / 4.0
    gy = cv2.Sobel(sm, cv2.CV_32F, 0, 1, 3) / 4.0
    g = np.hypot(gx, gy)
    thr = np.percentile(g, 99.5)
    ys, xs = np.nonzero(g >= thr)
    keep = (xs > half + 2) & (xs < Y.shape[1] - half - 2) & (ys > half + 2) & (ys < Y.shape[0] - half - 2)
    ys, xs = ys[keep], xs[keep]
    if len(ys) == 0:
        return None
    rng = np.random.default_rng(seed)
    if len(ys) > n_target:
        idx = rng.choice(len(ys), n_target, replace=False)
        ys, xs = ys[idx], xs[idx]
    nx = gx[ys, xs] / np.maximum(g[ys, xs], 1e-6)
    ny = gy[ys, xs] / np.maximum(g[ys, xs], 1e-6)
    ts = np.arange(-half, half + 1, 0.5, dtype=np.float32)
    P = np.empty((len(ys), len(ts)), np.float32)
    for k, t in enumerate(ts):
        mx = (xs + nx * t).astype(np.float32)
        my = (ys + ny * t).astype(np.float32)
        P[:, k] = cv2.remap(Yf, mx.reshape(-1, 1), my.reshape(-1, 1),
                            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).ravel()
    return P, ts


def analyse(Y, seed=0):
    r = profiles(Y, seed=seed)
    if r is None:
        return {}
    P, ts = r
    lo = P[:, :3].mean(1)          # far dark side (t = -12..-11)
    hi = P[:, -3:].mean(1)         # far bright side
    step = hi - lo
    good = step > 25               # only real steps
    if good.sum() < 50:
        return {'n_edges': int(good.sum())}
    P = P[good]; lo = lo[good]; hi = hi[good]; step = step[good]
    N = (P - lo[:, None]) / step[:, None]      # 0 at dark plateau, 1 at bright plateau
    mean_prof = N.mean(0)
    # 10-90 rise measured on the mean normalised profile
    c = len(ts) // 2

    def cross(level):
        for i in range(1, len(ts)):
            if mean_prof[i - 1] < level <= mean_prof[i]:
                f = (level - mean_prof[i - 1]) / (mean_prof[i] - mean_prof[i - 1] + 1e-9)
                return ts[i - 1] + f * (ts[i] - ts[i - 1])
        return None
    t10, t90 = cross(0.1), cross(0.9)
    out = {'n_edges': int(len(P))}
    if t10 is not None and t90 is not None:
        out['rise_10_90_px'] = float(t90 - t10)
    over = mean_prof[c + 1:].max() - 1.0
    j = int(np.argmax(mean_prof[c + 1:]))
    under = 0.0 - mean_prof[:c].min()
    k = int(np.argmin(mean_prof[:c]))
    out['overshoot_pct'] = float(over * 100)
    out['undershoot_pct'] = float(under * 100)
    out['overshoot_radius_px'] = float(ts[c + 1 + j])
    out['undershoot_radius_px'] = float(abs(ts[k]))
    out['mean_step_adu'] = float(step.mean())
    out['profile'] = [round(float(v), 4) for v in mean_prof]
    out['ts'] = [float(v) for v in ts]
    return out


def alpha_contour(rgba_path):
    im = cv2.imread(rgba_path, cv2.IMREAD_UNCHANGED)
    if im is None or im.shape[2] < 4:
        return None
    a = im[:, :, 3].astype(np.float32) / 255.0
    inner = a > 0.98
    outer = a < 0.02
    soft = (~inner) & (~outer)
    dist_in = cv2.distanceTransform((a > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform((a <= 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    sd = np.where(a > 0.5, dist_in, -dist_out)
    band = np.abs(sd) < 6
    if band.sum() < 100:
        return None
    # transition width: mean |d alpha/d n| inverse -> width where 10%<a<90%
    trans = ((a > 0.1) & (a < 0.9))
    # perimeter length of the 0.5 contour
    edges = cv2.Canny((a > 0.5).astype(np.uint8) * 255, 50, 150)
    per = max(int((edges > 0).sum()), 1)
    return {'soft_frac_of_fg': float(soft.sum() / max(inner.sum(), 1)),
            'trans_px_per_perim': float(trans.sum() / per),
            'mid_alpha_px': int(trans.sum()),
            'perimeter_px': per,
            'fg_px': int(inner.sum())}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--crop', default=None, help='x0,y0,x1,y1 fractions')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    res = []
    for pat in a.paths:
        for f in sorted(glob.glob(pat)):
            bgr = cv2.imread(f, cv2.IMREAD_COLOR)
            if bgr is None:
                continue
            if a.crop:
                x0, y0, x1, y1 = [float(v) for v in a.crop.split(',')]
                H, W = bgr.shape[:2]
                bgr = bgr[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
            Y = (0.2126 * bgr[:, :, 2] + 0.7152 * bgr[:, :, 1] + 0.0722 * bgr[:, :, 0]).astype(np.float64)
            d = analyse(Y)
            d['file'] = os.path.basename(f)
            res.append(d)
            print('%-28s n=%5d rise10-90=%s px  over=%5.1f%% @%.1fpx  under=%5.1f%% @%.1fpx  step=%.0f' % (
                d['file'][:28], d.get('n_edges', 0),
                ('%.2f' % d['rise_10_90_px']) if 'rise_10_90_px' in d else ' n/a',
                d.get('overshoot_pct', 0), d.get('overshoot_radius_px', 0),
                d.get('undershoot_pct', 0), d.get('undershoot_radius_px', 0),
                d.get('mean_step_adu', 0)))
    if a.out:
        json.dump(res, open(a.out, 'w'), indent=1)
