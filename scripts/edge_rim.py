"""Pikzels-style cut-out rim: opaque warm-white stroke + wide Gaussian outer glow.

Constants fitted to the MEASURED Pikzels edge on
research/reference/ttt_own/cSz-vkSwVlk.jpg (the 9,800-view thumbnail).
Fit: 4-param least squares against the 16-point alpha ladder, RMS 0.0070 alpha.

NOTHING here touches subject pixels except by COVERING the matte's own
antialiased fringe with an opaque fill. No face, expression, pose or clothing
pixel is repainted, warped or synthesised.
"""
from __future__ import annotations
import numpy as np, cv2

STROKE_RGB     = (252, 250, 235)   # sRGB, L*98.0 a*-2 b*+7 ; NOT #FFFFFF
STROKE_R       = 2.65              # px half-width -> 5.3px opaque core
STROKE_AA      = 0.85              # px gaussian antialias (ladder+inner balance)
GLOW_SIGMA     = 14.5              # px
GLOW_ALPHA     = 1.00              # step height at the silhouette
MATTE_1090     = 2.5               # px target matte transition
STROKE_R_PCT_W = STROKE_R  / 1280.0
GLOW_SIG_PCT_W = GLOW_SIGMA / 1280.0


def _srgb_to_lin(u8):
    x = np.asarray(u8, np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92,
                    1.055 * x ** (1 / 2.4) - 0.055) * 255.0


def measure_1090(alpha_u8):
    """10-90 transition width in px = (area>=.10 - area>=.90) / perimeter."""
    a = np.asarray(alpha_u8, np.float64) / 255.0
    cs, _ = cv2.findContours((a >= .5).astype(np.uint8), cv2.RETR_EXTERNAL,
                             cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cs if cv2.contourArea(c) > 200)
    return float((np.sum(a >= .10) - np.sum(a >= .90)) / max(per, 1.0))


def tighten_matte(alpha_u8, target=MATTE_1090):
    """Contrast-remap alpha about its own 0.5 level set. Pure alpha edit."""
    cur = measure_1090(alpha_u8)
    k = max(cur / max(target, 1e-6), 1.0)
    a = np.asarray(alpha_u8, np.float64) / 255.0
    return np.clip((a - 0.5) * k + 0.5, 0, 1), cur, k


def signed_distance(alpha01, ss=4):
    """Signed px distance to the alpha 0.5 level set; POSITIVE = OUTSIDE."""
    H, W = alpha01.shape
    big = cv2.resize((alpha01 * 255).astype(np.uint8), (W * ss, H * ss),
                     interpolation=cv2.INTER_LANCZOS4)
    m = (big >= 128).astype(np.uint8)
    d = (cv2.distanceTransform(1 - m, cv2.DIST_L2, 5)
         - cv2.distanceTransform(m, cv2.DIST_L2, 5)) / float(ss)
    return cv2.resize(d, (W, H), interpolation=cv2.INTER_AREA)


def rim_layers(alpha_u8, *, R=None, aa=STROKE_AA, glow_sigma=None,
               glow_alpha=GLOW_ALPHA, tighten=True, verbose=True):
    """Return (stroke_alpha, glow_alpha, signed_distance, tightened_matte)."""
    H, W = alpha_u8.shape
    R = STROKE_R_PCT_W * W if R is None else R
    glow_sigma = GLOW_SIG_PCT_W * W if glow_sigma is None else glow_sigma
    if tighten:
        a01, cur, k = tighten_matte(alpha_u8)
        if verbose:
            print(f"  matte 10-90 {cur:.2f}px -> {MATTE_1090}px (gain k={k:.2f})")
    else:
        a01 = np.asarray(alpha_u8, np.float64) / 255.0
    d = signed_distance(a01)
    # stroke: hard band |d|<=R, gaussian-antialiased (erf shoulder)
    from scipy.special import erf
    S = np.clip(0.5 * (erf((R - d) / (aa * np.sqrt(2)))
                       + erf((R + d) / (aa * np.sqrt(2)))), 0, 1)
    # glow: the silhouette step, gaussian-blurred -> erfc profile, amp 1.0
    G = cv2.GaussianBlur((d <= 0).astype(np.float64), (0, 0), glow_sigma,
                         borderType=cv2.BORDER_REPLICATE) * glow_alpha
    return S, np.clip(G, 0, 1), d, a01


def rim(canvas_bgr, alpha_u8, *, stroke_rgb=STROKE_RGB, **kw):
    """Draw the rim onto a frame where the subject is ALREADY composited.

    Layer order, which is the whole point:
        plate  ->  GLOW over plate  ->  subject over that  ->  STROKE on top.
    The glow is masked by the subject matte so it sits BEHIND the subject; a
    glow composited over the subject would flood-fill the person with white.
    Returns (out_bgr, S, G_visible, signed_d, tightened_alpha).
    """
    S, G, d, a01 = rim_layers(alpha_u8, **kw)
    Gv = G * (1.0 - a01)                      # glow lives behind the subject
    lin = _srgb_to_lin(canvas_bgr)
    col = _srgb_to_lin(np.array(stroke_rgb[::-1], np.uint8))[None, None, :]
    out = lin * (1 - Gv[..., None]) + col * Gv[..., None]
    out = out * (1 - S[..., None]) + col * S[..., None]
    return _lin_to_srgb(out).round().astype(np.uint8), S, Gv, d, a01


def rim_composite(plate_bgr, subject_bgr, alpha_u8, *, stroke_rgb=STROKE_RGB,
                  **kw):
    """Explicit four-layer build from separate plate and subject. Preferred."""
    S, G, d, a01 = rim_layers(alpha_u8, **kw)
    P = _srgb_to_lin(plate_bgr); F = _srgb_to_lin(subject_bgr)
    col = _srgb_to_lin(np.array(stroke_rgb[::-1], np.uint8))[None, None, :]
    out = P * (1 - G[..., None]) + col * G[..., None]        # glow OVER plate
    out = out * (1 - a01[..., None]) + F * a01[..., None]    # subject OVER
    out = out * (1 - S[..., None]) + col * S[..., None]      # stroke OVER
    return _lin_to_srgb(out).round().astype(np.uint8), S, G, d, a01
