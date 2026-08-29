"""Q2_surgical - OUR construction, executed to a much higher standard of craft.

Nathan, 2026-08-29: "fix the thumbnails with the team use ours as reference
just take them to the next level quality and detail wise".

The construction is NOT up for renegotiation and is copied from
`scripts/make_thumbnail_v5.py`, which was measured off the one thumbnail of
ours that has actually shipped (READY-TO-POST/1_LONGFORM_thumbnail.jpg):

    courtroom PLATE carrying the defendant and his attorney, full frame
    JUDGE BOYD matted out of her Zoom tile, bottom-anchored, bleeding off the
      right edge, NO outline stroke on the cut-out
    a red arrow from clear space, pointing at the defendant
    ONE line of type, top-left, white -> yellow, heavy black stroke + soft glow
    graded, and the type burned in AFTER the grade

What is different here is only HOW WELL each of those is executed. Every change
below closes a measured defect, with the measurement named:

 1  SEVERED ARM (shipped CARTHIEF). The old regroup cloned background columns
    over the defendant and cut whatever crossed the scrubs' column range. Two
    changes: (a) the frame is chosen so BiRefNet returns him as his own
    connected component - measured, src 4437 gives a component 2.51x the
    scrubs width because the two men merge, src 4578 gives 1.21x; (b) the hole
    he vacates is filled from a TRUE CLEAN PLATE - a temporal median of 54
    frames taken after the parties leave the podium - rather than by cloning.
    Measured: the camera is static to sub-pixel (phase correlation on the
    ceiling band dx=0.604 dy=-0.046, response 1.056; unoccupied-band absolute
    difference 1.5/255), so those are real observations of that wall, not
    invented pixels. His silhouette is moved WHOLE and its area is checked
    either side of the move.

 2  MATTE EDGE. birefnet-portrait (what ships) -> BiRefNet-matting refined with
    a colour-guided filter and composited against a DECONTAMINATED foreground.
    Measured on judge_3944: contour alignment 2.115 -> 2.219, colour fringe
    20.06 -> ~15.2, matting residual 2.36 -> 1.85, soft hair mass 762 -> ~1030.
    ViTMatte-S scores marginally better still (align 2.271, fringe 14.81) but
    its weights are trained on Adobe's Composition-1k, whose dataset page
    states no licence terms at all - unresolved provenance on a monetised
    channel, so it is NOT used here. The guided filter is our own code.

 3  SOFTNESS. The whole restorative chain moved to the correct side of the
    upscale. Measured on the real judge tile: chroma clean + deblock +
    Richardson-Lucy sigma 0.8 x12 AT NATIVE RESOLUTION puts band_s1 at 6.41
    against a top-tier YouTube target of 6.21 - dead on; the subsequent 2x
    Lanczos then throws 57% of it away (6.41 -> 2.77), which is why the shipped
    build, which upscales first and unsharps last at sigma 2.0, has nothing at
    sigma=1. Second RL pass after the upscale with an anti-ringing clamp, then
    a small-radius output sharpen at sigma 0.7 (RawTherapee's guidance for
    in-focus material is 0.5-0.7; darktable deprecates USM at 2.0 outright).

 4  ARROW. Auto-placed under TWO constraints, not one: zero pixels on any
    person, AND a ray cast from the tip along its own pointing direction must
    actually reach the defendant. The zero-overlap constraint alone once
    scored a perfect 0% while pointing at nothing.

 5  CHROMA BLOCKING. grade_image's fix stays. Its output-resolution chroma
    median and its sigma-2.0 unsharp are switched OFF here because both are now
    done properly at native resolution; the tone curve, saturation knee and
    highlight rolloff - the part Nathan approved - are untouched.

Plus three things the shipped build does not do at all:
    LIGHT WRAP  - the plate's own light glowed onto her contour, in screen
                  mode. `_rim` in v5 is a constant brightness lift and is
                  switched off by default; a constant cannot make her sit in
                  the room's light.
    SEPARATION  - a soft falloff band around the cut-out, SIGNED by the
                  measured dL*_edge, so the ground is pushed away from her
                  lightness rather than always darkened.
    GRAIN       - monochromatic, midtone-weighted, sigma 5.2 at size 0.48.
                  Reference thumbnails carry grain sigma 4.40; ours measures
                  0.775, a 5.7x gap, and ours is coarse chroma blotch rather
                  than fine luma grain.

LICENCES, all fetched not recalled, all clear for a monetised channel:
    BiRefNet (incl. -matting)      MIT, "Copyright (c) 2024 ZhengPeng"
    emrikol/birefnet-matting-onnx  MIT
    pymatting 1.1.15               MIT
    opencv                         Apache-2.0
    numpy / scipy / scikit-image   BSD-3
    TTT Headline                   the project's baked static instance of
                                   Archivo (SIL OFL 1.1) at weight 900 / w70
    rembg is NOT imported here; its default session is bria-rmbg, CC BY-NC 4.0.
    NOT USED, and why: ViTMatte-S (training-data provenance, above);
    CodeFormer (S-Lab 1.0, non-commercial); GFPGAN / RestoreFormer++ / GPEN
    (FFHQ, CC BY-NC-SA 4.0); 4xFaceUpDAT (FaceUp dataset, non-commercial).
    Nothing in this file synthesises detail - it is inverse filtering and
    additive grain only, which matters because the people in frame are real,
    named, and the footage is public record.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import scipy.ndimage as nd
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

W, H = 1280, 720
YELLOW = (254, 251, 3)
WHITE = (255, 255, 255)
ARROW_RED = (253, 1, 1)

# --- geometry, measured off the shipped Thompson thumbnail, not chosen -----
TEXT_X = 23
TEXT_TOP = 31
TEXT_RIGHT = 1072
CAP_PX = 71                 # 0.0986 H, measured on the "Y" of "Your"
STROKE = 11
GLOW_RADIUS = 20
ARROW_W, ARROW_H = 105, 76  # 0.41% of frame
SUBJECT_H = 0.90
SUBJECT_BLEED = 60

FONT = ROOT / "assets" / "fonts" / "TTTHeadline-Regular.ttf"
BIREFNET_MATTING = os.path.expanduser(
    "~/.cache/huggingface/hub/models--emrikol--birefnet-matting-onnx/"
    "snapshots/0d58d809b3a360b44c556223d2f5812aeace9ba3/birefnet-matting.onnx")

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)
_SESS: dict = {}


# ====================================================================== matte
def birefnet_alpha(rgb: np.ndarray, model_path: str = BIREFNET_MATTING) -> np.ndarray:
    """BiRefNet-matting (MIT) run directly on onnxruntime.

    Not through rembg, for two reasons: rembg 2.0.80 does not ship this
    checkpoint at all, and its `new_session` default is `bria-rmbg`
    (CC BY-NC 4.0), which must never be reached by accident on this channel.
    Preprocessing is rembg's own - squash to 1024, ImageNet normalisation,
    min-max renormalisation of the sigmoid - because pad-to-square was measured
    to trade hair mass for colour fringe the wrong way (matting/pad: hair 4914
    fringe 49.75; matting/squash: hair 4189 fringe 39.31).

    Measured against the three BiRefNet models rembg does ship, over 4 judge
    frames: -matting places the contour best AND carries 15% more soft hair
    than -portrait AND has an 11% lower matting-equation residual. -massive is
    the worst of them for hair, not the best: it is a DICHOTOMOUS segmentation
    checkpoint, so a binary edge is its training objective.
    """
    import onnxruntime as ort
    if model_path not in _SESS:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 8
        _SESS[model_path] = ort.InferenceSession(
            model_path, so, providers=["CPUExecutionProvider"])
    sess = _SESS[model_path]
    h, w = rgb.shape[:2]
    x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR)
    x = x.astype(np.float32) / 255.0
    x = ((x - _IMAGENET_MEAN) / _IMAGENET_STD).transpose(2, 0, 1)[None]
    y = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    p = 1.0 / (1.0 + np.exp(-y[:, 0]))
    p = (p - p.min()) / (p.max() - p.min() + 1e-9)
    a = np.squeeze(p)
    return np.clip(cv2.resize(a, (w, h), interpolation=cv2.INTER_LANCZOS4)
                   * 255.0, 0, 255).astype(np.uint8)


def _box(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_filter_color(I: np.ndarray, p: np.ndarray, r: int = 2,
                        eps: float = 1e-4) -> np.ndarray:
    """He, Sun & Tang, Guided Image Filtering (ECCV 2010 / TPAMI 2013), the
    COLOUR-guide variant - the one with the proven link to the matting
    Laplacian. Written out here because cv2.ximgproc.guidedFilter is not
    reachable in this interpreter: pip lists opencv-contrib-python-headless
    5.0.0.93 alongside opencv-python 4.14.0.94, but `import cv2` resolves to
    4.14.0 and dir(cv2.ximgproc) returns zero names.

    r=2, eps=1e-4 is the measured setting. r=8 scores better on the matting
    residual (1.14 vs 1.77) but blows the colour fringe from 20.06 to 50.97 -
    never above r=4.

    The textbook alternatives are a measured NEGATIVE on this material:
    closed-form, KNN and LBDM matting on a trimap all pull the contour OFF the
    image edges here (alignment 2.115 -> 2.089 / 1.782 / 1.665, raggedness
    0.237 -> 0.363 / 0.407 / 0.461) because the matting Laplacian assumes a
    local colour-line model and this is a 612x338 crop of 4:2:0 court Zoom at
    447 kbps - blocky chroma violates that assumption outright.
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
    mb = _box(b, r)
    return np.clip((ma * I).sum(-1) + mb, 0, 1)


def decontaminate(rgb: np.ndarray, alpha_sharp: np.ndarray,
                  soft_sigma: float = 2.0) -> np.ndarray:
    """Estimate the PURE foreground colour, so the beige wall Judge Boyd was
    shot against does not ride along as a halo when she is dropped onto a
    darker plate. That halo is the documented '(sl)Edge Hammer' failure mode
    and it is what the fringe metric reads at 20.06 on the shipped cut-out.

    The important detail, measured: running estimate_foreground_ml on the alpha
    we SHIP makes the fringe 43% WORSE (20.06 -> 28.67). F has to be solved
    from a SOFT alpha and then composited with the SHARP one - decoupling the
    two is what makes decontamination work on this material.
    """
    from pymatting import estimate_foreground_ml
    soft = cv2.GaussianBlur(alpha_sharp.astype(np.float32) / 255.0,
                            (0, 0), soft_sigma)
    I = rgb.astype(np.float64) / 255.0
    F = estimate_foreground_ml(I, np.clip(soft, 0, 1).astype(np.float64))
    return np.clip(F * 255.0, 0, 255).astype(np.uint8)


# ============================================================ surface finish
def _ycc(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)


def _unycc(y):
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def rl_deconv(Y, sigma, iters):
    """Richardson-Lucy with a Gaussian PSF. It recovers detail that IS present
    but smeared; it cannot fabricate. That is the whole reason it is here
    instead of a GAN or diffusion upscaler - on a public-record channel an
    invented eyelash on a named defendant is a factual problem, not an
    aesthetic one."""
    Y = np.clip(Y.astype(np.float32), 1e-3, None)
    est = Y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        est = est * cv2.GaussianBlur(Y / np.maximum(conv, 1e-3), (0, 0), sigma)
        est = np.clip(est, 0, 300)
    return est


def s1_chroma_clean(bgr, r=2):
    """Chroma median at NATIVE resolution. grade_image does radius 5 at
    1280x720, i.e. an 11x11 median on already-upscaled chroma - the same
    artifact removal for far more smearing of real coloured detail."""
    y = _ycc(bgr)
    for c in (1, 2):
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8),
                                    2 * r + 1).astype(np.float32)
    return _unycc(y)


def s2_deblock(bgr, h=3):
    y = _ycc(bgr)
    y[:, :, 0] = cv2.fastNlMeansDenoising(
        y[:, :, 0].astype(np.uint8), None, h, 7, 21).astype(np.float32)
    return _unycc(y)


def s3_deconv(bgr, sigma=0.8, iters=12):
    y = _ycc(bgr)
    y[:, :, 0] = rl_deconv(y[:, :, 0], sigma, iters)
    return _unycc(y)


def s3b_deconv_clamped(bgr, sigma=1.3, iters=16, clamp_r=1, blend=0.85):
    """RL after the upscale, with an anti-ringing clamp.

    Unclamped this is the biggest single win AND visibly wrong: undershoot ran
    to 60.4% of step height on the defendant tile against a reference p90 of
    44.56%, readable as a dark band along the ceiling beam. Clamping into the
    [erode, dilate] of the PRE-deconvolution luma at r=1 returns undershoot to
    44.2% - the same as an untouched Lanczos upscale - while band_s1 still
    rises 2.71 -> 5.32 and the 10-90 edge rise falls 1.29 -> 0.92 px."""
    y = _ycc(bgr)
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, sigma, iters)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1,) * 2)
    Y = np.clip(Y, cv2.erode(Y0, k), cv2.dilate(Y0, k))
    y[:, :, 0] = np.clip(Y0 + (Y - Y0) * blend, 0, 255)
    return _unycc(y)


def s7_output_sharpen(bgr, sigma=0.7, amount=0.55, threshold=2.0):
    """Small-radius output sharpening. RawTherapee's guidance for in-focus,
    low-noise material is radius 0.5-0.7; grade_image uses 2.0, which boosts
    the sigma 2-8 octave - the one octave we are NOT short of - and adds
    nothing at sigma 1."""
    y = _ycc(bgr)
    Y = y[:, :, 0]
    d = Y - cv2.GaussianBlur(Y, (0, 0), sigma)
    d = np.where(np.abs(d) < threshold, 0.0, d)
    y[:, :, 0] = np.clip(Y + amount * d, 0, 255)
    return _unycc(y)


def s6_grain(bgr, sigma=5.2, size=0.48, seed=7):
    """Monochromatic grain, midtone-weighted, at output resolution, ONCE.

    Measured target from n=24 top-tier YouTube thumbnails (plate region only):
    residual sigma median 4.40, autocorrelation FWHM 1.18 px, chroma/luma
    residual ratio 0.102. Ours measures sigma 0.775, FWHM 1.56-1.94 px, chroma
    ratio 0.48-0.57 - five times too little, too big, and half of it chroma
    blotch rather than grain. Film one-sheets at native 2000x3000 confirm the
    midtone weighting: in 6 of 8, sigma-vs-luminance peaks in the midtones and
    falls at both ends."""
    rng = np.random.default_rng(seed)
    y = _ycc(bgr)
    n = rng.standard_normal(y.shape[:2]).astype(np.float32)
    if size > 0:
        n = cv2.GaussianBlur(n, (0, 0), size)
    n /= max(n.std(), 1e-6)
    t = y[:, :, 0] / 255.0
    n *= np.clip(1.0 - np.abs(t - 0.45) / 0.55, 0.25, 1.0)
    n /= max(n.std(), 1e-6)
    y[:, :, 0] = np.clip(y[:, :, 0] + n * sigma, 0, 255)
    return _unycc(y)


def finish(tile_bgr, size, post_sigma, post_iters, blend, sharp, soften=0.0,
           native_iters=12):
    """Every restorative stage at NATIVE resolution first, then the upscale,
    then only what genuinely belongs at output scale. This ordering is the
    single largest measured change in the file: the shipped build resizes
    first (make_thumbnail_v5.py:439) and unsharps last (grade_image), by which
    point 57% of the recovered band_s1 energy is already gone."""
    a = s1_chroma_clean(tile_bgr, 2)
    a = s2_deblock(a, 3)
    if native_iters:
        a = s3_deconv(a, 0.8, native_iters)
    a = cv2.resize(a, size, interpolation=cv2.INTER_LANCZOS4)
    if post_iters:
        a = s3b_deconv_clamped(a, post_sigma, post_iters, 1, blend)
    if sharp:
        a = s7_output_sharpen(a, 0.7, sharp, 2.0)
    if soften > 0:
        # The GROUND, deliberately less acute than the hero. In every top-tier
        # reference the subject is sharper than its ground (hf_fg/hf_bg median
        # 1.65); our shipped files measure 0.365, i.e. the composited hero is
        # the SOFTEST object in frame. That inversion is the mechanical
        # definition of "pasted on".
        a = cv2.GaussianBlur(a, (0, 0), soften)
    return a


# =================================================================== sources
def grab(clip: Path, src_t: float, offset: float, crop: str, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.is_file():
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{src_t - offset:.3f}", "-i", str(clip),
                        "-vf", crop, "-frames:v", "1", str(out)], check=True)
    return cv2.imread(str(out))


def clean_plate(clip: Path, offset: float, crop: str, t0: float, t1: float,
                cache: Path) -> np.ndarray:
    """TRUE clean plate: a temporal median of the tail, after the parties have
    left the podium.

    This is the difference between "surgical" and "slop". The previous regroup
    cloned one background column across the strip the defendant vacated, which
    smears whatever is behind him; every pixel here is a real observation of
    that wall, taken at a different second by the same static camera.
    Registration is measured, not assumed: phase correlation on the ceiling
    band gives dx=0.604 dy=-0.046 at response 1.056, and the mean absolute
    difference in bands neither man occupies is 1.5/255."""
    if cache.is_file():
        return cv2.imread(str(cache))
    frames = []
    tmp = cache.parent / "cp"
    tmp.mkdir(parents=True, exist_ok=True)
    for t in np.arange(t0, t1, 1.0):
        f = grab(clip, float(t), offset, crop, tmp / f"{t:.0f}.png")
        if f is not None:
            frames.append(f)
    st = np.stack(frames).astype(np.float32)
    med = np.median(st, axis=0).astype(np.uint8)
    mad = np.median(np.abs(st - med[None]), axis=(0, 3))
    cv2.imwrite(str(cache), med)
    print(f"  clean plate: median of {len(frames)} frames {t0:.0f}-{t1:.0f}s; "
          f"median abs deviation mean {mad.mean():.2f}, "
          f"{(mad > 12).mean() * 100:.1f}% of pixels unstable")
    return med


# ================================================================== regroup
def scrub_mask(bgr: np.ndarray) -> np.ndarray:
    """Find the defendant by his county scrubs, not by face detection.

    Face detection has failed on this docket three times: on CARTHIEF it picked
    the attorney, who stands nearer the camera than his client, and on ROMERO
    it found no face at all. Scrubs are a property of the subject matter - the
    attorneys wear grey and navy, the room is beige - which is why this holds
    where the classifier did not."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0].astype(np.float32) * 255.0 / 179.0
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    m = (((h > 5) & (h < 32)) | ((h > 125) & (h < 165))) & (s > 110) & (v > 80)
    m[: int(m.shape[0] * 0.20), :] = False
    return m


def regroup(plate: np.ndarray, clean: np.ndarray, max_ratio: float = 1.45,
            gap_keep: int = 2, dbg: Path | None = None):
    """Move the defendant toward his attorney with his whole silhouette intact.

    Nathan, 2026-08-28: "maybe even somehow scoot the defendant closer to his
    attorny?"  and  "it doesnt look good when you have those hard crops like
    you cut the defendants whole arm off in one theres have to be surgical cuts
    not slop".

    Three hard rules, each one a defect that actually shipped:
      * he must come back from the matte as his OWN connected component, or
        this refuses - a merged blob cannot be split without guessing where one
        body ends, which is exactly how his arm came off at the shoulder;
      * how far he moves is bounded by the MINIMUM PER-ROW clearance to the
        attorney, not by their bounding boxes, so no part of him can overlap;
      * the hole is filled from the clean plate, per row, never cloned.
    """
    rgb = cv2.cvtColor(plate, cv2.COLOR_BGR2RGB)
    a = birefnet_alpha(rgb)
    lbl, n = nd.label(a > 28)
    if n == 0:
        raise RuntimeError("empty matte")
    sm = scrub_mask(plate)
    counts = nd.sum(sm, lbl, range(1, n + 1))
    him_id = int(np.argmax(counts)) + 1
    him = lbl == him_id
    ys, xs = np.nonzero(him)
    # The scrubs width has to come from the DENSEST column band, not from the
    # whole saturated mask: this attorney wears an orange-striped tie, which is
    # inside the scrubs hue range and 400px away, and taking the raw bbox made
    # the merged-blob guard read 0.41x instead of 2.51x - i.e. silently off.
    sy, sx = np.nonzero(sm)
    hist, edges = np.histogram(sx, bins=24, range=(0, plate.shape[1]))
    pk = int(np.argmax(hist))
    lo, hi = edges[max(0, pk - 3)], edges[min(len(edges) - 1, pk + 4)]
    sel = (sx >= lo) & (sx <= hi)
    sw = max(1, int(sx[sel].max() - sx[sel].min()))
    ratio = (xs.max() - xs.min()) / sw
    area0 = int(him.sum())
    print(f"  matte: {n} components; defendant = #{him_id} "
          f"x{xs.min()}-{xs.max()} y{ys.min()}-{ys.max()} area={area0}px, "
          f"{ratio:.2f}x the scrubs width")
    if ratio > max_ratio:
        raise RuntimeError(
            f"REFUSING: the defendant's matte component is {ratio:.2f}x the "
            f"scrubs width, i.e. he is merged with another person. Any cut "
            f"would run through a body. Pick a frame where they do not touch.")

    others = np.zeros_like(him)
    for c in range(1, n + 1):
        if c != him_id and (lbl == c).sum() > 8000:
            others |= (lbl == c)

    clearances = []
    for y in range(plate.shape[0]):
        hx = np.nonzero(him[y])[0]
        ox = np.nonzero(others[y])[0]
        if not len(hx) or not len(ox):
            continue
        ox = ox[ox < hx.min()]
        if len(ox):
            clearances.append(int(hx.min() - ox.max()))
    min_clear = min(clearances) if clearances else 999
    shift = max(0, min_clear - gap_keep)
    print(f"  clearance to the attorney: min {min_clear}px over "
          f"{len(clearances)} shared rows -> shift {shift}px left "
          f"(keeping a {gap_keep}px gap)")

    # --- erase him, from REAL background, following his silhouette exactly -
    soft = cv2.GaussianBlur((him * 255).astype(np.uint8), (0, 0), 1.0) / 255.0
    hard = np.clip(soft * 1.6, 0, 1)[..., None]
    base = (clean.astype(np.float32) * hard
            + plate.astype(np.float32) * (1 - hard)).astype(np.uint8)

    # --- put him back, shifted, WHOLE -------------------------------------
    Hh, Ww = plate.shape[:2]
    sa = np.zeros((Hh, Ww), np.float32)
    sr = np.zeros_like(plate)
    if shift > 0:
        sa[:, :Ww - shift] = (him * 255).astype(np.float32)[:, shift:]
        sr[:, :Ww - shift] = plate[:, shift:]
    else:
        sa[:] = (him * 255).astype(np.float32)
        sr[:] = plate
    sa = cv2.GaussianBlur(sa, (0, 0), 0.8) / 255.0
    out = (sr.astype(np.float32) * sa[..., None]
           + base.astype(np.float32) * (1 - sa[..., None])).astype(np.uint8)

    # --- PROVE nothing was cut --------------------------------------------
    #
    # NOT by re-matting the result: once he is 2px from his attorney BiRefNet
    # returns the two of them as ONE component, so a re-matte reports his area
    # as +123% and means nothing. The check that actually answers the question
    # is per-row: his silhouette is a rigid translation, so every row must
    # carry exactly as many of his pixels afterwards as before, and every one
    # of those pixels must survive into the output rather than being painted
    # over by the fill.
    moved = int((sa > 0.5).sum())
    r0 = (him > 0).sum(axis=1)
    r1 = (sa > 0.5).sum(axis=1)
    row_worst = float(np.max(np.abs(r0.astype(int) - r1.astype(int))))
    drawn = int(((sa > 0.5) & (np.abs(out.astype(int)
                                      - base.astype(int)).sum(2) > 2)).sum())
    rep = {"area0": area0, "moved": moved, "drawn": drawn,
           "loss_moved": 100.0 * (area0 - moved) / max(1, area0),
           "loss_drawn": 100.0 * (area0 - drawn) / max(1, area0),
           "row_worst": row_worst,
           "shift": shift, "min_clear": min_clear, "ratio": ratio, "seam": None}
    print(f"  silhouette: {area0}px before -> {moved}px pasted "
          f"({rep['loss_moved']:+.3f}%), {drawn}px actually drawn into the "
          f"output ({rep['loss_drawn']:+.3f}%); worst per-row difference "
          f"{row_worst:.0f}px over {plate.shape[0]} rows")
    if shift > 0:
        s0, s1 = max(0, int(xs.max()) - shift), min(Ww, int(xs.max()) + 3)
        # The right comparison for the fill is the CLEAN PLATE itself, not the
        # column beside it - the column beside it is him.
        a_ = out[:, s0:s1].astype(float)
        b_ = clean[:, s0:s1].astype(float)
        rep["seam"] = float(np.abs(a_ - b_).mean())
        gx = cv2.Sobel(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.CV_32F, 1, 0, 3)
        edge_here = float(np.abs(gx[:, max(0, s1 - 2):s1 + 2]).mean())
        edge_ref = float(np.abs(gx[:, max(0, s0 - 30):s0 - 10]).mean())
        print(f"  vacated strip x{s0}-{s1}: mean |fill - clean plate| = "
              f"{rep['seam']:.2f}/255; vertical gradient at the join "
              f"{edge_here:.1f} vs {edge_ref:.1f} elsewhere "
              f"(a seam shows as a spike here)")
    if dbg:
        cv2.imwrite(str(dbg / "regroup_before.png"), plate)
        cv2.imwrite(str(dbg / "regroup_after.png"), out)
        cv2.imwrite(str(dbg / "regroup_him.png"), (sa * 255).astype(np.uint8))
    return out, rep, (sa * 255).astype(np.uint8)


# ============================================================== compositing
def light_wrap(canvas_bg, fg, alpha, amount=0.38, radius=22.0):
    """The plate's own light, glowed onto the cut-out's contour, in screen mode.

    This is the professional fix for "subject lifted off a differently-lit
    background", and the shipped builder does not do it: `_rim` adds a CONSTANT
    brightness lift derived from FIND_EDGES on the alpha (and its default is
    0.0, i.e. off). A constant cannot make her sit in this room's light. Real
    light wrap samples the BACKGROUND plate's pixels and wraps them onto the
    foreground edge. Kept deliberately low - the craft rule from the same
    sources is "you just want to feel the light wrap, you don't really wanna
    see it"."""
    a = alpha.astype(np.float32) / 255.0
    soft = cv2.GaussianBlur(a, (0, 0), radius)
    band = np.clip(a * (1.0 - soft) * 2.6, 0, 1)[..., None]
    bg = cv2.GaussianBlur(canvas_bg.astype(np.float32) / 255.0, (0, 0), radius)
    f = fg.astype(np.float32) / 255.0
    screen = 1.0 - (1.0 - f) * (1.0 - np.clip(bg * amount, 0, 1))
    return np.clip((f * (1 - band) + screen * band) * 255.0,
                   0, 255).astype(np.uint8)


def separation_falloff(canvas, mask, radius=90, dC=0.10, target=8.0,
                       quiet=False):
    """Push the GROUND away from the subject's own lightness, with the sign
    taken from the measurement rather than fixed.

    Built the wrong way round first: darkening the ground by dL=-6 took
    dE00_edge DOWN 17.0 -> 14.9, because on this frame the subject is already
    darker than the ground (dL*_edge = -7.2). Brightening it instead moved
    17.0 -> 19.3, toward the top-tier reference median of 21.4."""
    from skimage import color as skcolor
    lab = skcolor.rgb2lab(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
                          .astype(np.float64) / 255.0)
    L = lab[:, :, 0]
    hard = (mask > 127).astype(np.uint8)
    din = cv2.distanceTransform(hard, cv2.DIST_L2, 5)
    dout = cv2.distanceTransform(1 - hard, cv2.DIST_L2, 5)
    bi = (din > 2) & (din <= 22)
    bo = (dout > 2) & (dout <= 22)
    if not bi.any() or not bo.any():
        return canvas, 0.0
    dL = float(L[bi].mean() - L[bo].mean())
    push = target if dL < 0 else -target        # away from the subject's L*
    d = cv2.distanceTransform((mask <= 127).astype(np.uint8), cv2.DIST_L2, 5)
    w = np.clip(1.0 - d / radius, 0, 1) ** 1.5
    w[mask > 127] = 0
    lab[:, :, 0] = np.clip(L + push * w, 0, 100)
    lab[:, :, 1] *= (1 - dC * w)
    lab[:, :, 2] *= (1 - dC * w)
    out = np.clip(skcolor.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)
    if not quiet:
        print(f"  separation: dL*_edge measured {dL:+.2f} -> pushing the ground "
              f"{push:+.1f} L* in a {radius}px band around her contour")
    return cv2.cvtColor(out, cv2.COLOR_RGB2BGR), dL


# ==================================================================== arrow
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


def place_arrow(anyone: np.ndarray, target: np.ndarray, head, scale,
                exclude_top: int = 0):
    """Two constraints, because one was not enough.

      (a) ZERO arrow pixels on any person. Measured on the shipped Thompson
          thumbnail: 3,822 arrow pixels, 0 of them on the matte - it sits in
          the gap beside the defendant and points back into him.
      (b) A RAY cast forward from the tip must actually reach the DEFENDANT
          before it reaches anyone else. An earlier auto-placer scored a
          perfect 0% overlap while pointing at empty ceiling, which is worse
          than a hand-placed arrow because it reports success.
    """
    occ = anyone > 24
    if exclude_top > 0:
        occ = occ.copy()
        occ[:exclude_top, :] = True          # the type is drawn later, on top
    tgt = target > 24
    hx, hy = head
    for radius in range(70, 520, 8):
        best = None
        for deg in range(-180, 180, 5):
            a = math.radians(deg)
            tx, ty = hx + radius * math.cos(a), hy + radius * math.sin(a)
            if not (0.03 * W < tx < 0.97 * W and 0.05 * H < ty < 0.95 * H):
                continue
            point_at = math.degrees(math.atan2(hy - ty, hx - tx))
            poly = arrow_poly(tx, ty, point_at, scale)
            m = np.zeros((H, W), np.uint8)
            cv2.fillPoly(m, [np.array(poly, np.int32)], 255)
            if ((m > 0) & occ).any():
                continue
            ux = math.cos(math.radians(point_at))
            uy = math.sin(math.radians(point_at))
            hit, dist = False, 0
            for s in range(2, int(radius * 1.8)):
                px, py = int(tx + ux * s), int(ty + uy * s)
                if not (0 <= px < W and 0 <= py < H):
                    break
                if tgt[py, px]:
                    hit, dist = True, s
                    break
                if occ[py, px]:
                    break
            # Prefer a tip ABOVE him, pointing down into him. That is what
            # the shipped Thompson thumbnail does - its arrow sits at y
            # 166-241 with the tip at its lower-left, coming down out of empty
            # ceiling - and a horizontal arrow squeezed between two people
            # reads as a sticker rather than as a pointer.
            cost = dist + (0 if ty < hy else 120)
            if hit and (best is None or cost < best[0]):
                best = (cost, dist, (tx, ty), point_at)
        if best is not None:
            _, dist, tip, deg = best
            print(f"  arrow: tip {radius}px out from his head at "
                  f"({tip[0]:.0f},{tip[1]:.0f}), pointing {deg:.0f} deg; its "
                  f"ray reaches him after {dist}px of clear space")
            return tip, deg
    return None, None


def draw_arrow(canvas, tip, angle_deg, scale=1.0):
    """Drawn AFTER the grade and the grain, so the red stays exactly #FD0101 -
    the value measured on the shipped Thompson thumbnail. Sized to the measured
    105x76 box (0.41% of frame) rather than to taste: Audit's own 42K flop
    oversized theirs by 67%, so arrow area is a real constraint."""
    poly = np.array(arrow_poly(tip[0], tip[1], angle_deg, scale), np.int32)
    cv2.fillPoly(canvas, [poly], ARROW_RED[::-1], lineType=cv2.LINE_AA)
    cv2.polylines(canvas, [poly], True, (0, 0, 0),
                  max(3, int(round(3 * scale))), lineType=cv2.LINE_AA)
    return canvas


# ===================================================================== build
def build(args) -> Path:
    clip = Path(args.clip)
    dbg = Path(args.work)
    dbg.mkdir(parents=True, exist_ok=True)

    # ---- 1. sources ------------------------------------------------------
    judge_tile = grab(clip, args.judge_t, args.offset, args.judge_crop,
                      dbg / f"J_{args.judge_t:.0f}.png")
    plate_tile = grab(clip, args.plate_t, args.offset, args.plate_crop,
                      dbg / f"D_{args.plate_t:.0f}.png")
    print(f"  judge frame src {args.judge_t:.0f}s "
          f"{judge_tile.shape[1]}x{judge_tile.shape[0]}; "
          f"plate frame src {args.plate_t:.0f}s "
          f"{plate_tile.shape[1]}x{plate_tile.shape[0]}")

    # ---- 2. surgical regroup ---------------------------------------------
    rep = {"shift": 0}
    him_tile = None
    if args.regroup:
        clean = clean_plate(clip, args.offset, args.plate_crop,
                            args.clean_t0, args.clean_t1,
                            dbg / "CLEANPLATE_median.png")
        plate_tile, rep, him_tile = regroup(plate_tile, clean, dbg=dbg)

    # ---- 3. mattes -------------------------------------------------------
    jrgb = cv2.cvtColor(judge_tile, cv2.COLOR_BGR2RGB)
    ja_raw = birefnet_alpha(jrgb)
    I = jrgb.astype(np.float32) / 255.0
    ja = np.clip(guided_filter_color(I, ja_raw.astype(np.float32) / 255.0,
                                     r=2, eps=1e-4) * 255,
                 0, 255).astype(np.uint8)
    jF = decontaminate(jrgb, ja)
    cv2.imwrite(str(dbg / "judge_alpha.png"), ja)

    prgb = cv2.cvtColor(plate_tile, cv2.COLOR_BGR2RGB)
    pa = birefnet_alpha(prgb)
    if him_tile is None:
        lbl, n = nd.label(pa > 28)
        sm = scrub_mask(plate_tile)
        him_tile = ((lbl == int(np.argmax(nd.sum(sm, lbl, range(1, n + 1)))) + 1)
                    * 255).astype(np.uint8)

    # ---- 4. finish each element at NATIVE resolution, then upscale --------
    #
    # THREE depths, not two. Blurring the whole plate softens the defendant,
    # who is the person the arrow points at, and that reads as a mistake rather
    # than as depth: the two men are at the same distance from the camera, so a
    # real lens focused on them would throw only the ROOM soft. So the plate is
    # finished twice and recombined through its own matte. Measured reason: in
    # every top-tier reference the subject is sharper than its ground
    # (hf_fg/hf_bg median 1.65); our shipped files sit at 0.365.
    ph, pw = plate_tile.shape[:2]
    s = max(W / pw, H / ph)
    pts = (max(1, round(pw * s)), max(1, round(ph * s)))
    # Strengths SEEN, not merely measured. A six-panel sweep of the rendered
    # face at 2:1 (work/q2/SWEEP_restore.png, SWEEP_judge.png) shows where the
    # chain stops recovering and starts inventing texture: on the defendant,
    # native-only reads clean at band_s1 2.85 and the full post-upscale pass
    # (blend 0.85 / sharp 0.50) reaches 4.52 but speckles his skin and turns
    # his hair to foil. On the judge the break comes EARLIER, because her face
    # is only 78 real pixels: anything past a light post pass pits the skin
    # around her nose. Metrics alone would have picked the crunchy one.
    room = finish(plate_tile, pts, 1.1, 0, 0.0, 0.0, soften=1.3,
                  native_iters=6)
    men = finish(plate_tile, pts, 1.10, 6, 0.45, 0.26, native_iters=10)
    pa_up = cv2.resize(pa, pts, interpolation=cv2.INTER_LANCZOS4)
    pm = (pa_up.astype(np.float32) / 255.0)[..., None]
    ground = (men * pm + room * (1 - pm)).astype(np.uint8)
    if args.room_push > 0:
        # Aerial perspective on the ROOM only: light and colour both fall off
        # with distance, and the court's flat fluorescent Zoom feed has neither.
        k = args.room_push
        f = ground.astype(np.float32)
        grey = f.mean(axis=2, keepdims=True)
        f = f * (1 - 0.06 * k) * (1 - 0.18 * k) + grey * 0.18 * k
        ground = (f * (1 - pm) + ground * pm).astype(np.uint8)

    # LEFT-anchored, not centred. Centring trims 20px off each side, which
    # clipped the court's own "187th DC" badge to "87th DC" - and that badge is
    # present, whole, in the shipped Thompson thumbnail. The 41px it costs on
    # the right sits behind the judge's cut-out anyway.
    ox, oy = 0, (ground.shape[0] - H) // 2
    canvas = ground[oy:oy + H, ox:ox + W].copy()
    plate_people = pa_up[oy:oy + H, ox:ox + W]
    defendant = cv2.resize(him_tile, pts,
                           interpolation=cv2.INTER_LANCZOS4)[oy:oy + H, ox:ox + W]

    ys, xs = np.nonzero(ja > 12)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    th = int(round(SUBJECT_H * H))
    sc = th / (y1 - y0)
    tw = max(1, int(round((x1 - x0) * sc)))
    cutF = finish(cv2.cvtColor(jF[y0:y1, x0:x1], cv2.COLOR_RGB2BGR),
                  (tw, th), 1.05, 6, 0.42, 0.28, native_iters=12)
    ca = cv2.resize(ja[y0:y1, x0:x1], (tw, th), interpolation=cv2.INTER_LANCZOS4)
    print(f"  judge cut-out {x1 - x0}x{y1 - y0} native -> {tw}x{th} ({sc:.2f}x); "
          f"plate {pw}x{ph} -> {pts[0]}x{pts[1]} ({s:.2f}x)")

    # ---- 4b. SOLVE the bleed so she does not bury him ---------------------
    #
    # The bleed is not a taste knob here. Swapping the matte model moves her
    # bounding box, which moves her whole silhouette, and at the inherited
    # bleed=60 this matte buries the defendant's face behind her shoulder. So
    # it is solved against two hard requirements: his HEAD must be clear of her
    # silhouette, and HER face must stay fully in frame, because pushing her
    # right is what buys his head back.
    dys, dxs = np.nonzero(defendant > 24)
    head_band = np.zeros((H, W), np.uint8)
    if len(dys):
        hy0 = int(dys.min())
        hy1 = int(dys.min() + (dys.max() - dys.min()) * 0.42)
        head_band[hy0:hy1, :] = (defendant[hy0:hy1, :] > 24) * 255
    gj = cv2.equalizeHist(cv2.cvtColor(cutF, cv2.COLOR_BGR2GRAY))
    jf = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    ).detectMultiScale(gj, 1.08, 5, minSize=(120, 120))
    jface_r = int(max([b[0] + b[2] for b in jf], default=int(tw * 0.72)))
    bleed = SUBJECT_BLEED
    for cand in range(SUBJECT_BLEED, args.max_bleed + 1, 10):
        cx_t = W - tw + cand
        if cx_t + jface_r > W - 12:          # her own face would leave the frame
            break
        m = np.zeros((H, W), np.uint8)
        xs0t, xs1t = max(0, cx_t), min(W, cx_t + tw)
        m[H - th:H, xs0t:xs1t] = ca[:, xs0t - cx_t:xs0t - cx_t + (xs1t - xs0t)]
        bleed = cand
        if not ((m > 24) & (head_band > 0)).any():
            break
    cx = W - tw + bleed
    print(f"  bleed solved {SUBJECT_BLEED} -> {bleed}px; her face's right edge "
          f"lands at x{cx + jface_r} of {W}")

    xs0, xs1 = max(0, cx), min(W, cx + tw)
    cx0 = xs0 - cx
    cx1 = cx0 + (xs1 - xs0)
    ys0 = H - th
    region = canvas[ys0:H, xs0:xs1]
    fgw = light_wrap(region, cutF[:, cx0:cx1], ca[:, cx0:cx1],
                     amount=args.wrap, radius=22.0)
    af = (ca[:, cx0:cx1].astype(np.float32) / 255.0)[..., None]
    canvas[ys0:H, xs0:xs1] = (fgw * af + region * (1 - af)).astype(np.uint8)
    jmask = np.zeros((H, W), np.uint8)
    jmask[ys0:H, xs0:xs1] = ca[:, cx0:cx1]
    everyone = np.maximum(plate_people, jmask)
    cv2.imwrite(str(dbg / "composed_raw.png"), canvas)

    # ---- 5a. faces, found ONCE on the UNGRADED composite ------------------
    #
    # Detected here rather than after the grade because the grade solver below
    # is anchored to skin luminance, so it needs the boxes first; and because
    # detecting on the ungraded frame makes the boxes independent of whichever
    # candidate grade is being scored.
    g = cv2.equalizeHist(cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY))
    boxes = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        for b in cc.detectMultiScale(g, 1.08, 5, minSize=(70, 70)):
            boxes.append(tuple(int(v) for v in b))
    left = [b for b in boxes if b[0] + b[2] / 2 < cx]
    right = [b for b in boxes if b[0] + b[2] / 2 >= cx]
    keep = []
    if left:
        keep.append(max(left, key=lambda b: b[2] * b[3]))
    if right:
        keep.append(max(right, key=lambda b: b[2] * b[3]))
    print(f"  {len(boxes)} face(s) found, {len(keep)} protected")
    # The JUDGE's box is the one inside the cut-out. She is the constant across
    # every thumbnail this channel will ever make, so she is what the grade is
    # anchored to; the defendant changes case to case and his skin tone with him.
    jbox = keep[-1] if right and keep else (keep[0] if keep else None)

    def _skin(bgr, box):
        x, y, w, h = box
        core = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[
            y + int(h * .35):y + int(h * .85), x + int(w * .25):x + int(w * .75)]
        return float(np.median(core))

    # ---- 5. grade the PICTURE, ANCHORED TO SKIN --------------------------
    #
    # The previous objective here was |global luminance mean - 118|, and it was
    # wrong in a way that only measuring the finished file exposes. It railed to
    # the corner of its own search box (curve_strength 1.00, brightness 1.16),
    # put the two faces at core-median Y 141 and 158, and STILL left the plate
    # region at mean 77.2 with 23.2% of its pixels below Y=32. Measured, plate
    # region only (y >= 0.45 H), p5/p25/p50/p75/p90/p95:
    #
    #   shipped Thompson (the approved reference)  17 68 101 144 203 216, blk 8.6%
    #   this build under the old objective          5 33  62 115 159 186, blk 23.2%
    #
    # A black floor of 5 against the reference's 17 is a crushed picture, and no
    # amount of midtone brightness fixes it - brightness is the one control that
    # cannot reach either end. Two changes:
    #
    #   * the ANCHOR is skin, not the global mean. The shipped Thompson
    #     thumbnail's own face cores measure 113 (judge) and 116 (defendant) by
    #     the same median-of-core measurement used here, and this composite's
    #     UNGRADED judge core already measures 110 - i.e. the source skin is
    #     already at the reference's finished skin level, so the grade's job on
    #     this frame is contrast and colour, not exposure.
    #   * the CURVE is searched, not just scaled. The shipped control points
    #     (0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97) lift midtones hard and
    #     pull the top DOWN, which is the exact opposite of what a crushed,
    #     dim-highlight frame needs. The search opens the shadow floor and the
    #     three-quarter point instead and holds the midtone near linear.
    from boydclips.thumbnail import grade_image
    base_cfg = {"contrast": args.contrast, "chroma_denoise": False,
                "sharpen_percent": 0, "sat_gain": args.sat}
    # Scored on the FINISHED frame - grade, then separation, then grain - and at
    # half resolution so a 72-point search costs seconds. Measuring the grade's
    # own output lies: the separation falloff darkens a 70px band around a
    # silhouette covering a third of the canvas, and the first version of this
    # solver reported luminance 118.0 for a file that measured 106.0.
    small = cv2.resize(canvas, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    jm_s = cv2.resize(jmask, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST)
    src_s = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    sbox = tuple(int(v / 2) for v in jbox) if jbox else None
    skin_ungraded = _skin(canvas, jbox) if jbox else 0.0
    best = None
    for floor in (0.05, 0.07, 0.09, 0.11):
        for mid in (0.50, 0.53, 0.56):
            for hi in (0.88, 0.92):
                for br in (1.00, 1.02, 1.04):
                    curve = [(0.0, floor), (0.25, (floor + mid) / 2 + 0.025),
                             (0.5, mid), (0.75, hi), (1.0, 0.99)]
                    cfg = {**base_cfg, "curve": curve, "curve_strength": 1.0,
                           "brightness": br}
                    t = cv2.cvtColor(np.asarray(grade_image(src_s, cfg)),
                                     cv2.COLOR_RGB2BGR)
                    t, _ = separation_falloff(t, jm_s, radius=args.sep_radius // 2,
                                              target=args.sep, quiet=True)
                    t = s6_grain(t, sigma=args.grain, size=0.48)
                    Y = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY).astype(np.float32)
                    pl = Y[int(0.45 * Y.shape[0]):, :]
                    blk = float((pl < 32).mean())
                    p5, p95 = (float(v) for v in np.percentile(pl, [5, 95]))
                    skin = (_skin(t, sbox) if sbox else float(np.median(Y)))
                    # TWO anchors, both like-for-like against the reference, and
                    # deliberately NOT the fraction of black pixels. Capping that
                    # fraction is what railed the first version of this search to
                    # a shadow floor of 0.11, which reads as milky grey on a
                    # judicial robe: Thompson has few black pixels (8.6%) because
                    # its content is a bright courtroom, not because its blacks
                    # are lifted - its shadow FLOOR sits at p5 = 17, the same
                    # place a correctly graded picture of our darker frame should
                    # put it. So: skin where the reference's skin is, black floor
                    # where the reference's black floor is, and let the fraction
                    # land where the two navy suits and the robe put it.
                    cost = (abs(skin - args.skin_target)
                            + 0.9 * abs(p5 - args.shadow_target)
                            + 0.15 * max(0.0, 175.0 - p95))
                    if best is None or cost < best[0]:
                        best = (cost, curve, br, skin, blk, p95, p5)
    _, curve, br, skin_s, blk_s, p95_s, p5_s = best
    canvas = cv2.cvtColor(np.asarray(grade_image(
        Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)),
        {**base_cfg, "curve": curve, "curve_strength": 1.0, "brightness": br})),
        cv2.COLOR_RGB2BGR)
    cs = 1.0
    print("  grade solved on SKIN: curve floor %.2f mid %.2f hi %.2f, "
          "brightness %.2f  (grade_image's own chroma median and its sigma-2.0 "
          "unsharp stay OFF - both are done at native resolution now)"
          % (curve[0][1], curve[2][1], curve[3][1], br))
    print(f"    judge face-core Y: {skin_ungraded:.0f} ungraded -> {skin_s:.0f} "
          f"finished, against the shipped Thompson's own 113 (its defendant 116)"
          f"; plate-region shadow floor p5 {p5_s:.0f} (Thompson 17, the "
          f"global-mean objective this replaces 5); blacks {blk_s * 100:.1f}% "
          f"measured not targeted (Thompson 8.6%, shipped CARTHIEF 19.7%, the "
          f"old objective 23.2%); plate p95 {p95_s:.0f} (Thompson 216)")
    if args.out_chroma:
        # A 3x3 chroma median at OUTPUT resolution, after the saturation gain.
        # The native-resolution 5x5 is the real cleanup; this only catches the
        # blue/magenta fringe the gain re-amplifies on her glasses, and at r=1
        # it moves the measured flat-area chroma deviation without touching
        # luma at all.
        y = cv2.cvtColor(canvas, cv2.COLOR_BGR2YCrCb)
        for ch in (1, 2):
            y[:, :, ch] = cv2.medianBlur(y[:, :, ch], 3)
        canvas = cv2.cvtColor(y, cv2.COLOR_YCrCb2BGR)

    # ---- 6. separation, then grain, once, on the composed frame ----------
    canvas, dL = separation_falloff(canvas, jmask, radius=args.sep_radius,
                                    target=args.sep)
    canvas = s6_grain(canvas, sigma=args.grain, size=0.48)

    # ---- 7. faces: what the type may not touch ---------------------------
    #
    # The boxes come from step 5a, detected on the UNGRADED composite. Only the
    # TWO subjects are guarded, not every face in the room: a bystander
    # attorney standing behind the defendant was being protected too, and his
    # box alone shrank the clear band below what one line of type needs.
    #
    # And the FEATURES are guarded, not the whole head. Measured on the shipped
    # Thompson thumbnail: 18.8% of its text pixels sit inside Judge Boyd's raw
    # Haar face box (36% once padded) - its line crosses her hair and forehead
    # and stops above her eyes - so a whole-box rule rejects the exact layout
    # being copied. The guard therefore starts a quarter of the way down the
    # box, which is about the brow line.
    guard = np.zeros((H, W), np.uint8)
    for (fx, fy, fw, fh) in keep:
        pad = int(fw * 0.12)
        cv2.rectangle(guard, (fx - pad, fy + int(fh * 0.25)),
                      (fx + fw + pad, fy + fh + pad), 255, -1)

    # ---- 8. arrow ---------------------------------------------------------
    #
    # Aimed from HIS OWN MATTE COMPONENT, never from a face box. The largest
    # face left of the cut-out is the ATTORNEY - he stands nearer the camera -
    # and the first run of this file duly put a red arrow beside the lawyer's
    # ear while every automated check passed, because the "defendant" mask it
    # was checked against contained both men. The scrubs component cannot make
    # that mistake: it is the defendant by definition.
    arrow_meta = None
    if args.arrow and len(dys):
        rows = np.nonzero((defendant > 24).any(axis=1))[0]
        hy = int(rows.min())
        hrow = np.nonzero(defendant[min(H - 1, hy + 40)] > 24)[0]
        hx = float(hrow.mean()) if len(hrow) else float(dxs.mean())
        head = (hx, hy + 55.0)
        lh_est = int(round(args.cap / 0.72 * 1.04))
        tip, deg = place_arrow(everyone, defendant, head, args.arrow_scale,
                               exclude_top=TEXT_TOP + lh_est + 2 * STROKE)
        if tip is None:
            print("  REFUSING the arrow: no position both clear of every "
                  "person and actually pointing at him")
        else:
            canvas = draw_arrow(canvas, tip, deg, args.arrow_scale)
            arrow_meta = {"tip": [float(tip[0]), float(tip[1])],
                          "deg": float(deg), "scale": float(args.arrow_scale),
                          "head": [float(head[0]), float(head[1])]}

    # ---- 9. type, burned in last -----------------------------------------
    pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    words = [(w, WHITE) for w in args.white.split()]
    words += [(w, YELLOW) for w in args.yellow.split()]
    text = " ".join(w for w, _ in words)
    cap = args.cap
    while cap > 40:
        f = ImageFont.truetype(str(FONT), round(cap / 0.72))
        if d.textlength(text, font=f) <= (TEXT_RIGHT - TEXT_X):
            break
        cap -= 1
    font = ImageFont.truetype(str(FONT), round(cap / 0.72))
    top = TEXT_TOP + STROKE + args.top_adjust

    # Glow, measured rather than chosen. A radius-20 glow at FULL black put
    # 33.4% of the text band into near-black against 18.4% on the shipped
    # Thompson - nearly double. It is a separation aid, not an outline; it
    # should sit under the type, not swallow it.
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).text((TEXT_X, top), text, font=font, fill=255,
                              stroke_width=STROKE, stroke_fill=255)
    g2 = glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS))
    pil.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0),
              g2.point(lambda v: int(v * args.glow)))
    d = ImageDraw.Draw(pil)
    x = TEXT_X
    for wd, col in words:
        d.text((x, top), wd, font=font, fill=col,
               stroke_width=STROKE, stroke_fill=(0, 0, 0))
        x += d.textlength(wd + " ", font=font)
    ink = Image.new("L", (W, H), 0)
    ImageDraw.Draw(ink).text((TEXT_X, top), text, font=font, fill=255,
                             stroke_width=STROKE, stroke_fill=255)
    np.save(str(dbg / "type_ink.npy"), np.asarray(ink))
    yellow_x = TEXT_X + d.textlength(args.white + " ", font=font)
    print(f"  type: 1 line, cap {cap}px ({cap / H:.4f} H), x{TEXT_X}->"
          f"{TEXT_X + d.textlength(text, font=font):.0f}, yellow begins x"
          f"{yellow_x:.0f} ({yellow_x / W:.3f} W)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pil.save(out, "JPEG", quality=95, subsampling=0)
    print(f"  -> {out}  ({out.stat().st_size:,} bytes)")

    np.save(str(dbg / "everyone.npy"), everyone)
    np.save(str(dbg / "guard.npy"), guard)
    np.save(str(dbg / "jmask.npy"), jmask)
    np.save(str(dbg / "defendant.npy"), defendant)

    # The verifier reads THIS, not the builder's own variables. Everything a
    # gate needs to re-measure the file independently: the regroup's before/
    # after silhouette areas, the arrow's exact polygon, the copy, the frames.
    import json as _json
    meta = {
        "out": str(out), "work": str(dbg),
        "clip": str(clip), "offset": args.offset,
        "judge_t": args.judge_t, "plate_t": args.plate_t,
        "judge_crop": args.judge_crop, "plate_crop": args.plate_crop,
        "regroup": bool(args.regroup), "regroup_report": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in rep.items()},
        "arrow": arrow_meta, "cap": int(cap), "top": int(top),
        "white": args.white, "yellow": args.yellow,
        "grade": {"curve": [[float(a_), float(b_)] for a_, b_ in curve],
                  "brightness": float(br), "sat_gain": float(args.sat),
                  "contrast": float(args.contrast),
                  "solver_skin": float(skin_s), "solver_blacks": float(blk_s),
                  "solver_plate_p95": float(p95_s), "solver_plate_p5": float(p5_s),
                  "faces": [list(b) for b in keep],
                  "judge_box": list(jbox) if jbox else None},
        "bleed": int(bleed), "dL_edge": float(dL),
        "grain_sigma": float(args.grain), "wrap": float(args.wrap),
    }
    Path(str(out) + ".meta.json").write_text(_json.dumps(meta, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default=str(
        ROOT / "work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4"))
    ap.add_argument("--offset", type=float, default=3554.0)
    ap.add_argument("--judge-crop", default="crop=612:338:18:190")
    ap.add_argument("--plate-crop", default="crop=620:338:644:190")
    ap.add_argument("--judge-t", type=float, default=3944.0)
    ap.add_argument("--plate-t", type=float, default=4578.0)
    ap.add_argument("--clean-t0", type=float, default=4642.0)
    ap.add_argument("--clean-t1", type=float, default=4696.0)
    ap.add_argument("--regroup", action="store_true", default=True)
    ap.add_argument("--no-regroup", dest="regroup", action="store_false")
    ap.add_argument("--white", default="18 years old and")
    ap.add_argument("--yellow", default="already in jail")
    ap.add_argument("--cap", type=int, default=CAP_PX)
    ap.add_argument("--top-adjust", type=int, default=0)
    ap.add_argument("--glow", type=float, default=0.55)
    ap.add_argument("--grade", type=float, default=1.0)
    ap.add_argument("--contrast", type=float, default=1.06)
    ap.add_argument("--grain", type=float, default=6.6,
                    help="pre-JPEG amplitude; q95 and the flat-area measurement land it near the reference median of 4.40")
    ap.add_argument("--wrap", type=float, default=0.38)
    ap.add_argument("--sep", type=float, default=7.0)
    ap.add_argument("--sep-radius", type=int, default=70)
    ap.add_argument("--arrow", action="store_true", default=True)
    ap.add_argument("--no-arrow", dest="arrow", action="store_false")
    ap.add_argument("--arrow-scale", type=float, default=1.0)
    ap.add_argument("--room-push", type=float, default=0.35,
                    help="aerial perspective on the room behind the people")
    ap.add_argument("--max-bleed", type=int, default=320)
    ap.add_argument("--sat", type=float, default=1.22,
                    help="grade_image sat_gain. 1.45 is the shipped value, but "
                         "our plate already measures MORE saturated than the "
                         "top-tier YouTube set (C*_p95 70.3 vs 47.4) and about "
                         "as saturated as a film one-sheet (73.6)")
    ap.add_argument("--out-chroma", action="store_true", default=True)
    ap.add_argument("--no-out-chroma", dest="out_chroma", action="store_false")
    ap.add_argument("--skin-target", type=float, default=120.0,
                    help="median luminance of the judge's face core in the "
                         "FINISHED frame. The shipped Thompson thumbnail "
                         "measures 113 there (its defendant 116) and this "
                         "composite's ungraded judge core measures 110, so the "
                         "grade is not an exposure control on this material")
    ap.add_argument("--shadow-target", type=float, default=17.0,
                    help="5th-percentile luminance of the PLATE REGION "
                         "(y >= 0.45 H) in the finished frame. Shipped "
                         "Thompson measures 17 there; the global-mean "
                         "objective this replaces left ours at 5")
    ap.add_argument("--work", default=str(ROOT / "work/q2/build"))
    ap.add_argument("--out", required=True)
    build(ap.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
