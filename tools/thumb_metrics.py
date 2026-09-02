# -*- coding: utf-8 -*-
"""
thumb_metrics.py — exact implementations of the Team B thumbnail metrics.

Self-contained. No JSON, no scratchpad, no hardcoded file lists.
Every public function takes an RGB uint8 HxWx3 array and returns a float.

    flat_g_p90(rgb, alpha=None)          -> Gate A, part 1
    poster_fa(rgb, alpha=None)           -> Gate A, part 2
    bg_mush(rgb, faces, alpha=None)      -> Gate B
    subject_max_L(rgb, faces)            -> Gate C
    detect_faces(rgb, model_path)        -> helper, YuNet

FACE FORMAT (Gate B and C): a list of dicts, each
    {"cx": <centre x / W>, "cy": <centre y / H>, "bw": <box width in px of the
     ARRAY YOU PASSED>, "bh": <box height in px of the array you passed>}
`detect_faces` returns exactly this.

--------------------------------------------------------------------------
FOUR THINGS THAT MAKE OR BREAK REPRODUCTION — all four are load-bearing:

 1. Everything is computed at a canonical 1280x720 (cv2.INTER_AREA). The
    metrics are NOT scale-invariant; measuring at native 4K gives other numbers.
 2. The title text is MASKED OUT. White/yellow glyph blobs, area-filtered, then
    dilated 13x13 to swallow the black stroke. Text is enormously "flat" in
    Lab a* and it is not image quality. Skipping this inflates flat_g_p90 by
    roughly +0.05 and is the most likely cause of a failed reproduction.
 3. Tiles are 40x40, CONTIGUOUS (stride 40, not overlapping), and a tile is
    DISCARDED unless >=78% of it is content (mask mean >= 200 on a 0/255 mask).
    Partial-text tiles must not enter the percentile.
 4. "Flat" is per-pixel 3x3 dilate == 3x3 erode, evaluated on the raw uint8
    channel. No blur, no denoise, no downscale beyond step 1.
--------------------------------------------------------------------------
"""

import numpy as np
import cv2

CANON_W, CANON_H = 1280, 720
TILE = 40
TILE_CONTENT_MIN = 200      # 0/255 mask mean -> ~78% of the tile must be content
BG_TILE_CONTENT_MIN = 220   # stricter for the background gate (~86%)

__all__ = ["flat_g_p90", "poster_fa", "bg_mush", "subject_max_L",
           "detect_faces", "text_mask", "all_metrics"]


# ----------------------------------------------------------------- internals
def _canon(rgb, alpha=None):
    """Resize to 1280x720. Returns (rgb_canon, valid_mask_uint8_0_255)."""
    if rgb.dtype != np.uint8:
        raise TypeError("expected uint8 RGB")
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("expected HxWx3 RGB (drop alpha, pass it separately)")
    c = cv2.resize(rgb, (CANON_W, CANON_H), interpolation=cv2.INTER_AREA)
    if alpha is None:
        valid = np.full((CANON_H, CANON_W), 255, np.uint8)
    else:
        a = cv2.resize(alpha, (CANON_W, CANON_H), interpolation=cv2.INTER_AREA)
        valid = ((a > 128).astype(np.uint8)) * 255
    return c, valid


def text_mask(rgb_canon):
    """White / saturated-yellow glyph blobs, dilated to include the dark stroke.

    Input MUST already be canonical 1280x720 (the area and size filters below
    are in canonical pixels).
    """
    r = rgb_canon[:, :, 0].astype(int)
    g = rgb_canon[:, :, 1].astype(int)
    b = rgb_canon[:, :, 2].astype(int)
    white = (b > 225) & (g > 225) & (r > 225)
    yellow = (r > 190) & (g > 150) & (b < 110) & ((r - b) > 90)
    # The ARROW is graphics too. It is deliberately flat vector art, exactly like
    # the glyphs, and excluding one but not the other made gate A fire on it as
    # though it were photographic posterisation.
    red = (r > 120) & (g < 95) & (b < 95) & ((r - g) > 70)
    m = ((white | yellow | red).astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        if 40 <= a <= 90000 and h < 260 and w < 900:
            keep[lab == i] = 255
    return cv2.dilate(keep, np.ones((13, 13), np.uint8))


def _flat_map(ch):
    """Per-pixel local flatness: 3x3 dilate == 3x3 erode. Bool array."""
    k = np.ones((3, 3), np.uint8)
    return cv2.dilate(ch, k) == cv2.erode(ch, k)


def _tile_values(field, content, min_content=TILE_CONTENT_MIN, reduce="mean"):
    """Contiguous 40x40 tiles; keep only tiles that are >=min_content content.

    `field` is float/bool HxW; `content` is a 0/255 uint8 mask.
    reduce: 'mean' (for flat maps) or 'std' (for high-pass maps).
    """
    f = field.astype(np.float32)
    out = []
    for y in range(0, CANON_H - TILE + 1, TILE):
        for x in range(0, CANON_W - TILE + 1, TILE):
            if content[y:y + TILE, x:x + TILE].mean() < min_content:
                continue
            t = f[y:y + TILE, x:x + TILE]
            out.append(float(t.mean()) if reduce == "mean" else float(t.std()))
    return np.array(out, dtype=np.float64)


def _content_mask(rgb_canon, valid):
    return cv2.bitwise_and(cv2.bitwise_not(text_mask(rgb_canon)), valid)


# ------------------------------------------------------------------- Gate A
def flat_g_p90(rgb, alpha=None):
    """90th percentile, over content tiles, of the locally-flat pixel share in
    GRAYSCALE. High = large smooth/posterised/smeared regions."""
    c, valid = _canon(rgb, alpha)
    content = _content_mask(c, valid)
    gray = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    v = _tile_values(_flat_map(gray), content)
    return float(np.percentile(v, 90)) if v.size else float("nan")


def poster_fa(rgb, alpha=None, tile_flat_threshold=0.8):
    """Share of content tiles in which MORE THAN 80% of pixels are locally flat
    in Lab a*. Chroma posterisation / banding."""
    c, valid = _canon(rgb, alpha)
    content = _content_mask(c, valid)
    lab = cv2.cvtColor(c, cv2.COLOR_RGB2LAB)
    v = _tile_values(_flat_map(lab[:, :, 1]), content)
    return float((v > tile_flat_threshold).mean()) if v.size else float("nan")


# ------------------------------------------------------------------- Gate B
def _face_mask(faces, src_w, src_h, pad=0.55):
    """Rect per face, half-extent scaled by (0.5 + pad) => 2.1x the box.
    faces carry bw/bh in SOURCE pixels, cx/cy normalised."""
    m = np.zeros((CANON_H, CANON_W), np.uint8)
    sx, sy = CANON_W / float(src_w), CANON_H / float(src_h)
    for f in faces:
        bw = f["bw"] * sx
        bh = f["bh"] * sy
        cx = f["cx"] * CANON_W
        cy = f["cy"] * CANON_H
        x0 = int(max(0, cx - bw * (0.5 + pad)))
        x1 = int(min(CANON_W, cx + bw * (0.5 + pad)))
        y0 = int(max(0, cy - bh * (0.5 + pad)))
        y1 = int(min(CANON_H, cy + bh * (0.5 + pad)))
        if x1 > x0 and y1 > y0:
            cv2.rectangle(m, (x0, y0), (x1, y1), 255, -1)
    return m


def bg_mush(rgb, faces, alpha=None, hf_threshold=1.0, blur_sigma=1.2):
    """Fraction OF BACKGROUND TILES (faces + title text + transparent excluded)
    whose high-pass standard deviation is below `hf_threshold`.

    high-pass = gray - GaussianBlur(gray, sigma=1.2). A tile below 1.0 has
    essentially no fine detail: smeared / AI-mush / over-denoised.

    NOTE the denominator: it is background tiles, NOT all tiles. A frame whose
    subjects fill it has few background tiles and the value gets noisy; the
    tile count is returned by all_metrics() so you can see when that happens.
    """
    src_h, src_w = rgb.shape[:2]
    c, valid = _canon(rgb, alpha)
    fm = _face_mask(faces, src_w, src_h)
    tm = text_mask(c)
    bgm = cv2.bitwise_and(cv2.bitwise_not(cv2.bitwise_or(fm, tm)), valid)
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).astype(np.float32)
    hf = g - cv2.GaussianBlur(g, (0, 0), blur_sigma)
    v = _tile_values(hf, bgm, min_content=BG_TILE_CONTENT_MIN, reduce="std")
    return float((v < hf_threshold).mean()) if v.size else float("nan")


def bg_tile_count(rgb, faces, alpha=None):
    src_h, src_w = rgb.shape[:2]
    c, valid = _canon(rgb, alpha)
    bgm = cv2.bitwise_and(
        cv2.bitwise_not(cv2.bitwise_or(_face_mask(faces, src_w, src_h), text_mask(c))),
        valid)
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).astype(np.float32)
    hf = g - cv2.GaussianBlur(g, (0, 0), 1.2)
    return int(_tile_values(hf, bgm, min_content=BG_TILE_CONTENT_MIN, reduce="std").size)


# ------------------------------------------------------------------- Gate C
def _graphics_mask(rgb):
    """Red arrow + white/yellow text, at the resolution of `rgb`."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    red = (((H < 8) | (H > 172)) & (S > 150) & (V > 90))
    r, g, b = rgb[:, :, 0].astype(int), rgb[:, :, 1].astype(int), rgb[:, :, 2].astype(int)
    white = (b > 225) & (g > 225) & (r > 225)
    yellow = (r > 190) & (g > 150) & (b < 110) & ((r - b) > 90)
    m = ((red | white | yellow).astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    sc = rgb.shape[0] / 720.0
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 30 * sc * sc:
            keep[lab == i] = 255
    k = max(3, int(9 * sc) | 1)
    return cv2.dilate(keep, np.ones((k, k), np.uint8))


def subject_max_L(rgb, faces, n_subjects=2):
    """Max, over the n largest faces, of the median Lab L* of that face —
    graphics inpainted out, hair/shadow (L<=40) and blowout (L>=250) dropped.
    Measured at NATIVE resolution (a median is scale-stable)."""
    if not faces:
        return float("nan")
    H, W = rgb.shape[:2]
    gm = _graphics_mask(rgb)
    big = sorted(faces, key=lambda f: -f["bw"] * f["bh"])[:n_subjects]
    vals = []
    for f in big:
        cx, cy = f["cx"] * W, f["cy"] * H
        x0 = int(max(0, cx - f["bw"] * 0.40)); x1 = int(min(W, cx + f["bw"] * 0.40))
        y0 = int(max(0, cy - f["bh"] * 0.40)); y1 = int(min(H, cy + f["bh"] * 0.40))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        L = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
        ok = (gm[y0:y1, x0:x1] == 0) & (L > 40) & (L < 250)
        if ok.sum() >= 400:
            vals.append(float(np.median(L[ok])))
    return max(vals) if vals else float("nan")


# ------------------------------------------------------------------- faces
_DET = None


def detect_faces(rgb, model_path, score_threshold=0.55):
    """YuNet. Returns [{cx, cy, bw, bh, score}] in the units this module wants:
    cx/cy normalised to the passed array, bw/bh in pixels of the passed array.
    Sorted largest first."""
    global _DET
    h, w = rgb.shape[:2]
    scale = 1280.0 / max(h, w) if max(h, w) > 1280 else 1.0
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    im = (cv2.resize(bgr, (int(round(w * scale)), int(round(h * scale))),
                     interpolation=cv2.INTER_AREA) if scale != 1.0 else bgr)
    hh, ww = im.shape[:2]
    if _DET is None:
        _DET = cv2.FaceDetectorYN.create(model_path, "", (ww, hh), score_threshold, 0.3, 5000)
    _DET.setInputSize((ww, hh))
    _DET.setScoreThreshold(score_threshold)
    res = _DET.detect(im)[1]
    out = []
    if res is None:
        return out
    for f in res:
        x, y, fw, fh = [float(v) / scale for v in f[:4]]
        out.append({"cx": (x + fw / 2) / w, "cy": (y + fh / 2) / h,
                    "bw": fw, "bh": fh, "score": float(f[-1])})
    out.sort(key=lambda d: -d["bw"] * d["bh"])
    return out


def all_metrics(rgb, faces=None, alpha=None, model_path=None):
    if faces is None:
        if model_path is None:
            raise ValueError("pass faces= or model_path=")
        faces = detect_faces(rgb, model_path)
    return {
        "flat_g_p90": flat_g_p90(rgb, alpha),
        "poster_fa": poster_fa(rgb, alpha),
        "bg_mush": bg_mush(rgb, faces, alpha),
        "bg_tiles": bg_tile_count(rgb, faces, alpha),
        "subject_max_L": subject_max_L(rgb, faces),
        "n_faces": len(faces),
    }
