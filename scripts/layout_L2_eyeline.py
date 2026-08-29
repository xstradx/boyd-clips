"""L2_eyeline - the EYELINE leads the whole arrangement.

    python scripts/layout_L2_eyeline.py CARTHIEF|SANCHEZ|OFFERUP|ALL

THE THESIS
    Every arrangement decision is derived from one measurement: where the two
    subjects are looking.

      1. which tile holds the bench and which holds the courtroom -> measured
         (caption OCR, then face-count/dominance fallback). Never "the judge is
         on the left": she is on the LEFT in one of these hearings and on the
         RIGHT in the other two.
      2. WHICH FRAME the hero comes from -> the frame where she is looking INTO
         the room, gated against a HEARING-LEVEL gaze census. Never a timestamp.
      3. WHICH EDGE she bleeds off -> the edge she is NOT facing.
         side = -sign(median nd) over the whole hearing.
      4. WHERE THE TYPE GOES -> in the direction of her gaze: the corner her
         look opens up.
      5. WHERE THE ARROW GOES -> ON the eye path. Its direction is the vector
         from her eye midpoint to the defendant's head; the tip is walked back
         along that ray until it clears every person. The arrow is the visible
         part of the look.
      6. HOW BIG the hero is -> solved so the eyeline lands at the measured
         house height (0.327 H) with the cut-out bottom-anchored. Face height
         yields to the eyeline, not the other way round.

    Nothing here is keyed to a case. The per-hearing dict carries only SOURCE
    facts (file, stream offset, the Zoom tile rects, the case range) and the
    COPY. The HOUSE block is style measured across the six shipped thumbnails
    and is byte-identical for all three hearings.

LICENCES (monetised channel)
    YuNet model                      MIT   (opencv_zoo face_detection_yunet)
    birefnet-portrait / -general-lite MIT  (rembg's DEFAULT bria-rmbg is
                                            CC BY-NC and is never selected)
    rembg                            MIT
    RapidOCR                         Apache-2.0
    SmartText (mechanism only)       MIT
    PosterLayout metrics             no licence file -> reimplemented from the
                                     definitions in eval.py, no code copied
    Court footage                    public record
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
sys.path.insert(0, os.path.join(ROOT, "scripts", "adaptive"))
from layout_core import (Face, ali_penalty, build_field, burnin_mask,  # noqa: E402
                         detect_faces, integral, overlap_ratio, rect_sum)

YUNET = f"{ROOT}/models/yunet.onnx"
FONT = f"{ROOT}/assets/fonts/TTTHeadline-Regular.ttf"
OUTDIR = "C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/LAYOUT"
CACHE = os.path.join(ROOT, "scripts", "_l2cache")
W, H = 1280, 720

# ===========================================================================
# SOURCE FACTS + COPY. No layout numbers live here.
# ===========================================================================
HEARINGS = {
    "CARTHIEF": dict(
        src=f"{ROOT}/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
        off=3554.0, case=(3574.0, 4628.0),
        tiles={"A": (612, 338, 18, 190), "B": (620, 338, 644, 190)},
        white="18 years old and", yellow="already in cuffs"),
    "SANCHEZ": dict(
        src=f"{ROOT}/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
        off=3683.0, case=(3703.0, 4148.0),
        tiles={"A": (468, 348, 726, 6), "B": (628, 348, 6, 6)},
        white="You are why your son", yellow="is struggling"),
    "OFFERUP": dict(
        src=f"{ROOT}/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
        off=10550.0, case=(10570.0, 11117.0),
        tiles={"A": (628, 348, 646, 186), "B": (628, 348, 6, 186)},
        white="Do you want", yellow="a jury trial?"),
}

# ===========================================================================
# HOUSE STYLE. Every value measured; the measurement is named beside it.
# ===========================================================================
HOUSE = dict(
    # --- hero -------------------------------------------------------------
    eye_y=0.327,             # 6 shipped, median 0.327 H, IQR 0.325-0.334
    hero_face_lo=0.38, hero_face_hi=0.52,     # shipped 0.383-0.559
    lead_opts=(0.743, 0.750, 0.760, 0.770, 0.783),   # Audit nose-room IQR
    lead_target=0.750,       # Audit median
    bleed_min=0.02,          # of W. DEFAULT, not corpus-measured
    # --- hero frame gates --------------------------------------------------
    gate_nd=0.20,            # |nd| >= this, and sign == hearing median sign
    gate_nv=0.50,            # higher = looking down; 0.41 up vs 0.63 reading
    gate_roll=4.0,           # deg; shipped heroes 0.48-2.28
    gate_face_in_tile=0.33,  # faceH / tileH, keeps the upscale <= 2.7x
    phantom_max=0.15,        # boundary px with local |grad| < 35; n=3 default
    edge_touch_max=0.02,     # matte coverage of a NON-bleed tile column
    # --- plate --------------------------------------------------------------
    defe_face_h=0.22, defe_face_lo=0.19, defe_face_hi=0.33,   # shipped med .219
    sep=0.50, sep_lo=0.42, sep_hi=0.58,      # corpus n=32, med .5116
    dcy=0.09, dcy_max=0.22,                  # corpus med .0945
    upscale_max=2.7,
    # --- type ---------------------------------------------------------------
    cap_opts=(0.100, 0.095, 0.090),   # 6/6 measure 0.0986-0.1014; floor .0806
    pitch=1.42,                       # baselines 99->202 = 103 px, 5/5
    inset_x=0.0211, inset_y=0.0375,   # 27 px on both axes
    top_y_max=0.092,                  # Audit's own max top inset
    wmax_opts=(0.82, 0.78, 0.74, 0.70, 0.66, 0.62),
    break_target=0.75, break_min=0.55,
    stroke=0.0086, glow_blur=10,
    face_gap=0.038, face_gap_target=0.082,
    hair_max=0.02,
    area_lo=0.13, area_hi=0.26,
    # --- arrow --------------------------------------------------------------
    arrow_len=0.096, arrow_shaft=0.240, arrow_head=0.475,
    arrow_area=0.00448, arrow_col=(253, 1, 1),
    arrow_house_deg=137.9,
    arrow_eye_tol=25.0,      # deg either side of the EYE PATH - the L2 rule
    standoff_min=4.0, standoff_max=0.065,
    body_clear=0.054,
    text_gap=0.046,
    # --- grade ---------------------------------------------------------------
    lum_mean=125.0, blacks=0.090,
)
ST_BORDER = 4 / 120.0   # SmartText generate_candidates.py forbidden border

# ===========================================================================
# THE YIELD LADDER. Identical for every hearing, walked in order, and the rung
# that was reached is REPORTED. Above the line nothing ever yields: 1280x720,
# zero type ink on a face, zero type ink on a body, zero arrow px on a person,
# the arrow's ray reaching the tracked defendant, no severed limb, and the
# 0.038 W type -> hero-face corridor. Below the line the two things that give
# way are the corpus SEPARATION band and the upscale ceiling - because both are
# bounded by the Zoom grid this hearing happens to have been shot on, not by
# taste. A rung > 0 is a measured statement about the SOURCE, not a fudge.
# ===========================================================================
YIELD = (
    dict(rung=0, why="corpus band (n=32, median 0.5116)",
         sep=(0.42, 0.58), upscale=2.7, defe=(0.19, 0.33), dcy=0.22),
    dict(rung=1, why="separation widened to the shipped-six range",
         sep=(0.36, 0.62), upscale=2.7, defe=(0.19, 0.33), dcy=0.22),
    dict(rung=2, why="+ upscale ceiling 3.0x (the 2.7x figure is a default, "
                     "not corpus-measured)",
         sep=(0.32, 0.64), upscale=3.0, defe=(0.185, 0.34), dcy=0.22),
    dict(rung=3, why="+ upscale 3.3x, defendant-face band to the shipped range",
         sep=(0.27, 0.66), upscale=3.3, defe=(0.17, 0.36), dcy=0.22),
)


# ===========================================================================
# geometry on a YuNet face
# ===========================================================================
def eye_mid(f):
    return ((f.lex + f.rex) / 2.0, (f.ley + f.rey) / 2.0)


def mouth_mid(f):
    return ((f.mlx + f.mrx) / 2.0, (f.mly + f.mry) / 2.0)


def nd(f):
    """nose deviation / interocular. NEGATIVE = head turned image-LEFT."""
    io = f.interocular
    if io < 1e-6:
        return 0.0
    ex, _ = eye_mid(f)
    return (f.nx - ex) / io


def nv(f):
    """de-rolled pitch proxy: how far down the eye->mouth run the nose sits.
    HIGHER = looking DOWN. Rendered check: 0.41-0.47 head up, 0.62-0.64 reading."""
    ex, ey = eye_mid(f)
    mx, my = mouth_mid(f)
    th = -math.radians(f.roll)
    c, s = math.cos(th), math.sin(th)

    def rot(px, py):
        dx, dy = px - ex, py - ey
        return (dx * c - dy * s, dx * s + dy * c)

    _, ny_ = rot(f.nx, f.ny)
    _, my_ = rot(mx, my)
    if abs(my_) < 1e-6:
        return 0.0
    return ny_ / my_


def med(a):
    return float(np.median(a)) if len(a) else 0.0


# ===========================================================================
# STAGE A - perception across the whole hearing
# ===========================================================================
def sample_hearing(cfg, n_target=200, name=""):
    """Decode ~n_target frames spread across the CASE range and detect faces in
    both tiles. The only decode sweep; every later stage reads this."""
    os.makedirs(CACHE, exist_ok=True)
    cp = os.path.join(CACHE, f"census_{name}_{n_target}.json")
    if os.path.exists(cp):
        raw = json.load(open(cp))
        out = []
        for r in raw["s"]:
            out.append({"f": r["f"], "t": r["t"], "sharp": r["sharp"],
                        "tiles": {k: [Face(*v[:14], score=v[14]) for v in vs]
                                  for k, vs in r["tiles"].items()}})
        return out, raw["fps"]
    t0, t1 = cfg["case"]
    off = cfg["off"]
    cap = cv2.VideoCapture(cfg["src"])
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    nfr = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    f_lo = max(0, int((t0 - off) * fps))
    f_hi = min(int((t1 - off) * fps), nfr - 2)
    idx = np.unique(np.linspace(f_lo, f_hi, n_target).astype(int))
    out = []
    for i in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        rec = {"f": int(i), "t": off + i / fps, "tiles": {}, "sharp": {}}
        for k, (tw, th, tx, ty) in cfg["tiles"].items():
            img = fr[ty:ty + th, tx:tx + tw]
            rec["tiles"][k] = detect_faces(img, YUNET, 0.55)
            rec["sharp"][k] = float(cv2.Laplacian(
                cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_32F).var())
        out.append(rec)
    cap.release()
    json.dump({"fps": fps, "s": [
        {"f": r["f"], "t": r["t"], "sharp": r["sharp"],
         "tiles": {k: [[f.x, f.y, f.w, f.h, f.lex, f.ley, f.rex, f.rey, f.nx,
                        f.ny, f.mlx, f.mly, f.mrx, f.mry, f.score] for f in fs]
                   for k, fs in r["tiles"].items()}} for r in out]},
        open(cp, "w"))
    return out, fps


def grab(cfg, frame_idx):
    cap = cv2.VideoCapture(cfg["src"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, fr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"decode failed at frame {frame_idx}")
    return fr


_OCR = None


def read_caption(bgr):
    """The court's own burned-in tile label. READ, never inferred from where
    the tile sits."""
    global _OCR
    try:
        if _OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
    except Exception:
        return ""
    h, w = bgr.shape[:2]
    band = bgr[int(h * 0.78):h, 0:int(w * 0.62)]
    band = cv2.resize(band, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    res, _ = _OCR(band)
    return " ".join(r[1] for r in (res or [])).upper()


def cluster_faces(samples, key, tile_w, tile_h):
    """A person is a CLUSTER over time, not the biggest box in one frame.
    Tolerance (dcx < 0.06 tile widths, |d log h| < 0.35)."""
    cl = []
    for si, rec in enumerate(samples):
        for f in rec["tiles"][key]:
            hit = None
            for c in cl:
                if (abs(f.cx - c["cx"]) < 0.06 * tile_w
                        and abs(math.log(max(f.h, 1.0))
                                - math.log(max(c["h"], 1.0))) < 0.35):
                    hit = c
                    break
            if hit is None:
                cl.append(dict(cx=f.cx, cy=f.cy, h=f.h, n=1,
                               members=[(si, f)], frames={si}))
            else:
                k = hit["n"]
                hit["cx"] = (hit["cx"] * k + f.cx) / (k + 1)
                hit["cy"] = (hit["cy"] * k + f.cy) / (k + 1)
                hit["h"] = (hit["h"] * k + f.h) / (k + 1)
                hit["n"] = k + 1
                hit["members"].append((si, f))
                hit["frames"].add(si)
    for c in cl:
        nds = [nd(f) for _, f in c["members"]]
        nvs = [nv(f) for _, f in c["members"]]
        c["persistence"] = round(len(c["frames"]) / max(1, len(samples)), 3)
        c["nd_med"] = round(med(nds), 4)
        c["nv_med"] = round(med(nvs), 4)
        c["nd_p10"] = round(float(np.percentile(nds, 10)), 4)
        c["nd_p90"] = round(float(np.percentile(nds, 90)), 4)
        c["nv_p10"] = round(float(np.percentile(nvs, 10)), 4)
        c["h_frac"] = round(c["h"] / tile_h, 4)
        c["cx_frac"] = round(c["cx"] / tile_w, 4)
    return sorted(cl, key=lambda c: -c["n"])


def brief(c):
    return {k: c[k] for k in ("n", "persistence", "cx_frac", "h_frac",
                              "nd_med", "nd_p10", "nd_p90", "nv_med", "nv_p10")}


# ===========================================================================
# matte
# ===========================================================================
_SESS = {}


def matte(bgr, key, model="birefnet-portrait"):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{key}_{model}.png")
    if os.path.exists(p):
        a = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if a is not None and a.shape == bgr.shape[:2]:
            return a.astype(np.float32) / 255.0
    from rembg import new_session, remove
    if model not in _SESS:
        _SESS[model] = new_session(model)   # MIT weights only
    rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    a = np.asarray(remove(rgb, session=_SESS[model],
                          post_process_mask=True).split()[-1])
    cv2.imwrite(p, a)
    return a.astype(np.float32) / 255.0


def matte_quality(bgr, alpha):
    """The computable form of 'surgical cuts not slop'. A cut that follows a
    real edge sits on several times the image's own median gradient; a cut
    through a flat forearm does not."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag = np.sqrt(gx * gx + gy * gy)
    hard = (alpha > 0.5).astype(np.uint8)
    band = (cv2.dilate(hard, np.ones((3, 3), np.uint8))
            - cv2.erode(hard, np.ones((3, 3), np.uint8))) > 0
    if band.sum() == 0:
        return dict(ok=False, reason="empty matte")
    bmed = float(np.median(mag[band]))
    imed = float(np.median(mag)) or 1e-6
    hh, ww = hard.shape
    return dict(ok=True, boundary_grad=round(bmed, 1), tile_grad=round(imed, 1),
                ratio=round(bmed / imed, 2),
                phantom=round(float((mag[band] < 35).mean()), 3),
                touch_L=round(float(hard[:, 0].mean()), 3),
                touch_R=round(float(hard[:, ww - 1].mean()), 3),
                touch_T=round(float(hard[0, :].mean()), 3),
                coverage=round(float(hard.mean()), 3))


def gesture_score(alpha, f):
    """Mid-gesture hands add drama; a hand on the chin does not. PROXY:
    alpha below the chin and outside the torso column, over face-box area.
    Labelled a proxy; used only as a tiebreak, never as a gate."""
    hh, ww = alpha.shape
    y0 = int(min(hh - 1, f.y + f.h))
    y1 = int(min(hh, f.y + f.h * 2.6))
    if y1 <= y0:
        return 0.0
    band = alpha[y0:y1] > 0.5
    outside = np.abs(np.arange(ww) - f.cx) > 1.05 * f.w
    return float((band & outside[None, :]).sum()) / max(1.0, f.w * f.h)


# ===========================================================================
# type
# ===========================================================================
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
    """Greedy wrap that FILLS line 1 - what the shipped thumbnails do. Returns
    per-line INK rects, not em boxes (136 px em vs 91 px ink at cap 85)."""
    font = font_for_cap(cap_px)
    d = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    words = (white + " " + yellow).split()
    n_white = len(white.split())
    lines, cur = [], []
    for w_ in words:
        if cur and d.textlength(" ".join(cur + [w_]), font=font) > wmax:
            lines.append(cur)
            cur = [w_]
        else:
            cur.append(w_)
    if cur:
        lines.append(cur)
    if not lines or len(lines) > 2:
        return None
    pitch = int(round(cap_px * HOUSE["pitch"]))
    rects, wid = [], []
    for i, ln in enumerate(lines):
        bb = font.getbbox(" ".join(ln))
        rects.append([int(bb[0]), i * pitch + int(bb[1]),
                      int(bb[2]), i * pitch + int(bb[3])])
        wid.append(int(bb[2]) - int(bb[0]))
    y0 = min(r[1] for r in rects)
    x0 = min(r[0] for r in rects)
    rects = [[a - x0, b - y0, c - x0, e - y0] for a, b, c, e in rects]
    n1 = len(lines[0])
    if n_white >= n1:
        bf = 1.0
    elif n_white == 0:
        bf = 0.0
    else:
        bf = float(d.textlength(" ".join(lines[0][:n_white]) + " ",
                                font=font)) / max(1.0, wid[0])
    return dict(font=font, cap=cap_px, lines=[" ".join(l) for l in lines],
                rects=rects, pitch=pitch,
                w=max(r[2] for r in rects), h=max(r[3] for r in rects),
                n_white=n_white, ink_dx=x0, ink_dy=y0,
                break_frac=round(bf, 3),
                line2_yellow=bool(len(lines) < 2 or n_white <= n1),
                line1_w=wid[0], n_lines=len(lines))


def ink_mask(ts, ox, oy, stroke):
    g = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(g)
    for i, ln in enumerate(ts["lines"]):
        d.text((ox, oy + i * ts["pitch"]), ln, font=ts["font"], fill=255,
               stroke_width=stroke, stroke_fill=255)
    return np.asarray(g) > 0


# ===========================================================================
# arrow
# ===========================================================================
def arrow_poly(start, tip):
    sx, sy = start
    tx, ty = tip
    L = math.hypot(tx - sx, ty - sy)
    if L < 1:
        return None
    ux, uy = (tx - sx) / L, (ty - sy) / L
    px, py = -uy, ux
    shaft = L * HOUSE["arrow_shaft"] * 0.5
    hx, hy = tx - ux * L * (1 - HOUSE["arrow_head"]), ty - uy * L * (1 - HOUSE["arrow_head"])
    hw = shaft * 2.4
    return np.array([[sx + px * shaft, sy + py * shaft],
                     [hx + px * shaft, hy + py * shaft],
                     [hx + px * hw, hy + py * hw],
                     [tx, ty],
                     [hx - px * hw, hy - py * hw],
                     [hx - px * shaft, hy - py * shaft],
                     [sx - px * shaft, sy - py * shaft]], dtype=np.int32)


def raster_arrow(start, tip):
    m = np.zeros((H, W), np.uint8)
    pts = arrow_poly(start, tip)
    if pts is not None:
        cv2.fillPoly(m, [pts], 1)
    return m


# ===========================================================================
# largest people-free rectangle
# ===========================================================================
def max_free_rect(free):
    h, w = free.shape
    heights = np.zeros(w + 1, np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(h):
        heights[:w] = np.where(free[y], heights[:w] + 1, 0)
        stack = []
        for x in range(w + 1):
            cur = int(heights[x]) if x < w else 0
            start = x
            while stack and stack[-1][1] >= cur:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, sx, y - sh + 1, x, y + 1)
                start = sx
            stack.append((start, cur))
    return best


# ===========================================================================
# grade
# ===========================================================================
def grade(bgr):
    """Light and measured: solve a gamma for the house luminance mean, then a
    black point for the house blacks fraction. Reported, not eyeballed."""
    f = bgr.astype(np.float32) / 255.0
    m = max(1.0, float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()))
    g = float(np.clip(math.log(HOUSE["lum_mean"] / 255.0)
                      / math.log(m / 255.0), 0.75, 1.35))
    f = np.power(f, g)
    q = float(np.quantile(cv2.cvtColor((f * 255).astype(np.uint8),
                                       cv2.COLOR_BGR2GRAY), HOUSE["blacks"])) / 255.0
    f = np.clip((f - q * 0.85) / max(1e-3, 1.0 - q * 0.85), 0, 1)
    out = (f * 255).astype(np.uint8)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.10, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR), round(g, 3)


# ===========================================================================
# THE BUILD
# ===========================================================================
def build(name, n_samples=200, verbose=True):
    t_start = time.time()
    cfg = HEARINGS[name]
    os.makedirs(OUTDIR, exist_ok=True)
    log = dict(hearing=name, spec="L2_eyeline",
               copy=dict(white=cfg["white"], yellow=cfg["yellow"]))

    # ---------- A. perceive -------------------------------------------------
    samples, fps = sample_hearing(cfg, n_samples, name)
    log["census"] = dict(frames_sampled=len(samples), fps=round(fps, 3),
                         case_range=list(cfg["case"]))
    if verbose:
        print(f"[{name}] sampled {len(samples)} frames  ({time.time()-t_start:.0f}s)")

    # ---------- B. roles: measured, never a side ----------------------------
    mid = samples[len(samples) // 2]
    fr_mid = grab(cfg, mid["f"])
    caps = {}
    for k, (tw, th, tx, ty) in cfg["tiles"].items():
        caps[k] = read_caption(fr_mid[ty:ty + th, tx:tx + tw])
    court = [k for k, v in caps.items() if "187" in v or " DC" in " " + v]
    if len(court) == 1:
        court_k, how = court[0], "caption OCR"
    else:
        stat = {k: (np.mean([len(s["tiles"][k]) for s in samples]),
                    np.mean([(s["tiles"][k][0].h / s["tiles"][k][1].h)
                             if len(s["tiles"][k]) > 1 else 99.0
                             for s in samples])) for k in cfg["tiles"]}
        court_k = max(stat, key=lambda k: (stat[k][0], -stat[k][1]))
        how = "face-count/dominance fallback"
    bench_k = [k for k in cfg["tiles"] if k != court_k][0]
    ctw, cth, ctx, cty = cfg["tiles"][court_k]
    btw, bth, btx, bty = cfg["tiles"][bench_k]
    log["roles"] = dict(method=how, court_tile=court_k, bench_tile=bench_k,
                        captions=caps,
                        bench_tile_rect=[btw, bth, btx, bty],
                        court_tile_rect=[ctw, cth, ctx, cty],
                        bench_side_in_grid=("LEFT" if btx < ctx else "RIGHT"),
                        mean_faces={k: round(float(np.mean(
                            [len(s["tiles"][k]) for s in samples])), 2)
                            for k in cfg["tiles"]})

    # ---------- C. the eyeline census ---------------------------------------
    bench_cl = cluster_faces(samples, bench_k, btw, bth)
    court_cl = cluster_faces(samples, court_k, ctw, cth)
    judge = bench_cl[0]
    persistent = [c for c in court_cl if c["persistence"] >= 0.25] or court_cl[:3]
    defe_cl = min(persistent, key=lambda c: abs(c["cx"] - ctw / 2.0))
    nd_h = judge["nd_med"]
    if abs(nd_h) < 0.12:
        raise SystemExit(f"REFUSE {name}: hearing-median nd={nd_h:.3f} is "
                         "inside the frontal dead-band - no eyeline to lead on")
    side = "R" if nd_h < 0 else "L"          # bleed off the edge she is NOT facing
    gaze = "image-LEFT" if nd_h < 0 else "image-RIGHT"
    type_side = "L" if nd_h < 0 else "R"     # the type goes where she is looking
    log["eyeline"] = dict(
        judge_cluster=brief(judge), defendant_cluster=brief(defe_cl),
        other_court_clusters=[brief(c) for c in persistent if c is not defe_cl][:4],
        hearing_median_nd=nd_h, gaze=gaze,
        hero_bleeds=("RIGHT" if side == "R" else "LEFT"),
        type_corner=("TOP-LEFT" if type_side == "L" else "TOP-RIGHT"),
        rule="side = -sign(median nd) over the hearing; type on the gaze side",
        frac_frames_turned=round(float(np.mean(
            [1.0 if (nd(f) < 0) == (nd_h < 0) and abs(nd(f)) >= HOUSE["gate_nd"]
             else 0.0 for _, f in judge["members"]])), 3))
    if verbose:
        print(f"[{name}] roles={how} bench={bench_k}"
              f"({log['roles']['bench_side_in_grid']}) nd={nd_h:+.3f} "
              f"gaze {gaze} -> hero {log['eyeline']['hero_bleeds']}, "
              f"type {log['eyeline']['type_corner']}")

    # ---------- D. hero frame: a GATE, not a timestamp ----------------------
    sgn = -1.0 if nd_h < 0 else 1.0
    pool = []
    for si, f in judge["members"]:
        v_nd, v_nv = nd(f), nv(f)
        if v_nd * sgn < HOUSE["gate_nd"]:
            continue
        if v_nv > HOUSE["gate_nv"]:
            continue
        if abs(f.roll) > HOUSE["gate_roll"]:
            continue
        if f.h / bth < HOUSE["gate_face_in_tile"]:
            continue
        pool.append((si, f, v_nd, v_nv))
    log["hero_gate"] = dict(
        candidates=len(judge["members"]), passed=len(pool),
        gates=dict(nd=f"nd*{int(sgn)} >= {HOUSE['gate_nd']}",
                   nv=f"<= {HOUSE['gate_nv']}", roll=f"<= {HOUSE['gate_roll']} deg",
                   face_in_tile=f">= {HOUSE['gate_face_in_tile']}"))
    if not pool:
        raise SystemExit(f"REFUSE {name}: no frame passes the eyes-level gate")
    pool.sort(key=lambda p: (p[3], -abs(p[2])))     # lowest nv, then most turned

    hero = None
    tried = []
    for si, f, v_nd, v_nv in pool[:10]:
        rec = samples[si]
        fr = grab(cfg, rec["f"])
        img = fr[bty:bty + bth, btx:btx + btw]
        a = matte(img, f"{name}_bench_{rec['f']}")
        q = matte_quality(img, a)
        q["frame"] = rec["f"]
        q["nd"] = round(v_nd, 3)
        q["nv"] = round(v_nv, 3)
        q["roll"] = round(f.roll, 2)
        q["gesture"] = round(gesture_score(a, f), 3)
        # the tile-edge rule: a matte that reaches a tile column is ALREADY
        # severed there. That column has to become the frame edge she bleeds
        # off; if it is the other side, the sever lands inside the canvas.
        far = q["touch_L"] if side == "R" else q["touch_R"]
        q["non_bleed_column_touch"] = far
        q["pass"] = bool(q["ok"] and q["phantom"] <= HOUSE["phantom_max"]
                         and far <= HOUSE["edge_touch_max"])
        tried.append(q)
        if q["pass"] and hero is None:
            hero = dict(frame=rec["f"], t=rec["t"], face=f, img=img, alpha=a,
                        nd=v_nd, nv=v_nv, q=q)
        if hero is not None and len([t for t in tried if t["pass"]]) >= 3:
            break
    log["hero_frames_tried"] = tried
    if hero is None:
        raise SystemExit(f"REFUSE {name}: every gated hero frame fails the "
                         f"matte gate (phantom<= {HOUSE['phantom_max']}, "
                         f"non-bleed column touch <= {HOUSE['edge_touch_max']})")
    jf = hero["face"]
    if verbose:
        print(f"[{name}] hero frame {hero['frame']} nd={hero['nd']:+.3f} "
              f"nv={hero['nv']:.3f} roll={jf.roll:+.2f} matte {hero['q']['ratio']}x "
              f"phantom {hero['q']['phantom']}  ({time.time()-t_start:.0f}s)")

    # ---------- E. hero geometry: the EYELINE sets the scale ----------------
    ys, xs = np.nonzero(hero["alpha"] > 0.5)
    cy0, cy1 = int(ys.min()), int(ys.max()) + 1
    cx0, cx1 = int(xs.min()), int(xs.max()) + 1
    ex, ey = eye_mid(jf)
    # bottom-anchored, eye at the house height -> scale is SOLVED, not chosen
    denom = max(1.0, (cy1 - ey))
    scale = (H - HOUSE["eye_y"] * H) / denom
    fh = jf.h * scale / H
    clamped = None
    if fh < HOUSE["hero_face_lo"] or fh > HOUSE["hero_face_hi"]:
        clamped = round(fh, 4)
        scale = (np.clip(fh, HOUSE["hero_face_lo"], HOUSE["hero_face_hi"])
                 * H / jf.h)
        fh = jf.h * scale / H
    cut_w = int(round((cx1 - cx0) * scale))
    cut_h = int(round((cy1 - cy0) * scale))
    cut_y = H - cut_h
    eye_y_px = cut_y + (ey - cy0) * scale
    rgba_src = np.dstack([hero["img"][cy0:cy1, cx0:cx1],
                          (hero["alpha"][cy0:cy1, cx0:cx1] * 255).astype(np.uint8)])
    rgba = cv2.resize(rgba_src, (cut_w, cut_h), interpolation=cv2.INTER_LANCZOS4)

    heroes = []
    for lead in HOUSE["lead_opts"]:
        eye_x_px = lead * W if side == "R" else (1.0 - lead) * W
        cut_x = int(round(eye_x_px - (ex - cx0) * scale))
        bleed = (cut_x + cut_w - W) if side == "R" else (-cut_x)
        if bleed < HOUSE["bleed_min"] * W:
            continue
        occ = np.zeros((H, W), np.float32)
        ax0, ay0 = max(0, cut_x), max(0, cut_y)
        ax1, ay1 = min(W, cut_x + cut_w), min(H, cut_y + cut_h)
        if ax1 <= ax0 or ay1 <= ay0:
            continue
        occ[ay0:ay1, ax0:ax1] = rgba[ay0 - cut_y:ay1 - cut_y,
                                     ax0 - cut_x:ax1 - cut_x, 3] / 255.0
        fbox = (cut_x + (jf.x - cx0) * scale, cut_y + (jf.y - cy0) * scale,
                cut_x + (jf.x + jf.w - cx0) * scale,
                cut_y + (jf.y + jf.h - cy0) * scale)
        heroes.append(dict(lead=lead, x=cut_x, y=cut_y, w=cut_w, h=cut_h,
                           occ=occ, fbox=fbox, eye=(eye_x_px, eye_y_px),
                           bleed_px=int(bleed)))
    if not heroes:
        raise SystemExit(f"REFUSE {name}: cut-out will not bleed "
                         f"{HOUSE['bleed_min']} W off the {side} edge at any lead")
    log["hero_geom"] = dict(
        scale=round(float(scale), 3), face_h_frac=round(float(fh), 4),
        face_h_clamped_from=clamped,
        eye_y_frac=round(float(eye_y_px / H), 4),
        eye_y_house=HOUSE["eye_y"], bottom_anchored=True,
        leads_available=[h["lead"] for h in heroes],
        bleed_px={h["lead"]: h["bleed_px"] for h in heroes},
        matte_quality=hero["q"],
        rule="scale solved from bottom-anchor + house eyeline height")

    # ---------- F. plate frame: reaction + the eye path closing -------------
    hero_at = "RIGHT" if side == "R" else "LEFT"
    plate_rank = []
    for si, f in defe_cl["members"]:
        rec = samples[si]
        # the defendant looking back TOWARD the hero closes the eye path
        toward = (nd(f) > 0) if side == "R" else (nd(f) < 0)
        plate_rank.append((0 if toward else 1, -rec["sharp"][court_k],
                           abs(nv(f) - 0.5), si, f))
    plate_rank.sort(key=lambda p: (p[0], p[1], p[2]))
    log["plate_gate"] = dict(candidates=len(plate_rank),
                             looking_toward_hero=sum(1 for p in plate_rank if p[0] == 0),
                             hero_at=hero_at)

    best = None
    plate_used = None
    rung_used = None
    fields = {}
    for yl in YIELD:
        for _, _, _, si, defe in plate_rank[:6]:
            rec = samples[si]
            if si not in fields:
                fr = grab(cfg, rec["f"])
                timg = fr[cty:cty + cth, ctx:ctx + ctw]
                burn = burnin_mask(timg)
                pm = matte(timg, f"{name}_court_{rec['f']}", "birefnet-general-lite")
                fields[si] = (timg, burn,
                              build_field(timg, rec["tiles"][court_k], pm, burn))
            timg, burn, fld = fields[si]
            cand = compose(name, cfg, fld, burn, defe, heroes, side, type_side,
                           log, verbose, yl)
            if cand is not None:
                best = cand
                rung_used = yl
                plate_used = dict(frame=rec["f"], t=round(rec["t"], 2),
                                  defendant_nd=round(nd(defe), 3),
                                  defendant_nv=round(nv(defe), 3),
                                  looks_toward_hero=bool(
                                      (nd(defe) > 0) if side == "R" else (nd(defe) < 0)),
                                  sharpness=round(rec["sharp"][court_k], 1))
                best["tile"] = timg
                best["fld"] = fld
                best["defe"] = defe
                break
        if best is not None:
            break
    if best is None:
        raise SystemExit(f"REFUSE {name}: no plate frame admitted a legal "
                         "crop x type x arrow layout at any rung of the "
                         "yield ladder")
    log["yield_ladder"] = dict(rung_used=rung_used["rung"], why=rung_used["why"],
                               sep_band=list(rung_used["sep"]),
                               upscale_ceiling=rung_used["upscale"],
                               defendant_face_band=list(rung_used["defe"]),
                               rungs_defined=len(YIELD))
    log["plate_frame"] = plate_used
    if verbose:
        print(f"[{name}] plate frame {plate_used['frame']} "
              f"J={best['J']:.3f}  ({time.time()-t_start:.0f}s)")

    out = render(name, best, hero, rgba, log)
    log["elapsed_s"] = round(time.time() - t_start, 1)
    with open(os.path.join(OUTDIR, f"L2_eyeline_{name}.json"), "w") as fh:
        json.dump(log, fh, indent=2, default=str)
    return out, log


# ===========================================================================
# the joint crop x type x arrow search
# ===========================================================================
def compose(name, cfg, fld, burn, defe, heroes, side, type_side, log,
            verbose, yl):
    Ht, Wt = fld.sal.shape
    ii_burn = integral(burn)
    people_t = fld.people
    dist_t = cv2.distanceTransform((people_t < 0.5).astype(np.uint8),
                                   cv2.DIST_L2, 3)

    # ---- pre-render every typeset x y position once ------------------------
    stroke = max(6, int(round(HOUSE["stroke"] * W)))
    inset_x = int(round(HOUSE["inset_x"] * W))
    blocks = []
    for capf in HOUSE["cap_opts"]:
        for wf in HOUSE["wmax_opts"]:
            ts = typeset(cfg["white"], cfg["yellow"], int(round(capf * H)),
                         int(round(wf * W)))
            if ts is None:
                continue
            if ts["n_lines"] == 2 and not (ts["line2_yellow"]
                                           and ts["break_frac"] >= HOUSE["break_min"]):
                continue
            if ts["w"] + 2 * inset_x > W:
                continue
            blocks.append((capf, wf, ts))
    if not blocks:
        raise SystemExit(f"REFUSE {name}: the copy will not set - re-split it "
                         "(white/yellow), a human call")
    y_lo = int(round(HOUSE["inset_y"] * H))
    y_hi = int(round(HOUSE["top_y_max"] * H))
    placements = []
    for capf, wf, ts in blocks:
        ox = inset_x - ts["ink_dx"] if type_side == "L" else \
            (W - inset_x - ts["w"]) - ts["ink_dx"]
        bx0 = ox + ts["ink_dx"]
        for ty in range(y_lo, y_hi + 1, 4):
            oy = ty - ts["ink_dy"]
            m = ink_mask(ts, ox, oy, stroke)
            iys, ixs = np.nonzero(m)
            if len(iys) == 0:
                continue
            box = (int(ixs.min()), int(iys.min()), int(ixs.max()) + 1,
                   int(iys.max()) + 1)
            sub = slice(None, None, 3)
            placements.append(dict(ts=ts, ox=ox, oy=oy, ty=ty, box=box,
                                   capf=capf, wf=wf,
                                   pys=iys[sub], pxs=ixs[sub],
                                   n_ink=int(m.sum()),
                                   area=(box[2] - box[0]) * (box[3] - box[1])))

    # ---- crop candidates ---------------------------------------------------
    s_min = max(0.35, (W / yl["upscale"]) / Wt)
    crops = []
    for s_ in np.arange(s_min, 1.0001, 0.02):
        cw = int(round(Wt * s_))
        ch = int(round(cw * 9 / 16))
        if cw > Wt or ch > Ht:
            continue
        fh_frac = defe.h / ch
        if not (yl["defe"][0] <= fh_frac <= yl["defe"][1]):
            continue
        kx, ky = W / cw, H / ch
        for y0 in range(0, Ht - ch + 1, 6):
            if y0 > defe.y - 0.45 * defe.h:
                continue
            if y0 + ch < defe.y + defe.h * 1.35:
                continue
            for x0 in range(0, Wt - cw + 1, 6):
                if x0 > defe.x - 0.25 * defe.w:
                    continue
                if x0 + cw < defe.x + defe.w * 1.25:
                    continue
                if rect_sum(ii_burn, x0, y0, x0 + cw, y0 + ch) > 1.0:
                    continue
                crops.append((x0, y0, cw, ch, kx, ky, fh_frac))
    log.setdefault("search", {})["crops_clean"] = len(crops)
    if not crops:
        return None

    funnel = dict(inframe=0, occluded=0, sep=0, dcy=0, no_type=0, no_arrow=0,
                  full=0)
    sep_seen, fh_seen, gap_seen = [], [], []
    scored = []
    for hero_g in heroes:
        hx_face = hero_g["fbox"]
        hcx = (hx_face[0] + hx_face[2]) / 2 / W
        hcy = (hx_face[1] + hx_face[3]) / 2 / H
        for (x0, y0, cw, ch, kx, ky, fh_frac) in crops:
            dfx0 = (defe.x - 0.30 * defe.w - x0) * kx
            dfx1 = (defe.x + defe.w * 1.30 - x0) * kx
            dfy0 = (defe.y - 0.30 * defe.h - y0) * ky
            dfy1 = (defe.y + defe.h * 1.30 - y0) * ky
            if not (0 <= dfx0 and dfx1 < W and 0 <= dfy0 and dfy1 < H):
                funnel["inframe"] += 1
                continue
            if hero_g["occ"][int(dfy0):int(dfy1), int(dfx0):int(dfx1)].max() > 0.10:
                funnel["occluded"] += 1
                continue
            dcx = (defe.cx - x0) * kx / W
            dcy_ = (defe.cy - y0) * ky / H
            sep = abs(hcx - dcx)
            sep_seen.append(sep)
            fh_seen.append(fh_frac)
            if not (yl["sep"][0] <= sep <= yl["sep"][1]):
                funnel["sep"] += 1
                continue
            dy = abs(hcy - dcy_)
            if dy > yl["dcy"]:
                funnel["dcy"] += 1
                continue
            pre = (-2.5 * abs(fh_frac - HOUSE["defe_face_h"])
                   - 2.0 * abs(sep - HOUSE["sep"])
                   - 1.5 * abs(dy - HOUSE["dcy"]) / HOUSE["dcy_max"])
            scored.append((pre, hero_g, x0, y0, cw, ch, kx, ky, fh_frac, sep, dy,
                           dcx, dcy_))
    log["search"]["crops_geometry_ok"] = len(scored)
    log["search"]["funnel"] = dict(funnel)
    log["search"]["sep_seen"] = ([round(min(sep_seen), 3), round(max(sep_seen), 3)]
                                 if sep_seen else None)
    log["search"]["fh_seen"] = ([round(min(fh_seen), 3), round(max(fh_seen), 3)]
                                if fh_seen else None)
    if not scored:
        if verbose:
            print(f"    funnel {dict(funnel)} crops_clean={log['search']['crops_clean']}"
                  f" sep_seen={log['search']['sep_seen']}"
                  f" fh_seen={log['search']['fh_seen']}")
        return None
    scored.sort(key=lambda s: -s[0])
    scored = scored[:150]

    best = None
    for (pre, hero_g, x0, y0, cw, ch, kx, ky, fh_frac, sep, dy, dcx,
         dcy_) in scored:
        hfb = hero_g["fbox"]
        # ---------- ARROW: it follows the EYE PATH --------------------------
        fx0, fy0 = (defe.x - x0) * kx, (defe.y - y0) * ky
        fx1, fy1 = (defe.x + defe.w - x0) * kx, (defe.y + defe.h - y0) * ky
        P = ((fx0 + fx1) / 2.0, fy0 + 0.30 * (fy1 - fy0))
        E = hero_g["eye"]
        eye_deg = math.degrees(math.atan2(P[1] - E[1], P[0] - E[0]))
        L = HOUSE["arrow_len"] * W
        arrow = None
        for dd in np.arange(-HOUSE["arrow_eye_tol"], HOUSE["arrow_eye_tol"] + .01, 2.5):
            deg = eye_deg + float(dd)
            th = math.radians(deg)
            ux, uy = math.cos(th), math.sin(th)
            tip = None
            for back in range(0, int(0.55 * W), 2):
                tx_, ty_ = P[0] - ux * back, P[1] - uy * back
                if not (2 <= tx_ < W - 2 and 2 <= ty_ < H - 2):
                    break
                TX = int(np.clip(x0 + tx_ / kx, 0, Wt - 1))
                TY = int(np.clip(y0 + ty_ / ky, 0, Ht - 1))
                if people_t[TY, TX] < 0.5 and hero_g["occ"][int(ty_), int(tx_)] < 0.10:
                    tip = (P[0] - ux * (back + 4), P[1] - uy * (back + 4))
                    break
            if tip is None:
                continue
            sd = math.hypot(max(fx0 - tip[0], tip[0] - fx1, 0.0),
                            max(fy0 - tip[1], tip[1] - fy1, 0.0))
            if sd < HOUSE["standoff_min"] or sd > HOUSE["standoff_max"] * W:
                continue
            start = (tip[0] - ux * L, tip[1] - uy * L)
            if not (2 <= start[0] < W - 2 and 2 <= start[1] < H - 2):
                continue
            m = raster_arrow(start, tip)
            ays, axs = np.nonzero(m)
            if len(ays) == 0:
                continue
            if hero_g["occ"][ays, axs].max() > 0.10:
                continue
            TX = np.clip((x0 + axs / kx).astype(int), 0, Wt - 1)
            TY = np.clip((y0 + ays / ky).astype(int), 0, Ht - 1)
            n_person = int((people_t[TY, TX] > 0.5).sum())
            if n_person:
                continue
            gcx, gcy = float(axs.mean()), float(ays.mean())
            clear_t = float(dist_t[int(np.clip(y0 + gcy / ky, 0, Ht - 1)),
                                   int(np.clip(x0 + gcx / kx, 0, Wt - 1))]) * kx
            hero_hard = (hero_g["occ"] > 0.5).astype(np.uint8)
            if "dist_h" not in hero_g:
                hero_g["dist_h"] = cv2.distanceTransform(1 - hero_hard,
                                                         cv2.DIST_L2, 3)
            clear = min(clear_t, float(hero_g["dist_h"][int(gcy), int(gcx)]))
            if clear < HOUSE["body_clear"] * W:
                continue
            sc = (abs(dd) / HOUSE["arrow_eye_tol"]
                  + 0.25 * abs(deg - HOUSE["arrow_house_deg"]) / 90.0
                  + 0.5 * sd / W)
            if arrow is None or sc < arrow["sc"]:
                arrow = dict(sc=sc, start=start, tip=tip, deg=deg, n=len(ays),
                             standoff=sd, clear=clear, eye_deg=eye_deg,
                             d_eye=float(dd), mask=m,
                             box=(int(axs.min()), int(ays.min()),
                                  int(axs.max()) + 1, int(ays.max()) + 1))
        if arrow is None:
            funnel["no_arrow"] += 1
            continue

        # ---------- TYPE ------------------------------------------------------
        best_t = None
        for pl in placements:
            b = pl["box"]
            # hard: never on the hero's face box
            if not (b[2] < hfb[0] or b[0] > hfb[2] or b[3] < hfb[1] or b[1] > hfb[3]):
                continue
            # the collision rule: measured 6/6 violated in the shipped six
            gap = (hfb[0] - b[2]) if type_side == "L" else (b[0] - hfb[2])
            if gap < HOUSE["face_gap"] * W:
                continue
            # hard: 0 ink on any plate person or face box
            TX = np.clip((x0 + pl["pxs"] / kx).astype(int), 0, Wt - 1)
            TY = np.clip((y0 + pl["pys"] / ky).astype(int), 0, Ht - 1)
            inb = ((pl["pxs"] >= 0) & (pl["pxs"] < W) & (pl["pys"] >= 0)
                   & (pl["pys"] < H))
            if int((fld.forbid[TY, TX] > 0.5).sum()) > 0:
                continue
            # hero hair only, <= 2% of ink
            hair = float((hero_g["occ"][pl["pys"], pl["pxs"]] > 0.5).mean())
            if hair > HOUSE["hair_max"]:
                continue
            # arrow must not touch the ink, and must keep the measured gap
            ab = arrow["box"]
            if not (ab[2] < b[0] or ab[0] > b[2] or ab[3] < b[1] or ab[1] > b[3]):
                continue
            gap_a = max(ab[0] - b[2], b[0] - ab[2], ab[1] - b[3], b[1] - ab[3])
            if gap_a < HOUSE["text_gap"] * W:
                continue
            occ = float(fld.sal[TY, TX].mean())
            rea = float(fld.grad[TY, TX].mean())
            area_f = pl["area"] / float(W * H)
            sc = (2.0 * occ + 1.0 * rea + 1.2 * hair
                  + 1.2 * max(0.0, HOUSE["face_gap_target"] * W - gap) / (0.05 * W)
                  + 1.6 * abs(pl["ty"] / H - HOUSE["inset_y"])
                  + 0.8 * abs(pl["ts"]["break_frac"] - HOUSE["break_target"])
                  - 0.45 * (pl["ts"]["n_lines"] == 2)
                  - 0.35 * (HOUSE["area_lo"] <= area_f <= HOUSE["area_hi"]))
            if best_t is None or sc < best_t[0]:
                best_t = (sc, pl, occ, rea, hair, gap, area_f)
        if best_t is None:
            funnel["no_type"] += 1
            continue
        _, pl, t_occ, t_rea, t_hair, t_gap, area_f = best_t
        funnel["full"] += 1

        # ---------- objective -------------------------------------------------
        boxes = [pl["box"], arrow["box"],
                 (max(0, hero_g["x"]), max(0, hero_g["y"]),
                  min(W, hero_g["x"] + hero_g["w"]), H)]
        R_ali = ali_penalty(boxes, W, H)
        R_ove = overlap_ratio(boxes)
        cov = np.zeros((H, W), np.uint8)
        for (bx0, by0, bx1, by1) in boxes[:2]:
            cov[int(by0):int(by1), int(bx0):int(bx1)] = 1
        free = ~(hero_g["occ"] > 0.5)
        R_uti = float((cov.astype(bool) & free).sum()) / max(1.0, float(free.sum()))
        J = (-2.0 * t_occ - 1.0 * t_rea - 1.2 * t_hair
             + 1.2 * R_uti - 0.9 * R_ali - 3.0 * R_ove
             - 2.5 * abs(fh_frac - HOUSE["defe_face_h"])
             - 2.0 * abs(sep - HOUSE["sep"])
             - 1.5 * abs(dy - HOUSE["dcy"]) / HOUSE["dcy_max"]
             - 1.5 * abs(hero_g["lead"] - HOUSE["lead_target"]) / 0.10
             - 1.5 * abs(arrow["d_eye"]) / HOUSE["arrow_eye_tol"]
             - 1.2 * max(0.0, HOUSE["face_gap"] * W - t_gap) / (0.026 * W)
             + 0.45 * (pl["ts"]["n_lines"] == 2)
             + 0.35 * (HOUSE["area_lo"] <= area_f <= HOUSE["area_hi"]))
        if best is None or J > best["J"]:
            best = dict(J=float(J), crop=(x0, y0, cw, ch), hero=hero_g,
                        pl=pl, arrow=arrow, side=side, type_side=type_side,
                        defe_canvas=(fx0, fy0, fx1, fy1), yl=yl,
                        metrics=dict(
                            R_occ_type=round(t_occ, 5), R_rea_type=round(t_rea, 5),
                            R_uti=round(R_uti, 4), R_ali=round(R_ali, 4),
                            R_ove=round(R_ove, 5),
                            type_ink_on_hero_matte=round(t_hair, 4),
                            type_gap_to_hero_face_px=round(t_gap, 1),
                            type_gap_W=round(t_gap / W, 4),
                            type_area_frac=round(area_f, 4),
                            type_cap_frac=round(pl["capf"], 4),
                            type_wmax_frac=round(pl["wf"], 3),
                            type_break_frac=pl["ts"]["break_frac"],
                            type_lines=pl["ts"]["n_lines"],
                            defendant_face_h=round(fh_frac, 4),
                            separation_W=round(sep, 4), delta_cy_H=round(dy, 4),
                            hero_lead=hero_g["lead"],
                            arrow_deg=round(arrow["deg"], 1),
                            arrow_eye_path_deg=round(arrow["eye_deg"], 1),
                            arrow_deviation_from_eye_path=round(arrow["d_eye"], 1),
                            arrow_px=arrow["n"],
                            arrow_area_frac=round(arrow["n"] / (W * H), 5),
                            arrow_standoff_px=round(arrow["standoff"], 1),
                            arrow_body_clearance_W=round(arrow["clear"] / W, 4)))
    log["search"]["funnel"] = dict(funnel)
    if verbose:
        print(f"    funnel {dict(funnel)}  crops_clean={log['search']['crops_clean']}"
              f" geom_ok={log['search']['crops_geometry_ok']}"
              f" sep_seen={log['search'].get('sep_seen')}"
              f" fh_seen={log['search'].get('fh_seen')}"
              f" gap_seen={log['search'].get('gap_seen')}")
    return best


# ===========================================================================
# render + verify
# ===========================================================================
def render(name, best, hero, rgba, log):
    x0, y0, cw, ch = best["crop"]
    hg = best["hero"]
    pl = best["pl"]
    ts = pl["ts"]
    stroke = max(6, int(round(HOUSE["stroke"] * W)))

    plate = cv2.resize(best["tile"][y0:y0 + ch, x0:x0 + cw], (W, H),
                       interpolation=cv2.INTER_LANCZOS4)
    base = Image.fromarray(cv2.cvtColor(plate, cv2.COLOR_BGR2RGB)).convert("RGBA")
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lay.paste(Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)),
              (hg["x"], hg["y"]))
    comp = Image.alpha_composite(base, lay)

    # grade the PHOTOGRAPH, then burn the graphics in on top
    gbgr, gamma = grade(cv2.cvtColor(np.asarray(comp.convert("RGB")),
                                     cv2.COLOR_RGB2BGR))
    img = Image.fromarray(cv2.cvtColor(gbgr, cv2.COLOR_BGR2RGB)).convert("RGBA")

    am = best["arrow"]["mask"]
    red = Image.new("RGBA", (W, H), (*HOUSE["arrow_col"], 255))
    red.putalpha(Image.fromarray((am * 255).astype(np.uint8)))
    img = Image.alpha_composite(img, red)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, ln in enumerate(ts["lines"]):
        gd.text((pl["ox"], pl["oy"] + i * ts["pitch"]), ln, font=ts["font"],
                fill=(0, 0, 0, 240), stroke_width=stroke + 3,
                stroke_fill=(0, 0, 0, 240))
    img = Image.alpha_composite(img, glow.filter(
        ImageFilter.GaussianBlur(HOUSE["glow_blur"])))

    d = ImageDraw.Draw(img)
    done = 0
    for i, ln in enumerate(ts["lines"]):
        px = pl["ox"]
        for w_ in ln.split():
            col = (255, 255, 255, 255) if done < ts["n_white"] else (255, 216, 0, 255)
            d.text((px, pl["oy"] + i * ts["pitch"]), w_, font=ts["font"],
                   fill=col, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            px += d.textlength(w_ + " ", font=ts["font"])
            done += 1

    out = os.path.join(OUTDIR, f"L2_eyeline_{name}.jpg")
    img.convert("RGB").save(out, quality=95, subsampling=0, optimize=True)
    log["grade"] = dict(gamma=gamma)
    log["metrics"] = best["metrics"]
    log["chosen"] = dict(crop=[x0, y0, cw, ch],
                         hero_box=[hg["x"], hg["y"], hg["w"], hg["h"]],
                         hero_face_box=[round(v, 1) for v in hg["fbox"]],
                         hero_eye=[round(hg["eye"][0] / W, 4),
                                   round(hg["eye"][1] / H, 4)],
                         hero_bleed_px=hg["bleed_px"],
                         type_box=list(pl["box"]),
                         arrow_box=list(best["arrow"]["box"]),
                         arrow_tip=[round(v, 1) for v in best["arrow"]["tip"]],
                         J=round(best["J"], 4), out=out)
    log["verification"] = verify(out, name, best, hg, pl, am)
    return out


def verify(path, name, best, hg, pl, am):
    """Measured on the RENDERED JPEG, not on the code."""
    chk = cv2.imread(path)
    v = dict(size=list(chk.shape[:2][::-1]),
             size_ok=bool(chk.shape[0] == H and chk.shape[1] == W))
    stroke = max(6, int(round(HOUSE["stroke"] * W)))
    ts = pl["ts"]
    glyph = ink_mask(ts, pl["ox"], pl["oy"], stroke)
    v["type_ink_px"] = int(glyph.sum())

    faces = detect_faces(chk, YUNET, 0.5)
    hfb = hg["fbox"]

    def boxm(f):
        m = np.zeros((H, W), bool)
        m[int(max(0, f.y)):int(f.y + f.h), int(max(0, f.x)):int(f.x + f.w)] = True
        return m

    v["faces_detected_in_output"] = [
        dict(cx=round(f.cx / W, 3), cy=round(f.cy / H, 3),
             h=round(f.h / H, 3), nd=round(nd(f), 3), nv=round(nv(f), 3),
             roll=round(f.roll, 2)) for f in faces[:6]]
    v["type_ink_on_a_detected_face"] = [int((glyph & boxm(f)).sum()) for f in faces[:6]]
    v["arrow_px_on_a_detected_face"] = [int(((am > 0) & boxm(f)).sum()) for f in faces[:6]]

    # people, re-mattted off the RENDER (not the tile) - the D9 fix
    pm = matte(chk, f"{name}_render_verify_{os.path.getsize(path)}",
               "birefnet-general-lite")
    people = (pm > 0.5)
    for f in faces:
        people |= boxm(f)
    v["arrow_px_on_a_person"] = int(((am > 0) & people).sum())
    v["type_ink_on_a_person"] = int((glyph & people).sum())
    v["type_ink_on_person_frac"] = round(float((glyph & people).sum())
                                         / max(1, glyph.sum()), 4)

    # arrow shape, measured off the red channel of the JPEG
    b, g, r = [chk[..., i].astype(int) for i in range(3)]
    redm = ((r > 190) & (g < 60) & (b < 60) & ((r - g) > 150)).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(redm, 8)
    if n > 1:
        i = max(range(1, n), key=lambda j: st[j, 4])
        ax, ay, aw, ah, aa = st[i]
        v["arrow_measured"] = dict(px=int(aa), bbox=[int(ax), int(ay), int(aw), int(ah)],
                                   fill=round(float(aa) / max(1, aw * ah), 3),
                                   fill_band=[0.44, 0.48],
                                   area_frac=round(aa / (W * H), 5),
                                   area_band=[0.0028, 0.0066])

    # the arrow RAY: does it actually reach the defendant?
    tip = best["arrow"]["tip"]
    th = math.radians(best["arrow"]["deg"])
    ux, uy = math.cos(th), math.sin(th)
    hitname, hitd = None, None
    dfx0, dfy0, dfx1, dfy1 = best["defe_canvas"]
    for s in range(0, int(0.5 * W)):
        px, py = tip[0] + ux * s, tip[1] + uy * s
        if not (0 <= px < W and 0 <= py < H):
            break
        if dfx0 <= px <= dfx1 and dfy0 <= py <= dfy1:
            hitname, hitd = "defendant_face_box", s
            break
    v["ray_reaches_defendant"] = bool(hitname is not None)
    v["ray_travel_px"] = hitd
    v["arrow_tip_standoff_px"] = round(best["arrow"]["standoff"], 1)
    if faces:
        nf = min(faces, key=lambda f: math.hypot(f.cx - (dfx0 + dfx1) / 2,
                                                 f.cy - (dfy0 + dfy1) / 2))
        d2 = [math.hypot(f.cx - tip[0], f.cy - tip[1]) for f in faces]
        v["nearest_face_to_tip_is_defendant"] = bool(
            faces[int(np.argmin(d2))] is nf)

    # hero eyeline, re-detected on the output
    if faces:
        hf = min(faces, key=lambda f: math.hypot(
            f.cx - (hfb[0] + hfb[2]) / 2, f.cy - (hfb[1] + hfb[3]) / 2))
        exx, eyy = eye_mid(hf)
        v["hero_in_output"] = dict(
            eye_x_frac=round(exx / W, 4), eye_y_frac=round(eyy / H, 4),
            eye_y_house=HOUSE["eye_y"],
            nd=round(nd(hf), 3), nv=round(nv(hf), 3), roll=round(hf.roll, 2),
            eyes_level_not_down=bool(nv(hf) <= HOUSE["gate_nv"]
                                     and abs(hf.roll) <= HOUSE["gate_roll"]),
            looking_into_frame=bool((nd(hf) < 0) == (best["side"] == "R")))

    # free rectangle, on the composite
    free = ~people
    area, rx0, ry0, rx1, ry1 = max_free_rect(free)
    tb = pl["box"]
    inter = max(0, min(tb[2], rx1) - max(tb[0], rx0)) * \
        max(0, min(tb[3], ry1) - max(tb[1], ry0))
    v["free_rect"] = dict(frac_of_frame=round(area / (W * H), 4),
                          box=[int(rx0), int(ry0), int(rx1), int(ry1)])
    v["type_inside_free_rect"] = round(inter / max(1, (tb[2] - tb[0]) * (tb[3] - tb[1])), 3)

    lum = cv2.cvtColor(chk, cv2.COLOR_BGR2GRAY)
    v["luminance_mean"] = round(float(lum.mean()), 1)
    v["blacks_frac"] = round(float((lum < 32).mean()), 4)

    m = best["metrics"]
    v["GATES"] = {
        "1280x720": v["size_ok"],
        "type ink on any face == 0": all(x == 0 for x in v["type_ink_on_a_detected_face"]),
        "type ink on any person == 0": v["type_ink_on_a_person"] == 0,
        "arrow px on any person == 0": v["arrow_px_on_a_person"] == 0,
        "arrow ray reaches defendant": v["ray_reaches_defendant"],
        "arrow standoff 4..83px": 4.0 <= m["arrow_standoff_px"] <= HOUSE["standoff_max"] * W,
        "separation inside the rung band": (best["yl"]["sep"][0]
            <= m["separation_W"] <= best["yl"]["sep"][1]),
        "separation inside the CORPUS band 0.42-0.58": (
            HOUSE["sep_lo"] <= m["separation_W"] <= HOUSE["sep_hi"]),
        "|dcy| <= 0.22": m["delta_cy_H"] <= HOUSE["dcy_max"],
        "type->hero face gap >= 0.038W": m["type_gap_W"] >= HOUSE["face_gap"],
        "ali <= 0.06": m["R_ali"] <= 0.06,
        "eyes level not down": v.get("hero_in_output", {}).get("eyes_level_not_down", False),
        "hero looks into frame": v.get("hero_in_output", {}).get("looking_into_frame", False),
    }
    return v


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "ALL"
    names = list(HEARINGS) if which.upper() == "ALL" else [which.upper()]
    for nm in names:
        try:
            out, lg = build(nm)
            print(f"\n=== {nm} -> {out}")
            print(json.dumps(lg["verification"]["GATES"], indent=2))
        except SystemExit as e:
            print(f"\n=== {nm} REFUSED: {e}")
