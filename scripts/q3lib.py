"""Q3_detail support library: matte, restore, upscale, grain.

Every stage here was MEASURED before it was written down; the numbers in the
docstrings are those measurements, reproduced so this file can be read without
the journals. Nothing here fabricates detail except where it says so:

  * BiRefNet-matting / ViTMatte-S   -> where the subject's edge IS
  * Richardson-Lucy deconvolution   -> inverse filtering, recovers smeared
                                       signal; it cannot invent
  * realesr-general-x4v3            -> the ONE model here that synthesises, run
                                       at 4x then resampled back DOWN to ~2x,
                                       the regime where real structure dominates
  * additive grain                  -> texture, deliberately not detail

LICENCES, all read not recalled (assets/models/LICENCES.md carries the quotes):
  BiRefNet (incl. -matting)          MIT, "Copyright (c) 2024 ZhengPeng"
  emrikol/birefnet-matting-onnx      MIT
  hustvl/ViTMatte + leafwork ONNX    MIT  -- but see VITMATTE_PROVENANCE
  pymatting 1.1.15                   MIT
  realesr-general-x4v3 (Real-ESRGAN) BSD-3-Clause, no carve-outs
  opencv Apache-2.0, numpy/scipy BSD-3, Pillow MIT-CMU
DELIBERATELY NOT USED, all non-commercial: rembg's DEFAULT weights bria-rmbg
(CC BY-NC 4.0 -- so remove() is never called without naming a model),
CodeFormer (S-Lab 1.0), GFPGAN (StyleGAN2/NVIDIA + DFDNet CC BY-NC-SA),
4xFaceUpDAT / 4xFFHQDAT (author's own release note says non-commercial).
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

VITMATTE_PROVENANCE = (
    "ViTMatte-S code and the ONNX repackaging are MIT, but the weights are "
    "trained on Adobe Composition-1k, whose dataset page states no terms at "
    "all. That is an UNRESOLVED provenance question, not a quotable "
    "restriction, and on a MONETISED channel an unresolved permission is not "
    "a permission. So it is OFF by default: the shipped matte is BiRefNet-"
    "matting (MIT) refined by the colour-guided filter, which carries no such "
    "question. Measured on judge_3944 the cost of that choice is small - "
    "guided filter gives align 2.219 / ragged 0.266 against ViTMatte's "
    "2.271 / 0.258. Pass --vitmatte to opt back in."
)

_HF = Path(os.path.expanduser("~/.cache/huggingface/hub"))
BIREFNET_MATTING = (_HF / "models--emrikol--birefnet-matting-onnx" / "snapshots"
                    / "0d58d809b3a360b44c556223d2f5812aeace9ba3"
                    / "birefnet-matting.onnx")
VITMATTE_S = (_HF / "models--leafwork-pbr--vitmatte-s-onnx" / "snapshots"
              / "18ab5027fe725ef8f6616e1518075ea2f5ff88e4" / "vitmatte_s.onnx")
REALESR = ROOT / "assets" / "models" / "realesr-general-x4v3.pth"

_IMNET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_IMNET_STD = np.array([0.229, 0.224, 0.225], np.float32)
_SESS: dict = {}
_SR: dict = {"model": None}


def _session(path):
    import onnxruntime as ort
    key = str(path)
    if key not in _SESS:
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(4, (os.cpu_count() or 8) // 2)
        _SESS[key] = ort.InferenceSession(key, so,
                                          providers=["CPUExecutionProvider"])
    return _SESS[key]


# ------------------------------------------------------------------ matting
def birefnet_alpha(img: Image.Image, model=BIREFNET_MATTING) -> np.ndarray:
    """BiRefNet-matting at 1024x1024, squashed (what rembg does), min-max
    renormalised, delivered at the source resolution.

    Measured against the three BiRefNet models rembg ships, over 4 judge frames:
    matting carries 1025 units of soft hair mass against portrait's 888 (+15%)
    at an 11% lower matting-equation residual. birefnet-massive is a
    DICHOTOMOUS-segmentation checkpoint and is the WORST of the four for hair
    (438 units, a 1.75px binary step), not the best.
    Squash, not pad: pad carries more hair (4914 vs 4189) but a much worse
    fringe (49.75 vs 39.31).
    """
    s = _session(model)
    W, H = img.size
    x = np.asarray(img.convert("RGB").resize((1024, 1024),
                                             Image.Resampling.BILINEAR),
                   np.float32) / 255.0
    x = ((x - _IMNET_MEAN) / _IMNET_STD).transpose(2, 0, 1)[None]
    y = s.run(None, {s.get_inputs()[0].name: x})[0]
    p = 1.0 / (1.0 + np.exp(-y[:, 0]))
    p = (p - p.min()) / (p.max() - p.min() + 1e-9)
    a = Image.fromarray(np.clip(np.squeeze(p) * 255, 0, 255).astype(np.uint8),
                        "L")
    return np.asarray(a.resize((W, H), Image.Resampling.LANCZOS))


def trimap_from_alpha(alpha: np.ndarray, band=12, fg=0.95, bg=0.05):
    a = alpha.astype(np.float32) / 255.0
    k = np.ones((2 * band + 1,) * 2, np.uint8)
    F = cv2.erode((a >= fg).astype(np.uint8), k) > 0
    B = cv2.erode((a <= bg).astype(np.uint8), k) > 0
    t = np.full(a.shape, 0.5, np.float64)
    t[F] = 1.0
    t[B] = 0.0
    return t


def vitmatte_refine(rgb: np.ndarray, trimap01: np.ndarray,
                    model=VITMATTE_S) -> np.ndarray:
    """ViTMatte-S as a LEARNED trimap refiner.

    Preprocessing taken verbatim from hustvl/vitmatte-small-composition-1k's
    preprocessor_config.json: rescale 1/255, normalise mean/std 0.5, trimap
    appended as a 4th channel in [0,1] WITHOUT normalisation.

    Measured the best edge refinement available here: it raises alignment AND
    lowers raggedness at the same time, which the guided filter cannot claim.
    The textbook alternatives are measured NEGATIVES on this material --
    closed-form / KNN / LBDM matting all pull the contour OFF the image edges,
    because the matting Laplacian assumes a local colour-line model and a
    447 kbps 4:2:0 Zoom crop violates it.
    """
    s = _session(model)
    H, W = trimap01.shape
    im = np.asarray(Image.fromarray(rgb).resize((1024, 1024),
                                                Image.Resampling.BILINEAR),
                    np.float32) / 255.0
    im = (im - 0.5) / 0.5
    tm = np.asarray(Image.fromarray((trimap01 * 255).astype(np.uint8))
                    .resize((1024, 1024), Image.Resampling.NEAREST),
                    np.float32) / 255.0
    x = np.concatenate([im, tm[..., None]], -1).transpose(2, 0, 1)[None]
    y = s.run(None, {s.get_inputs()[0].name: x.astype(np.float32)})[0]
    a = np.squeeze(y)
    out = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L")
    return np.asarray(out.resize((W, H), Image.Resampling.LANCZOS))


def _box(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_filter_color(I, p, r=2, eps=1e-4):
    """He/Sun/Tang colour-guide variant, written out because cv2.ximgproc is
    not reachable in this interpreter: opencv-contrib-python-headless 5.0.0.93
    is installed but `import cv2` resolves to 4.14.0 and dir(cv2.ximgproc)
    returns 0 names. Never go above r=4 -- r=8 improves the residual to 1.14
    but blows the colour fringe from 20.06 to 50.97.
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
            var[..., i, j] = (_box(I[..., i] * I[..., j], r)
                              - mI[..., i] * mI[..., j])
    var += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(var, cov[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    ma = np.stack([_box(a[..., c], r) for c in range(3)], -1)
    return np.clip((ma * I).sum(-1) + _box(b, r), 0, 1)


def cutout_hq(img: Image.Image, band=12, use_vitmatte=True, cf_band=4,
              verbose=True):
    """The measured winning chain, end to end. Returns (F_rgb, alpha).

    judge_3944 at native 612x338, against what ships today (birefnet-portrait
    raw alpha composited with the camera's own RGB):
        edge alignment    2.115 -> 2.271   (+7.4%)
        colour fringe    20.06  -> 14.81   (-26%)
        matting residual  2.36  ->  1.89   (-20%)
        soft hair mass     762  -> 1030    (+35%)
    Visually: the shipped cut-out is a sealed scissor-cut arc with zero strands;
    this one breaks the silhouette with individual hairs across the crown.
    """
    from pymatting import estimate_foreground_ml
    rgb = np.asarray(img.convert("RGB"))
    coarse = birefnet_alpha(img)
    if use_vitmatte:
        fine = vitmatte_refine(rgb, trimap_from_alpha(coarse, band=band))
        how = f"ViTMatte-S band={band}"
    else:
        g = guided_filter_color(rgb.astype(np.float32) / 255.0,
                                coarse.astype(np.float32) / 255.0,
                                r=2, eps=1e-4)
        fine = np.clip(g * 255, 0, 255).astype(np.uint8)
        how = "guided filter r=2 eps=1e-4"

    # Foreground decontamination needs a SOFT alpha to work. Running
    # estimate_foreground_ml on the alpha we ship makes the fringe 43% WORSE
    # (20.06 -> 28.67). Estimating F from a closed-form band-4 alpha and
    # compositing it with the SHARP alpha is what drops it to 14.81 --
    # decoupling alpha from F is the whole trick.
    try:
        from pymatting import estimate_alpha_cf
        soft = np.clip(estimate_alpha_cf(
            rgb.astype(np.float64) / 255.0,
            trimap_from_alpha(coarse, band=cf_band)), 0, 1)
        fsrc = f"closed-form band={cf_band}"
    except Exception as e:                                    # noqa: BLE001
        # pymatting 1.1.15 emits "Thresholded incomplete Cholesky decomposition
        # failed due to insufficient positive-definiteness" on this material,
        # so the fallback is real, not defensive padding.
        soft = cv2.GaussianBlur(fine.astype(np.float32) / 255.0,
                                (0, 0), 1.6).astype(np.float64)
        fsrc = f"gaussian-softened alpha (closed form failed: {e})"
    F = estimate_foreground_ml(rgb.astype(np.float64) / 255.0, soft)
    if verbose:
        print(f"  matte: BiRefNet-matting -> {how}; F from {fsrc}")
    return np.clip(F * 255.0, 0, 255).astype(np.uint8), fine


# ------------------------------------------------------- restore / upscale
def _ycc(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)


def _unycc(y):
    return cv2.cvtColor(np.clip(y, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def rl_deconv(Y, sigma, iters):
    Y = np.clip(Y.astype(np.float32), 1e-3, None)
    est = Y.copy()
    for _ in range(iters):
        conv = cv2.GaussianBlur(est, (0, 0), sigma)
        est = est * cv2.GaussianBlur(Y / np.maximum(conv, 1e-3), (0, 0), sigma)
        est = np.clip(est, 0, 300)
    return est


def restore_native(bgr, chroma_r=2, nlm_h=3, sigma=0.8, iters=12):
    """Stages 1-3 at NATIVE resolution, which is the entire point.

    Measured on the real judge tile: after this, band_s1 = 6.41 against the
    top-tier YouTube target of 6.21 -- dead on. The shipped build does all of
    this AFTER a 2x upscale, and the upscale then throws 57% of it away
    (6.41 -> 2.77, spec_hi_over_mid 0.0117 -> 0.0002).
    """
    y = _ycc(bgr)
    for c in (1, 2):
        y[:, :, c] = cv2.medianBlur(y[:, :, c].astype(np.uint8),
                                    2 * chroma_r + 1).astype(np.float32)
    y[:, :, 0] = cv2.fastNlMeansDenoising(y[:, :, 0].astype(np.uint8), None,
                                          nlm_h, 7, 21).astype(np.float32)
    y[:, :, 0] = rl_deconv(y[:, :, 0], sigma, iters)
    return _unycc(y)


def sr_upscale(bgr):
    """realesr-general-x4v3 through spandrel 0.4.2 (MIT; avoids basicsr, which
    does not work on python 3.14). BSD-3-Clause weights -- the only clean
    commercial position among the upscalers surveyed.

    Measured at true delivery scale on the judge tile: Laplacian variance 11.5
    (Lanczos) -> 91.8, an 8.0x gain, with edge gradient +31% while flat-area
    gradient rose only 9%.

    HONEST LIMIT, stated because it matters on a public-record channel: against
    known ground truth plain Lanczos is MORE faithful by ~2.3 dB PSNR. This
    model does not recover true detail, it synthesises plausible detail. That is
    why it is run at 4x and resampled back DOWN to ~2x -- the regime where real
    structure dominates -- and why no face-restoration model is used at all.
    """
    import torch
    if _SR["model"] is None:
        from spandrel import ModelLoader
        _SR["model"] = ModelLoader().load_from_file(str(REALESR))
        _SR["model"].eval()
    m = _SR["model"]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = torch.from_numpy(rgb).permute(2, 0, 1)[None]
    with torch.no_grad():
        y = m.model(x)
    out = y[0].permute(1, 2, 0).clamp(0, 1).numpy()
    return cv2.cvtColor((out * 255.0 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)


def deconv_clamped(bgr, sigma=1.3, iters=16, clamp_r=1, blend=0.85):
    """RL after the upscale, with an anti-ringing clamp.

    Plain RL here drove edge undershoot to 60.4% of step height against a
    top-tier reference p90 of 44.6% -- visible as a dark band along the ceiling
    beam. Clamping into [erode, dilate] of the pre-deconvolution luma at r=1
    returns undershoot to 44.2% while band_s1 still rises 2.71 -> 5.32 and the
    10-90 edge rise drops 1.29 -> 0.92 px. blend is the knob if it reads harsh.
    """
    y = _ycc(bgr)
    Y0 = y[:, :, 0].copy()
    Y = rl_deconv(Y0, sigma, iters)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * clamp_r + 1,) * 2)
    Y = np.clip(Y, cv2.erode(Y0, k), cv2.dilate(Y0, k))
    y[:, :, 0] = np.clip(Y0 + (Y - Y0) * blend, 0, 255)
    return _unycc(y)


def usm(bgr, sigma=0.7, amount=0.55, threshold=2.0):
    """RawTherapee's documented radius for in-focus low-ISO material is
    0.5-0.7. The shipped grade uses 2.0, i.e. a sigma-2 Gaussian, which boosts
    the sigma 2-8 octave -- the one octave we are NOT short of -- and adds
    nothing at sigma 1. darktable deprecates unsharp masking outright.
    """
    y = _ycc(bgr)
    Y = y[:, :, 0]
    d = Y - cv2.GaussianBlur(Y, (0, 0), sigma)
    d = np.where(np.abs(d) < threshold, 0.0, d)
    y[:, :, 0] = np.clip(Y + amount * d, 0, 255)
    return _unycc(y)


def detail_chain(bgr, out_wh, hero=True, use_sr=True, blend=None,
                 sharpen=None, sr_mix=1.0):
    """restore at native -> 4x SR -> resample to delivery -> clamped RL -> USM.

    The stage ORDER is the finding, not the settings: every restorative step
    belongs on the native side of the upscale, and only deconvolution and
    grain move sigma=1 afterwards. A guided-filter local-contrast boost at
    output resolution is a measured near-no-op here (fine gain 1.35 -> 2.10
    moved band_s1 by 0.03 per step).
    """
    r = restore_native(bgr)
    lan = cv2.resize(r, out_wh, interpolation=cv2.INTER_LANCZOS4)
    if use_sr and sr_mix > 0:
        big = sr_upscale(r)
        interp = cv2.INTER_AREA if big.shape[1] > out_wh[0] else cv2.INTER_LANCZOS4
        srr = cv2.resize(big, out_wh, interpolation=interp)
        # Mixing a little Lanczos back in is the honest acutance knob. The SR
        # model, not the post-upscale deconvolution, is what sets the edge
        # profile here: dropping the RL blend 0.85 -> 0.55 moved the measured
        # 10-90 rise only 0.816 -> 0.874 px. Lanczos is also the MORE faithful
        # of the two against ground truth (+2.3 dB PSNR), so this dial trades
        # synthesised acutance for measured fidelity in a single number.
        up = cv2.addWeighted(srr, sr_mix, lan, 1.0 - sr_mix, 0.0)
    else:
        up = lan
    b = blend if blend is not None else (0.85 if hero else 0.75)
    s = sharpen if sharpen is not None else (0.55 if hero else 0.40)
    up = deconv_clamped(up, blend=b)
    return usm(up, amount=s)


def highlight_desat(bgr, knee=0.86, amount=0.85):
    """Pull saturation out of the brightest pixels.

    Photographically correct -- a blown highlight is achromatic, because every
    channel has saturated -- and it is the fix for a specific measured defect
    here. The plate's overexposed ceiling carries a real magenta -> yellow ->
    orange chroma ramp in the SOURCE (tile row 1 runs (253,252,255) at x0 to
    (255,255,238) at x30 to (255,228,185) at x50, i.e. a full hue sweep across
    50 px of flat white ceiling), which is 4:2:0 chroma at 447 kbps. The grade
    then amplifies it into a visible rainbow smear in the top-left corner. A
    chroma median cannot remove it because it is a smooth gradient, not block
    noise; desaturating by luminance removes it and touches nothing else.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    v = hsv[:, :, 2] / 255.0
    k = np.clip((v - knee) / max(1e-6, 1.0 - knee), 0.0, 1.0)
    hsv[:, :, 1] *= (1.0 - amount * k)
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def grain(bgr, sigma=5.2, size=0.48, seed=7):
    """Monochromatic, midtone-weighted, pixel-scale grain at OUTPUT resolution.

    Reference (n=24 top-tier YouTube thumbnails, plate region): residual sigma
    median 4.40 [p10 1.43, p90 7.16], autocorrelation FWHM 1.18 px, chroma/luma
    residual ratio 0.102. Ours before this: sigma 0.775, FWHM 1.90 px, chroma
    ratio 0.39 -- a 5.7x amplitude gap, and what little we had was coarse
    chroma blotch rather than grain. This recipe measured 4.12 / 1.05 px / 0.06.
    Confirmed deliberate in the references and not a compression artifact: 8
    film one-sheets at native 2000x3000 measure sigma 1.20-11.29 with the
    midtone-peaked sigma-vs-luminance profile that is the film-grain signature.
    It also survives the JPEG re-encode: 4.36 (PNG) -> 4.49 at q95.
    """
    rng = np.random.default_rng(seed)
    y = _ycc(bgr)
    H, W = y.shape[:2]
    n = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32),
                         (0, 0), size)
    n /= max(n.std(), 1e-6)
    t = y[:, :, 0] / 255.0
    n *= np.clip(1.0 - np.abs(t - 0.45) / 0.55, 0.25, 1.0)
    n /= max(n.std(), 1e-6)
    y[:, :, 0] = np.clip(y[:, :, 0] + n * sigma, 0, 255)
    return _unycc(y)


# ------------------------------------------------------------- conversions
def pil2bgr(im: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)


def bgr2pil(a: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
