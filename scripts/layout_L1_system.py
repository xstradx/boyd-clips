"""L1_system - parametric Boyd thumbnail placement. BOYD THUMBNAIL PLACEMENT SPEC v1.

    python scripts/layout_L1_system.py CARTHIEF|SANCHEZ|OFFERUP|--all

There are NO per-case coordinates, timestamps, sides, scales or offsets in this
file. The only per-hearing inputs are the job facts (source file, stream offset,
case range, the Zoom grid rects, and Nathan's copy). Every position on the canvas
is derived by measuring THIS hearing:

  STAGE A  gaze/geometry census over 220 frames of the case range
  STAGE B  role assignment from the court's own burned-in tile caption
  STAGE C  hero frame chosen by GATES (turn, pitch, roll, size, matte quality)
  STAGE D  hero placement anchored on the EYES, side = -sign(median nd)
  STAGE E  plate crop search, hard rejects in cost order
  STAGE F  type: house geometry, semantic white/yellow break, collision rule
  STAGE G  arrow: ray walked back off the people mask of the COMPOSITE
  then     objective J, yield ladder, render, and verification re-measured on
           the written JPEG.

Licences of every weight used: YuNet MIT (opencv_zoo), BiRefNet / rembg
`birefnet-*` MIT (rembg's DEFAULT bria-rmbg is CC BY-NC and is never selected),
RapidOCR Apache-2.0. PosterLayout has NO licence file, so its metrics are
reimplemented from the published definitions; no code copied. SmartText MIT
(mechanism only: anchored sweep + min-sum window).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = "C:/Users/natha/Projects/boyd-clips"
YUNET = f"{ROOT}/models/yunet.onnx"                     # 229,738 B, MIT
FONT = f"{ROOT}/assets/fonts/TTTHeadline-Regular.ttf"   # "TTT Headline", settled
CACHE = f"{ROOT}/work/_L1"
OUTDIR = "C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/LAYOUT"
W, H = 1280, 720

# =====================================================================
# JOB FACTS. Not tuning: the source, where the stream clock starts, the case
# range, the Zoom grid rects the encoder used, and Nathan's copy. Note the
# judge is on a DIFFERENT SIDE in each - nothing below ever reads which.
# =====================================================================
JOBS = {
    "CARTHIEF": dict(
        src=f"{ROOT}/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
        off=3554.0, case=(3574.0, 4628.0),
        tiles={"A": (612, 338, 18, 190), "B": (620, 338, 644, 190)},
        white="18 years old and", yellow="already in cuffs"),
    "SANCHEZ": dict(
        src=f"{ROOT}/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
        off=3683.0, case=(3703.0, 4148.0),
        tiles={"A": (468, 348, 726, 6), "B": (628, 348, 6, 6)},
        white="You're why your son", yellow="is struggling"),
    "OFFERUP": dict(
        src=f"{ROOT}/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
        off=10550.0, case=(10570.0, 11117.0),
        tiles={"A": (628, 348, 646, 186), "B": (628, 348, 6, 186)},
        white="Do you want", yellow="a jury trial?"),
}

# =====================================================================
# SPEC v1 CONSTANTS. Every one carries its measurement in the comment.
# =====================================================================
SPEC = dict(
    # -- STAGE C gates ------------------------------------------------
    gate_turn=0.20,          # |nd|>=; judge hearing-medians .305/.314/.346
    gate_pitch=0.50,         # nv<=; rendered check 0.412-0.468 = eyes level
    gate_roll=4.0,           # deg; shipped hero rolls 0.48-2.28
    gate_face_in_tile=0.33,  # faceH/tileH, keeps the 1280 upscale <= 2.7x
    # -- STAGE D hero -------------------------------------------------
    hero_face_h=0.45, hero_face_h_lo=0.38, hero_face_h_hi=0.52,  # shipped med .4328
    lead=0.750, lead_lo=0.743, lead_hi=0.783,     # Audit nose-room med .750
    eye_y=0.327, eye_y_lo=0.315, eye_y_hi=0.340,  # ours + all 43 corpus = .327
    side_assert=0.12,        # |median nd| below this = no gaze evidence -> stop
    bleed_w=0.02,            # silhouette crosses the outside edge by >= .02 W
    bottom_cov=0.15,         # alpha on the composite bottom row, hero x-span
    edge_col=0.02,           # matte on a tile column > this => severed there
    phantom_fail=0.15, phantom_warn=0.12,   # boundary px with local |grad|<35
    grad_ratio=3.0,          # boundary |grad| median / tile |grad| median
    # -- STAGE E plate ------------------------------------------------
    upscale_max=2.7,
    defe_face_h=0.22, defe_face_h_lo=0.19, defe_face_h_hi=0.33,  # shipped .219
    sep=0.50, sep_lo=0.42, sep_hi=0.58,   # corpus n=32 med .5116 IQR .447-.562
    dcy=0.09, dcy_max=0.22,               # corpus med .0945 IQR .061-.150
    # -- STAGE F type -------------------------------------------------
    cap=0.100, cap_lo=0.090,     # 71-73 px in 6/6; never below Audit med .0806
    pitch=1.425,                 # baselines 99->202 = 103 px = 1.425 x cap, 5/5
    inset_x=0.0211, inset_y=0.0375,      # 27 px on BOTH axes, 5/5 and 4/5
    inset_y_max=0.092,                   # Audit's own max top inset
    stroke=0.0086, glow_blur=10,         # 11 px + zero-offset black glow
    wmax_sweep=(0.82, 0.78, 0.74, 0.70, 0.66, 0.62),
    break_min=0.55, break_target=0.75,   # first yellow word / line-1 ink width
    gap_hero_hard=0.038, gap_hero_aim=0.082,   # Audit t_face_gap floor/median
    ink_on_hair=0.02, ink_on_people=0.02,
    freerect=0.90, freerect_floor=0.60,
    area_lo=0.13, area_hi=0.26,          # our block area; ABOVE SmartText's band
    # -- STAGE G arrow ------------------------------------------------
    arrow_rgb=(253, 1, 1),               # #FD0101
    arrow_len=0.096, arrow_shaft=0.240, arrow_head=0.475,   # fill .463 +- .008
    arrow_area_lo=0.0028, arrow_area_hi=0.0066,
    arrow_deg=137.9, arrow_lo=110.0, arrow_hi=152.0,   # hero RIGHT; mirrored if L
    standoff_min=4.0, standoff_aim_lo=0.006, standoff_aim_hi=0.031,
    standoff_max=0.065,
    body_clear=0.054,                    # Audit a_body_clearance med .0623 W
    arrow_type_gap=0.046, arrow_type_aim=0.077,
    # -- grade (Thompson: luminance mean 125, blacks 9.0%) -------------
    grade_mean=125.0, grade_blacks=0.090,
)
SMARTTEXT_BAND = (1 / 17.0, 1 / 7.0)   # reported; deliberately NOT adopted
CENSUS_N = 220


def log(*a):
    print(*a, flush=True)


# =====================================================================
# geometry helpers
# =====================================================================
class Det:
    """One YuNet detection, expressed in the three scalars the spec uses."""
    __slots__ = ("x", "y", "w", "h", "s", "nd", "nv", "roll", "t", "i",
                 "ex", "ey")

    def __init__(self, r, t=0.0, i=0):
        v = [float(q) for q in r]
        self.x, self.y, self.w, self.h = v[0], v[1], v[2], v[3]
        e0 = np.array(v[4:6]); e1 = np.array(v[6:8])      # the two eyes
        no = np.array(v[8:10])
        m0 = np.array(v[10:12]); m1 = np.array(v[12:14])  # the two mouth corners
        self.s = v[14]
        em = (e0 + e1) / 2.0
        mm = (m0 + m1) / 2.0
        self.ex, self.ey = float(em[0]), float(em[1])   # the EYE anchor
        io = float(np.hypot(*(e1 - e0)))
        self.roll = math.degrees(math.atan2(e1[1] - e0[1], e1[0] - e0[0]))
        if io < 1e-6:
            self.nd = self.nv = 0.0
        else:
            # de-rolled, so a tilted head cannot fake a turn or a droop
            c = math.cos(-math.radians(self.roll)); s_ = math.sin(-math.radians(self.roll))
            R = np.array([[c, -s_], [s_, c]])
            n_ = R @ (no - em)
            m_ = R @ (mm - em)
            dv = abs(float(m_[1]))             # eye-mid -> mouth-mid, de-rolled
            if dv < 1e-6:
                self.nd = self.nv = 0.0
            else:
                # NOTE: normalised by dv, NOT by the interocular. The spec's s0
                # text says interocular, but every nd number in the spec came
                # from research/gaze/gz_measure.py:face_metrics, which uses dv.
                # Checked: OFFERUP judge nd_med -0.341 here == gz_tiles.json.
                self.nd = float(n_[0] / dv)    # <0 = head turned image-LEFT
                self.nv = float(n_[1] / dv)    # higher = looking DOWN
        self.t = t
        self.i = i

    @property
    def cx(self): return self.x + self.w / 2

    @property
    def cy(self): return self.y + self.h / 2

    def rec(self):
        return dict(x=self.x, y=self.y, w=self.w, h=self.h, s=self.s,
                    nd=self.nd, nv=self.nv, roll=self.roll, t=self.t, i=self.i,
                    ex=self.ex, ey=self.ey)


def detector(w, h, thresh=0.55):
    d = cv2.FaceDetectorYN.create(YUNET, "", (w, h), thresh, 0.3, 5000)
    d.setInputSize((w, h))
    return d


def integral(a):
    return cv2.integral(a.astype(np.float64))


def rsum(ii, x0, y0, x1, y1):
    return ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]


def sobel_mag(bgr):
    """sqrt((gx^2+gy^2)/2) on a SIGNED Sobel. Depth must be CV_32F: with
    cv2.Sobel(g,-1,...) the negative half of every edge is clipped to zero and
    the tile median collapses to 0.7, which makes the absolute phantom
    threshold of 35 meaningless (measured: phantom 0.38 instead of 0.10).
    With CV_32F this reproduces [MQ]: OFFERUP boundary 121.5 vs its 129.3."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    return np.sqrt((gx ** 2 + gy ** 2) / 2)


def grad_norm(bgr):
    """PosterLayout metrics_rea: the same map normalised by its own max."""
    m = sobel_mag(bgr)
    mx = float(m.max())
    return m / mx if mx > 0 else m


def ali_penalty(boxes):
    """PosterLayout metrics_ali, from its published definition."""
    if len(boxes) <= 1:
        return 0.0
    th = np.array([[a / W, b / H, (a + c) / (2 * W), (b + d) / (2 * H), c / W, d / H]
                   for (a, b, c, d) in boxes], dtype=np.float64)
    tot = 0.0
    for i in range(len(th)):
        g = []
        for j in range(6):
            col = th[:, j]
            dmin = float(np.abs(col[i] - np.delete(col, i)).min())
            g.append(-math.log10(1.0 - min(dmin, 0.999999)))
        tot += min(g)
    return tot


def overlap_ratio(boxes):
    n = len(boxes)
    if n < 2:
        return 0.0
    tot = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            ax0, ay0, ax1, ay1 = boxes[i]; bx0, by0, bx1, by1 = boxes[j]
            iw = min(ax1, bx1) - max(ax0, bx0); ih = min(ay1, by1) - max(ay0, by0)
            inter = iw * ih if iw > 0 and ih > 0 else 0.0
            a = (ax1 - ax0) * (ay1 - ay0); b = (bx1 - bx0) * (by1 - by0)
            tot += inter / max(1e-9, a + b - inter)
    return tot / n


def max_free_rect(free):
    """Largest all-true axis-aligned rectangle, histogram method."""
    h, w = free.shape
    height = np.zeros(w, np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(h):
        height = np.where(free[y], height + 1, 0)
        stack = []
        for x in range(w + 1):
            cur = int(height[x]) if x < w else 0
            start = x
            while stack and stack[-1][1] >= cur:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, sx, y - sh + 1, x, y + 1)
                start = sx
            stack.append((start, cur))
    return best


# =====================================================================
# STAGE A - census
# =====================================================================
def census(name, cfg):
    p = f"{CACHE}/{name}_census_v2.json"
    if os.path.exists(p):
        return json.load(open(p))
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    cap = cv2.VideoCapture(cfg["src"])
    a, b = cfg["case"]
    times = [float(t) for t in np.linspace(a, b, CENSUS_N)]
    dets = {k: [] for k in cfg["tiles"]}
    ocr_txt = {k: [] for k in cfg["tiles"]}
    dts = {k: detector(r[0], r[1]) for k, r in cfg["tiles"].items()}
    ocr = None
    ocr_at = set(int(x) for x in np.linspace(5, CENSUS_N - 6, 5))
    for i, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, (t - cfg["off"]) * 1000.0)
        ok, fr = cap.read()
        if not ok:
            continue
        for k, (tw, th, tx, ty) in cfg["tiles"].items():
            tile = fr[ty:ty + th, tx:tx + tw]
            _, raw = dts[k].detect(tile)
            if raw is not None:
                for r in raw:
                    dets[k].append(Det(r, t, i).rec())
            if i in ocr_at:
                if ocr is None:
                    from rapidocr_onnxruntime import RapidOCR
                    ocr = RapidOCR()
                band = tile[int(th * 0.80):th, 0:int(tw * 0.60)]
                band = cv2.resize(band, None, fx=2.5, fy=2.5,
                                  interpolation=cv2.INTER_CUBIC)
                res, _ = ocr(band)
                ocr_txt[k].append(" ".join(r[1] for r in (res or [])).upper())
    cap.release()
    out = dict(times=times, dets=dets, ocr=ocr_txt, n=CENSUS_N,
               secs=round(time.time() - t0, 1))
    json.dump(out, open(p, "w"))
    return out


def cluster(recs, tw, dcx=0.06, dlh=0.35, min_frac=0.15, n_frames=CENSUS_N):
    """Persistent face tracks: same cx to within dcx tile-widths and the same
    log face height to within dlh. NOT 'the biggest face' - largest-face
    selection returns the attorney (CARTHIEF: attorney cx .144, defendant .5365)."""
    cl = []
    for r in recs:
        cx = r["x"] + r["w"] / 2
        for c in cl:
            if (abs(cx - c["cx"]) < dcx * tw
                    and abs(math.log(max(1e-6, r["h"] / c["h"]))) < dlh):
                c["n"] += 1
                c["cx"] += (cx - c["cx"]) / c["n"]
                c["h"] += (r["h"] - c["h"]) / c["n"]
                c["recs"].append(r)
                break
        else:
            cl.append(dict(cx=cx, h=r["h"], n=1, recs=[r]))
    for c in cl:
        c["frames"] = len({r["i"] for r in c["recs"]})
    keep = [c for c in cl if c["frames"] >= min_frac * n_frames]
    return sorted(keep or cl, key=lambda c: -c["frames"])


# =====================================================================
# matting
# =====================================================================
_SESS = {}


def matte(bgr, model, key):
    p = f"{CACHE}/{key}_{model}.png"
    if os.path.exists(p):
        a = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if a is not None and a.shape == bgr.shape[:2]:
            return a.astype(np.float32) / 255.0
    from rembg import new_session, remove
    if model not in _SESS:
        _SESS[model] = new_session(model)     # birefnet-* only. MIT.
    a = np.asarray(remove(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)),
                          session=_SESS[model], post_process_mask=True).split()[-1])
    cv2.imwrite(p, a)
    return a.astype(np.float32) / 255.0


def matte_quality(bgr, alpha):
    """The computable form of 'surgical cuts not slop'. A cut that follows a
    real edge sits on 3-5x the image's own median gradient; a cut through a
    flat forearm does not."""
    g = sobel_mag(bgr)
    m = (alpha > 0.5).astype(np.uint8)
    k = np.ones((3, 3), np.uint8)
    boundary = (cv2.dilate(m, k) - cv2.erode(m, k)) > 0
    if boundary.sum() < 50 or m.sum() < 500:
        return dict(ok=False, why="matte empty or has no boundary")
    bg = g[boundary]
    tile_med = float(np.median(g))
    b_med = float(np.median(bg))
    hh, ww = m.shape
    return dict(ok=True, boundary_grad_med=round(b_med, 1),
                tile_grad_med=round(tile_med, 1),
                grad_ratio=round(b_med / max(1e-6, tile_med), 2),
                phantom=round(float((bg < 35).mean()), 3),
                col_left=round(float(m[:, 0].mean()), 3),
                col_right=round(float(m[:, ww - 1].mean()), 3),
                row_bottom=round(float(m[hh - 1, :].mean()), 3),
                coverage=round(float(m.mean()), 3))


def gesture(bgr, alpha, face):
    """Weak proxy for Nathan's 'a hand MID-GESTURE adds drama'. Skin-toned
    component inside the matte, below the chin box, of hand-like area, whose
    principal axis is not vertical. A PREFERENCE, never a gate."""
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    cr = ycc[..., 1].astype(int); cb = ycc[..., 2].astype(int)
    skin = ((cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127) & (alpha > 0.5))
    fy1 = int(face["y"] + face["h"] * 1.25)
    skin[:max(0, fy1), :] = False
    n, lab, st, _ = cv2.connectedComponentsWithStats(skin.astype(np.uint8), 8)
    fa = face["w"] * face["h"]
    for i in range(1, n):
        a = int(st[i, 4])
        if not (0.12 * fa <= a <= 1.3 * fa):
            continue
        ys, xs = np.nonzero(lab == i)
        if len(xs) < 30:
            continue
        c = np.cov(np.stack([xs.astype(float), ys.astype(float)]))
        _, evec = np.linalg.eigh(c)
        v = evec[:, -1]
        ang = abs(math.degrees(math.atan2(abs(v[1]), abs(v[0]))))
        if ang < 65:        # principal axis off vertical -> reaching, not resting
            return True, a
    return False, 0


# =====================================================================
# STAGE F - typesetting
# =====================================================================
def font_for_cap(cap_px):
    lo, hi = 8, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = ImageFont.truetype(FONT, mid)
        bb = f.getbbox("H")
        if (bb[3] - bb[1]) <= cap_px:
            lo = mid
        else:
            hi = mid - 1
    return ImageFont.truetype(FONT, lo)


def typeset(white, yellow, cap_px, wmax):
    """Greedy fill of line 1, ragged line 2 - what 5/5 of ours do. Returns INK
    rectangles, never em boxes (136 px em vs 91 px ink at cap 85)."""
    font = font_for_cap(cap_px)
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    words = white.split() + yellow.split()
    nw = len(white.split())
    lines, cur = [], []
    for w_ in words:
        if cur and d.textlength(" ".join(cur + [w_]), font=font) > wmax:
            lines.append(cur); cur = [w_]
        else:
            cur.append(w_)
    if cur:
        lines.append(cur)
    if not (1 <= len(lines) <= 2):
        return None
    pitch = int(round(cap_px * SPEC["pitch"]))
    idx = 0
    rects, fy = [], None
    for li, ln in enumerate(lines):
        bb = font.getbbox(" ".join(ln))
        rects.append([int(bb[0]), li * pitch + int(bb[1]),
                      int(bb[2]), li * pitch + int(bb[3])])
        px = 0.0
        for w_ in ln:
            if idx == nw and fy is None:
                fy = (li, px)
            px += d.textlength(w_ + " ", font=font)
            idx += 1
    if fy is None:
        fy = (len(lines) - 1, 0.0)
    y0 = min(r[1] for r in rects)
    rects = [[a, b - y0, c, dd - y0] for a, b, c, dd in rects]
    l1w = rects[0][2] - rects[0][0]
    return dict(font=font, cap=cap_px, lines=[" ".join(l) for l in lines],
                words=lines, n_white=nw, rects=rects, pitch=pitch,
                w=max(r[2] for r in rects), h=max(r[3] for r in rects),
                ink_dy=y0, l1w=l1w,
                break_frac=(fy[1] / max(1.0, l1w)) if fy[0] == 0 else 1.0,
                # line 2 is 100% yellow in 5/5 of ours: true iff the break is
                # on line 1 (or there is only one line)
                line2_yellow=(len(lines) == 1 or fy[0] == 0))


def glyph_mask(ts, stroke):
    """The actual ink, stroke included, at a local origin. The hard tests are
    run against THIS, not against the em box."""
    pad = 2 * stroke
    im = Image.new("L", (ts["w"] + 2 * pad, ts["h"] + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(ts["lines"]):
        d.text((pad, pad - ts["ink_dy"] + i * ts["pitch"]), ln, font=ts["font"],
               fill=255, stroke_width=stroke, stroke_fill=255)
    return np.asarray(im) > 0, pad


# =====================================================================
# STAGE G - arrow polygon
# =====================================================================
def arrow_poly(tip, deg, L):
    tx, ty = tip
    th = math.radians(deg)
    ux, uy = math.cos(th), math.sin(th)
    sx, sy = tx - ux * L, ty - uy * L
    px, py = -uy, ux
    shaft = L * SPEC["arrow_shaft"] * 0.5
    hl = L * (1 - SPEC["arrow_head"])
    hx, hy = tx - ux * hl, ty - uy * hl
    hw = shaft * 2.4
    return np.array([[sx + px * shaft, sy + py * shaft],
                     [hx + px * shaft, hy + py * shaft],
                     [hx + px * hw, hy + py * hw],
                     [tx, ty],
                     [hx - px * hw, hy - py * hw],
                     [hx - px * shaft, hy - py * shaft],
                     [sx - px * shaft, sy - py * shaft]], dtype=np.float32)


def raster(poly, shape=(H, W)):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(poly).astype(np.int32)], 1)
    return m


# =====================================================================
# grade - applied BEFORE the arrow and the type burn in, so #FD0101 and the
# white/yellow stay exact. Target from the shipped Thompson: mean 125.
# =====================================================================
def grade(bgr):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L = lab[..., 0].astype(np.float32)
    m = float(L.mean())
    if m > 1:
        gm = math.log(max(1e-3, SPEC["grade_mean"] / 255.0)) / math.log(max(1e-3, m / 255.0))
        L = 255.0 * np.power(np.clip(L / 255.0, 0, 1), float(np.clip(gm, 0.62, 1.6)))
    x = L / 255.0
    L = 255.0 * np.clip(x + 0.16 * (x - 0.5) * (1 - np.abs(2 * x - 1)), 0, 1)
    lab[..., 0] = np.clip(L, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.08, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# =====================================================================
# burn-in furniture inside a tile
# =====================================================================
_OCR = None


def burnin(bgr):
    """Zoom's active-speaker ring + the court's own caption slab, found by OCR
    at its returned polygon. A white-colour rule is NOT usable: (S<40)&(V>200)
    marks 16.6% of the OFFERUP tile - it selects the courtroom's white ceiling
    - and rejected 15,481/15,481 candidate crops."""
    global _OCR
    h, w = bgr.shape[:2]
    b, g, r = [bgr[..., i].astype(int) for i in range(3)]
    m = (((g - np.maximum(r, b)) > 55) & (g > 165)).astype(np.uint8)
    try:
        if _OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        res, _ = _OCR(bgr)
        for box, txt, conf in (res or []):
            p = np.array(box, dtype=np.int32)
            x0, y0 = int(p[:, 0].min()), int(p[:, 1].min())
            x1, y1 = int(p[:, 0].max()), int(p[:, 1].max())
            pad = int(0.35 * (y1 - y0))
            cv2.rectangle(m, (max(0, x0 - pad), max(0, y0 - pad)),
                          (min(w, x1 + pad), min(h, y1 + pad)), 1, -1)
    except Exception as e:
        log("   OCR unavailable for burn-in:", e)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8)).astype(np.float32)


def grab(cap, off, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, (t - off) * 1000.0)
    ok, fr = cap.read()
    if not ok:
        raise RuntimeError(f"decode failed at t={t}")
    return fr


# =====================================================================
# STAGE D - hero geometry on the canvas
# =====================================================================
def hero_geom(tile, alpha, face, side, face_h, lead):
    """Anchor on the EYES. Scale from the face height, then put the eye
    midpoint at (lead*W, .327 H) on the gaze side, and let the bottom fall off
    the canvas. Never mirrored - mirroring is the one operation that can point
    her gaze off the outside edge."""
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) < 200:
        return None
    cy0, cy1, cx0, cx1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    scale = (face_h * H) / face["h"]
    cw = int(round((cx1 - cx0) * scale)); chh = int(round((cy1 - cy0) * scale))
    if cw < 40 or chh < 40 or cw > 6000 or chh > 6000:
        return None
    rgba = cv2.resize(np.dstack([tile[cy0:cy1, cx0:cx1],
                                 (alpha[cy0:cy1, cx0:cx1] * 255).astype(np.uint8)]),
                      (cw, chh), interpolation=cv2.INTER_LANCZOS4)
    eye_x = (lead if side == "R" else 1.0 - lead) * W
    hx = int(round(eye_x - (face["ex"] - cx0) * scale))
    hy = int(round(SPEC["eye_y"] * H - (face["ey"] - cy0) * scale))
    occ = np.zeros((H, W), np.float32)
    ax0, ay0 = max(0, hx), max(0, hy)
    ax1, ay1 = min(W, hx + cw), min(H, hy + chh)
    if ax1 <= ax0 or ay1 <= ay0:
        return None
    occ[ay0:ay1, ax0:ax1] = rgba[ay0 - hy:ay1 - hy, ax0 - hx:ax1 - hx, 3] / 255.0
    fb = (hx + (face["x"] - cx0) * scale, hy + (face["y"] - cy0) * scale,
          hx + (face["x"] + face["w"] - cx0) * scale,
          hy + (face["y"] + face["h"] - cy0) * scale)
    # BLEED: columns of real alpha lying beyond the outside frame edge
    a05 = rgba[..., 3] > 127
    if side == "R":
        beyond = a05[:, max(0, W - hx):]
    else:
        beyond = a05[:, :max(0, -hx)]
    bleed_px = int((beyond.any(axis=0)).sum()) if beyond.size else 0
    span = (max(0, hx), min(W, hx + cw))
    bot = occ[H - 1, span[0]:span[1]]
    return dict(x=hx, y=hy, w=cw, h=chh, rgba=rgba, occ=occ, scale=scale,
                face_box=fb, side=side, face_h=face_h, lead=lead,
                bleed_px=bleed_px,
                bottom_cov=float((bot > 0.5).mean()) if bot.size else 0.0,
                eye=(eye_x, SPEC["eye_y"] * H))


def hero_masks(G):
    """Split the hero alpha into BODY (never any ink) and HAIR (<=2% of ink).
    Nathan's rule names 'face or body'; the shipped OFFERUP thumbnail sets the
    word 'honest' over her hair and he shipped it."""
    a = G["occ"] > 0.5
    fb = G["face_box"]
    body = a.copy()
    hair = np.zeros_like(a)
    top = int(max(0, fb[1]))
    hair[:top, :] = a[:top, :]
    body[:top, :] = False
    return body, hair


# =====================================================================
# STAGE B/C - roles, tracks, hero frame
# =====================================================================
def pick_roles(cs, cfg):
    votes = {}
    for k, txts in cs["ocr"].items():
        joined = " ".join(txts).upper()
        votes[k] = ("187" in joined) or (" DC" in " " + joined)
    court = [k for k, v in votes.items() if v]
    how = "caption OCR ('187'/' DC')"
    if len(court) != 1:
        # fallback: the courtroom tile carries several similarly sized faces,
        # the bench tile one dominant one
        stat = {}
        for k, (tw, th, tx, ty) in cfg["tiles"].items():
            cl = cluster(cs["dets"][k], tw)
            hs = sorted([c["h"] for c in cl], reverse=True)
            stat[k] = (len(cl), (hs[0] / hs[1]) if len(hs) > 1 else 99.0)
        court = [max(stat, key=lambda k: (stat[k][0], -stat[k][1]))]
        how = f"face-count/dominance fallback {stat}"
    court = court[0]
    bench = [k for k in cfg["tiles"] if k != court][0]
    return court, bench, how, {k: " ".join(v)[:80] for k, v in cs["ocr"].items()}


def gaze_stats(recs):
    nd = np.array([r["nd"] for r in recs]); nv = np.array([r["nv"] for r in recs])
    return dict(n=len(recs),
                nd_med=float(np.median(nd)), nd_p10=float(np.percentile(nd, 10)),
                nd_p90=float(np.percentile(nd, 90)),
                nv_med=float(np.median(nv)), nv_p10=float(np.percentile(nv, 10)),
                nv_p90=float(np.percentile(nv, 90)),
                frac_turned=float((np.abs(nd) >= SPEC["gate_turn"]).mean()))


# =====================================================================
# the build
# =====================================================================
def build(name):
    t_start = time.time()
    cfg = JOBS[name]
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    rep = dict(hearing=name, spec="BOYD THUMBNAIL PLACEMENT SPEC v1",
               copy=dict(white=cfg["white"], yellow=cfg["yellow"]),
               relaxed=[], refused=None)
    log(f"\n================ {name} ================")

    # ---------- STAGE A ----------
    cs = census(name, cfg)
    rep["census"] = dict(frames=cs["n"], seconds=cs["secs"],
                         dets={k: len(v) for k, v in cs["dets"].items()})
    log("A census", rep["census"])

    # ---------- STAGE B ----------
    court, bench, how, caps = pick_roles(cs, cfg)
    ctw, cth, ctx, cty = cfg["tiles"][court]
    btw, bth, btx, bty = cfg["tiles"][bench]
    rep["roles"] = dict(method=how, court_tile=court, bench_tile=bench,
                        court_tile_x=ctx, bench_tile_x=btx, captions=caps,
                        judge_side_in_grid=("LEFT" if btx < ctx else "RIGHT"))
    log("B roles", rep["roles"]["court_tile"], "court /", bench, "bench;",
        "judge is", rep["roles"]["judge_side_in_grid"], "in the Zoom grid")

    # persistent tracks
    b_cl = cluster(cs["dets"][bench], btw)
    if not b_cl:
        return refuse(rep, "no persistent face in the bench tile")
    # DOMINANCE, not persistence: what makes a tile the bench tile is one big
    # face (measured dominance 5.6-99.0) against the courtroom tile's 1.06-1.25.
    judge = max(b_cl, key=lambda c: c["h"])
    c_cl = cluster(cs["dets"][court], ctw)
    if not c_cl:
        return refuse(rep, "no persistent face in the courtroom tile")
    # DEFENDANT = the persistent cluster nearest tile centre. Largest-face
    # selection returns the attorney.
    s_lo = max(0.42, (W / SPEC["upscale_max"]) / ctw)
    ch_min = int(round(int(round(ctw * s_lo)) * 9 / 16))
    ch_max = min(cth, int(round(ctw * 9 / 16)))
    h_lo = SPEC["defe_face_h_lo"] * ch_min
    h_hi = SPEC["defe_face_h_hi"] * ch_max
    viable = [c for c in c_cl if h_lo <= c["h"] <= h_hi]
    if not viable:
        return refuse(rep, f"no persistent courtroom face can reach the "
                           f"{SPEC['defe_face_h_lo']}-{SPEC['defe_face_h_hi']} H "
                           f"band at any admissible crop (need {h_lo:.0f}-{h_hi:.0f} px "
                           f"in tile, have {[round(c['h']) for c in c_cl]})")
    defe_cl = min(viable, key=lambda c: abs(c["cx"] - ctw / 2.0))
    rep["tracks"] = dict(
        court_clusters=[dict(cx_frac=round(c["cx"] / ctw, 4),
                             h_frac=round(c["h"] / cth, 4), frames=c["frames"],
                             viable_defendant=bool(h_lo <= c["h"] <= h_hi))
                        for c in c_cl],
        defendant_h_band_px=[round(h_lo, 1), round(h_hi, 1)],
        bench_cluster_detail=[dict(cx_frac=round(c["cx"] / btw, 4),
                                   h_frac=round(c["h"] / bth, 4),
                                   frames=c["frames"]) for c in b_cl],
        defendant_cx_frac=round(defe_cl["cx"] / ctw, 4),
        defendant_h_frac=round(defe_cl["h"] / cth, 4),
        largest_face_cx_frac=round(max(c_cl, key=lambda c: c["h"])["cx"] / ctw, 4),
        bench_clusters=len(b_cl), judge_frames=judge["frames"])
    log("B defendant cluster cx", rep["tracks"]["defendant_cx_frac"],
        "vs largest-face cx", rep["tracks"]["largest_face_cx_frac"])

    # ---------- STAGE D.1 side, from the HEARING median, never one frame ----
    gs = gaze_stats(judge["recs"])
    rep["gaze"] = {k: round(v, 4) for k, v in gs.items()}
    if abs(gs["nd_med"]) < SPEC["side_assert"]:
        return refuse(rep, f"judge median nd {gs['nd_med']:+.3f} is inside the "
                           f"+-{SPEC['side_assert']} dead band: no gaze evidence")
    side = "R" if gs["nd_med"] < 0 else "L"
    rep["hero_side"] = dict(side=side, rule="side = -sign(median nd)",
                            median_nd=round(gs["nd_med"], 4),
                            frames=gs["n"], frac_turned=round(gs["frac_turned"], 3))
    log(f"D side={side} from median nd {gs['nd_med']:+.3f} over {gs['n']} detections")

    # ---------- STAGE C hero frame, by GATE not by timestamp ---------------
    sgn = -1.0 if gs["nd_med"] < 0 else 1.0
    passers = [r for r in judge["recs"]
               if sgn * r["nd"] >= SPEC["gate_turn"]
               and r["nv"] <= SPEC["gate_pitch"]
               and abs(r["roll"]) <= SPEC["gate_roll"]
               and r["h"] / bth >= SPEC["gate_face_in_tile"]]
    rep["hero_gate"] = dict(
        candidates=len(judge["recs"]), passed=len(passers),
        gates=dict(turn=f"sign*nd>={SPEC['gate_turn']}", pitch=f"nv<={SPEC['gate_pitch']}",
                   roll=f"|roll|<={SPEC['gate_roll']}",
                   size=f"faceH/tileH>={SPEC['gate_face_in_tile']}"),
        by_gate=dict(
            turn=sum(1 for r in judge["recs"] if sgn * r["nd"] >= SPEC["gate_turn"]),
            pitch=sum(1 for r in judge["recs"] if r["nv"] <= SPEC["gate_pitch"]),
            roll=sum(1 for r in judge["recs"] if abs(r["roll"]) <= SPEC["gate_roll"]),
            size=sum(1 for r in judge["recs"] if r["h"] / bth >= SPEC["gate_face_in_tile"])))
    log("C hero gate", rep["hero_gate"]["passed"], "of",
        rep["hero_gate"]["candidates"], "|", rep["hero_gate"]["by_gate"])
    if not passers:
        return refuse(rep, "no frame passes the hero gates "
                           "(turn AND pitch AND roll AND size)")
    # eyes level first, then most turned. Gesture is decided after the matte.
    passers.sort(key=lambda r: (r["nv"], -abs(r["nd"])))

    cap = cv2.VideoCapture(cfg["src"])
    hero, hero_try = None, []
    for r in passers[:8]:
        tile = grab(cap, cfg["off"], r["t"])[bty:bty + bth, btx:btx + btw]
        a = matte(tile, "birefnet-portrait", f"{name}_hero_{int(r['t']*100)}")
        q = matte_quality(tile, a)
        gest, garea = gesture(tile, a, r) if q["ok"] else (False, 0)
        # THE TILE-EDGE RULE. If the source matte covers a tile column, the
        # silhouette is already severed there by the Zoom boundary; that column
        # must become the frame edge she bleeds off, or the frame is refused.
        far = q.get("col_left" if side == "R" else "col_right", 1.0)
        near = q.get("col_right" if side == "R" else "col_left", 0.0)
        ok = (q["ok"] and q["grad_ratio"] >= SPEC["grad_ratio"]
              and q["phantom"] <= SPEC["phantom_fail"]
              and far <= SPEC["edge_col"] and q["row_bottom"] > 0.02)
        rec = dict(t=round(r["t"], 2), nd=round(r["nd"], 3), nv=round(r["nv"], 3),
                   roll=round(r["roll"], 2), faceH_in_tile=round(r["h"] / bth, 3),
                   gesture=gest, gesture_px=garea, pass_matte=bool(ok),
                   severed_far_column=round(far, 3), bleed_column=round(near, 3), **q)
        hero_try.append(rec)
        if ok:
            hero = (r, tile, a, gest, q)
            if gest:
                break
    rep["hero_frames_examined"] = hero_try
    if hero is None:
        cap.release()
        return refuse(rep, "every gated hero frame fails the matte / tile-edge "
                           "rule (see hero_frames_examined)")
    hr, htile, halpha, hgest, hq = hero
    rep["hero_chosen"] = dict(t=round(hr["t"], 2), nd=round(hr["nd"], 3),
                              nv=round(hr["nv"], 3), roll=round(hr["roll"], 2),
                              gesture=hgest, matte=hq)
    log("C hero t=", round(hr["t"], 1), "nd", round(hr["nd"], 3), "nv",
        round(hr["nv"], 3), "gesture", hgest, "phantom", hq["phantom"],
        "grad_ratio", hq["grad_ratio"])

    # ---------- STAGE D.2 hero geometries (ladder rungs 4 and 7) -----------
    geoms = []
    for fh in (SPEC["hero_face_h"], 0.42, SPEC["hero_face_h_lo"]):
        for ld in (SPEC["lead"], SPEC["lead_hi"]):
            G = hero_geom(htile, halpha, hr, side, fh, ld)
            if G is None:
                continue
            if G["bleed_px"] < SPEC["bleed_w"] * W:
                continue
            if G["bottom_cov"] < SPEC["bottom_cov"]:
                continue
            G["body"], G["hair"] = hero_masks(G)
            G["ii_body"] = integral(G["body"].astype(np.float32))
            G["ii_hair"] = integral(G["hair"].astype(np.float32))
            G["ii_occ"] = integral((G["occ"] > 0.10).astype(np.float32))
            G["dist_hero"] = cv2.distanceTransform((G["occ"] <= 0.5).astype(np.uint8),
                                                   cv2.DIST_L2, 3)
            geoms.append(G)
    rep["hero_geoms"] = [dict(face_h=g["face_h"], lead=g["lead"], x=g["x"], y=g["y"],
                              w=g["w"], h=g["h"], bleed_px=g["bleed_px"],
                              bottom_cov=round(g["bottom_cov"], 3),
                              face_box=[round(v, 1) for v in g["face_box"]],
                              face_cx=round((g["face_box"][0] + g["face_box"][2]) / 2 / W, 4),
                              face_cy=round((g["face_box"][1] + g["face_box"][3]) / 2 / H, 4))
                         for g in geoms]
    if not geoms:
        cap.release()
        return refuse(rep, "hero will not bleed off the frame edge and reach the "
                           "bottom at any admitted scale")
    log("D", len(geoms), "hero geometries; face_cx",
        [g["face_cx"] for g in rep["hero_geoms"]][:2])

    # ---------- STAGE E plate frames, by GATE not by timestamp -------------
    hmed = float(np.median([r["h"] for r in defe_cl["recs"]]))
    pc = [r for r in defe_cl["recs"]
          if r["s"] >= 0.60 and 0.85 * hmed <= r["h"] <= 1.15 * hmed]
    pc.sort(key=lambda r: (r["nv"] > 0.60, -r["s"]))
    # spread the candidates over the case so they are not three neighbours
    chosen, seen = [], []
    for r in pc:
        if all(abs(r["t"] - u) > 0.03 * (cfg["case"][1] - cfg["case"][0]) for u in seen):
            chosen.append(r); seen.append(r["t"])
        if len(chosen) >= 3:
            break
    if not chosen:
        chosen = pc[:3] or defe_cl["recs"][:3]
    rep["plate_frames"] = [dict(t=round(r["t"], 2), score=round(r["s"], 3),
                                nv=round(r["nv"], 3), nd=round(r["nd"], 3),
                                h=round(r["h"], 1)) for r in chosen]
    log("E plate candidates", [round(r['t'], 1) for r in chosen])

    # typesets: the whole ladder of wrap widths x cap heights, deduped
    tss = []
    seen_key = set()
    for cf in (SPEC["cap"], 0.095, SPEC["cap_lo"]):
        for wf in SPEC["wmax_sweep"]:
            ts = typeset(cfg["white"], cfg["yellow"], int(round(cf * H)),
                         int(round(wf * W)))
            if not ts:
                continue
            k = (tuple(ts["lines"]), ts["cap"])
            if k in seen_key:
                continue
            seen_key.add(k)
            ts["cap_frac"] = cf
            ts["wmax_frac"] = wf
            ts["glyph"], ts["gpad"] = glyph_mask(ts, max(6, int(round(SPEC["stroke"] * W))))
            tss.append(ts)
    # the semantic break rule: line 2 100% yellow (5/5) and the first yellow
    # word at >= .55 of line-1 ink width (6/6 fall in the last 45%)
    good = [t for t in tss if t["line2_yellow"] and t["break_frac"] >= SPEC["break_min"]]
    rep["typesets"] = dict(
        built=len(tss), satisfying_break_rule=len(good),
        options=[dict(cap=t["cap"], lines=t["lines"], break_frac=round(t["break_frac"], 3),
                      line2_yellow=t["line2_yellow"], w_frac=round(t["w"] / W, 3),
                      area=round(t["w"] * t["h"] / (W * H), 4),
                      in_smarttext_band=bool(SMARTTEXT_BAND[0] <= t["w"] * t["h"] / (W * H)
                                             <= SMARTTEXT_BAND[1])) for t in tss])
    if good:
        tss = good
    else:
        rep["relaxed"].append("break rule unsatisfiable at any w_max - the copy "
                              "needs re-splitting (spec s6.3 / ladder step 8)")
    log("F typesets", len(tss), "of", rep["typesets"]["built"], "satisfy the break rule")

    # ---------- the joint search ------------------------------------------
    best, funnel = None, dict(scale=0, xy=0, burn=0, occl=0, sep=0, dcy=0,
                              faceh=0, crops=0, no_type=0, no_arrow=0, full=0)
    plates = {}
    for r in chosen:
        ptile = grab(cap, cfg["off"], r["t"])[cty:cty + cth, ctx:ctx + ctw]
        key = f"{name}_plate_{int(r['t']*100)}"
        pm = matte(ptile, "birefnet-general-lite", key)
        bi = burnin(ptile)
        dts = detector(ctw, cth, 0.55)
        _, raw = dts.detect(ptile)
        faces = [Det(q, r["t"]) for q in (raw if raw is not None else [])]
        # the defendant IN THIS FRAME = the detection nearest the track
        dsel = min(faces, key=lambda f: abs(f.cx - defe_cl["cx"]) + abs(f.h - defe_cl["h"])) \
            if faces else None
        if dsel is None or abs(dsel.cx - defe_cl["cx"]) > 0.10 * ctw:
            continue
        fmask = np.zeros((cth, ctw), np.float32)
        for f in faces:
            fmask[max(0, int(f.y - .12 * f.h)):int(f.y + 1.12 * f.h),
                  max(0, int(f.x - .12 * f.w)):int(f.x + 1.12 * f.w)] = 1.0
        people = np.maximum((pm > 0.5).astype(np.float32), (bi > 0.5).astype(np.float32))
        faceonly = fmask
        plates[r["t"]] = dict(
            tile=ptile, defe=dsel, faces=faces, burn=bi, people=people,
            ii_burn=integral(bi), ii_people=integral(people),
            ii_face=integral(faceonly),
            ii_forbid=integral(np.maximum(people, faceonly)),
            ii_grad=integral(grad_norm(ptile)),
            ii_sal=integral(np.maximum(np.maximum(pm, fmask), bi)),
            dist_people=cv2.distanceTransform(
                (np.maximum(people, faceonly) <= 0.5).astype(np.uint8), cv2.DIST_L2, 3),
            t=r["t"])
    cap.release()
    if not plates:
        return refuse(rep, "the defendant track is not re-detectable in any "
                           "gated plate frame")
    rep["plate_burnin"] = {round(k, 1): round(float((v["burn"] > 0.5).mean()), 4)
                           for k, v in plates.items()}
    log("E burn-in coverage", rep["plate_burnin"])

    stroke = max(6, int(round(SPEC["stroke"] * W)))
    tx = int(round(SPEC["inset_x"] * W))
    s_min = max(0.42, (W / SPEC["upscale_max"]) / ctw)
    rep["crop_scale_floor"] = round(s_min, 4)
    cands = []
    for P in plates.values():
        d = P["defe"]
        for s_ in np.arange(s_min, 1.0001, 0.02):
            cw = int(round(ctw * s_)); ch = int(round(cw * 9 / 16))
            if ch > cth or cw > ctw:
                funnel["scale"] += 1
                continue
            fhf = d.h / ch
            if not (SPEC["defe_face_h_lo"] <= fhf <= SPEC["defe_face_h_hi"]):
                funnel["faceh"] += 1
                continue
            kx = W / cw
            px0, px1 = d.x - .30 * d.w, d.x + 1.30 * d.w
            py0, py1 = d.y - .30 * d.h, d.y + 1.30 * d.h
            xs_ = range(max(0, int(math.ceil(px1 - cw))),
                        min(ctw - cw, int(px0)) + 1, 4)
            ys_ = range(max(0, int(math.ceil(py1 - ch))),
                        min(cth - ch, int(py0)) + 1, 4)
            for x0 in xs_:
                dcx = (d.cx - x0) * kx / W
                for y0 in ys_:
                    dcy = (d.cy - y0) * (H / ch) / H
                    funnel["xy"] += 1
                    if rsum(P["ii_burn"], x0, y0, x0 + cw, y0 + ch) > 1.0:
                        funnel["burn"] += 1
                        continue
                    cands.append((P, x0, y0, cw, ch, dcx, dcy, fhf))
    log("E crops surviving burn-in:", len(cands), "of", funnel["xy"])

    for G in geoms:
        hfb = G["face_box"]
        hcx = (hfb[0] + hfb[2]) / 2 / W
        hcy = (hfb[1] + hfb[3]) / 2 / H
        pool = []
        for (P, x0, y0, cw, ch, dcx, dcy, fhf) in cands:
            sep = abs(hcx - dcx)
            if not (SPEC["sep_lo"] <= sep <= SPEC["sep_hi"]):
                funnel["sep"] += 1
                continue
            if abs(hcy - dcy) > SPEC["dcy_max"]:
                funnel["dcy"] += 1
                continue
            kx, ky = W / cw, H / ch
            d = P["defe"]
            bx0 = (d.x - .30 * d.w - x0) * kx; bx1 = (d.x + 1.30 * d.w - x0) * kx
            by0 = (d.y - .30 * d.h - y0) * ky; by1 = (d.y + 1.30 * d.h - y0) * ky
            if not (0 <= bx0 and bx1 < W and 0 <= by0 and by1 < H):
                continue
            if rsum(G["ii_occ"], int(bx0), int(by0), int(bx1), int(by1)) > 0.5:
                funnel["occl"] += 1
                continue
            pool.append((abs(sep - SPEC["sep"]) + abs(fhf - SPEC["defe_face_h"]) * 2
                         + abs(abs(hcy - dcy) - SPEC["dcy"]),
                         P, x0, y0, cw, ch, dcx, dcy, fhf, sep))
        pool.sort(key=lambda z: z[0])
        funnel["crops"] += len(pool)
        for (_, P, x0, y0, cw, ch, dcx, dcy, fhf, sep) in pool[:70]:
            c = evaluate(P, G, x0, y0, cw, ch, dcx, dcy, fhf, sep, tss, tx,
                         stroke, funnel)
            if c is None:
                continue
            funnel["full"] += 1
            if best is None or c["J"] > best["J"]:
                best = c
    rep["funnel"] = funnel
    log("search funnel", funnel)
    if best is None:
        return refuse(rep, "no crop admitted a legal type AND arrow placement "
                           f"(funnel {funnel})")

    out = render(name, best, rep, cfg)
    rep["seconds"] = round(time.time() - t_start, 1)
    json.dump(rep, open(f"{OUTDIR}/L1_system_{name}.json", "w"), indent=2, default=str)
    log("wrote", out, "in", rep["seconds"], "s")
    return rep


def refuse(rep, why):
    rep["refused"] = why
    log("REFUSED:", why)
    os.makedirs(OUTDIR, exist_ok=True)
    json.dump(rep, open(f"{OUTDIR}/L1_system_{rep['hearing']}.json", "w"),
              indent=2, default=str)
    return rep


# =====================================================================
# one (crop x typeset x arrow) candidate
# =====================================================================
def evaluate(P, G, x0, y0, cw, ch, dcx, dcy, fhf, sep, tss, tx, stroke, funnel):
    kx, ky = W / cw, H / ch
    hfb = G["face_box"]
    d = P["defe"]
    # the defendant's face box on the canvas
    dfb = ((d.x - x0) * kx, (d.y - y0) * ky,
           (d.x + d.w - x0) * kx, (d.y + d.h - y0) * ky)

    # ---------------- STAGE F: type ----------------
    # anchor x at the house inset; sweep y over the measured band. SmartText's
    # mechanism, with an integral image instead of avg_pool2d.
    right_max = hfb[0] - SPEC["gap_hero_hard"] * W    # THE COLLISION RULE
    best_t = None
    for ts in tss:
        if tx + ts["w"] > right_max:
            continue
        for ty in range(int(SPEC["inset_y"] * H), int(SPEC["inset_y_max"] * H) + 1, 4):
            occ = rea = area = 0.0
            bad = False
            for (rx0, ry0, rx1, ry1) in ts["rects"]:
                cX0, cY0, cX1, cY1 = tx + rx0, ty + ry0, tx + rx1, ty + ry1
                if cX1 > right_max:
                    bad = True; break
                # never any ink on the hero's face box
                if not (cX1 < hfb[0] or cX0 > hfb[2] or cY1 < hfb[1] or cY0 > hfb[3]):
                    bad = True; break
                # never any ink on the hero's BODY matte
                if rsum(G["ii_body"], cX0, cY0, cX1, cY1) > 0.5:
                    bad = True; break
                tX0, tY0 = int(x0 + cX0 / kx), int(y0 + cY0 / ky)
                tX1 = int(math.ceil(x0 + cX1 / kx)); tY1 = int(math.ceil(y0 + cY1 / ky))
                if tX1 > x0 + cw or tY1 > y0 + ch or tX1 <= tX0 or tY1 <= tY0:
                    bad = True; break
                # never any ink on a plate FACE box
                if rsum(P["ii_face"], tX0, tY0, tX1, tY1) > 0.5:
                    bad = True; break
                a = float((tX1 - tX0) * (tY1 - tY0))
                occ += rsum(P["ii_sal"], tX0, tY0, tX1, tY1)
                rea += rsum(P["ii_grad"], tX0, tY0, tX1, tY1)
                area += a
            if bad or area <= 0:
                continue
            occ /= area; rea /= area
            hair = rsum(G["ii_hair"], tx, ty, tx + ts["w"], ty + ts["h"]) / float(ts["w"] * ts["h"])
            gapf = (hfb[0] - (tx + ts["w"])) / W
            sc = (-2.0 * occ - 1.0 * rea - 1.2 * hair
                  - 0.20 * abs(ty / H - SPEC["inset_y"]) / 0.055
                  - 0.10 * (SPEC["wmax_sweep"][0] - ts["wmax_frac"]) / 0.20
                  - 0.60 * abs(ts["cap_frac"] - SPEC["cap"]) / 0.010
                  - 1.2 * max(0.0, SPEC["gap_hero_hard"] - gapf) * 26
                  - 0.8 * abs(ts["break_frac"] - SPEC["break_target"])
                  + 0.45 * (len(ts["lines"]) == 2)
                  + 0.35 * (SPEC["area_lo"] <= ts["w"] * ts["h"] / (W * H) <= SPEC["area_hi"]))
            if best_t is None or sc > best_t[0]:
                best_t = (sc, ts, ty, occ, rea, hair, gapf)
    if best_t is None:
        funnel["no_type"] += 1
        return None
    tsc, ts, ty, t_occ, t_rea, t_hair, gapf = best_t
    trects = [(tx + a, ty + b, tx + c, ty + dd) for (a, b, c, dd) in ts["rects"]]

    # ---------------- STAGE G: arrow ----------------
    lo, hi = ((SPEC["arrow_lo"], SPEC["arrow_hi"]) if G["side"] == "R"
              else (180 - SPEC["arrow_hi"], 180 - SPEC["arrow_lo"]))
    aim = SPEC["arrow_deg"] if G["side"] == "R" else 180 - SPEC["arrow_deg"]
    L = SPEC["arrow_len"] * W
    Pt = (dfb[0] + 0.5 * (dfb[2] - dfb[0]), dfb[1] + 0.30 * (dfb[3] - dfb[1]))
    best_a = None
    for deg in np.arange(lo, hi + 0.01, 3.0):
        th = math.radians(float(deg))
        ux, uy = math.cos(th), math.sin(th)
        tip = None
        for back in range(0, int(SPEC["standoff_max"] * W) + 12, 2):
            qx, qy = Pt[0] - ux * back, Pt[1] - uy * back
            if not (2 <= qx < W - 2 and 2 <= qy < H - 2):
                break
            TX = int(np.clip(x0 + qx / kx, 0, cw + x0 - 1))
            TY = int(np.clip(y0 + qy / ky, 0, ch + y0 - 1))
            if (P["people"][TY, TX] < 0.5 and G["occ"][int(qy), int(qx)] < 0.10
                    and P["ii_face"] is not None):
                # also off every plate face box
                if rsum(P["ii_face"], TX, TY, TX + 1, TY + 1) < 0.5:
                    tip = (qx - ux * 4.0, qy - uy * 4.0)   # +4 px standoff floor
                    break
        if tip is None:
            continue
        stand = math.hypot(max(dfb[0] - tip[0], tip[0] - dfb[2], 0.0),
                           max(dfb[1] - tip[1], tip[1] - dfb[3], 0.0))
        if not (SPEC["standoff_min"] <= stand <= SPEC["standoff_max"] * W):
            continue
        poly = arrow_poly(tip, float(deg), L)
        if poly[:, 0].min() < 2 or poly[:, 0].max() > W - 2 \
                or poly[:, 1].min() < 2 or poly[:, 1].max() > H - 2:
            continue
        m = raster(poly)
        ys_, xs_ = np.nonzero(m)
        n = len(ys_)
        if n == 0:
            continue
        if G["occ"][ys_, xs_].max() > 0.10:
            continue
        TX = np.clip((x0 + xs_ / kx).astype(int), 0, x0 + cw - 1)
        TY = np.clip((y0 + ys_ / ky).astype(int), 0, y0 + ch - 1)
        if int((P["people"][TY, TX] > 0.5).sum()) > 0:
            continue
        ab = (int(xs_.min()), int(ys_.min()), int(xs_.max()) + 1, int(ys_.max()) + 1)
        # arrow ink <-> type ink, disjoint with a gap
        gap = min(box_gap(ab, r) for r in trects)
        if gap < SPEC["arrow_type_gap"] * W:
            continue
        # centroid clearance to the nearest person pixel, both layers
        cxa, cya = float(xs_.mean()), float(ys_.mean())
        dp = float(P["dist_people"][int(np.clip(y0 + cya / ky, 0, y0 + ch - 1)),
                                    int(np.clip(x0 + cxa / kx, 0, x0 + cw - 1))]) * kx
        dh = float(G["dist_hero"][int(cya), int(cxa)])
        clear = min(dp, dh)
        # the tip's nearest face must BE the tracked defendant
        near = nearest_face_canvas(tip, P, x0, y0, kx, ky, G)
        if near != "defendant":
            continue
        sc = (-1.5 * abs(float(deg) - aim) / 90.0
              - 1.0 * abs(n / (W * H) - 0.00448) * 120
              - 0.6 * max(0.0, SPEC["body_clear"] * W - clear) / (SPEC["body_clear"] * W)
              - 0.5 * max(0.0, stand / W - SPEC["standoff_aim_hi"]) / 0.034
              - 0.3 * abs(gap - SPEC["arrow_type_aim"] * W) / W)
        if best_a is None or sc > best_a[0]:
            best_a = (sc, tip, float(deg), n, stand, ab, clear, gap, poly, m)
    if best_a is None:
        funnel["no_arrow"] += 1
        return None
    asc, tip, adeg, an, astand, ab, aclear, agap, apoly, amask = best_a

    boxes = [(tx, ty, tx + ts["w"], ty + ts["h"]), ab,
             (max(0, G["x"]), max(0, G["y"]), min(W, G["x"] + G["w"]), H)]
    R_ali = ali_penalty(boxes)
    R_ove = overlap_ratio(boxes)
    cov = np.zeros((H, W), bool)
    for (bx0, by0, bx1, by1) in boxes[:2]:
        cov[int(by0):int(by1), int(bx0):int(bx1)] = True
    free = G["occ"] <= 0.5
    R_uti = float((cov & free).sum()) / max(1.0, float(free.sum()))

    J = (-2.0 * t_occ - 1.0 * t_rea - 1.2 * t_hair
         + 1.2 * R_uti - 0.9 * R_ali - 3.0 * R_ove
         - 2.5 * abs(fhf - SPEC["defe_face_h"])
         - 2.0 * abs(sep - SPEC["sep"])
         - 1.5 * abs(abs(dcy - (G["face_box"][1] + G["face_box"][3]) / 2 / H)
                     - SPEC["dcy"]) / SPEC["dcy_max"]
         - 1.5 * abs(G["lead"] - SPEC["lead"]) / 0.10
         - 1.5 * abs(adeg - aim) / 90.0
         - 1.2 * max(0.0, SPEC["gap_hero_hard"] - gapf) * 26
         + 0.45 * (len(ts["lines"]) == 2)
         + 0.35 * (SPEC["area_lo"] <= ts["w"] * ts["h"] / (W * H) <= SPEC["area_hi"])
         - 0.8 * abs(G["face_h"] - SPEC["hero_face_h"]) / 0.07
         - 0.6 * abs(ts["cap_frac"] - SPEC["cap"]) / 0.010
         - 0.20 * abs(ty / H - SPEC["inset_y"]) / 0.055
         - 0.6 * max(0.0, SPEC["body_clear"] * W - aclear) / (SPEC["body_clear"] * W))
    return dict(J=float(J), P=P, G=G, ts=ts, tx=tx, ty=ty, crop=(x0, y0, cw, ch),
                tip=tip, adeg=adeg, apoly=apoly, amask=amask, an=an,
                astand=astand, ab=ab, aclear=aclear, agap=agap, gapf=gapf,
                sep=sep, fhf=fhf, dcx=dcx, dcy=dcy, trects=trects,
                metrics=dict(occ_type=round(t_occ, 5), rea_type=round(t_rea, 5),
                             hair=round(float(t_hair), 5), uti=round(R_uti, 4),
                             ali=round(R_ali, 4), ove=round(R_ove, 5)))


def box_gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    if dx == 0 and dy == 0:
        return -1.0
    return math.hypot(dx, dy)


def nearest_face_canvas(pt, P, x0, y0, kx, ky, G):
    """Which face is the tip actually nearest to - the defendant, another
    person in the courtroom, or the judge? 'the red arrow actually make sense'."""
    best, who = 1e9, None
    for f in P["faces"]:
        bx = ((f.x - x0) * kx, (f.y - y0) * ky, (f.x + f.w - x0) * kx, (f.y + f.h - y0) * ky)
        dd = math.hypot(max(bx[0] - pt[0], pt[0] - bx[2], 0.0),
                        max(bx[1] - pt[1], pt[1] - bx[3], 0.0))
        if dd < best:
            best, who = dd, ("defendant" if f is P["defe"] else "other_person")
    hb = G["face_box"]
    dd = math.hypot(max(hb[0] - pt[0], pt[0] - hb[2], 0.0),
                    max(hb[1] - pt[1], pt[1] - hb[3], 0.0))
    if dd < best:
        who = "judge"
    return who


# =====================================================================
# render  -  plate -> hero -> GRADE -> arrow -> glow -> type
# =====================================================================
def render(name, b, rep, cfg):
    P, G, ts = b["P"], b["G"], b["ts"]
    x0, y0, cw, ch = b["crop"]
    plate = cv2.resize(P["tile"][y0:y0 + ch, x0:x0 + cw], (W, H),
                       interpolation=cv2.INTER_LANCZOS4)
    base = Image.fromarray(cv2.cvtColor(plate, cv2.COLOR_BGR2RGB)).convert("RGBA")
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lay.paste(Image.fromarray(cv2.cvtColor(G["rgba"], cv2.COLOR_BGRA2RGBA)),
              (G["x"], G["y"]))
    comp = Image.alpha_composite(base, lay)

    # GRADE first, so #FD0101 and the white/yellow are never pushed by it
    gr = grade(cv2.cvtColor(np.asarray(comp.convert("RGB")), cv2.COLOR_RGB2BGR))
    img = Image.fromarray(cv2.cvtColor(gr, cv2.COLOR_BGR2RGB)).convert("RGBA")

    red = Image.new("RGBA", (W, H), SPEC["arrow_rgb"] + (255,))
    red.putalpha(Image.fromarray((b["amask"] * 255).astype(np.uint8)))
    img = Image.alpha_composite(img, red)

    stroke = max(6, int(round(SPEC["stroke"] * W)))
    ox, oy = b["tx"], b["ty"] - ts["ink_dy"]
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, ln in enumerate(ts["lines"]):
        gd.text((ox, oy + i * ts["pitch"]), ln, font=ts["font"], fill=(0, 0, 0, 240),
                stroke_width=stroke + 3, stroke_fill=(0, 0, 0, 240))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(SPEC["glow_blur"])))

    d = ImageDraw.Draw(img)
    done = 0
    for i, ln in enumerate(ts["words"]):
        px = ox
        for w_ in ln:
            col = (255, 255, 255, 255) if done < ts["n_white"] else (255, 216, 0, 255)
            d.text((px, oy + i * ts["pitch"]), w_, font=ts["font"], fill=col,
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            px += d.textlength(w_ + " ", font=ts["font"])
            done += 1

    out = f"{OUTDIR}/L1_system_{name}.jpg"
    img.convert("RGB").save(out, quality=95, subsampling=0, optimize=True)
    verify(name, out, b, rep, ox, oy, stroke)
    rep["out"] = out
    return out


# =====================================================================
# verification - re-measured on the WRITTEN FILE, not on the code
# =====================================================================
def sever_check(occ, exclude_edges=2):
    """A severed limb reads as a perfectly straight silhouette edge inside the
    canvas. CARTHIEF's shipped adaptive build put a 0.358-coverage tile column
    at x~700 and rendered a vertical seam through her robe."""
    a = (occ > 0.5)
    worst_v, worst_h = 0, 0
    Hh, Ww = a.shape
    for sgn, name_ in ((1, "right"), (-1, "left")):
        edge = np.zeros((Hh,), np.int32) - 1
        for y in range(Hh):
            xs = np.flatnonzero(a[y])
            if len(xs) == 0:
                continue
            e = xs.max() if sgn == 1 else xs.min()
            if e <= exclude_edges or e >= Ww - 1 - exclude_edges:
                continue
            edge[y] = e
        run = 0
        for y in range(1, Hh):
            if edge[y] >= 0 and edge[y] == edge[y - 1]:
                run += 1
                worst_v = max(worst_v, run)
            else:
                run = 0
    for sgn in (1, -1):
        edge = np.zeros((Ww,), np.int32) - 1
        for x in range(Ww):
            ys = np.flatnonzero(a[:, x])
            if len(ys) == 0:
                continue
            e = ys.min() if sgn == -1 else ys.max()
            if e <= exclude_edges or e >= Hh - 1 - exclude_edges:
                continue
            edge[x] = e
        run = 0
        for x in range(1, Ww):
            if edge[x] >= 0 and edge[x] == edge[x - 1]:
                run += 1
                worst_h = max(worst_h, run)
            else:
                run = 0
    return worst_v, worst_h


def verify(name, path, b, rep, ox, oy, stroke):
    P, G, ts = b["P"], b["G"], b["ts"]
    x0, y0, cw, ch = b["crop"]
    kx, ky = W / cw, H / ch
    chk = cv2.imread(path)
    v = dict(file=path, size=list(chk.shape[:2][::-1]),
             size_ok=bool(chk.shape[1] == W and chk.shape[0] == H))

    # ---- the type's real ink, as drawn ----
    gi = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(gi)
    for i, ln in enumerate(ts["lines"]):
        gd.text((ox, oy + i * ts["pitch"]), ln, font=ts["font"], fill=255,
                stroke_width=stroke, stroke_fill=255)
    ink = np.asarray(gi) > 0
    nink = int(ink.sum())

    # ---- faces re-detected ON THE OUTPUT FILE ----
    dt = detector(W, H, 0.50)
    _, raw = dt.detect(chk)
    faces = [Det(r) for r in (raw if raw is not None else [])]
    hfb = G["face_box"]
    on_face = 0
    per_face = []
    for f in faces:
        m = np.zeros((H, W), bool)
        m[max(0, int(f.y)):int(f.y + f.h), max(0, int(f.x)):int(f.x + f.w)] = True
        c = int((ink & m).sum())
        per_face.append(dict(cx=round(f.cx / W, 3), cy=round(f.cy / H, 3),
                             h=round(f.h / H, 3), nd=round(f.nd, 3),
                             nv=round(f.nv, 3), roll=round(f.roll, 2), ink_px=c))
        on_face += c
    v["faces_detected_in_output"] = per_face
    v["type_ink_px"] = nink
    v["type_ink_px_on_any_face_box"] = on_face
    v["GATE_no_type_on_a_face"] = bool(on_face == 0)

    body, hair = G["body"], G["hair"]
    v["type_ink_on_hero_body"] = int((ink & body).sum())
    v["type_ink_on_hero_hair_frac"] = round(float((ink & hair).sum()) / max(1, nink), 4)
    v["GATE_no_type_on_hero_body"] = bool((ink & body).sum() == 0)
    v["GATE_type_on_hair_le_2pct"] = bool(v["type_ink_on_hero_hair_frac"] <= SPEC["ink_on_hair"])

    # plate people, mapped from the tile
    ys_, xs_ = np.nonzero(ink)
    TX = np.clip((x0 + xs_ / kx).astype(int), 0, x0 + cw - 1)
    TY = np.clip((y0 + ys_ / ky).astype(int), 0, y0 + ch - 1)
    v["type_ink_on_plate_people_frac"] = round(
        float((P["people"][TY, TX] > 0.5).mean()) if nink else 0.0, 4)

    # ---- the arrow, re-measured from the JPEG's own red pixels ----
    bb, gg, rr = [chk[..., i].astype(int) for i in range(3)]
    redm = ((rr > 185) & (gg < 70) & (bb < 70) & ((rr - gg) > 140)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(redm, 8)
    if n > 1:
        i = max(range(1, n), key=lambda j: st[j, 4])
        ax, ay, aw, ah, aa = [int(q) for q in st[i]]
        comp_mask = (lab == i)
        v["arrow"] = dict(px=aa, bbox=[ax, ay, aw, ah],
                          fill_ratio=round(aa / float(aw * ah), 3),
                          area_frac=round(aa / float(W * H), 5),
                          heading_deg=round(b["adeg"], 1),
                          tip=[round(q, 1) for q in b["tip"]],
                          standoff_px=round(b["astand"], 1),
                          body_clearance_px=round(b["aclear"], 1),
                          gap_to_type_px=round(b["agap"], 1))
        ys2, xs2 = np.nonzero(comp_mask)
        pTX = np.clip((x0 + xs2 / kx).astype(int), 0, x0 + cw - 1)
        pTY = np.clip((y0 + ys2 / ky).astype(int), 0, y0 + ch - 1)
        onp = int((P["people"][pTY, pTX] > 0.5).sum()) + int((G["occ"][ys2, xs2] > 0.10).sum())
        onf = sum(int((comp_mask & _bm(f)).sum()) for f in faces)
        v["arrow"]["px_on_a_person"] = onp
        v["arrow"]["px_on_a_detected_face_box"] = onf
        v["GATE_arrow_zero_px_on_a_person"] = bool(onp == 0 and onf == 0)
        v["GATE_arrow_fill_0.44_0.48"] = bool(0.42 <= aa / float(aw * ah) <= 0.50)
        v["GATE_arrow_area_in_band"] = bool(SPEC["arrow_area_lo"] <= aa / float(W * H)
                                            <= SPEC["arrow_area_hi"])
    else:
        v["arrow"] = None
        v["GATE_arrow_zero_px_on_a_person"] = False

    # does the RAY actually reach the defendant?
    dfb = ((P["defe"].x - x0) * kx, (P["defe"].y - y0) * ky,
           (P["defe"].x + P["defe"].w - x0) * kx, (P["defe"].y + P["defe"].h - y0) * ky)
    th = math.radians(b["adeg"])
    ux, uy = math.cos(th), math.sin(th)
    hit, step = False, 0.0
    while step < 400:
        qx, qy = b["tip"][0] + ux * step, b["tip"][1] + uy * step
        if not (0 <= qx < W and 0 <= qy < H):
            break
        if dfb[0] <= qx <= dfb[2] and dfb[1] <= qy <= dfb[3]:
            hit = True
            break
        step += 1.0
    v["defendant_face_box"] = [round(q, 1) for q in dfb]
    v["GATE_ray_from_tip_reaches_defendant_face_box"] = bool(hit)
    v["ray_travel_px_to_defendant"] = round(step, 1) if hit else None
    v["arrow_tip_nearest_face"] = nearest_face_canvas(b["tip"], P, x0, y0, kx, ky, G)
    v["GATE_tip_nearest_face_is_defendant"] = bool(v["arrow_tip_nearest_face"] == "defendant")
    v["GATE_standoff_4_to_83px"] = bool(SPEC["standoff_min"] <= b["astand"]
                                        <= SPEC["standoff_max"] * W)

    # ---- arrangement ----
    hcx = (hfb[0] + hfb[2]) / 2 / W; hcy = (hfb[1] + hfb[3]) / 2 / H
    v["separation_W"] = round(abs(hcx - b["dcx"]), 4)
    v["delta_cy_H"] = round(abs(hcy - b["dcy"]), 4)
    v["hero_eye_xy"] = [round(G["eye"][0] / W, 4), round(G["eye"][1] / H, 4)]
    v["hero_face_h_H"] = round((hfb[3] - hfb[1]) / H, 4)
    v["defendant_face_h_H"] = round(b["fhf"], 4)
    v["hero_defendant_height_ratio"] = round((hfb[3] - hfb[1]) / H / max(1e-6, b["fhf"]), 3)
    v["gap_type_to_hero_face_W"] = round(b["gapf"], 4)
    v["GATE_separation_0.42_0.58"] = bool(SPEC["sep_lo"] <= v["separation_W"] <= SPEC["sep_hi"])
    v["GATE_delta_cy_le_0.22"] = bool(v["delta_cy_H"] <= SPEC["dcy_max"])
    v["GATE_eye_at_lead_and_0.327H"] = bool(
        abs(v["hero_eye_xy"][0] - (SPEC["lead"] if G["side"] == "R" else 1 - SPEC["lead"])) <= 0.04
        and abs(v["hero_eye_xy"][1] - SPEC["eye_y"]) <= 0.015)
    v["GATE_gap_type_to_hero_face_ge_0.038W"] = bool(b["gapf"] >= SPEC["gap_hero_hard"])

    # ---- severed limb ----
    sv, sh = sever_check(G["occ"])
    v["longest_straight_silhouette_run_px"] = dict(vertical=int(sv), horizontal=int(sh))
    v["GATE_no_severed_limb"] = bool(sv < 0.08 * H and sh < 0.08 * W)
    v["hero_bleed_px_past_edge"] = int(G["bleed_px"])
    v["hero_bottom_row_coverage"] = round(G["bottom_cov"], 3)
    v["hero_matte_quality"] = rep["hero_chosen"]["matte"]

    # ---- eyes level and directed (the hero, re-measured on the OUTPUT) ----
    cand = [f for f in faces if abs(f.cx / W - hcx) < 0.10 and abs(f.cy / H - hcy) < 0.10]
    if cand:
        f = max(cand, key=lambda q: q.h)
        v["hero_in_output"] = dict(nd=round(f.nd, 3), nv=round(f.nv, 3),
                                   roll=round(f.roll, 2))
        v["GATE_hero_eyes_level_not_down"] = bool(
            f.nv <= SPEC["gate_pitch"] and abs(f.roll) <= SPEC["gate_roll"] + 2)
        v["GATE_hero_gaze_into_frame"] = bool(
            (f.nd < 0) if G["side"] == "R" else (f.nd > 0))
    else:
        v["hero_in_output"] = None
        v["GATE_hero_eyes_level_not_down"] = None
        v["GATE_hero_gaze_into_frame"] = None

    # ---- free rectangle ----
    ppl = (G["occ"] > 0.5)
    up = cv2.resize((P["people"][y0:y0 + ch, x0:x0 + cw] > 0.5).astype(np.uint8),
                    (W, H), interpolation=cv2.INTER_NEAREST) > 0
    allp = ppl | up
    for f in faces:
        allp |= _bm(f)
    # dilate before the 4x decimation so the free rect can never claim a
    # person pixel that decimation happened to skip
    big = cv2.dilate(allp.astype(np.uint8), np.ones((5, 5), np.uint8))
    small = cv2.resize(big, (W // 4, H // 4), interpolation=cv2.INTER_NEAREST) > 0
    area, fx0, fy0, fx1, fy1 = max_free_rect(~small)
    R = [fx0 * 4, fy0 * 4, fx1 * 4, fy1 * 4]
    inside = int(ink[R[1]:R[3], R[0]:R[2]].sum())
    v["free_rect"] = dict(rect=R, frac_of_frame=round(area * 16 / float(W * H), 4),
                          type_ink_inside_frac=round(inside / max(1, nink), 4),
                          on_type_side=bool((R[0] + R[2]) / 2 < W / 2) == (G["side"] == "R"))
    v["GATE_type_in_free_rect_ge_0.60"] = bool(inside / max(1, nink) >= SPEC["freerect_floor"])

    # ---- alignment + tone ----
    v["ali"] = round(ali_penalty([(b["tx"], b["ty"], b["tx"] + ts["w"], b["ty"] + ts["h"]),
                                  b["ab"],
                                  (max(0, G["x"]), max(0, G["y"]),
                                   min(W, G["x"] + G["w"]), H)]), 4)
    v["GATE_ali_le_0.06"] = bool(v["ali"] <= 0.06)
    lum = cv2.cvtColor(chk, cv2.COLOR_BGR2GRAY)
    v["luminance_mean"] = round(float(lum.mean()), 1)
    v["blacks_frac_below_16"] = round(float((lum < 16).mean()), 4)
    v["type"] = dict(lines=ts["lines"], cap_px=ts["cap"], cap_frac=round(ts["cap"] / H, 4),
                     pitch_px=ts["pitch"], break_frac=round(ts["break_frac"], 3),
                     line2_all_yellow=ts["line2_yellow"], wmax=ts["wmax_frac"],
                     left_inset_frac=round(b["tx"] / W, 4),
                     top_inset_frac=round(b["ty"] / H, 4),
                     area_frac=round(ts["w"] * ts["h"] / float(W * H), 4))
    v["crop"] = dict(tile_rect=[x0, y0, cw, ch], upscale=round(W / cw, 3),
                     plate_frame_t=round(P["t"], 2))
    gates = {k: val for k, val in v.items() if k.startswith("GATE_")}
    v["GATES_PASSED"] = sum(1 for q in gates.values() if q is True)
    v["GATES_TOTAL"] = len(gates)
    v["GATES_FAILED"] = [k for k, q in gates.items() if q is not True]
    rep["verification"] = v
    rep["metrics"] = b["metrics"]
    rep["J"] = round(b["J"], 4)
    log("VERIFY", name, f'{v["GATES_PASSED"]}/{v["GATES_TOTAL"]} gates',
        "FAILED:" if v["GATES_FAILED"] else "all pass", v["GATES_FAILED"])
    return v


def _bm(f):
    m = np.zeros((H, W), bool)
    m[max(0, int(f.y)):int(f.y + f.h), max(0, int(f.x)):int(f.x + f.w)] = True
    return m


# =====================================================================
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    names = args or list(JOBS)
    if "--all" in sys.argv:
        names = list(JOBS)
    summary = []
    for nm in names:
        try:
            r = build(nm)
        except Exception as e:
            import traceback
            traceback.print_exc()
            r = dict(hearing=nm, refused=f"EXCEPTION {e}")
        summary.append(r)
    log("\n================ SUMMARY ================")
    for r in summary:
        if r.get("refused"):
            log(f'{r["hearing"]:9s} REFUSED  {r["refused"]}')
        else:
            v = r["verification"]
            log(f'{r["hearing"]:9s} {v["GATES_PASSED"]}/{v["GATES_TOTAL"]} gates  '
                f'sep {v["separation_W"]}  dcy {v["delta_cy_H"]}  '
                f'gap {v["gap_type_to_hero_face_W"]}  ali {v["ali"]}  '
                f'-> {r["out"]}')
            if v["GATES_FAILED"]:
                log(f'{"":9s} FAILED: {v["GATES_FAILED"]}')
