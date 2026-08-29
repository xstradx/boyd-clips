"""Q4_light - OUR construction, executed to a higher standard of finish.

Nathan, 2026-08-29: "fix the thumbnails with the team use ours as reference just
take them to the next level quality and detail wise".

So the CONSTRUCTION is frozen and copied from `make_thumbnail_v5.py` / the
shipped `READY-TO-POST/1_LONGFORM_thumbnail.jpg`:

    courtroom plate carrying the defendant and his attorney, full frame
    Judge Boyd matted out of her own Zoom tile, composited over it,
      bottom-anchored, bleeding off the RIGHT edge, NO outline stroke
    a red arrow pointing at the defendant from clear space
    ONE line of type, top-left, white with the key phrase in yellow,
      heavy black stroke plus a soft zero-offset glow
    graded, with the type burned in AFTER the grade

What changes is only the CRAFT, and every change below is something that was
measured rather than chosen. The bet this variant makes is that FINISH, not
resolution, is what reads as premium:

  1. STAGE ORDER. The old build upscaled first and sharpened last at radius 2.0
     - i.e. it destroyed the sigma-1 octave with a Lanczos resize and then
     boosted the sigma 2-8 octave, which was the one octave we were NOT short
     of. Measured on the real judge tile: chroma clean + deblock + Richardson-
     Lucy at NATIVE resolution puts band_s1 at 6.41 against a top-tier YouTube
     target of 6.21 - dead on - and the subsequent 2x upscale then throws 57%
     of it away. So every restorative step now happens on the correct side of
     the upscale, and a second, anti-ringing-clamped deconvolution happens
     after it.

  2. SUBJECT / GROUND SEPARATION. In 24 top-tier YouTube thumbnails the subject
     is SHARPER than its ground (hf_fg/hf_bg median 1.65). In all four of ours
     it is softer (median 0.365, below their 10th percentile). A composited
     hero that is the softest object in frame is the mechanical definition of
     "pasted on". Here the hero gets more acutance than the ground, by
     construction, and the depth-of-field is applied to the ROOM ONLY so both
     men stay sharp - they stand at the same distance from the lens as each
     other, so blurring one of them would read as a mistake, not as depth.

  3. LIGHT WRAP, replacing `_rim`. The old rim was a CONSTANT brightness lift
     off the alpha's own edge, so it could never make her sit in the plate's
     light. This samples the PLATE's actual pixels behind her, blurs them, and
     screens them into a band just inside her contour. Nukepedia's rule for it
     is quoted in the code: you want to feel it, not see it.

  4. GRAIN. Reference work carries visible grain (residual sigma median 4.40
     over n=24) and ours had 0.775 - a 5.7x gap - and ours was the wrong SIZE
     (1.9px vs 1.18px) and the wrong COLOUR (48% chroma vs 10%). Added once, on
     the composed frame, monochromatic and midtone-weighted, which is the
     measured film-grain signature.

  5. NO REGROUP. `regroup_plate.py` moves the defendant toward his attorney and
     on CARTHIEF it cut his arm off at the shoulder - visible in the shipped
     file as a hard vertical edge through his right shoulder. Nathan: "a
     severed limb is worse than a looser composition". At source 4437 the two
     men already stand adjacent, so there is nothing to gain and a body to
     lose. The operation is simply not run; nothing in the plate is moved.

MODEL AND FONT LICENCES, all verified for a monetised channel:
    BiRefNet / birefnet-matting     MIT   (emrikol/birefnet-matting-onnx)
    pymatting 1.1.15                MIT
    onnxruntime 1.28.0              MIT
    opencv-python                   Apache-2.0
    numpy / scipy / scikit-image    BSD-3
    TTT Headline (Archivo w900/wd70) OFL
ViTMatte is deliberately NOT used even though it measured as the best edge
refiner: its weights are trained on Adobe's Composition-1k, whose dataset page
states no terms at all, and that is an open training-data question on a
monetised channel. The guided-filter refinement used instead is a direct
implementation of He, Sun & Tang (ECCV 2010) and carries no such question.
rembg's DEFAULT session is bria-rmbg, which is CC BY-NC 4.0 - it is never
called here; the ONNX is loaded directly.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

# ---- MEASURED SPEC, off the shipped Thompson thumbnail. Do not drift. ----
W, H = 1280, 720
YELLOW = (254, 251, 3)
WHITE = (255, 255, 255)
ARROW_RED = (253, 1, 1)              # #FD0101
TEXT_X = 23
TEXT_TOP = 31
TEXT_RIGHT = 1072                    # line runs x23 -> x1072 = 1049px
CAP_PX = 71                          # 0.0986 H, measured on the letter Y
STROKE = 11
GLOW_RADIUS = 20
ARROW_W, ARROW_H = 105, 76           # 0.41% of frame

MATTING_ONNX = (Path(os.path.expanduser("~")) / ".cache" / "huggingface" / "hub"
                / "models--emrikol--birefnet-matting-onnx" / "snapshots")

# ===================================================================== matte
_SESS: dict = {}


def _onnx(path: str):
    import onnxruntime as ort
    if path not in _SESS:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 8
        _SESS[path] = ort.InferenceSession(path, so,
                                           providers=["CPUExecutionProvider"])
    return _SESS[path]


def _matting_model() -> str:
    hits = sorted(MATTING_ONNX.glob("*/birefnet-matting.onnx"))
    if not hits:
        raise SystemExit(f"birefnet-matting.onnx not found under {MATTING_ONNX}")
    return str(hits[0])


_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def birefnet_alpha(bgr: np.ndarray) -> np.ndarray:
    """BiRefNet-matting at 1024x1024, delivered at the tile's native size.

    Squash (not pad) because that is what rembg does and because measured on
    this crop pad trades hair mass for colour fringe the wrong way: matting/pad
    gives hair 4914 fringe 49.75, matting/squash gives hair 4189 fringe 39.31.
    BiRefNet-matting was chosen over all three rembg BiRefNet models on this
    exact judge crop: best contour placement (align 2.227), +15% more soft hair
    than birefnet-portrait, -11% matting-equation residual. birefnet-massive is
    the WORST for hair despite being the biggest model - it is a DICHOTOMOUS
    segmentation checkpoint, so a binary edge is its training objective.
    """
    h, w = bgr.shape[:2]
    s = _onnx(_matting_model())
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR)
    x = x.astype(np.float32) / 255.0
    x = ((x - _MEAN) / _STD).transpose(2, 0, 1)[None]
    y = s.run(None, {s.get_inputs()[0].name: x})[0]
    p = 1.0 / (1.0 + np.exp(-np.squeeze(y[:, 0])))
    a = cv2.resize((np.clip(p, 0, 1) * 255).astype(np.uint8), (w, h),
                   interpolation=cv2.INTER_LANCZOS4)
    return a


def _boxf(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_color(I: np.ndarray, p: np.ndarray, r=2, eps=1e-4) -> np.ndarray:
    """He, Sun & Tang, 'Guided Image Filtering', ECCV 2010 / TPAMI 2013 -
    the COLOUR-guide variant, the one with the proven link to the matting
    Laplacian. Own implementation: cv2.ximgproc is not reachable in this
    interpreter (opencv resolves to 4.14.0 and dir(cv2.ximgproc) returns 0
    names) despite opencv-contrib being installed - a version shadow.

    r=2 eps=1e-4 is the measured setting: residual 2.36 -> 1.77 with fringe
    flat. r=8 looks better on residual (1.14) but blows fringe to 50.97 - never
    go above r=4.
    """
    I = I.astype(np.float32)
    p = p.astype(np.float32)
    mI = np.stack([_boxf(I[..., c], r) for c in range(3)], -1)
    mp = _boxf(p, r)
    mIp = np.stack([_boxf(I[..., c] * p, r) for c in range(3)], -1)
    cov = mIp - mI * mp[..., None]
    var = np.empty(I.shape[:2] + (3, 3), np.float32)
    for i in range(3):
        for j in range(3):
            var[..., i, j] = _boxf(I[..., i] * I[..., j], r) - mI[..., i] * mI[..., j]
    var += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(var, cov[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    ma = np.stack([_boxf(a[..., c], r) for c in range(3)], -1)
    mb = _boxf(b, r)
    return np.clip((ma * I).sum(-1) + mb, 0, 1)


def refined_cutout(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (decontaminated RGB-as-BGR, alpha) for a tile.

    The colour-fringe fix is NOT simply 'run estimate_foreground_ml' - on the
    alpha we ship today that makes the fringe 43% WORSE (20.06 -> 28.67).
    It needs a SOFT alpha to solve F and the SHARP alpha to composite:
    decoupling the two is what makes decontamination work here (14.81, -26%).
    """
    from pymatting import estimate_foreground_ml
    a0 = birefnet_alpha(bgr)
    I = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    sharp = guided_color(I, a0.astype(np.float32) / 255.0, r=2, eps=1e-4)
    soft = guided_color(I, a0.astype(np.float32) / 255.0, r=6, eps=4e-4)
    F = estimate_foreground_ml(I.astype(np.float64),
                               np.clip(soft, 0, 1).astype(np.float64))
    fg = np.clip(F * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(fg, cv2.COLOR_RGB2BGR), (np.clip(sharp, 0, 1) * 255).astype(np.uint8)


# =================================================================== finish
def _ycc(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)


def _unycc(y):
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def rl_deconv(Y, sigma, iters):
    """Richardson-Lucy with a Gaussian PSF. It recovers detail that IS present
    but smeared; it cannot fabricate. That distinction is the reason no GAN or
    diffusion upscaler is used here - on a public-record channel an invented
    eyelash on a named defendant is a factual problem, not an aesthetic one."""
    Y = np.clip(Y.astype(np.float32), 1e-3, None)
    est = Y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        est = est * cv2.GaussianBlur(Y / np.maximum(conv, 1e-3), (0, 0), sigma)
        est = np.clip(est, 0, 300)
    return est


def deconv_clamped(bgr, sigma=1.3, iters=16, clamp_r=1, blend=0.85):
    """RL with an anti-ringing clamp.

    Plain RL after an upscale produces a dark band beside every strong edge:
    measured undershoot rose to 60.4% of step height against a reference 90th
    percentile of 44.6%, visible as a dark line along the ceiling beam. Clamping
    into the [erode, dilate] range of the PRE-deconvolution luma removes it -
    real detail never exceeds its own neighbourhood extremes - and returns
    undershoot to 44.2% while band_s1 still rises 2.71 -> 5.32.
    """
    y = _ycc(bgr)
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, sigma, iters)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1,) * 2)
    Y = np.clip(Y, cv2.erode(Y0, k), cv2.dilate(Y0, k))
    y[:, :, 0] = np.clip(Y0 + (Y - Y0) * blend, 0, 255)
    return _unycc(y)


def usm(bgr, sigma=0.7, amount=0.55, threshold=2.0):
    """Small-radius output sharpening. RawTherapee's guidance for in-focus, low
    noise material is radius 0.5-0.7; darktable deprecates USM entirely. The old
    grade used radius 2.0, which is a sigma-2 Gaussian - the wrong octave."""
    y = _ycc(bgr)
    Y = y[:, :, 0]
    d = Y - cv2.GaussianBlur(Y, (0, 0), sigma)
    d = np.where(np.abs(d) < threshold, 0.0, d)
    y[:, :, 0] = np.clip(Y + amount * d, 0, 255)
    return _unycc(y)


def finish(tile_bgr, size, *, post_blend=0.85, sharp=0.55, alpha=None):
    """The proven chain, native-first. Returns (bgr, alpha) at `size`.

    The alpha rides along through the identical geometry so the matte can never
    drift off the picture it belongs to.
    """
    a = cv2.medianBlur(tile_bgr, 1)  # no-op placeholder keeps dtype/shape clear
    y = _ycc(tile_bgr)
    for c in (1, 2):                                    # (1) chroma median 5x5
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8), 5).astype(np.float32)
    a = _unycc(y)
    y = _ycc(a)                                         # (2) NLM luma deblock
    y[:, :, 0] = cv2.fastNlMeansDenoising(
        y[:, :, 0].astype(np.uint8), None, 3, 7, 21).astype(np.float32)
    a = _unycc(y)
    y = _ycc(a)                                         # (3) RL at NATIVE res
    y[:, :, 0] = rl_deconv(y[:, :, 0], 0.8, 12)
    a = _unycc(y)
    a = cv2.resize(a, size, interpolation=cv2.INTER_LANCZOS4)   # (4) upscale
    a = deconv_clamped(a, 1.3, 16, 1, post_blend)               # (5) clamped RL
    a = usm(a, 0.7, sharp, 2.0)                                 # (6) USM
    af = None
    if alpha is not None:
        af = cv2.resize(alpha, size, interpolation=cv2.INTER_LANCZOS4)
    return a, af


# ==================================================================== light
def defocus(bgr, radius):
    """A real out-of-focus lens has a DISC point-spread function, not a
    Gaussian. A Gaussian blur reads as 'blurred photo'; a disc reads as 'shot at
    f/2', because out-of-focus specular highlights bloom into little circles
    instead of smearing. The courtroom's downlights are exactly such highlights,
    so the difference is visible on this plate specifically."""
    if radius <= 0:
        return bgr
    r = int(round(radius))
    k = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
    cv2.circle(k, (r, r), r, 1.0, -1)
    k /= k.sum()
    return cv2.filter2D(bgr, -1, k, borderType=cv2.BORDER_REFLECT)


def aerial(bgr, darken=0.0, desat=0.0, cool=0.0):
    """Aerial perspective: with distance, light falls off, colour desaturates
    and the cast goes cooler. All three are things a real room does, which is
    the constraint - it has to keep reading as an unretouched frame."""
    a = bgr.astype(np.float32)
    if darken:
        a *= (1.0 - darken)
    if desat:
        g = a.mean(axis=2, keepdims=True)
        a = a * (1 - desat) + g * desat
    if cool:
        a[:, :, 0] *= (1.0 + cool * 0.5)      # B up
        a[:, :, 2] *= (1.0 - cool * 0.3)      # R down
    return np.clip(a, 0, 255).astype(np.uint8)


def light_wrap(fg_bgr, alpha, bg_bgr, radius=18, amount=0.15):
    """Sample the PLATE and glow it onto the subject's contour.

    Our case is the documented failure Nukepedia calls the '(sl)Edge Hammer'
    problem: a subject shot against a BRIGHT field (the beige courtroom wall
    behind Judge Boyd) dropped onto a darker plate keeps a halo of her ORIGINAL
    background wrapping her - which is exactly what the fringe metric measured
    at 20.06 on the shipped file. The fix is not to erase the halo, it is to
    replace it with the NEW background's light. `_rim()` in make_thumbnail_v5
    could never do this: it adds a CONSTANT brightness off the alpha's own
    edge, so it lifts the contour identically whether the plate behind is a
    dark robe or a white ceiling.

    The craft rule, from the same sources: "you just want to feel the light
    wrap, you don't really wanna see it." Hence a screen blend at 0.42, in a
    band that dies within ~26px of the contour.
    """
    a = alpha.astype(np.float32) / 255.0
    # band just INSIDE the silhouette: blur the OUTSIDE, keep only where we are in
    inv = cv2.GaussianBlur(1.0 - a, (0, 0), radius)
    band = np.clip(inv * a, 0, 1)
    if band.max() > 1e-6:
        band = band / band.max()
    glow = cv2.GaussianBlur(bg_bgr.astype(np.float32), (0, 0), radius)
    f = fg_bgr.astype(np.float32) / 255.0
    g = np.clip(glow / 255.0, 0, 1)
    w = (band * amount)[..., None]
    out = 1.0 - (1.0 - f) * (1.0 - g * w)                 # screen
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


def ground_falloff(bgr, mask, radius=90, drop_C=0.10, amp=10.0):
    """Push the ground AWAY from the subject's own L*, with the SIGN taken from
    the measurement rather than assumed.

    Built the wrong way round first and it made separation WORSE: darkening the
    ground by dL=-6 took dE00_edge DOWN 17.0 -> 14.9, because on this frame the
    subject is already darker than the ground (dL*_edge = -7.2). Brightening
    instead moved it toward the top-tier YouTube median of 21.4 (dL=+10 -> 19.3).
    So the direction is computed here, every time, from this frame's own
    dL*_edge - a fixed 'darken the background' is a coin flip.
    """
    from skimage import color as skcolor
    lab = skcolor.rgb2lab(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0)
    L = lab[:, :, 0]
    hard = (mask > 127).astype(np.uint8)
    if hard.sum() == 0 or (1 - hard).sum() == 0:
        return bgr, 0.0
    din = cv2.distanceTransform(hard, cv2.DIST_L2, 5)
    dout = cv2.distanceTransform(1 - hard, cv2.DIST_L2, 5)
    bi = (din > 2) & (din <= 22)
    bo = (dout > 2) & (dout <= 22)
    dL = float(L[bi].mean() - L[bo].mean()) if bi.any() and bo.any() else 0.0
    amp = abs(amp) if dL < 0 else -abs(amp)   # push the ground the other way
    w = np.clip(1.0 - dout / radius, 0, 1) ** 1.5
    w[hard > 0] = 0
    lab[:, :, 0] = np.clip(lab[:, :, 0] + amp * w, 0, 100)
    lab[:, :, 1] *= (1 - drop_C * w)
    lab[:, :, 2] *= (1 - drop_C * w)
    out = np.clip(skcolor.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_RGB2BGR), dL


def key_falloff(bgr, cx, cy, strength=0.30):
    """One key light in a real room falls off toward the corners. Centred on the
    face rather than the canvas so it reads as light, not as a vignette filter."""
    if strength <= 0:
        return bgr
    h, w = bgr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - cx * w) / (w * 0.80)) ** 2 + ((yy - cy * h) / (h * 0.80)) ** 2)
    m = np.clip(1.0 - strength * np.clip(r - 0.34, 0, None) ** 1.6, 0.0, 1.0)
    return np.clip(bgr.astype(np.float32) * m[..., None], 0, 255).astype(np.uint8)


def highlight_rolloff(bgr, knee=0.80, ceiling=0.985):
    """Soft knee instead of a hard clip. Lifting brightness globally is what
    drove our clipped-highlight fraction to 0.145 against a reference 0.076."""
    y = _ycc(bgr)
    v = y[:, :, 0] / 255.0
    hi = v > knee
    v[hi] = knee + (v[hi] - knee) / (1.0 + (v[hi] - knee) * 6.0)
    y[:, :, 0] = np.clip(v, 0, ceiling) * 255.0
    return _unycc(y)


def saturate(bgr, gain=1.30, knee=0.10):
    """Gain ramped in over the first `knee` of saturation, so a near-neutral
    pixel keeps a gain of ~1.0. The old grade had an ADDITIVE floor (S*g + 0.06)
    applied to every pixel, which took a white ceiling pixel at S~0.01 to 0.074
    - a 7x lift on something that should stay white - and since 4:2:0 chroma
    noise differs block to block, each block landed on a different tint. That is
    the chroma blocking Nathan saw."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    s = hsv[:, :, 1] / 255.0
    ramp = np.clip(s / max(knee, 1e-6), 0, 1)
    hsv[:, :, 1] = np.clip(s * (1.0 + (gain - 1.0) * ramp), 0, 1) * 255.0
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def grain(bgr, sigma=5.2, size=0.48, seed=7):
    """Monochromatic, midtone-weighted grain, ONCE, on the composed frame.

    Target measured on n=24 top-tier YouTube thumbnails: residual sigma 4.40,
    autocorrelation FWHM 1.18px, chroma/luma residual 0.102. Ours measured
    0.775 / 1.90px / 0.48 - a fifth of the amplitude, twice the size, and half
    of it chroma noise rather than grain. Confirmed deliberate rather than
    compression: 8 film one-sheets at native 2000x3000 measure sigma 1.20-11.29
    with FWHM 1.10-1.25px, and in 6 of 8 the sigma-vs-luminance profile PEAKS in
    the midtones - the film-grain signature reproduced by the weighting below.
    """
    rng = np.random.default_rng(seed)
    y = _ycc(bgr)
    h, w = y.shape[:2]
    n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), size)
    n /= max(n.std(), 1e-6)
    t = y[:, :, 0] / 255.0
    n *= np.clip(1.0 - np.abs(t - 0.45) / 0.55, 0.25, 1.0)
    n /= max(n.std(), 1e-6)
    y[:, :, 0] = np.clip(y[:, :, 0] + n * sigma, 0, 255)
    return _unycc(y)


# =============================================================== components
def scrubs_blob(bgr):
    """Find the defendant by his JAIL SCRUBS - as ONE CONNECTED BLOB, not as a
    hue mask.

    Face detection has failed on this docket three times: on CARTHIEF it picked
    the ATTORNEY (who stands nearer the camera than his client) and on ROMERO it
    found no face at all. Every in-custody defendant here wears county scrubs,
    and scrubs are the most saturated large garment in the room.

    But the plain hue mask is not enough, and this is the bug that put the arrow
    on the attorney's face in the first Q4 render: measured on D_4437 the mask
    at S>110 covers 49,402 px spanning the WHOLE tile (x7-619, y0-337), because
    this courtroom's wooden ceiling sits in the same 10-45 deg hue band. Raising
    the saturation floor to 160 and taking the single largest 8-connected
    component isolates the torso exactly: x226-452, y172-338, 25,446 px.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh = hsv[:, :, 0].astype(np.int32) * 2          # OpenCV hue is 0..179
    s_, v_ = hsv[:, :, 1], hsv[:, :, 2]
    orange = (hh > 12) & (hh < 40)
    blue = (hh > 250) & (hh < 330)
    m = ((orange | blue) & (s_ > 160) & (v_ > 80)).astype(np.uint8)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None, m
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return (int(st[i, 0]), int(st[i, 1]), int(st[i, 2]), int(st[i, 3])), (lbl == i).astype(np.uint8)


def defendant_region(plate_bgr, people_alpha):
    """A mask of HIM ONLY, for aiming and for verification - never for cutting.

    The matte returns the two men as ONE component when they touch (measured:
    453x283, a single component on D_4437), and `regroup_plate.py` refuses in
    exactly that case because any split would cut through a body. Nothing is cut
    here: this is his scrubs blob plus the head box directly above it,
    intersected with the people matte, and it exists only so the arrow can be
    proved to point at HIM rather than at his lawyer.
    """
    bb, blob = scrubs_blob(plate_bgr)
    if bb is None:
        return None, None
    sx, sy, sw, sh = bb
    box = np.zeros(plate_bgr.shape[:2], np.uint8)
    y_top = max(0, int(sy - 1.25 * sw))
    cv2.rectangle(box, (max(0, sx - 8), y_top),
                  (min(box.shape[1] - 1, sx + sw + 8), sy + sh), 1, -1)
    box |= blob
    return np.where(box > 0, people_alpha, 0).astype(np.uint8), bb


def people_components(alpha, min_frac=0.012):
    """Keep only components that are actually PEOPLE-sized. Guards against the
    matte's stray specks turning into sharp islands in a defocused room."""
    hard = (alpha > 28).astype(np.uint8)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(hard, 8)
    keep = np.zeros_like(hard)
    total = hard.shape[0] * hard.shape[1]
    comps = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_frac * total:
            keep |= (lbl == i).astype(np.uint8)
            comps.append((i, stats[i]))
    out = np.where(keep > 0, alpha, 0).astype(np.uint8)
    return out, lbl, comps


# ==================================================================== arrow
def arrow_poly(tip_x, tip_y, angle_deg, scale):
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    px, py = -uy, ux
    aw, ah = ARROW_W * scale, ARROW_H * scale
    hl, hw, sw = aw * 0.46, ah * 0.92, ah * 0.38

    def at(b, s):
        return (tip_x - ux * b + px * s, tip_y - uy * b + py * s)
    return [at(0, 0), at(hl, hw / 2), at(hl, sw / 2), at(aw, sw / 2),
            at(aw, -sw / 2), at(hl, -sw / 2), at(hl, -hw / 2)]


def place_arrow(occupied, target_mask, target_pt, scale, exclude_top_px=0,
                min_gap=18, max_gap=260):
    """Satisfy THREE constraints, not just the easy one.

      (a) zero arrow pixels on any person - measured on the shipped Thompson
          thumbnail: 3,822 arrow pixels, ZERO of them on the matte.
      (b) the ray out of the tip must actually REACH the defendant, and
      (c) it must reach him from a real gap: at least `min_gap` px of clear
          space, at most `max_gap`.

    (b) exists because an early auto-placer scored a perfect 0% overlap while
    pointing at nothing - it aimed at a `target_pt` that had drifted into empty
    ceiling, and an overlap test cannot see that. (c) exists because the first
    Q4 render satisfied (a) and (b) with a tip 5px off his hair, which reads as
    the arrow touching him rather than indicating him.

    Directions are tried in Thompson's order: its arrow sits UP AND RIGHT of the
    defendant's head and points back down-left into it, so the search starts at
    -45 deg and spirals outward from there rather than sweeping blindly.
    """
    occ = occupied > 24
    if exclude_top_px > 0:
        occ = occ.copy()
        occ[:exclude_top_px, :] = True
    tx0, ty0 = target_pt
    tgt = target_mask > 24
    degs = sorted(range(-180, 180, 5),
                  key=lambda d: abs(((d + 45 + 180) % 360) - 180))
    for radius in range(80, 520, 8):
        for deg in degs:
            a = math.radians(deg)
            tx = tx0 + radius * math.cos(a)
            ty = ty0 + radius * math.sin(a)
            if not (0.03 * W < tx < 0.97 * W and 0.05 * H < ty < 0.95 * H):
                continue
            point_at = math.degrees(math.atan2(ty0 - ty, tx0 - tx))
            poly = arrow_poly(tx, ty, point_at, scale)
            m = np.zeros((H, W), np.uint8)
            cv2.fillPoly(m, [np.array(poly, np.int32)], 255)
            if ((m > 0) & occ).any():
                continue
            ux = math.cos(math.radians(point_at))
            uy = math.sin(math.radians(point_at))
            hit = 0
            for t in range(2, 600):
                rx, ry = int(tx + ux * t), int(ty + uy * t)
                if not (0 <= rx < W and 0 <= ry < H):
                    break
                if tgt[ry, rx]:
                    hit = t
                    break
            if min_gap <= hit <= max_gap:
                return (tx, ty), point_at, radius, hit
    return None


def draw_arrow(bgr, tip, angle, scale):
    poly = np.array(arrow_poly(tip[0], tip[1], angle, scale), np.int32)
    cv2.fillPoly(bgr, [poly], (ARROW_RED[2], ARROW_RED[1], ARROW_RED[0]),
                 lineType=cv2.LINE_AA)
    cv2.polylines(bgr, [poly], True, (0, 0, 0), max(3, int(round(3 * scale))),
                  lineType=cv2.LINE_AA)
    return poly


# ================================================================== measure
def chroma_flat_dev(bgr, block=16, flat_thresh=3.0):
    """Chroma deviation in FLAT areas - the 'blocky bright background' metric.

    Flatness is decided on a MEDIAN-filtered luma, not the raw luma, so that
    added film grain cannot hide the blocks by making every region look busy.
    Reported as the mean per-block std of Cb and Cr over blocks whose smoothed
    luma std is under `flat_thresh`. Same function is run on the shipped files
    for comparison, so the numbers are directly comparable.
    """
    y = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Ys = cv2.GaussianBlur(cv2.medianBlur(y[:, :, 0].astype(np.uint8), 5).astype(np.float32),
                          (0, 0), 1.0)
    h, w = Ys.shape
    devs = []
    for by in range(0, h - block, block):
        for bx in range(0, w - block, block):
            if Ys[by:by + block, bx:bx + block].std() < flat_thresh:
                cb = y[by:by + block, bx:bx + block, 2]
                cr = y[by:by + block, bx:bx + block, 1]
                devs.append(0.5 * (cb.std() + cr.std()))
    return (float(np.mean(devs)), len(devs)) if devs else (0.0, 0)


def band_s1(bgr):
    Y = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float((cv2.GaussianBlur(Y, (0, 0), 0.5) - cv2.GaussianBlur(Y, (0, 0), 1.0)).std())


def hf_ratio_pair(bgr, fg_mask, bg_mask):
    """Subject sharpness over GROUND sharpness, with the ground named explicitly.

    Reported two ways on purpose. Against ALL non-judge pixels our construction
    can never reach the reference median of 1.65, because our "ground" contains
    two deliberately-sharp people - the reference thumbnails have one hero over
    a room. Against the ROOM only, the number means what the reference number
    means.
    """
    Y = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = np.abs(Y - cv2.GaussianBlur(Y, (0, 0), 2))
    fg, bg = fg_mask > 200, bg_mask > 200
    if not fg.any() or not bg.any():
        return 0.0
    return float(hp[fg].mean() / max(hp[bg].mean(), 1e-6))


def hf_ratio(bgr, mask):
    Y = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = np.abs(Y - cv2.GaussianBlur(Y, (0, 0), 2))
    fg, bg = mask > 200, mask < 40
    if not fg.any() or not bg.any():
        return 0.0
    return float(hp[fg].mean() / max(hp[bg].mean(), 1e-6))


# ============================================================== tone match
#
# TARGETS, measured on the shipped Thompson thumbnail Nathan approved, with the
# `_tone_stats` function below:
#     FULL FRAME    luma mean 124.9   blacks(<26) 9.20%   mean S 85.4
#     PLATE y>0.25  luma mean 116.9   blacks(<26) 7.68%   mean S 93.0
# Measured the same way, for comparison:
#     CARTHIEF (shipped)   105.8 / 14.64% / 123.5
#     Q4 first render       87.5 / 22.53% / 114.1
# So the currently shipped file is already 15% too dark and 45% too saturated
# against our own approved reference, and the first Q4 render was worse again.
# These are not taste knobs - they are a number the reference hits and we did
# not, so they get solved for rather than dialled.
TONE_LUMA = 116.9
TONE_BLACKS = 0.0768
TONE_SAT = 93.0
TONE_ROI = slice(180, 720)          # below the type band, so the type cannot
                                    # bias the statistic it is measured against


def _tone_stats(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[TONE_ROI]
    s = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[TONE_ROI, :, 1]
    return float(g.mean()), float((g < 26).mean()), float(s.mean())


def tone_match(bgr, luma=TONE_LUMA, blacks=TONE_BLACKS, sat=TONE_SAT, seed=11):
    """Solve a lift + gamma so the picture lands on the reference's tone -
    on LUMA ONLY, with chroma rescaled to follow it, in float, with dither.

    The first version applied the gamma to R, G and B in 8-bit. Two measured
    consequences, both visible at 2:1 on the rendered file:

      * SATURATION COLLAPSE. A gamma below 1 compresses the ratio between the
        channels, so lifting the picture desaturates it. Judge Boyd's hair
        measured S 50.1 coming out of the finish chain and S 24.5 in the
        delivered JPEG - the grade had drained half the colour out of it, and
        the global saturation solve then could not tell the difference between
        "her hair is grey" and "the frame is correctly saturated".
      * POSTERISATION. gamma 0.56 on 8-bit data stretches quantisation steps
        into visible plateaus, and her hair is a large smooth gradient with
        almost no real detail at a 176px source face - exactly the material
        that bands. Ablating the finish chain on that same crop ruled it out as
        the cause: plain Lanczos, full chain, and six intermediate variants all
        came back clean, so the banding could only be downstream of them.

    The fix is what a grading application does: transform Y, scale Cb-128 and
    Cr-128 by the same Y'/Y factor so the chroma-to-luma ratio - which is what
    saturation IS - survives the lift, keep the whole thing in float, and add a
    triangular +/- 1 LSB dither at the single 8-bit quantisation at the end.
    """
    y = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Y0 = y[:, :, 0]
    roi = Y0[TONE_ROI]

    def apply(Y, lift, gam):
        return 255.0 * np.power(
            np.clip((Y - lift) / max(1e-3, 255.0 - lift), 0, 1), gam)

    lift, gam = 0.0, 1.0
    for _ in range(4):
        lo, hi = -40.0, 60.0
        for _ in range(20):
            mid = (lo + hi) / 2
            f = (apply(roi, mid, gam) < 26).mean()
            if f > blacks:
                hi = mid
            else:
                lo = mid
        lift = (lo + hi) / 2
        lo, hi = 0.35, 2.2
        for _ in range(20):
            mid = (lo + hi) / 2
            if apply(roi, lift, mid).mean() > luma:
                lo = mid
            else:
                hi = mid
        gam = (lo + hi) / 2

    Yn = apply(Y0, lift, gam)
    ratio = np.clip(Yn / np.maximum(Y0, 4.0), 0.45, 2.6)
    y[:, :, 0] = Yn
    for c in (1, 2):
        y[:, :, c] = 128.0 + (y[:, :, c] - 128.0) * ratio
    rng = np.random.default_rng(seed)
    d = (rng.random(y.shape[:2]) - rng.random(y.shape[:2])).astype(np.float32)
    y[:, :, 0] += d                                  # triangular dither, 1 LSB
    out = cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)

    return out, {"lift": round(lift, 2), "gamma": round(gam, 3)}



# Reference saturation is SELECTIVE, not global - measured, and it overturned
# the first assumption. Over y>0.25H, with the jumpsuit defined as S>150 in the
# 10-50 deg hue band:
#
#     file                 jumpsuit area   S(all)   S(jumpsuit)   S(everything else)
#     Thompson (approved)      16.60%       93.0        241.2           63.5
#     Q4 matched globally      16.70%       93.8        191.0           74.3
#
# The jumpsuit occupies the SAME share of both frames - so the earlier guess
# that our orange was over-represented was simply wrong. What the reference
# actually does is split them: a screaming orange jumpsuit against a nearly
# neutral room. Matching the frame MEAN cannot produce that, and in fact
# produced the opposite - it drained Judge Boyd's hair from S 57 to S 33 while
# leaving the jumpsuit 50 points short of the reference. So the two are solved
# separately, which is what a colourist does with an HSL qualifier.
SAT_JUMP = 241.2
SAT_REST = 63.5


def selective_sat(bgr, jump=SAT_JUMP, rest=SAT_REST):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hh = hsv[:, :, 0] * 2.0
    S = hsv[:, :, 1]
    m = (((S > 150) & (hh > 10) & (hh < 50)).astype(np.float32))
    m = cv2.GaussianBlur(m, (0, 0), 3.0)            # feathered, so no hard edge
    sel_ = m > 0.5
    oth = ~sel_
    if not sel_.any() or not oth.any():
        return bgr, {"g_jump": 1.0, "g_rest": 1.0}

    def solve(mask, target):
        lo, hi = 0.3, 3.0
        for _ in range(18):
            mid = (lo + hi) / 2
            v = np.clip(S / 255.0 * (1.0 + (mid - 1.0)
                        * np.clip(S / 255.0 / 0.10, 0, 1)), 0, 1)[mask].mean() * 255
            if v < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    gj = solve(sel_, jump)
    gr = solve(oth, rest)
    g = gr * (1 - m) + gj * m
    s01 = S / 255.0
    ramp = np.clip(s01 / 0.10, 0, 1)
    hsv[:, :, 1] = np.clip(s01 * (1.0 + (g - 1.0) * ramp), 0, 1) * 255.0
    out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    return out, {"g_jump": round(float(gj), 3), "g_rest": round(float(gr), 3)}


# ==================================================================== build
def font(cap_px):
    return ImageFont.truetype(str(FONTS / "TTTHeadline-Regular.ttf"),
                              round(cap_px / 0.72))


def grab(video, src_t, crop, out, first_frame_src):
    out = Path(out)
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src_t - first_frame_src:.4f}",
                    "-i", str(video), "-frames:v", "1", "-vf", f"crop={crop}",
                    "-y", str(out)], check=True)
    return out


def cached(cache_dir, key, fn):
    """The finish chain costs ~20s per element and layout is what needs
    iterating, so the finished pixels are cached and a layout sweep is seconds."""
    f = Path(cache_dir) / (key + ".npy")
    if f.is_file():
        return np.load(f)
    v = fn()
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, v)
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path,
                    default=ROOT / "work" / "EwwnbiAQtFk"
                    / "EwwnbiAQtFk_h_3574_3554-4697.mp4")
    ap.add_argument("--first-frame-src", type=float, default=3554.0)
    ap.add_argument("--judge-src", type=float, default=4400.0)
    ap.add_argument("--plate-src", type=float, default=4437.0)
    ap.add_argument("--judge-crop", default="612:338:18:190")
    ap.add_argument("--plate-crop", default="620:338:644:190")
    ap.add_argument("--plate-window", default=None,
                    help="x0,w in TILE pixels: a pure crop of the plate tile "
                         "used to place and magnify the two men. Invents nothing "
                         "and moves nobody, unlike regroup_plate.py.")
    ap.add_argument("--plate-anchor", type=float, default=0.35,
                    help="vertical crop anchor, 0=top 1=bottom")
    ap.add_argument("--white", default="You boosted a")
    ap.add_argument("--yellow", default="Challenger?")
    ap.add_argument("--subject-h", type=float, default=0.90)
    ap.add_argument("--bleed", type=int, default=60)
    ap.add_argument("--dof", type=float, default=5.0)
    ap.add_argument("--judge-blend", type=float, default=0.85,
                    help="post-upscale RL blend for the cut-out; her source "
                         "face is only 176px and over-deconvolving it turns "
                         "soft hair strands into hard ribbons")
    ap.add_argument("--judge-sharp", type=float, default=0.55)
    ap.add_argument("--wrap", type=float, default=0.15)
    ap.add_argument("--grain", type=float, default=5.2)
    ap.add_argument("--key", type=float, default=0.16)
    ap.add_argument("--knee", type=float, default=0.80,
                    help="highlight shoulder; lower holds bright skin/hair")
    ap.add_argument("--sat", type=float, default=TONE_SAT,
                    help="target mean S over y>0.25H; reference is 93.0")
    ap.add_argument("--fall", type=float, default=7.0,
                    help="ground falloff amplitude in L*; the SIGN is solved "
                         "from this frame's own dL*_edge, never assumed")
    ap.add_argument("--work", type=Path, default=ROOT / "work" / "q4")
    ap.add_argument("--tag", default="Q4_light")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    a.work.mkdir(parents=True, exist_ok=True)
    cache = a.work / "cache"
    jp = grab(a.video, a.judge_src, a.judge_crop,
              a.work / f"J_{int(a.judge_src)}.png", a.first_frame_src)
    dp = grab(a.video, a.plate_src, a.plate_crop,
              a.work / f"D_{int(a.plate_src)}.png", a.first_frame_src)
    judge = cv2.imread(str(jp))
    plate_full = cv2.imread(str(dp))

    wx0, ww = 0, plate_full.shape[1]
    if a.plate_window:
        wx0, ww = (int(v) for v in a.plate_window.split(","))
    plate = plate_full[:, wx0:wx0 + ww]
    print(f"judge tile {judge.shape[1]}x{judge.shape[0]} @src {a.judge_src}")
    print(f"plate tile {plate.shape[1]}x{plate.shape[0]} @src {a.plate_src} "
          f"(window x{wx0}+{ww} of {plate_full.shape[1]})")

    # ---- mattes at NATIVE resolution ------------------------------------
    jk = f"jfg_{int(a.judge_src)}"
    if not (cache / (jk + ".npy")).is_file():
        fg, al = refined_cutout(judge)
        cache.mkdir(parents=True, exist_ok=True)
        np.save(cache / (jk + ".npy"), fg)
        np.save(cache / (jk + "_a.npy"), al)
    jfg = np.load(cache / (jk + ".npy"))
    jalpha = np.load(cache / (jk + "_a.npy"))
    palpha_raw = cached(cache, f"pa_{int(a.plate_src)}_{wx0}_{ww}",
                        lambda: birefnet_alpha(plate))
    palpha, plbl, pcomps = people_components(palpha_raw)
    print(f"plate matte: {len(pcomps)} person-sized component(s)")

    dmask_tile, sbb = defendant_region(plate, palpha)
    if dmask_tile is None:
        raise SystemExit("no scrubs found - cannot identify the defendant")
    print(f"  defendant isolated for AIMING ONLY: scrubs blob "
          f"x{sbb[0]}-{sbb[0]+sbb[2]} y{sbb[1]}-{sbb[1]+sbb[3]}, "
          f"{int((dmask_tile > 24).sum())}px. Nothing is cut.")

    # ---- geometry: cover the plate to the canvas ------------------------
    ph, pw = plate.shape[:2]
    s = max(W / pw, H / ph)
    cw, ch = int(round(pw * s)), int(round(ph * s))
    ox = (cw - W) // 2
    oy = int(round(a.plate_anchor * (ch - H)))

    def to_canvas(img, interp=cv2.INTER_LANCZOS4):
        return cv2.resize(img, (cw, ch), interpolation=interp)[oy:oy + H, ox:ox + W]

    hk = f"hero_{int(a.plate_src)}_{wx0}_{ww}_{cw}x{ch}"
    gk = f"grnd_{int(a.plate_src)}_{wx0}_{ww}_{cw}x{ch}"
    hero = cached(cache, hk,
                  lambda: finish(plate, (cw, ch), post_blend=0.85, sharp=0.55)[0])
    ground = cached(cache, gk,
                    lambda: finish(plate, (cw, ch), post_blend=0.75, sharp=0.30)[0])
    hero = hero[oy:oy + H, ox:ox + W]
    ground = ground[oy:oy + H, ox:ox + W]
    pm = cv2.GaussianBlur(to_canvas(palpha).astype(np.float32) / 255.0,
                          (0, 0), 1.2)[..., None]

    room = aerial(defocus(ground, a.dof), darken=0.0, desat=0.12, cool=0.05)
    canvas = np.clip(hero.astype(np.float32) * pm
                     + room.astype(np.float32) * (1 - pm), 0, 255).astype(np.uint8)
    print(f"  DOF: room defocused with a disc PSF r={a.dof}; both men kept sharp")

    dmask = to_canvas(dmask_tile, cv2.INTER_LINEAR)
    people_canvas = to_canvas(palpha, cv2.INTER_LINEAR)

    # ---- judge cut-out ---------------------------------------------------
    ys, xs = np.nonzero(jalpha > 12)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cut_src, cut_a = jfg[y0:y1, x0:x1], jalpha[y0:y1, x0:x1]
    th = int(round(a.subject_h * H))
    tw = max(1, int(round(cut_src.shape[1] * th / cut_src.shape[0])))
    ck = f"cut_{int(a.judge_src)}_{tw}x{th}_{a.judge_blend}_{a.judge_sharp}"
    cutf = cached(cache, ck,
                  lambda: finish(cut_src, (tw, th), post_blend=a.judge_blend,
                                 sharp=a.judge_sharp)[0])
    caf = cv2.resize(cut_a, (tw, th), interpolation=cv2.INTER_LANCZOS4)
    cx = W - tw + a.bleed
    xs0, xs1 = max(0, cx), min(W, cx + tw)
    c0 = xs0 - cx
    c1 = c0 + (xs1 - xs0)
    ys0 = H - th
    print(f"  judge bbox {x1 - x0}x{y1 - y0} -> {tw}x{th} at x{cx} "
          f"(covers x{xs0}-{xs1} = {(xs1 - xs0) / W * 100:.0f}% of the width)")

    bg_under = np.zeros_like(cutf)
    bg_under[:, c0:c1] = canvas[ys0:H, xs0:xs1]
    cutf = light_wrap(cutf, caf, bg_under, radius=18, amount=a.wrap)

    af = (caf[:, c0:c1].astype(np.float32) / 255.0)[..., None]
    canvas[ys0:H, xs0:xs1] = (cutf[:, c0:c1] * af
                              + canvas[ys0:H, xs0:xs1] * (1 - af)).astype(np.uint8)
    jmask = np.zeros((H, W), np.uint8)
    jmask[ys0:H, xs0:xs1] = caf[:, c0:c1]

    # ---- separation, then light ------------------------------------------
    canvas, dLe = ground_falloff(canvas, jmask, radius=90, amp=a.fall)
    print(f"  ground falloff: measured dL*_edge {dLe:+.2f} -> ground pushed "
          f"{'brighter' if dLe < 0 else 'darker'} by {a.fall} L*")

    g = cv2.equalizeHist(cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY))
    faces = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        faces += [tuple(int(v) for v in b)
                  for b in cc.detectMultiScale(g, 1.06, 5, minSize=(70, 70))]
    inm = lambda m, b: m[min(H - 1, b[1] + b[3] // 2), min(W - 1, b[0] + b[2] // 2)] > 24
    jf = [b for b in faces if inm(jmask, b)]
    df = [b for b in faces if inm(dmask, b)]
    jface = max(jf, key=lambda b: b[2] * b[3]) if jf else None
    dface = max(df, key=lambda b: b[2] * b[3]) if df else None
    kcx = (jface[0] + jface[2] / 2) / W if jface else 0.74
    kcy = (jface[1] + jface[3] / 2) / H if jface else 0.42
    canvas = key_falloff(canvas, kcx, kcy, a.key)

    before = _tone_stats(canvas)
    canvas, tp = tone_match(canvas)
    canvas, sp = selective_sat(canvas)
    tp.update(sp)
    # Rolloff AFTER the tone solve, not before. Run before it, the gamma lift
    # the solver picks re-expands the very highlights the knee just compressed -
    # which is what blew Judge Boyd's hair to near-white in the C render while
    # her skin stayed dark.
    canvas = highlight_rolloff(canvas, knee=a.knee)
    after = _tone_stats(canvas)
    print(f"  tone: luma {before[0]:.1f}->{after[0]:.1f} (target {TONE_LUMA}), "
          f"blacks {before[1] * 100:.2f}->{after[1] * 100:.2f}% "
          f"(target {TONE_BLACKS * 100:.2f}), S {before[2]:.1f}->{after[2]:.1f} "
          f"(target {a.sat})  via {tp}")

    canvas = grain(canvas, a.grain, 0.48)

    # ---- arrow, AFTER the grade so the red stays exactly #FD0101 ---------
    people = np.maximum(people_canvas, jmask)
    if dface is not None:
        tgt = (dface[0] + dface[2] * 0.5, dface[1] + dface[3] * 0.55)
        print(f"  arrow target = the DEFENDANT's face {dface}, verified inside "
              f"his own matte")
    else:
        ys2, xs2 = np.nonzero(dmask > 24)
        tgt = (float(xs2.mean()),
               float(ys2.min() + 0.12 * (ys2.max() - ys2.min())))
        print(f"  no face inside his matte; aiming at its top mass "
              f"({tgt[0]:.0f},{tgt[1]:.0f})")
    ex = TEXT_TOP + int(round(CAP_PX / 0.72 * 1.04)) + 2 * STROKE
    got = place_arrow(people, dmask, tgt, 1.0, exclude_top_px=ex)
    poly = None
    atx = aty = adeg = arad = ahit = None
    if got is None:
        print("  REFUSING the arrow: no clear placement whose ray reaches him")
    else:
        (atx, aty), adeg, arad, ahit = got
        poly = draw_arrow(canvas, (atx, aty), adeg, 1.0)
        print(f"  arrow tip ({atx / W:.3f},{aty / H:.3f}) {adeg:.0f}deg, "
              f"{arad}px out, ray reaches the defendant {ahit}px along")

    # ---- type LAST -------------------------------------------------------
    img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img)
    f = font(CAP_PX)
    words = ([(w, WHITE) for w in a.white.split()]
             + [(w, YELLOW) for w in a.yellow.split()])
    line = " ".join(w for w, _ in words)
    cap = CAP_PX
    lw = d.textlength(line, font=f)
    while lw > (TEXT_RIGHT - TEXT_X) and cap > 40:
        cap -= 1
        f = font(cap)
        lw = d.textlength(line, font=f)
    if cap != CAP_PX:
        print(f"  !! copy too long for the measured line: cap {CAP_PX} -> {cap}")
    top = TEXT_TOP + STROKE
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).text((TEXT_X, top), line, font=f, fill=255,
                              stroke_width=STROKE, stroke_fill=255)
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0),
              glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS)))
    d = ImageDraw.Draw(img)
    x = TEXT_X
    for wd, col in words:
        d.text((x, top), wd, font=f, fill=col, stroke_width=STROKE,
               stroke_fill=(0, 0, 0))
        x += d.textlength(wd + " ", font=f)
    print(f"  type: 1 line, cap {cap}px ({cap / H:.4f} H), "
          f"x{TEXT_X}->{int(TEXT_X + lw)}, top y{top}")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out, "JPEG", quality=95, subsampling=0)

    final = cv2.imread(str(a.out))
    cdev, nb = chroma_flat_dev(final)
    room_only = (((people_canvas <= 24) & (jmask <= 24)).astype(np.uint8)) * 255
    rep = {
        "tag": a.tag, "size": [final.shape[1], final.shape[0]],
        "judge_src": a.judge_src, "plate_src": a.plate_src,
        "plate_window": [wx0, ww], "plate_anchor": a.plate_anchor,
        "subject_h": a.subject_h, "bleed": a.bleed,
        "judge_covers_pct": round((xs1 - xs0) / W * 100, 1),
        "chroma_flat_dev": round(cdev, 3), "flat_blocks": nb,
        "band_s1": round(band_s1(final), 3),
        "hf_ratio_vs_all": round(hf_ratio(final, jmask), 3),
        "hf_ratio_vs_room": round(hf_ratio_pair(final, jmask, room_only), 3),
        "tone_params": tp,
        "tone_after_luma_blacks_sat": [round(v, 3) for v in _tone_stats(final)],
        "dL_edge": round(dLe, 2), "cap_px": cap, "line_px": int(lw),
        "arrow": (None if got is None else
                  {"tip": [round(atx, 1), round(aty, 1)], "deg": round(adeg, 1),
                   "ray_hit_px": ahit}),
        "faces": {"judge": jface, "defendant": dface},
    }
    (a.work / f"{a.tag}_report.json").write_text(json.dumps(rep, indent=1))
    for n, v in [("jmask", jmask), ("dmask", dmask), ("people", people)]:
        np.save(a.work / f"{a.tag}_{n}.npy", v)
    if poly is not None:
        np.save(a.work / f"{a.tag}_arrowpoly.npy", poly)
    print(json.dumps(rep, indent=1))
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
