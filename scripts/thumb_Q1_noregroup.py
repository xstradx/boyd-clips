"""Q1_noregroup - our shipped construction, executed to a far higher standard.

Nathan, 2026-08-29: "fix the thumbnails with the team use ours as reference just
take them to the next level quality and detail wise".

The CONSTRUCTION is unchanged and is the floor:
  courtroom plate carrying the defendant + attorney, Judge Boyd matted out of her
  own Zoom tile and composited over it bottom-anchored bleeding off the right
  edge with no outline stroke, a red arrow pointing at the defendant from clear
  space, one line of type top-left in white with the key phrase in yellow, heavy
  black stroke plus a soft glow, graded, type burned in AFTER the grade.

What is different is HOW each of those is executed.

  1. NO REGROUP.  scripts/regroup_plate.py moves the defendant toward his
     attorney by matting him, cloning background over his old position and
     pasting him back.  On CARTHIEF it amputated his arm, because BiRefNet
     returns ONE connected component when the two men touch and the isolation
     step then cuts through the merged blob.  A severed limb is worse than a
     looser composition, so nobody is moved here.  Tightness comes from FRAME
     CHOICE (source 4578, where the attorney has turned in toward his client and
     their two mattes are 8 px apart in tile pixels) and from a CROP WINDOW,
     which is a pure change of what is included and cannot invent or destroy a
     pixel.  The silhouette-area check in verify_Q1.py therefore reads 0.00%.

  2. SURFACE.  Measured against 24 top-tier YouTube thumbnails, our plate
     carried 6.6x less fine-scale detail and the whole deficit sat at sigma=1px
     - the octave a 2x Lanczos upscale destroys.  The old build upscaled first
     and sharpened last at radius 2.0, i.e. it boosted the one octave we were
     NOT short of.  Here every restorative step happens at NATIVE tile
     resolution, before the upscale, and the post-upscale deconvolution is
     clamped so it cannot ring:

       native : chroma median 5x5 -> NLM luma h=3 -> Richardson-Lucy s0.8 x12
       scale  : Lanczos4
       output : clamped Richardson-Lucy s1.3 x16 -> USM sigma 0.7

     Nothing in that chain invents detail.  It is inverse filtering plus
     additive grain - it recovers or textures, it never fabricates.  That is a
     hard requirement on a public-record channel: an invented eyelash on a named
     defendant is a factual problem, not an aesthetic one.  It is also why no
     GAN/diffusion face restorer is used; and separately every one of them
     (GFPGAN, CodeFormer, RestoreFormer++, GPEN, 4xFaceUpDAT) is either
     non-commercial or trained on FFHQ, which is CC BY-NC-SA 4.0.

  3. MATTE.  BiRefNet-matting (MIT) instead of rembg's birefnet-portrait -
     measured on four judge frames it places the contour as well and carries
     +15% more soft hair mass.  The alpha is then refined with a colour-guided
     filter (He/Sun/Tang, implemented here because cv2.ximgproc is shadowed out
     of this interpreter), and the edge RGB is replaced by a foreground estimate
     taken from a SOFTER alpha - which is what actually kills the colour fringe;
     estimating F from the shipping alpha makes the fringe 43% worse.

  4. LIGHT WRAP.  The tell that a cut-out was pasted on is that it keeps a halo
     of the background it was lifted off.  A real subject standing in the plate
     would catch the plate's light on its contour.  So the plate's own pixels
     are blurred and glowed onto the inside of her edge.  The old _rim() added a
     CONSTANT brightness lift from FIND_EDGES on the alpha, which cannot do this
     - it can only outline her.

  5. GRAIN.  Reference thumbnails carry 5.7x more residual than ours, and ours
     is the wrong size and wrong colour (coarse chroma blotch, not fine
     monochromatic grain).  Synthetic grain is added ONCE on the composed frame:
     monochromatic, midtone-weighted, shaped to a ~1.05 px autocorrelation FWHM.

  6. ORDER.  Arrow and type are both drawn AFTER the grade and after the grain.
     The old build drew the arrow first, so the grade lifted its red and the
     unsharp mask chewed its outline.  Drawn last it lands on the measured
     #FD0101 exactly.

LICENCES, all fetched rather than recalled, because this is a monetised channel:
  BiRefNet / birefnet-matting-onnx  MIT (c) 2024 ZhengPeng
  rembg                             MIT      pymatting 1.1.15  MIT
  opencv-python                     Apache-2.0   numpy/scipy/scikit-image BSD-3
  NOT USED, and why: bria-rmbg (rembg's DEFAULT session) is RMBG-2.0, CC BY-NC
  4.0 - never call rembg.remove() without naming a model.  ViTMatte-S refines
  the edge marginally better than the guided filter (align 2.271 vs 2.219) but
  its weights are trained on Adobe's Composition-1k, whose dataset page states
  no terms at all, so the provenance cannot be closed and it is not shipped.

REPRODUCE, exactly what shipped (3 s warm, the two mattes are cached on disk):

  python scripts/thumb_Q1_noregroup.py       --plate work/q1/P_4578.png --judge work/q1/J_3944.png       --white "18 years old," --yellow "already in jail"       --plate-crop 90,0,620,298 --subject-h 0.88 --bleed 100       --grade 1.25 --sat-gain 1.28 --wrap 0.30 --sep 6.0 --quality 95       --dump work/q1/dump       --out ".../READY-TO-POST/QUALITY/Q1_noregroup.jpg"

  python scripts/verify_Q1_noregroup.py --img <that> --dump work/q1/dump

COPY. The brief offered "18 years old and / already in cuffs". Changed, and the
reason is grep-able rather than editorial: "cuffs" appears nowhere in the case's
transcript and he is not visibly cuffed in any frame of it, so the word would be
a claim the footage does not support. "18 years old" is verbatim - THE COURT:
"how old are you?" / "18 years old, your honor" - and his counsel says on the
record "he's been in jail for uh almost 4 months now, Judge". Both halves are in
work/EwwnbiAQtFk/EwwnbiAQtFk.transcript.json inside the case window, which
verify_Q1_noregroup.py greps on every run. It also fits ONE line at the measured
cap of 71 px: 1,047 px against the reference's 1,049.

FRAME CHOICE, which is a human judgement and is recorded as one. Nathan's rule
is that Judge Boyd's eyes must be level and directed, never cast down; three
automated gaze metrics failed to reproduce it. Source 3944 is the frame he named
- "eyes level, looking at him" - and it is the one used. Source 4578 is his pick
for the defendant, and it is also the frame where the attorney has turned in
toward his client, which is what buys the tight composition WITHOUT moving
anybody.
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
W, H = 1280, 720

YELLOW = (254, 251, 3)
WHITE = (255, 255, 255)
ARROW_RED = (253, 1, 1)

TEXT_X = 23
TEXT_TOP = 31
TEXT_RIGHT = 1072
CAP_PX = 71
STROKE = 11
GLOW_RADIUS = 20
ARROW_W, ARROW_H = 105, 76

MATTING_ONNX = glob.glob(os.path.expanduser(
    "~/.cache/huggingface/hub/models--emrikol--birefnet-matting-onnx/"
    "snapshots/*/birefnet-matting.onnx"))


# --------------------------------------------------------------- matte ----
_SESS = {}
_IMNET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_IMNET_STD = np.array([0.229, 0.224, 0.225], np.float32)


def _session(path: str):
    import onnxruntime as ort
    if path not in _SESS:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 8
        _SESS[path] = ort.InferenceSession(path, so,
                                           providers=["CPUExecutionProvider"])
    return _SESS[path]


CACHE = ROOT / "work" / "q1" / "cache"


def matte_cached(img: Image.Image, tag: str) -> np.ndarray:
    """Same alpha, memoised on disk so composition sweeps are cheap.

    The 940 MB BiRefNet-matting ONNX runs on the CPU at ~20 s a tile; caching it
    is the difference between a 20-second iteration and an 80-second one, and
    the alpha is a pure function of the pixels.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    import hashlib
    h = hashlib.sha1(img.tobytes() + repr(img.size).encode()).hexdigest()[:16]
    p = CACHE / f"{tag}_{h}.png"
    if p.is_file():
        return np.asarray(Image.open(p).convert("L"))
    a = matte(img)
    Image.fromarray(a).save(p)
    return a


def matte(img: Image.Image, model: str | None = None) -> np.ndarray:
    """BiRefNet-matting alpha at the image's own resolution, 0-255 uint8.

    Preprocessing is rembg's exactly (squash to 1024, ImageNet normalisation,
    min-max renormalisation of the sigmoid) so the result stays comparable with
    everything measured before; only the CHECKPOINT differs.  Delivering the
    alpha straight from the raw 1024 prediction instead of round-tripping
    through the tile size was measured to change nothing (ragged 0.225 vs 0.226,
    resid 0.78 either way), so the simple path is kept.
    """
    if model is None:
        if not MATTING_ONNX:
            raise SystemExit("birefnet-matting.onnx not in the HF cache")
        model = MATTING_ONNX[0]
    s = _session(model)
    w, h = img.size
    x = np.asarray(img.convert("RGB").resize((1024, 1024), Image.BILINEAR),
                   np.float32) / 255.0
    x = ((x - _IMNET_MEAN) / _IMNET_STD).transpose(2, 0, 1)[None]
    y = s.run(None, {s.get_inputs()[0].name: x})[0]
    p = 1.0 / (1.0 + np.exp(-y[:, 0]))
    p = (p - p.min()) / (p.max() - p.min() + 1e-9)
    a = Image.fromarray(np.clip(np.squeeze(p) * 255, 0, 255).astype(np.uint8), "L")
    return np.asarray(a.resize((w, h), Image.LANCZOS))


def _box(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_color(I, p, r=2, eps=1e-4):
    """He, Sun & Tang, Guided Image Filtering (ECCV 2010 / TPAMI 2013), colour
    guide - the variant with the proven link to the matting Laplacian.

    cv2.ximgproc.guidedFilter is NOT reachable in this interpreter: pip lists
    both opencv-python 4.14 and opencv-contrib-python-headless 5.0, `import cv2`
    resolves to 4.14 and dir(cv2.ximgproc) returns 0 names.  So it is written
    out.  r>4 was measured to blow the colour fringe up (r=8 -> fringe 50.97
    against 20.06 at baseline), hence the low default.
    """
    I = I.astype(np.float32)
    p = p.astype(np.float32)
    mI = np.stack([_box(I[..., c], r) for c in range(3)], -1)
    mp = _box(p, r)
    mIp = np.stack([_box(I[..., c] * p, r) for c in range(3)], -1)
    cov = mIp - mI * mp[..., None]
    var = np.empty(I.shape[:2] + (3, 3), np.float32)
    for i in range(3):
        for j in range(3):
            var[..., i, j] = _box(I[..., i] * I[..., j], r) - mI[..., i] * mI[..., j]
    var += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(var, cov[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    ma = np.stack([_box(a[..., c], r) for c in range(3)], -1)
    return np.clip((ma * I).sum(-1) + _box(b, r), 0, 1)


def decontaminate(rgb: np.ndarray, alpha: np.ndarray,
                  soft_r: int = 6) -> np.ndarray:
    """Replace the edge RGB with an estimate of the PURE foreground colour.

    Germer et al. 2020, multi-level foreground estimation (pymatting, MIT).
    The subtlety, measured on judge_3944: running it on the alpha we SHIP makes
    the fringe 43% WORSE (20.06 -> 28.67).  F has to be estimated from a SOFTER
    alpha than the one used to composite - the soft alpha tells the solver which
    pixels are mixtures, the sharp one decides what actually gets drawn.
    Closed-form matting was the softener in the research build; a wide guided
    filter is used here instead because pymatting's incomplete Cholesky
    factorisation warns about positive-definiteness on this 4:2:0 material.
    """
    from pymatting import estimate_foreground_ml
    I = rgb.astype(np.float64) / 255.0
    soft = guided_color(I.astype(np.float32),
                        (alpha.astype(np.float32) / 255.0), r=soft_r, eps=4e-4)
    F = estimate_foreground_ml(I, soft.astype(np.float64))
    return np.clip(F * 255.0, 0, 255).astype(np.uint8)


# ------------------------------------------------------------- surface ----
def _ycc(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)


def _unycc(y):
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def rl_deconv(Y, sigma, iters):
    """Richardson-Lucy with a Gaussian PSF.  Recovers detail that IS present but
    smeared by the encoder and the resampler; it cannot fabricate."""
    Y = np.clip(Y.astype(np.float32), 1e-3, None)
    est = Y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        est = est * cv2.GaussianBlur(Y / np.maximum(conv, 1e-3), (0, 0), sigma)
        est = np.clip(est, 0, 300)
    return est


def native_restore(rgb: np.ndarray, chroma_r=2, nlm_h=3,
                   deconv_sigma=0.8, deconv_iters=12, clamp_r=1) -> np.ndarray:
    """Everything that must happen BEFORE the upscale, at native resolution.

    Measured on the real judge tile: this chain puts band_s1 at 6.41 against a
    top-tier YouTube target of 6.21 - dead on.  The subsequent 2x upscale then
    throws 57% of it back away (6.41 -> 2.77), which is exactly why it has to
    happen here, and why the old build (upscale first, sharpen last) could never
    reach the target no matter how hard it sharpened.
    """
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    y = _ycc(bgr)
    for c in (1, 2):
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8),
                                    2 * chroma_r + 1).astype(np.float32)
    y[:, :, 0] = cv2.fastNlMeansDenoising(
        y[:, :, 0].astype(np.uint8), None, nlm_h, 7, 21).astype(np.float32)
    # The SAME anti-ringing clamp the output stage uses, and for the same
    # reason - it was missing here and the ring it left was measurable in the
    # delivered file, not inferred.  Mean edge profile of the plate region,
    # normalised to step height, before and after:
    #
    #     t px     -9    -7    -5    -3    -1     0    +2    +5
    #     unclamped  0.12  0.39 -0.05 -0.43 -0.13  0.59  1.73  1.04
    #     clamped    0.04  0.06 -0.15 -0.32 -0.03  0.59  1.48  1.23
    #
    # i.e. a SECOND, bright halo sat 7 px out on the dark side of every strong
    # edge - a native-resolution ring at ~3 px carried out to 7 px by the 2.4x
    # cover scale.  It drove the 10-90 rise to 9.56 px against a reference band
    # of [0.90 .. 1.86] and overshoot to 73.4% against a p90 of 70.3%.  With the
    # clamp: rise 1.25 px, overshoot 48.9%, undershoot 32.0% - all three inside
    # the band measured over 24 top-tier YouTube thumbnails.  It costs band_s1
    # (3.61 -> 3.30), which is bought back with grain and a lighter room blur.
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, deconv_sigma, deconv_iters)
    if clamp_r:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1,) * 2)
        Y = np.clip(Y, cv2.erode(Y0, k), cv2.dilate(Y0, k))
    y[:, :, 0] = np.clip(Y, 0, 255)
    return cv2.cvtColor(_unycc(y), cv2.COLOR_BGR2RGB)


def output_restore(rgb: np.ndarray, sigma=1.3, iters=16, clamp_r=1,
                   blend=0.85, usm_sigma=0.7, usm_amount=0.55,
                   usm_thresh=2.0) -> np.ndarray:
    """Everything that happens AFTER the upscale.

    Plain RL on a Lanczos-upscaled frame RINGS: undershoot rose to 60.4% of step
    height against a reference 90th percentile of 44.6%, visible as a dark band
    along the ceiling beam before it was ever measured.  Clamping the result
    into the [erode, dilate] of the PRE-deconvolution luma at r=1 removes it
    while keeping the acutance, because real detail never exceeds its own
    neighbourhood extremes.

    The unsharp radius is 0.7, not the 2.0 the old grade used.  RawTherapee's
    guidance for in-focus low-ISO material is 0.5-0.7 and darktable deprecates
    USM outright; radius 2.0 boosts sigma 2-8, the octave we are not short of.
    """
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    y = _ycc(bgr)
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, sigma, iters)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1,) * 2)
    Y = np.clip(Y, cv2.erode(Y0, k), cv2.dilate(Y0, k))
    Y = np.clip(Y0 + (Y - Y0) * blend, 0, 255)
    d = Y - cv2.GaussianBlur(Y, (0, 0), usm_sigma)
    d = np.where(np.abs(d) < usm_thresh, 0.0, d)
    y[:, :, 0] = np.clip(Y + usm_amount * d, 0, 255)
    return cv2.cvtColor(_unycc(y), cv2.COLOR_BGR2RGB)


def add_grain(img: Image.Image, sigma=5.2, size=0.48, seed=7) -> Image.Image:
    """Monochromatic, midtone-weighted grain at output resolution.

    Reference measurement, plate region, n=24 top-tier YouTube thumbnails:
    residual sigma median 4.40 [p10 1.43, p90 7.16], autocorrelation FWHM
    1.18 px, chroma/luma residual 0.102.  Ours before this: sigma 0.775, FWHM
    1.90 px (a blur, not grain), chroma fraction 0.39 - half our residual was
    chroma blotch.  8 film one-sheets at native 2000x3000 show the same
    signature and confirm it is deliberate rather than compression: sigma
    1.20-11.29, FWHM 1.10-1.25, chroma 0.16-0.30, and in 6 of 8 the
    sigma-vs-luminance profile PEAKS in the midtones - which is what the
    weighting below reproduces.
    """
    rng = np.random.default_rng(seed)
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    y = _ycc(bgr)
    h, w = y.shape[:2]
    n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), size)
    n /= max(n.std(), 1e-6)
    t = y[:, :, 0] / 255.0
    n *= np.clip(1.0 - np.abs(t - 0.45) / 0.55, 0.25, 1.0)
    n /= max(n.std(), 1e-6)
    y[:, :, 0] = np.clip(y[:, :, 0] + n * sigma, 0, 255)
    return Image.fromarray(cv2.cvtColor(_unycc(y), cv2.COLOR_BGR2RGB))


def lanczos(rgb: np.ndarray, size) -> np.ndarray:
    return cv2.resize(rgb, size, interpolation=cv2.INTER_LANCZOS4)


# ---------------------------------------------------------- composition ----
def cover_window(img: Image.Image, crop):
    """Crop a window out of the tile, then report the cover scale.

    This is the ONLY thing allowed to change the composition.  It selects what
    is included; it never moves a person relative to another person, so it
    cannot sever a limb, cannot leave a seam and cannot duplicate anybody.
    """
    if crop:
        img = img.crop(crop)
    w, h = img.size
    return img, max(W / w, H / h)


def light_wrap(base: np.ndarray, fg: np.ndarray, alpha: np.ndarray,
               radius: float = 22.0, amount: float = 0.30) -> np.ndarray:
    """Glow the PLATE's own light onto the inside of the cut-out's edge.

    The professional fix for "subject lifted off a differently-lit background",
    and not what the old _rim() did: _rim added a CONSTANT brightness lift built
    from FIND_EDGES on the alpha, so it could only outline her, never make her
    sit in the plate's light.  Real light wrap samples the BACKGROUND and
    screens it onto the foreground contour.  Ours is the documented failure
    mode - she was shot against a bright beige courtroom wall and is dropped
    onto a darker plate, so the original background rides along as a halo.
    Craft rule from the same sources: you want to FEEL the wrap, not see it.
    """
    a = alpha.astype(np.float32) / 255.0
    inner = np.clip(a * (1.0 - cv2.GaussianBlur(a, (0, 0), radius)), 0, 1)
    if inner.max() > 1e-6:
        inner = inner / inner.max()
    b = cv2.GaussianBlur(base.astype(np.float32), (0, 0), radius)
    f = fg.astype(np.float32)
    w = b * (inner * amount)[..., None]
    return np.clip(255.0 - (255.0 - f) * (255.0 - w) / 255.0, 0, 255).astype(np.uint8)


def separate_ground(canvas: np.ndarray, alpha_full: np.ndarray,
                    band_px: float = 90.0, dL: float = 6.0) -> np.ndarray:
    """Push the ground AWAY from the subject's own L* in a soft band.

    Signed by the measurement, not applied as a fixed "darken the background".
    On our frames the subject is DARKER than its ground (dL*_edge median -9.13
    over 4 files) while the reference set runs +8.42, so darkening the ground
    takes dE00_edge DOWN (17.0 -> 14.9).  The caller passes the sign it
    measured; falloff is (1 - d/band)^1.5 in CIELAB.
    """
    from skimage import color as skcolor
    a = alpha_full.astype(np.float32) / 255.0
    inside = (a > 0.5).astype(np.uint8)
    if inside.sum() == 0:
        return canvas
    dist = cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    wgt = np.clip(1.0 - dist / band_px, 0, 1) ** 1.5
    wgt *= (1.0 - a)
    lab = skcolor.rgb2lab(canvas.astype(np.float32) / 255.0)
    lab[:, :, 0] = np.clip(lab[:, :, 0] + dL * wgt, 0, 100)
    return np.clip(skcolor.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)


def dL_edge(canvas: np.ndarray, alpha_full: np.ndarray, band: int = 20) -> float:
    from skimage import color as skcolor
    a = alpha_full > 128
    k = np.ones((2 * band + 1,) * 2, np.uint8)
    inner = a & ~(cv2.erode(a.astype(np.uint8), k) > 0)
    outer = (cv2.dilate(a.astype(np.uint8), k) > 0) & ~a
    if inner.sum() < 200 or outer.sum() < 200:
        return 0.0
    lab = skcolor.rgb2lab(canvas.astype(np.float32) / 255.0)[:, :, 0]
    return float(lab[inner].mean() - lab[outer].mean())


def depth(plate: np.ndarray, people: np.ndarray, blur: float, darken: float,
          desat: float, cool: float) -> np.ndarray:
    """Push the ROOM back while keeping the people in it sharp.

    A real portrait lens focused on the two men throws the room soft, not them.
    Blurring the whole plate softened the very person the arrow points at, which
    reads as a mistake rather than as depth.
    """
    if blur <= 0 and darken <= 0 and desat <= 0 and cool <= 0:
        return plate
    room = plate.astype(np.float32)
    if blur > 0:
        room = cv2.GaussianBlur(room, (0, 0), blur)
    if darken > 0:
        room *= (1.0 - darken)
    if desat > 0:
        g = room.mean(axis=2, keepdims=True)
        room = room * (1.0 - desat) + g * desat
    if cool > 0:
        room[:, :, 2] *= (1.0 + cool * 0.5)
        room[:, :, 0] *= (1.0 - cool * 0.3)
    room = np.clip(room, 0, 255)
    m = (people.astype(np.float32) / 255.0)[..., None]
    return np.clip(room * (1 - m) + plate.astype(np.float32) * m,
                   0, 255).astype(np.uint8)


# -------------------------------------------------------------- arrow ----
def arrow_poly(tip_x, tip_y, angle_deg, scale):
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    px, py = -uy, ux
    aw, ah = ARROW_W * scale, ARROW_H * scale
    head_len, head_w, shaft_w = aw * 0.46, ah * 0.92, ah * 0.38

    def at(back, side):
        return (tip_x - ux * back + px * side, tip_y - uy * back + py * side)

    return [at(0, 0), at(head_len, head_w / 2), at(head_len, shaft_w / 2),
            at(aw, shaft_w / 2), at(aw, -shaft_w / 2),
            at(head_len, -shaft_w / 2), at(head_len, -head_w / 2)]


def ray_hits(tip, angle_deg, target: np.ndarray, max_len: int = 520):
    """March forward from the tip along the arrow's own axis and return the
    distance at which it first enters `target`, or None.

    An earlier auto-placer scored a perfect 0% overlap while pointing at
    NOTHING - zero overlap is only half the constraint.  The arrow has to
    indicate somebody, so the ray is tested explicitly and a placement that
    misses is rejected however clear it is.
    """
    ux = math.cos(math.radians(angle_deg))
    uy = math.sin(math.radians(angle_deg))
    for d in range(4, max_len, 2):
        x, y = int(round(tip[0] + ux * d)), int(round(tip[1] + uy * d))
        if not (0 <= x < W and 0 <= y < H):
            return None
        if target[y, x]:
            return float(d)
    return None


def place_arrow(occupied: np.ndarray, defendant: np.ndarray,
                head, scale: float, exclude_top: float = 0.0,
                gap_min: int = 26, gap_max: int = 180,
                prefer_deg: float = -55.0):
    """First position, walking outward from his head, where the WHOLE arrow
    sits on nobody AND its ray lands on the defendant.

    Three constraints, all measured off the shipped Thompson thumbnail rather
    than chosen:
      * ZERO overlap - its 3,822 arrow pixels touch no person at all.
      * The ray has to actually reach him.  An earlier auto-placer scored a
        perfect 0% overlap while pointing at nothing, because zero overlap is
        only half the job.
      * DIRECTION.  Thompson's arrow sits up-and-right of the defendant's head
        and comes down-left into it.  Without this preference the search takes
        whatever clear space it meets first, which on our composition is the gap
        BETWEEN the two men - so the arrow came in horizontally from the left,
        out of the attorney's side of the frame, which reads as pointing away
        from the story rather than into it.  Candidate bearings are therefore
        tried in order of closeness to the reference bearing.

    `gap_min` keeps the tip off his skin: Thompson's tip stands clear of the
    defendant's head, and a tip 10 px from a cheek reads as a mistake.
    """
    occ = occupied > 24
    if exclude_top > 0:
        occ = occ.copy()
        occ[: int(H * exclude_top), :] = True
    tgt = defendant > 24
    hx, hy = head
    bearings = sorted(range(-180, 180, 5),
                      key=lambda d: abs((d - prefer_deg + 180) % 360 - 180))
    for radius in range(70, 520, 8):
        for deg in bearings:
            a = math.radians(deg)
            tx, ty = hx + radius * math.cos(a), hy + radius * math.sin(a)
            if not (0.03 * W < tx < 0.97 * W and 0.05 * H < ty < 0.95 * H):
                continue
            point_at = math.degrees(math.atan2(hy - ty, hx - tx))
            poly = arrow_poly(tx, ty, point_at, scale)
            m = Image.new("L", (W, H), 0)
            ImageDraw.Draw(m).polygon(poly, fill=255)
            mm = np.asarray(m, np.uint8) > 0
            if (mm & occ).any():
                continue
            d = ray_hits((tx, ty), point_at, tgt)
            if d is None or not (gap_min <= d <= gap_max):
                continue
            return (tx, ty), point_at, radius, d, int(mm.sum())
    return None


def draw_arrow(canvas: Image.Image, tip, angle_deg, scale):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(arrow_poly(tip[0], tip[1], angle_deg, scale),
                                  fill=ARROW_RED + (255,),
                                  outline=(0, 0, 0, 255),
                                  width=max(3, int(round(3 * scale))))
    return Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")


# --------------------------------------------------------------- type ----
def font_for_cap(cap_px: int, path: str | None = None):
    """Solve for the pixel size that gives the MEASURED cap height.

    The face is settled: assets/fonts/TTTHeadline-Regular.ttf, family
    "TTT Headline" - Archivo frozen at weight 900 / width 70.  Identified by
    matching the shipped Thompson thumbnail's 26-character line to 1049px at cap
    71; Montserrat Black gives cap 52 at that width and Archivo SemiCondensed
    SemiBold 68, both far too light.  size = round(cap/0.72) was an
    approximation that actually lands on cap 69, so the size is SOLVED here
    rather than assumed - which is also what makes our line width directly
    comparable with the reference's 1049px.
    """
    p = path or str(FONTS / "TTTHeadline-Regular.ttf")
    size = max(8, round(cap_px / 0.72))
    got = 0
    for _ in range(8):
        f = ImageFont.truetype(p, size)
        im = Image.new("L", (size * 2, size * 3), 0)
        ImageDraw.Draw(im).text((size // 2, size // 2), "Y", font=f, fill=255)
        bb = im.getbbox()
        got = bb[3] - bb[1]
        if got == cap_px:
            return f, size, got
        size += 1 if got < cap_px else -1
    return ImageFont.truetype(p, size), size, got


# --------------------------------------------------------------- build ----
def build(plate_png: Path, judge_png: Path, white_part: str, yellow_part: str,
          out: Path, plate_crop=None, subject_h: float = 0.90, bleed: int = 60,
          cap_px: int = CAP_PX, arrow_scale: float = 1.10, grade_cfg=None,
          bg_blur: float = 1.0, bg_darken: float = 0.10, bg_desat: float = 0.14,
          bg_cool: float = 0.06, wrap_amount: float = 0.30,
          grain_sigma: float = 6.5, sep_dL: float = 6.0,
          arrow_bearing: float = -150.0,
          ground_blend: float = 0.85, ground_usm: float = 0.85,
          hero_blend: float = 0.85, hero_usm: float = 0.85,
          quality: int = 95, dump=None) -> Path:
    say = print
    plate_img = Image.open(plate_png).convert("RGB")
    judge_img = Image.open(judge_png).convert("RGB")
    say(f"  plate {plate_img.size}  judge {judge_img.size}")

    plate_win, s_plate = cover_window(plate_img, plate_crop)
    pa_native = matte_cached(plate_win, 'plate')
    ja_native = matte_cached(judge_img, 'judge')
    say(f"  matte: plate window {plate_win.size} -> cover x{s_plate:.3f}")

    # ---- hero: refine the alpha, then decontaminate the edge RGB --------
    jr = np.asarray(judge_img)
    ja_ref = (guided_color(jr.astype(np.float32) / 255.0,
                           ja_native.astype(np.float32) / 255.0,
                           r=2, eps=1e-4) * 255).astype(np.uint8)
    jF = decontaminate(jr, ja_ref)

    # ---- surface: native first, always ---------------------------------
    jF = native_restore(jF)
    plate_n = native_restore(np.asarray(plate_win))

    # ---- upscale --------------------------------------------------------
    pw, ph = plate_win.size
    tw, th = int(round(pw * s_plate)), int(round(ph * s_plate))
    plate_up = lanczos(plate_n, (tw, th))
    pa_up = np.asarray(Image.fromarray(pa_native).resize((tw, th), Image.LANCZOS))
    ox, oy = (tw - W) // 2, (th - H) // 2
    plate_up = plate_up[oy:oy + H, ox:ox + W]
    pa_up = pa_up[oy:oy + H, ox:ox + W]

    jbb = Image.fromarray(ja_ref).getbbox()
    jF_c = jF[jbb[1]:jbb[3], jbb[0]:jbb[2]]
    ja_c = ja_ref[jbb[1]:jbb[3], jbb[0]:jbb[2]]
    hh = int(H * subject_h)
    hw = max(1, round(jF_c.shape[1] * hh / jF_c.shape[0]))
    j_up = lanczos(jF_c, (hw, hh))
    ja_upc = np.asarray(Image.fromarray(ja_c).resize((hw, hh), Image.LANCZOS))
    say(f"  judge alpha bbox {jbb} -> {hw}x{hh} (subject_h {subject_h}), "
        f"upscale x{hh / (jbb[3]-jbb[1]):.2f}")

    # ---- output-resolution restoration, per element --------------------
    plate_up = output_restore(plate_up, blend=ground_blend,
                              usm_amount=ground_usm)
    j_up = output_restore(j_up, blend=hero_blend, usm_amount=hero_usm)

    # ---- depth: room back, people sharp --------------------------------
    plate_up = depth(plate_up, pa_up, bg_blur, bg_darken, bg_desat, bg_cool)

    # ---- WHO IS WHO, decided on the plate BEFORE she is pasted ---------
    #
    # Found by his JAIL SCRUBS, not by face detection: face detection has picked
    # the attorney on this docket because the lawyer stands nearer the camera,
    # and on ROMERO it found no face at all.  Every in-custody defendant here
    # wears county orange, and orange is the most saturated large garment in a
    # room of grey suits and beige walls - a property of the subject matter
    # rather than of a classifier, which is why it holds where the classifier
    # did not.  Run on the PLATE, because once the cut-out is pasted the judge
    # can be covering most of him and the histogram then locks onto the
    # attorney's tie instead - which is exactly what happened on the first run.
    hsv = cv2.cvtColor(plate_up, cv2.COLOR_RGB2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    scrub = ((hue > 3) & (hue < 20)) & (sat > 110) & (val > 80)
    scrub[: int(H * 0.20), :] = False
    ys, xs = np.where(scrub)
    if len(xs) < 400:
        raise SystemExit("no jail scrubs found in the plate")
    hist, edges = np.histogram(xs, bins=24, range=(0, W))
    pk = int(np.argmax(hist))
    lo, hi = edges[max(0, pk - 3)], edges[min(len(edges) - 1, pk + 4)]
    sel = (xs >= lo) & (xs <= hi)
    sx0, sx1 = int(xs[sel].min()), int(xs[sel].max())
    sy0 = int(ys[sel].min())
    defendant = pa_up.copy()
    defendant[:, :max(0, sx0 - 70)] = 0
    defendant[:, min(W, sx1 + 70):] = 0
    say(f"  defendant located by his scrubs on the plate: "
        f"x{sx0}-{sx1}, top y{sy0}")

    g0 = cv2.equalizeHist(cv2.cvtColor(plate_up, cv2.COLOR_RGB2GRAY))
    plate_faces = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        for b in cc.detectMultiScale(g0, 1.06, 5, minSize=(60, 60)):
            plate_faces.append(tuple(int(v) for v in b))
    head = None
    for b in sorted(plate_faces, key=lambda b: -b[2] * b[3]):
        if sx0 - 60 <= b[0] + b[2] / 2 <= sx1 + 60:
            head = (b[0] + b[2] / 2, b[1] + b[3] * 0.45)
            break
    if head is None:
        head = ((sx0 + sx1) / 2, max(0.10 * H, sy0 - (sx1 - sx0) * 0.30))
    say(f"  plate faces {plate_faces}; aiming at the defendant's head "
        f"({head[0]:.0f}, {head[1]:.0f})")

    # ---- compose --------------------------------------------------------
    cut_x = W - hw + bleed
    cut_y = H - hh
    full_a = np.zeros((H, W), np.uint8)
    x0, x1 = max(0, cut_x), min(W, cut_x + hw)
    y0, y1 = max(0, cut_y), min(H, cut_y + hh)
    sx, sy = x0 - cut_x, y0 - cut_y
    full_a[y0:y1, x0:x1] = ja_upc[sy:sy + (y1 - y0), sx:sx + (x1 - x0)]
    full_f = np.zeros((H, W, 3), np.uint8)
    full_f[y0:y1, x0:x1] = j_up[sy:sy + (y1 - y0), sx:sx + (x1 - x0)]

    # light wrap samples the plate BEFORE she is pasted - the light she would
    # actually be standing in.
    full_f = light_wrap(plate_up, full_f, full_a, radius=22.0, amount=wrap_amount)

    a = (full_a.astype(np.float32) / 255.0)[..., None]
    canvas = np.clip(plate_up.astype(np.float32) * (1 - a) +
                     full_f.astype(np.float32) * a, 0, 255).astype(np.uint8)

    d0 = dL_edge(canvas, full_a)
    # PUSH THE GROUND AWAY FROM THE SUBJECT'S OWN L*, which means the sign is
    # the OPPOSITE of the measured dL*_edge.
    #
    # This was inverted and the inversion was visible in the build log rather
    # than inferred: on this frame dL*_edge measures -4.03 (she is DARKER than
    # the room behind her), the old line then darkened the ground by 6 L* and
    # the log printed "-> +0.02" - separation annihilated, the two brought to
    # the same lightness.  The 2026-08-29 measurement says the same thing:
    # "Darkening the ground by dL=-6 took dE00_edge DOWN 17.0 -> 14.9 ...
    # Brightening it instead: dL=+6 -> 18.1, dL=+10 -> 19.3."
    sign = 1.0 if d0 < 0 else -1.0
    canvas = separate_ground(canvas, full_a, 90.0, sign * sep_dL)
    say(f"  separation: dL*_edge {d0:+.2f}, ground pushed {sign * sep_dL:+.1f} L* "
        f"-> {dL_edge(canvas, full_a):+.2f}")

    img = Image.fromarray(canvas)

    # ---- grade the PICTURE, before any graphic --------------------------
    if grade_cfg is not None:
        sys.path.insert(0, str(ROOT / "src"))
        from boydclips.thumbnail import grade_image
        img = grade_image(img, grade_cfg)
        say("  graded the picture BEFORE the arrow and the type")

    img = add_grain(img, sigma=grain_sigma)
    say(f"  grain: sigma {grain_sigma}, monochromatic, midtone-weighted, once")

    if dump:
        Path(dump).mkdir(parents=True, exist_ok=True)
        Image.fromarray(full_a).save(Path(dump) / "alpha_judge.png")
        Image.fromarray(pa_up).save(Path(dump) / "alpha_plate.png")
        Image.fromarray(defendant).save(Path(dump) / "alpha_defendant.png")
        Image.fromarray(plate_up).save(Path(dump) / "plate_up.png")
        img.save(Path(dump) / "pre_type.png")

    # ---- who is in the frame, for the guards ---------------------------
    people = np.maximum(pa_up, full_a)
    # only the part of him the viewer can actually SEE: a ray that "reaches"
    # him through the judge's shoulder points at nothing.
    visible_def = np.where(full_a > 128, 0, defendant).astype(np.uint8)
    vis_frac = float((visible_def > 128).sum()) / max(1, (defendant > 128).sum())
    say(f"  defendant {100 * vis_frac:.1f}% visible after the cut-out is pasted")

    # ---- faces, for the no-type-over-a-face rule ------------------------
    g = cv2.equalizeHist(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY))
    boxes = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        for b in cc.detectMultiScale(g, 1.06, 5, minSize=(70, 70)):
            boxes.append(tuple(int(v) for v in b))
    left = [b for b in boxes if b[0] + b[2] / 2 < cut_x]
    right = [b for b in boxes if b[0] + b[2] / 2 >= cut_x]
    keep = []
    if left:
        keep.append(max(left, key=lambda b: b[2] * b[3]))
    if right:
        keep.append(max(right, key=lambda b: b[2] * b[3]))
    say(f"  {len(boxes)} face(s) found, {len(keep)} protected: {keep}")

    # ---- type: ONE line, solved for the measured cap -------------------
    font, size, got_cap = font_for_cap(cap_px)
    d = ImageDraw.Draw(img)
    line = (white_part + " " + yellow_part).strip()
    wpx = d.textlength(line, font=font)
    say(f"  type: cap {got_cap}px at size {size}px, line {wpx:.0f}px "
        f"(reference 1049px), {len(line)} chars, ONE line")
    if wpx > (TEXT_RIGHT - TEXT_X):
        raise SystemExit(f"copy measures {wpx:.0f}px against the measured "
                         f"{TEXT_RIGHT - TEXT_X}px one-line box - shorten it, "
                         "do not wrap it")
    lh = round(size * 1.04)
    top = TEXT_TOP + STROKE
    block = (TEXT_X - STROKE, TEXT_TOP,
             TEXT_X + int(wpx) + STROKE, TEXT_TOP + lh + 2 * STROKE)

    # No type over a FACE.  The guarded region starts a quarter of the way down
    # the detected box, roughly the brow line: the shipped Thompson thumbnail's
    # own line crosses the top of Judge Boyd's hair and forehead, so a
    # whole-head rule would reject the very layout being copied.
    for (fx, fy, fw, fh) in keep:
        pad = int(fw * 0.12)
        r = (fx - pad, fy + int(fh * 0.25), fx + fw + pad, fy + fh + pad)
        if not (block[2] <= r[0] or block[0] >= r[2] or
                block[3] <= r[1] or block[1] >= r[3]):
            raise SystemExit(f"the type box {block} would touch a face {r}")

    # ---- arrow, after the grade so its red is exactly #FD0101 ----------
    got = place_arrow(people, visible_def, head, arrow_scale,
                      exclude_top=(block[3] + 6) / H, prefer_deg=arrow_bearing)
    if got is None:
        say("  REFUSING the arrow: nowhere clear that also points at him")
    else:
        tip, deg, rad, ray, npx = got
        img = draw_arrow(img, tip, deg, arrow_scale)
        say(f"  arrow: tip ({tip[0] / W:.3f}, {tip[1] / H:.3f}), {deg:.0f} deg, "
            f"{rad}px out, ray reaches him at {ray:.0f}px, {npx}px drawn "
            f"({100 * npx / (W * H):.2f}% of frame; reference 0.41%)")

    # ---- glow, then type, last -----------------------------------------
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).text((TEXT_X, top), line, font=font, fill=255,
                              stroke_width=STROKE, stroke_fill=255)
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0),
              glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS)))
    d = ImageDraw.Draw(img)
    x = float(TEXT_X)
    for word in white_part.split():
        d.text((x, top), word, font=font, fill=WHITE,
               stroke_width=STROKE, stroke_fill=(0, 0, 0))
        x += d.textlength(word + " ", font=font)
    yellow_x = x
    for word in yellow_part.split():
        d.text((x, top), word, font=font, fill=YELLOW,
               stroke_width=STROKE, stroke_fill=(0, 0, 0))
        x += d.textlength(word + " ", font=font)
    say(f"  white x{TEXT_X}-{yellow_x:.0f}, yellow begins x{yellow_x:.0f} "
        f"= {yellow_x / W:.3f} W (reference 0.466)")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=quality, subsampling=0)
    say(f"  wrote {out} - {out.stat().st_size} bytes, q{quality} 4:4:4")

    # A machine-readable record of every geometric decision, so verify_Q1.py can
    # re-derive the same canvas independently instead of taking this script's
    # word for anything.
    import json
    meta = dict(plate=str(plate_png), judge=str(judge_png),
                plate_crop=list(plate_crop) if plate_crop else None,
                cover_scale=s_plate, subject_h=subject_h, bleed=bleed,
                cut_x=cut_x, cut_y=cut_y, judge_bbox=list(jbb),
                judge_size=[hw, hh], white=white_part, yellow=yellow_part,
                cap_px=got_cap, font_size=size, line_px=float(wpx),
                text_block=list(block), text_top=top,
                yellow_x=float(yellow_x),
                scrubs=[sx0, sx1, sy0], head=[float(head[0]), float(head[1])],
                defendant_visible_pct=100 * vis_frac,
                faces_protected=[list(b) for b in keep],
                arrow=(None if got is None else
                       dict(tip=[float(got[0][0]), float(got[0][1])],
                            deg=float(got[1]), radius=got[2], ray_px=got[3],
                            pixels=got[4])),
                grade=grade_cfg, grain_sigma=grain_sigma,
                wrap=wrap_amount, sep_dL=sign * sep_dL, quality=quality,
                regroup=False, scoot_tile_px=0)
    Path(str(out) + ".meta.json").write_text(json.dumps(meta, indent=1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", required=True, type=Path)
    ap.add_argument("--judge", required=True, type=Path)
    ap.add_argument("--white", required=True)
    ap.add_argument("--yellow", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--plate-crop", default=None, help="x0,y0,x1,y1 in tile px")
    ap.add_argument("--subject-h", type=float, default=0.90)
    ap.add_argument("--bleed", type=int, default=60)
    ap.add_argument("--cap", type=int, default=CAP_PX)
    ap.add_argument("--arrow-scale", type=float, default=1.10,
                    help="1.10, not 1.0, because the reference was re-measured "
                         "with the SAME test the verifier uses. The brief's "
                         "3,822 arrow pixels came from a looser red test; "
                         "counting |R-253|<14 & G<60 & B<60 on the shipped "
                         "Thompson JPEG gives 3,386 px = 0.37%% of frame. At "
                         "scale 1.0 ours delivers 2,683 (0.29%%); at 1.10 it "
                         "delivers 3,344 (0.36%%) - the reference size")
    ap.add_argument("--arrow-bearing", type=float, default=-150.0,
                    help="preferred bearing of the TIP from his head; -150 puts it up-left so the arrow descends into him, mirroring Thompson")
    ap.add_argument("--grade", type=float, default=1.15)
    ap.add_argument("--contrast", type=float, default=1.06)
    ap.add_argument("--sat-gain", type=float, default=1.45)
    ap.add_argument("--bg-blur", type=float, default=1.0)
    ap.add_argument("--bg-darken", type=float, default=0.10)
    ap.add_argument("--bg-desat", type=float, default=0.14)
    ap.add_argument("--bg-cool", type=float, default=0.06)
    ap.add_argument("--wrap", type=float, default=0.30)
    ap.add_argument("--ground-blend", type=float, default=0.85)
    ap.add_argument("--ground-usm", type=float, default=0.85)
    ap.add_argument("--hero-blend", type=float, default=0.85)
    ap.add_argument("--hero-usm", type=float, default=0.85)
    ap.add_argument("--grain", type=float, default=6.5)
    ap.add_argument("--sep", type=float, default=6.0)
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--dump", default=None)
    a = ap.parse_args()
    crop = tuple(int(v) for v in a.plate_crop.split(",")) if a.plate_crop else None
    build(a.plate, a.judge, a.white, a.yellow, a.out, plate_crop=crop,
          subject_h=a.subject_h, bleed=a.bleed, cap_px=a.cap,
          arrow_scale=a.arrow_scale, bg_blur=a.bg_blur, bg_darken=a.bg_darken,
          bg_desat=a.bg_desat, bg_cool=a.bg_cool, wrap_amount=a.wrap,
          grain_sigma=a.grain, sep_dL=a.sep, arrow_bearing=a.arrow_bearing,
          ground_blend=a.ground_blend, ground_usm=a.ground_usm,
          hero_blend=a.hero_blend, hero_usm=a.hero_usm,
          quality=a.quality, dump=a.dump,
          grade_cfg={"curve_strength": a.grade, "contrast": a.contrast,
                     "sat_gain": a.sat_gain,
                     # the output-resolution chroma median and the radius-2.0
                     # unsharp in grade_image are both replaced by native-
                     # resolution stages above; leaving them on double-treats
                     # the frame and re-softens what was just recovered.
                     "chroma_denoise": False, "sharpen_percent": 0})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
