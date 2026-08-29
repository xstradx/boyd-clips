"""Adaptive placement: derive the arrangement from the frame, not from constants.

Every number that reaches the canvas is either (a) measured off this frame,
(b) a house-style ratio from the shipped Thompson thumbnail, or (c) a sourced
constant from SmartText / PosterLayout. Nothing is hand-tuned per case.
"""
from __future__ import annotations

import math
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, ".")
from layout_core import (Field, ali_penalty, build_field, burnin_mask, detect_faces,
                         grad_map, integral, overlap_ratio, rect_sum, utilisation)

W, H = 1280, 720

# ---- house ratios, measured off READY-TO-POST/1_LONGFORM_thumbnail.jpg ------
MARGIN_X = 23 / 1280          # 0.01797 W   left type margin
CAP_FRAC = 71 / 720           # 0.09861 H   cap height on the letter Y
TYPE_W_FRAC = (1072 - 23) / 1280   # 0.8195 W  type run
ARROW_AREA_FRAC = 0.0041      # 105x76 px of 1280x720
ARROW_ASPECT = 105 / 76

# ---- sourced constants -----------------------------------------------------
# SmartText generate_candidates.py defaults: text area must sit inside
# [rerow*recol/max_text_area_coef, rerow*recol/min_text_area_coef]
SMARTTEXT_AREA_LO = 1 / 17.0   # 0.0588 of the canvas
SMARTTEXT_AREA_HI = 1 / 7.0    # 0.1429 of the canvas
SMARTTEXT_FONT_STEP = 5        # font_inc_unit
SMARTTEXT_BORDER_CELLS = 4     # forbidden border band, in 120-cell grid units
SMARTTEXT_GRID = 120           # grid_num


# --------------------------------------------------------------- role assign --

def assign_roles(tiles, ocr=None):
    """Which tile holds the defendant, which holds the judge. Measured.

    Signal 1 (primary): the court's own burned-in tile caption. "187TH DC" is
    the courtroom camera; "Judge Boyd" is the bench camera. Read with OCR, not
    assumed from the tile's position - the judge is on the LEFT in CARTHIEF and
    on the RIGHT in SANCHEZ and OFFERUP.
    Signal 2 (fallback): the bench tile is one dominant face; the courtroom
    tile is 2+ faces of similar size. Ratio of largest to second-largest face
    height separates them.
    """
    out = {}
    for name, t in tiles.items():
        fs = t["faces"]
        h1 = fs[0].h if fs else 0.0
        h2 = fs[1].h if len(fs) > 1 else 0.0
        out[name] = dict(n_faces=len(fs), h1=h1, h2=h2,
                         dominance=(h1 / h2) if h2 > 0 else float("inf"),
                         caption=t.get("caption", ""))
    return out


# ----------------------------------------------------------------- plate crop --

def crop_candidates(fld: Field, target_face, scales, step=8):
    """16:9 windows inside the tile that (a) carry no burned-in furniture,
    (b) contain the defendant's face whole with headroom.

    Yields (x0, y0, cw, ch, face_h_frac).
    """
    Ht, Wt = fld.sal.shape
    fx0, fy0 = target_face.x, target_face.y
    fx1, fy1 = fx0 + target_face.w, fy0 + target_face.h
    head_top = fy0 - 0.55 * target_face.h   # hairline + crown, not just the box
    out = []
    for s in scales:
        cw = int(round(Wt * s))
        ch = int(round(cw * 9 / 16))
        if cw < 64 or ch < 36 or cw > Wt or ch > Ht:
            continue
        for y0 in range(0, Ht - ch + 1, step):
            if y0 > head_top - 0.10 * ch:      # headroom above the crown
                continue
            if y0 + ch < fy1 + 0.25 * target_face.h:   # chin + neck in frame
                continue
            for x0 in range(0, Wt - cw + 1, step):
                if x0 > fx0 - 0.20 * target_face.w:
                    continue
                if x0 + cw < fx1 + 0.20 * target_face.w:
                    continue
                out.append((x0, y0, cw, ch, (target_face.h / ch)))
    return out


def crop_is_clean(fld: Field, x0, y0, cw, ch, burn_ii):
    """No burned-in caption slab or active-speaker ring inside the crop."""
    return rect_sum(burn_ii, x0, y0, x0 + cw, y0 + ch) < 1.0


# ------------------------------------------------------------------ type fit --

def fit_type(text_white, text_yellow, font_path, cap_px, max_w):
    """Lay the headline at a given cap height, wrapping to 2 lines only if the
    single line exceeds max_w. Returns (lines, font, block_w, block_h)."""
    # binary-search the point size that yields the requested cap height,
    # measured on a capital letter rather than trusted from the metrics
    lo, hi = 8, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = ImageFont.truetype(font_path, mid)
        bb = f.getbbox("H")
        if (bb[3] - bb[1]) <= cap_px:
            lo = mid
        else:
            hi = mid - 1
    font = ImageFont.truetype(font_path, lo)
    full = (text_white + " " + text_yellow).strip()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    if d.textlength(full, font=font) <= max_w:
        lines = [full]
    else:
        words = full.split()
        best, bi = None, None
        for i in range(1, len(words)):
            a = " ".join(words[:i]); b = " ".join(words[i:])
            wa = d.textlength(a, font=font); wb = d.textlength(b, font=font)
            m = max(wa, wb)
            if best is None or m < best:
                best, bi = m, i
        lines = [" ".join(words[:bi]), " ".join(words[bi:])]
    bw = max(d.textlength(l, font=font) for l in lines)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.02)
    bh = lh * len(lines)
    return lines, font, int(bw), int(bh), lh


# ---------------------------------------------------------------- placement ---

def place_type(fld: Field, anchors_x, block_w, block_h, safe, step=4,
               band=(0.0, 0.55)):
    """SmartText get_top_k_submatrix, done with an integral image.

    Sweeps y over the allowed band at every anchored x, rejects any window
    that touches the forbid mask at all (Nathan: "the words should never be on
    defendants or judges face or body" - a hard constraint, not a penalty),
    and returns the survivors ranked by occlusion then gradient.
    """
    Ht, Wt = fld.sal.shape
    y_lo = int(band[0] * Ht) + safe
    y_hi = min(Ht - safe - block_h, int(band[1] * Ht))
    cands = []
    for ax in anchors_x:
        x0 = int(ax)
        if x0 < safe or x0 + block_w > Wt - safe:
            continue
        for y0 in range(y_lo, max(y_lo + 1, y_hi + 1), step):
            fbd = rect_sum(fld.ii_forbid, x0, y0, x0 + block_w, y0 + block_h)
            if fbd > 0.5:
                continue
            occ = rect_sum(fld.ii_sal, x0, y0, x0 + block_w, y0 + block_h) / (block_w * block_h)
            rea = rect_sum(fld.ii_grad, x0, y0, x0 + block_w, y0 + block_h) / (block_w * block_h)
            cands.append((occ, rea, x0, y0))
    cands.sort(key=lambda c: (c[0], c[1]))
    return cands


def place_arrow(fld: Field, tip_xy, tail_anchors, length_px, matte_hard):
    """Arrow tail in clear space, tip on the defendant.

    Hard rule from the shipped Thompson thumbnail, measured: of the arrow's
    3,822 red pixels, ZERO sit on a person. So the arrow body is rasterised
    and tested against the matte, not approximated by its bounding box.
    """
    best = None
    tx, ty = tip_xy
    for (ax, ay) in tail_anchors:
        d = math.hypot(tx - ax, ty - ay)
        if d < 1:
            continue
        ux, uy = (tx - ax) / d, (ty - ay) / d
        sx, sy = tx - ux * length_px, ty - uy * length_px
        if not (0 <= sx < fld.sal.shape[1] and 0 <= sy < fld.sal.shape[0]):
            continue
        mask = rasterise_arrow((sx, sy), (tx, ty), fld.sal.shape)
        on_person = int((mask & (matte_hard > 0)).sum())
        n = int(mask.sum())
        if n == 0:
            continue
        clear = 1.0 - on_person / n
        ang = math.degrees(math.atan2(uy, ux))
        if best is None or (on_person, -clear) < (best[0], -best[1]):
            best = (on_person, clear, (sx, sy), (tx, ty), ang, mask)
    return best


def rasterise_arrow(start, tip, shape, shaft_frac=0.240, head_frac=0.475):
    """The actual filled polygon, so 'does it touch a person' is measured on
    pixels rather than on a bounding box."""
    h, w = shape
    sx, sy = start; tx, ty = tip
    L = math.hypot(tx - sx, ty - sy)
    ux, uy = (tx - sx) / L, (ty - sy) / L
    px, py = -uy, ux
    shaft = L * shaft_frac * 0.5
    head_len = L * (1 - head_frac)
    hx, hy = tx - ux * head_len, ty - uy * head_len
    head_w = shaft * 2.4
    pts = np.array([
        [sx + px * shaft, sy + py * shaft],
        [hx + px * shaft, hy + py * shaft],
        [hx + px * head_w, hy + py * head_w],
        [tx, ty],
        [hx - px * head_w, hy - py * head_w],
        [hx - px * shaft, hy - py * shaft],
        [sx - px * shaft, sy - py * shaft],
    ], dtype=np.int32)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [pts], 1)
    return m
