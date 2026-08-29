"""Premium-finish chain for a low-resolution, low-bitrate court plate.

Every stage is separable and measurable. Nothing here invents detail that is
not in the signal (no GAN, no diffusion) - on a public-record channel an
invented facial feature on a named defendant is a factual problem, not just an
aesthetic one.

Stage order matters and is the opposite of the current build:
  the current grade upscales first and sharpens last, at sigma 2.0, on the
  composed canvas. All real micro-detail is destroyed by the upscale before the
  sharpener ever sees it, and sigma 2.0 boosts the wrong octave.
"""
import numpy as np, cv2


# ---------------------------------------------------------------- helpers
def _box(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided(I, p, r, eps):
    """He, Sun & Tang, Guided Image Filtering, ECCV 2010 / PAMI 2013.
    Edge-preserving, and crucially free of the gradient reversal that makes a
    plain unsharp mask halo."""
    I = I.astype(np.float32); p = p.astype(np.float32)
    mI, mp = _box(I, r), _box(p, r)
    varI = _box(I * I, r) - mI * mI
    covIp = _box(I * p, r) - mI * mp
    a = covIp / (varI + eps)
    b = mp - a * mI
    return _box(a, r) * I + _box(b, r)


def rl_deconv(Y, sigma, iters):
    """Richardson-Lucy with a Gaussian PSF, done with separable blurs so it is
    fast. Recovers detail that IS present but smeared; it cannot fabricate."""
    Y = np.clip(Y.astype(np.float32), 1e-3, None)
    est = Y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        rel = Y / np.maximum(conv, 1e-3)
        est = est * cv2.GaussianBlur(rel, (0, 0), sigma)
        est = np.clip(est, 0, 300)
    return est


def ycc(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)


def unycc(y):
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


# ---------------------------------------------------------------- stages
def s1_chroma_clean(bgr, r=2):
    """Chroma median at NATIVE resolution. The current build does radius 5 at
    1280x720, i.e. an 11x11 median on already-upscaled chroma - same artifact
    removal, far more smearing of real coloured detail."""
    y = ycc(bgr)
    for c in (1, 2):
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8), 2 * r + 1).astype(np.float32)
    return unycc(y)


def s2_deblock(bgr, h=3):
    """Luma-preserving compression cleanup before upscale."""
    y = ycc(bgr)
    y[:, :, 0] = cv2.fastNlMeansDenoising(y[:, :, 0].astype(np.uint8), None, h, 7, 21).astype(np.float32)
    return unycc(y)


def s3_deconv(bgr, sigma=0.8, iters=12):
    y = ycc(bgr)
    y[:, :, 0] = rl_deconv(y[:, :, 0], sigma, iters)
    return unycc(y)


def s4_upscale(bgr, size):
    return cv2.resize(bgr, size, interpolation=cv2.INTER_LANCZOS4)


def s5_detail(bgr, gains=((1, 1e-4, 1.6), (3, 4e-4, 1.25)), clip=28.0):
    """Halo-free multiscale detail boost via guided filters.
    gains = ((radius_px, eps, gain), ...) applied fine -> coarse.
    eps is in normalised (0..1) luma units squared."""
    y = ycc(bgr)
    Y = y[:, :, 0] / 255.0
    out = Y.copy()
    for r, eps, g in gains:
        base = guided(out, out, r, eps)
        det = out - base
        out = base + np.clip(det * g, -clip / 255.0, clip / 255.0)
    y[:, :, 0] = np.clip(out * 255.0, 0, 255)
    return unycc(y)


def s6_grain(bgr, sigma=3.6, size=0.42, luma_shape=True, seed=7, chroma=0.0):
    """Monochromatic grain at the OUTPUT resolution.
    Reference measurement (n=24 top-tier YouTube thumbnails, plate region):
      residual sigma median 4.40, ACF FWHM 1.17 px, chroma/luma residual 0.11.
    `size` is the gaussian sigma used to shape white noise; 0.42 lands the ACF
    FWHM at ~1.2 px. Larger values give bigger, softer grain."""
    rng = np.random.default_rng(seed)
    y = ycc(bgr)
    H, W = y.shape[:2]
    n = rng.standard_normal((H, W)).astype(np.float32)
    if size > 0:
        n = cv2.GaussianBlur(n, (0, 0), size)
    n /= max(n.std(), 1e-6)
    if luma_shape:
        # film grain peaks in the midtones and dies at both ends
        t = y[:, :, 0] / 255.0
        w = 1.0 - np.abs(t - 0.45) / 0.55
        n *= np.clip(w, 0.25, 1.0)
        n /= max(n.std(), 1e-6)
    y[:, :, 0] = np.clip(y[:, :, 0] + n * sigma, 0, 255)
    if chroma > 0:
        for c in (1, 2):
            nc = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), size)
            nc /= max(nc.std(), 1e-6)
            y[:, :, c] = np.clip(y[:, :, c] + nc * sigma * chroma, 0, 255)
    return unycc(y)


def s7_output_sharpen(bgr, sigma=0.7, amount=0.55, threshold=2.0):
    """Small-radius output sharpening. RawTherapee's guidance for in-focus,
    low-noise material is radius 0.5-0.7; the current build uses 2.0, which
    boosts the sigma 2-8 octave (macro punch) and adds nothing at sigma 1."""
    y = ycc(bgr)
    Y = y[:, :, 0]
    blur = cv2.GaussianBlur(Y, (0, 0), sigma)
    d = Y - blur
    d = np.where(np.abs(d) < threshold, 0.0, d)
    y[:, :, 0] = np.clip(Y + amount * d, 0, 255)
    return unycc(y)


def s3b_deconv_clamped(bgr, sigma=1.2, iters=12, clamp_r=1, blend=1.0):
    """Richardson-Lucy with an anti-ringing clamp.

    Plain RL on a Lanczos-upscaled frame produces a dark band beside every
    strong edge. Measured on the CARTHIEF defendant tile: undershoot rose to
    60.4% of step height against a reference 90th percentile of 44.6%.
    Clamping the result into the [local min, local max] of the INPUT inside a
    clamp_r neighbourhood removes the overshoot while keeping the acutance,
    because real detail never exceeds its own neighbourhood extremes."""
    y = ycc(bgr)
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, sigma, iters)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1, 2 * clamp_r + 1))
    lo = cv2.erode(Y0, k)
    hi = cv2.dilate(Y0, k)
    Y = np.clip(Y, lo, hi)
    y[:, :, 0] = np.clip(Y0 + (Y - Y0) * blend, 0, 255)
    return unycc(y)
