"""Build the real construction (plate + matted judge, bottom-anchored, bleeding
off the right edge) and measure subject/ground separation before and after the
finish, using the same metrics that were measured on the reference set."""
import os, json
import numpy as np, cv2
from skimage import color as skcolor
from rembg import remove, new_session
import finish as F, surfmeas as M, grainchar as G

W, H = 1280, 720
SUBJECT_H = 0.90
BLEED = 60
SESS = None


def matte(bgr):
    global SESS
    if SESS is None:
        SESS = new_session('birefnet-portrait')
    ok, buf = cv2.imencode('.png', bgr)
    out = remove(buf.tobytes(), session=SESS, only_mask=True)
    a = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_UNCHANGED)
    if a.ndim == 3:
        a = a[:, :, -1]
    return a


def build(plate_tile, judge_tile, finish_plate, finish_judge, alpha=None):
    plate = finish_plate(plate_tile, (W, H))
    a = alpha if alpha is not None else matte(judge_tile)
    ys, xs = np.nonzero(a > 12)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cut = judge_tile[y0:y1, x0:x1]
    ca = a[y0:y1, x0:x1]
    th = int(round(SUBJECT_H * H))
    s = th / cut.shape[0]
    tw = max(1, int(round(cut.shape[1] * s)))
    cutf = finish_judge(cut, (tw, th))
    caf = cv2.resize(ca, (tw, th), interpolation=cv2.INTER_LANCZOS4)
    x = W - tw + BLEED
    canvas = plate.copy()
    amask = np.zeros((H, W), np.uint8)
    xs0 = max(0, x); xs1 = min(W, x + tw)
    cx0 = xs0 - x; cx1 = cx0 + (xs1 - xs0)
    ys0 = H - th
    af = (caf[:, cx0:cx1].astype(np.float32) / 255.0)[..., None]
    canvas[ys0:H, xs0:xs1] = (cutf[:, cx0:cx1] * af + canvas[ys0:H, xs0:xs1] * (1 - af)).astype(np.uint8)
    amask[ys0:H, xs0:xs1] = caf[:, cx0:cx1]
    return canvas, amask


def sep(bgr, m):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lab = skcolor.rgb2lab(rgb)
    L, a, b = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    hard = (m > 127).astype(np.uint8)
    din = cv2.distanceTransform(hard, cv2.DIST_L2, 5)
    dout = cv2.distanceTransform(1 - hard, cv2.DIST_L2, 5)
    bi = (din > 2) & (din <= 22)
    bo = (dout > 2) & (dout <= 22)
    fg = m > 200
    bg = m < 40
    ml = lambda s: np.array([L[s].mean(), a[s].mean(), b[s].mean()])
    li, lo = ml(bi), ml(bo)
    Y = M.luma(bgr)
    hp = np.abs(Y - cv2.GaussianBlur(Y, (0, 0), 2))
    return {
        'dL_edge': float(li[0] - lo[0]),
        'dE00_edge': float(skcolor.deltaE_ciede2000(li.reshape(1, 1, 3), lo.reshape(1, 1, 3))[0, 0]),
        'dE00_glob': float(skcolor.deltaE_ciede2000(ml(fg).reshape(1, 1, 3), ml(bg).reshape(1, 1, 3))[0, 0]),
        'hf_fg': float(hp[fg].mean()), 'hf_bg': float(hp[bg].mean()),
        'hf_ratio': float(hp[fg].mean() / max(hp[bg].mean(), 1e-6)),
    }


def measure_all(bgr, m, tag):
    Y = M.luma(bgr)
    d = {}
    d.update(M.bandpass_rms(Y))
    d.update(M.radial_spectrum(Y))
    d.update(M.acutance(Y))
    d['nF'] = M.flat_noise(Y) or 0
    s = sep(bgr, m)
    print('%-26s s1=%5.2f hi/mid=%.4f cut=%.3f grad=%5.2f nF=%5.2f | hf_fg=%5.2f hf_bg=%5.2f ratio=%5.2f dE00edge=%5.1f dLedge=%6.1f' % (
        tag, d['band_s1'], d['spec_hi_over_mid'], d['spec_cutoff_cpp'], d['grad_mean'], d['nF'],
        s['hf_fg'], s['hf_bg'], s['hf_ratio'], s['dE00_edge'], s['dL_edge']), flush=True)
    return d, s


# ---------------- finishers ----------------
def fin_current(tile, size):
    up = cv2.resize(tile, size, interpolation=cv2.INTER_LANCZOS4)
    y = cv2.cvtColor(up, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    for c in (1, 2):
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8), 5).astype(np.float32)
    Y = y[:, :, 0]
    dd = Y - cv2.GaussianBlur(Y, (0, 0), 2.0)
    dd = np.where(np.abs(dd) < 10, 0.0, dd)
    y[:, :, 0] = np.clip(Y + 1.15 * dd, 0, 255)
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def _chain(tile, size, post_sigma, post_iters, blend, sharp_amt, grain):
    a = F.s1_chroma_clean(tile, 2)
    a = F.s2_deblock(a, 3)
    a = F.s3_deconv(a, 0.8, 12)
    a = cv2.resize(a, size, interpolation=cv2.INTER_LANCZOS4)
    a = F.s3b_deconv_clamped(a, post_sigma, post_iters, 1, blend)
    a = F.s7_output_sharpen(a, 0.7, sharp_amt, 2.0)
    if grain:
        a = F.s6_grain(a, sigma=grain, size=0.48)
    return a


def fin_hero(tile, size):
    return _chain(tile, size, 1.3, 16, 1.0, 0.55, 0)      # grain added once, at the end


def fin_ground(tile, size):
    """The ground gets the same cleanup but LESS acutance, so the hero is the
    sharpest thing in frame. Reference median hf_fg/hf_bg = 1.65; the shipped
    build measures 0.37 - the composited hero is the softest object in the
    picture, which is the mechanical definition of 'pasted on'."""
    a = _chain(tile, size, 1.1, 8, 0.55, 0.25, 0)
    return cv2.GaussianBlur(a, (0, 0), 0.7)


def ground_falloff(canvas, m, drop_L=6.0, drop_C=0.12, radius=90):
    """Darken and desaturate the ground in a band around the subject contour.
    Raises dE00 across the boundary without touching layout."""
    d = cv2.distanceTransform((m <= 127).astype(np.uint8), cv2.DIST_L2, 5)
    w = np.clip(1.0 - d / radius, 0, 1) ** 1.5
    w[m > 127] = 0
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lab = skcolor.rgb2lab(rgb)
    lab[:, :, 0] = np.clip(lab[:, :, 0] - drop_L * w, 0, 100)
    lab[:, :, 1] *= (1 - drop_C * w)
    lab[:, :, 2] *= (1 - drop_C * w)
    out = np.clip(skcolor.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_RGB2BGR)


if __name__ == '__main__':
    plate = cv2.imread('D_4437.png')
    judge = cv2.imread('J_3944.png')
    a = matte(judge)
    cv2.imwrite('_judge_alpha.png', a)

    cur, m = build(plate, judge, fin_current, fin_current, a)
    cv2.imwrite('COMP_current.png', cur)
    measure_all(cur, m, 'CURRENT')

    c1, m1 = build(plate, judge, fin_hero, fin_hero, a)
    c1 = F.s6_grain(c1, sigma=5.2, size=0.48)
    cv2.imwrite('COMP_cand_flat.png', c1)
    measure_all(c1, m1, 'CANDIDATE equal-sharp')

    c2, m2 = build(plate, judge, fin_ground, fin_hero, a)
    c2 = F.s6_grain(c2, sigma=5.2, size=0.48)
    cv2.imwrite('COMP_cand_depth.png', c2)
    measure_all(c2, m2, 'CANDIDATE hero-forward')

    c3 = ground_falloff(c2, m2)
    cv2.imwrite('COMP_cand_depth_falloff.png', c3)
    measure_all(c3, m2, 'CANDIDATE +falloff')

    print()
    print('reference (n=24 top-tier YT): hf_ratio median 1.65 [0.62..3.5]  dE00_edge median 21.4 [12.1..49]')
