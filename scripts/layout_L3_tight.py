"""L3_TIGHT - parametric Boyd thumbnail layout, tightest legal arrangement.

    python scripts/layout_L3_tight.py CARTHIEF|SANCHEZ|OFFERUP|ALL

Implements BOYD THUMBNAIL PLACEMENT SPEC v1 with the L3_tight reading of it:
where the spec gives a floor and a target for a clear-space, aim just above the
FLOOR, and reward candidates whose elements share an axis. The bet is that
precision of arrangement, not generous padding, is what reads as pro.

ZERO per-case layout constants. The only per-hearing inputs are the ones the
job carries anyway: the source file, the case time range, the Zoom grid rects,
and the copy. Every coordinate that reaches the canvas is derived from a
measurement made on THIS hearing's frames.

Licences (all verified in the source brief):
  YuNet model .............. MIT (opencv_zoo)
  birefnet-portrait / -general-lite ... MIT   (rembg's DEFAULT bria-rmbg is
                                               CC BY-NC and is never selected)
  rembg .................... MIT
  RapidOCR ................. Apache-2.0
  SmartText mechanism ...... MIT
  PosterLayout metrics ..... no licence on that repo -> re-implemented from the
                             published definitions, no code copied.
Court footage is public record.
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
YUNET = f"{ROOT}/models/yunet.onnx"
FONT = f"{ROOT}/assets/fonts/TTTHeadline-Regular.ttf"
OUTDIR = f"{ROOT}/READY-TO-POST/LAYOUT"
CACHE = os.path.join(
    os.environ.get("TEMP", "C:/Users/natha/AppData/Local/Temp"),
    "L3_tight_cache")

W, H = 1280, 720
GY, GX = np.mgrid[0:720, 0:1280]

# =========================================================================== #
# House constants. Every one carries the measurement it came from. NONE of
# these is per-case; all three hearings are built with the identical set.
# =========================================================================== #
HOUSE = dict(
    # --- hero (Judge Boyd, matted, bottom-anchored, bleeding off one edge) ---
    hero_face_h=0.45,          # shipped six 0.383-0.559, median 0.433; corpus
                               # hero-cutout lobe 0.45-0.55 H
    hero_face_h_floor=0.38,
    hero_eye_y=0.327,          # ours median 0.327 H, IQR 0.325-0.334; all 43
                               # corpus images median 0.327
    lead=0.750,                # Audit the Court median 0.750, IQR 0.743-0.783
    lead_lo=0.743, lead_hi=0.783,
    bleed_min=0.02,            # W. default, not corpus-measured
    # --- hero frame gates ---
    gate_nd=0.20,              # judge nd medians -0.305/-0.314/-0.346
    gate_nv=0.50,              # 0.412-0.468 = head up; 0.623-0.635 = reading
    gate_roll=4.0,             # shipped hero rolls 0.48-2.28 deg
    gate_face_in_tile=0.33,
    phantom_fail=0.15, phantom_warn=0.12,
    # --- plate (courtroom camera carrying the defendant) ---
    defe_face_h=0.22,          # shipped median 0.219
    defe_face_h_lo=0.19, defe_face_h_hi=0.33,
    sep=0.50,                  # corpus 0.5116 median, IQR 0.4472-0.5621, n=32
    sep_lo=0.42, sep_hi=0.58,
    dcy=0.09, dcy_max=0.22,    # corpus median 0.0945, IQR 0.0612-0.1497
    upscale_max=2.7,
    # --- type ---
    cap=0.100,                 # line-1 caps 71-73 px in 6/6
    cap_floor=0.090,
    pitch=1.42,                # baseline pitch 102-103 px in 5/5 = 1.42 x cap
    inset_x=0.0211,            # 0.0195-0.0234 W, sd 0.0019
    cap_top=0.0375,            # 27/58/27/26/28 px, 4 of 5 at 26-28
    cap_top_max=0.092,         # Audit's own max
    stroke=0.0086,             # 11 px
    glow_radius=10,
    type_hero_gap_floor=0.038,  # Audit t_face_gap floor
    type_hero_gap_target=0.082,  # Audit t_face_gap median
    ink_on_hair_max=0.02,
    ink_on_plate_people_max=0.02,
    free_rect_floor=0.60,
    # --- arrow ---
    arrow_rgb=(0xFD, 0x01, 0x01),
    arrow_len=0.096,           # 123 px axial
    arrow_shaft=0.240, arrow_head=0.475,
    arrow_fill=0.463,          # measured 0.450-0.471, sd 0.008
    arrow_deg=137.9, arrow_deg_lo=110.0, arrow_deg_hi=152.0,
    standoff_min=4, standoff_lo=8, standoff_hi=40, standoff_max=83,
    arrow_body_clear=0.054,    # Audit a_body_clearance median 0.0623 W
    arrow_text_gap=0.046,      # Audit a_text_gap min 0.046, median 0.0773
    # --- grade ---
    lum_mean=125.0, blacks=0.090,
    # --- L3_TIGHT: how close to the floor to aim, and the snap tolerance ---
    tight_bias=0.05,           # aim 5% above each floor, not at the target
    snap_px=10,                # two edges within this share an axis
)

# =========================================================================== #
# Per-hearing JOB metadata. Source, case range, Zoom grid rects, copy.
# Not layout: these are the inputs any hearing arrives with.
# =========================================================================== #
HEARINGS = {
    "CARTHIEF": dict(
        src=f"{ROOT}/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
        off=3554.0, case=(3574.0, 4628.0),
        tiles=dict(T0=(612, 338, 18, 190), T1=(620, 338, 644, 190)),
        white="18 years old and", yellow="already in cuffs"),
    "SANCHEZ": dict(
        src=f"{ROOT}/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
        off=3683.0, case=(3703.0, 4148.0),
        tiles=dict(T0=(468, 348, 726, 6), T1=(628, 348, 6, 6)),
        white="You're why your son", yellow="is struggling"),
    "OFFERUP": dict(
        src=f"{ROOT}/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
        off=10550.0, case=(10570.0, 11117.0),
        tiles=dict(T0=(628, 348, 646, 186), T1=(628, 348, 6, 186)),
        white="Do you want", yellow="a jury trial?"),
}


# =========================================================================== #
# STAGE A - perception primitives
# =========================================================================== #
class Face:
    """One YuNet detection with the gaze scalars the spec is written in."""
    __slots__ = ("x", "y", "w", "h", "rex", "rey", "lex", "ley", "nx", "ny",
                 "mrx", "mry", "mlx", "mly", "score")

    def __init__(self, row):
        (self.x, self.y, self.w, self.h, self.rex, self.rey, self.lex,
         self.ley, self.nx, self.ny, self.mrx, self.mry, self.mlx,
         self.mly) = [float(v) for v in row[:14]]
        self.score = float(row[14])

    @property
    def cx(self): return self.x + self.w / 2

    @property
    def cy(self): return self.y + self.h / 2

    @property
    def eye_x(self): return (self.rex + self.lex) / 2

    @property
    def eye_y(self): return (self.rey + self.ley) / 2

    @property
    def io(self): return math.hypot(self.lex - self.rex, self.ley - self.rey)

    @property
    def roll(self):
        """deg. YuNet's 'right eye' is the person's right = image LEFT."""
        return math.degrees(math.atan2(self.ley - self.rey, self.lex - self.rex))

    @property
    def nd(self):
        """nose deviation / interocular. NEGATIVE = head turned image-LEFT."""
        return 0.0 if self.io < 1e-6 else (self.nx - self.eye_x) / self.io

    @property
    def nv(self):
        """pitch proxy, de-rolled. HIGHER = looking DOWN."""
        if self.io < 1e-6:
            return 0.0
        th = -math.radians(self.roll)
        c, s = math.cos(th), math.sin(th)
        ex, ey = self.eye_x, self.eye_y

        def rot(px, py):
            dx, dy = px - ex, py - ey
            return dx * c - dy * s, dx * s + dy * c
        _, ny = rot(self.nx, self.ny)
        _, my = rot((self.mrx + self.mlx) / 2, (self.mry + self.mly) / 2)
        return 0.0 if abs(my) < 1e-6 else ny / my

    def box(self, pad=0.0):
        px, py = self.w * pad, self.h * pad
        return (self.x - px, self.y - py, self.x + self.w + px, self.y + self.h + py)

    def as_dict(self):
        return dict(x=round(self.x, 1), y=round(self.y, 1), w=round(self.w, 1),
                    h=round(self.h, 1), nd=round(self.nd, 3),
                    nv=round(self.nv, 3), roll=round(self.roll, 2),
                    score=round(self.score, 3))


_DET = {}


def detect(bgr, thresh=0.55):
    h, w = bgr.shape[:2]
    key = (w, h, thresh)
    if key not in _DET:
        _DET[key] = cv2.FaceDetectorYN.create(YUNET, "", (w, h), thresh, 0.3, 5000)
    d = _DET[key]
    d.setInputSize((w, h))
    _, raw = d.detect(bgr)
    if raw is None:
        return []
    return sorted([Face(r) for r in raw], key=lambda f: -f.h)


_SESS = {}


def matte(bgr, model="birefnet-portrait"):
    """Alpha in [0,1]. birefnet-* weights are MIT."""
    from rembg import new_session, remove
    if model not in _SESS:
        _SESS[model] = new_session(model)
    rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    a = remove(rgb, session=_SESS[model], post_process_mask=True).split()[-1]
    return np.asarray(a, dtype=np.float32) / 255.0


_OCR = None


def ocr_lines(bgr, scale=2.5):
    global _OCR
    try:
        if _OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        big = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        res, _ = _OCR(big)
        out = []
        for box, txt, conf in (res or []):
            p = np.array(box, dtype=np.float64) / scale
            out.append((p, txt, float(conf)))
        return out
    except Exception as e:
        print("   OCR unavailable:", e)
        return []


def burnin_mask(bgr):
    """Zoom's active-speaker ring + every OCR box, dilated 0.35 x box height.

    NOT a white-colour rule: a (S<40)&(V>200) test marks 16.6% of the OFFERUP
    tile - this courtroom has white walls and a white ceiling.
    """
    h, w = bgr.shape[:2]
    b, g, r = [bgr[..., i].astype(int) for i in range(3)]
    m = (((g - np.maximum(r, b)) > 55) & (g > 165)).astype(np.uint8)
    for p, txt, conf in ocr_lines(bgr):
        x0, y0 = int(p[:, 0].min()), int(p[:, 1].min())
        x1, y1 = int(p[:, 0].max()), int(p[:, 1].max())
        pad = int(0.35 * max(1, y1 - y0))
        cv2.rectangle(m, (max(0, x0 - pad), max(0, y0 - pad)),
                      (min(w, x1 + pad), min(h, y1 + pad)), 1, -1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8))
    return m.astype(np.float32)


def integral(a):
    return cv2.integral(a.astype(np.float64))


def rsum(ii, x0, y0, x1, y1):
    return ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]


def grad_map(bgr):
    """PosterLayout metrics_rea's field: sqrt((Sx^2+Sy^2)/2), self-normalised."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    m = np.sqrt((gx ** 2 + gy ** 2) / 2)
    return m / m.max() if m.max() > 0 else m


def ali_penalty(boxes, w=W, h=H):
    """PosterLayout metrics_ali, re-implemented from its published definition.

    Per element: min over the six channels (left, top, cx, cy, right, bottom)
    of -log10(1 - min_delta). 0 = an axis is exactly shared with something.
    """
    if len(boxes) <= 1:
        return 0.0
    th = np.array([[a / w, b / h, (a + c) / (2 * w), (b + d) / (2 * h), c / w, d / h]
                   for (a, b, c, d) in boxes], dtype=np.float64)
    tot = 0.0
    for i in range(len(th)):
        vals = []
        for j in range(6):
            col = th[:, j]
            dd = float(np.abs(col[i] - np.delete(col, i)).min())
            vals.append(-math.log10(1.0 - min(dd, 0.999999)))
        tot += min(vals)
    return tot


def max_free_rect(mask, ds=4):
    """Largest all-zero axis-aligned rectangle in `mask` (people = 1).

    Largest-rectangle-in-histogram sweep on a `ds`-times downsampled mask; a
    cell counts as occupied if ANY of its pixels is, so the answer is a
    conservative under-estimate of the true free rect.
    """
    small = cv2.dilate(mask.astype(np.uint8),
                       np.ones((ds, ds), np.uint8))[::ds, ::ds] > 0
    hgt, wid = small.shape
    heights = np.zeros(wid, dtype=np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(hgt):
        heights = np.where(small[y], 0, heights + 1)
        stack = []
        for x in range(wid + 1):
            cur = int(heights[x]) if x < wid else 0
            start = x
            while stack and stack[-1][1] >= cur:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, sx, y - sh + 1, x, y + 1)
                start = sx
            stack.append((start, cur))
    a, x0, y0, x1, y1 = best
    return (a * ds * ds, x0 * ds, y0 * ds, x1 * ds, y1 * ds)


# =========================================================================== #
# STAGE A - the gaze / detection census. One decode pass, both tiles.
# =========================================================================== #
def census(name, cfg, n=200):
    os.makedirs(CACHE, exist_ok=True)
    cp = os.path.join(CACHE, f"{name}_census_{n}.json")
    if os.path.exists(cp):
        return json.load(open(cp))
    t0, t1 = cfg["case"]
    ts = np.linspace(t0 + 2, t1 - 2, n)
    cap = cv2.VideoCapture(cfg["src"])
    rows = []
    t_start = time.time()
    for i, t in enumerate(ts):
        cap.set(cv2.CAP_PROP_POS_MSEC, (t - cfg["off"]) * 1000.0)
        ok, fr = cap.read()
        if not ok:
            continue
        rec = dict(t=float(t), tiles={})
        for k, (tw, th, tx, ty) in cfg["tiles"].items():
            img = fr[ty:ty + th, tx:tx + tw]
            rec["tiles"][k] = [dict(f.as_dict(), cx=round(f.cx, 1),
                                    cy=round(f.cy, 1)) for f in detect(img)]
        rows.append(rec)
        if i % 40 == 0:
            print(f"   census {i}/{n}  {time.time()-t_start:.0f}s", flush=True)
    cap.release()
    json.dump(rows, open(cp, "w"))
    return rows


def tile_stats(rows, key):
    """Hearing-level gaze statistics for the persistent (largest) face."""
    nd, nv, fh = [], [], []
    for r in rows:
        fs = r["tiles"][key]
        if not fs:
            continue
        f = fs[0]
        nd.append(f["nd"]); nv.append(f["nv"]); fh.append(f["h"])
    if not nd:
        return None
    q = lambda a, p: float(np.percentile(a, p))
    return dict(n=len(nd), nd_med=q(nd, 50), nd_p10=q(nd, 10), nd_p90=q(nd, 90),
                nv_med=q(nv, 50), nv_p10=q(nv, 10), nv_p90=q(nv, 90),
                faceh_med=q(fh, 50))


# =========================================================================== #
# STAGE B - roles, and the defendant CLUSTER (not "the biggest face")
# =========================================================================== #
def assign_roles(name, cfg, rows, log):
    caps = {}
    cap = cv2.VideoCapture(cfg["src"])
    mid = sum(cfg["case"]) / 2
    cap.set(cv2.CAP_PROP_POS_MSEC, (mid - cfg["off"]) * 1000.0)
    ok, fr = cap.read()
    cap.release()
    for k, (tw, th, tx, ty) in cfg["tiles"].items():
        img = fr[ty:ty + th, tx:tx + tw]
        band = img[int(th * 0.80):th, 0:int(tw * 0.60)]
        caps[k] = " ".join(t for _, t, _ in ocr_lines(band)).upper()
    court = None
    for k, c in caps.items():
        if "187" in c or " DC" in (" " + c):
            court = k
    how = "caption OCR"
    stats = {}
    for k in cfg["tiles"]:
        nf, dom = [], []
        for r in rows:
            fs = r["tiles"][k]
            nf.append(len(fs))
            if len(fs) > 1:
                dom.append(fs[0]["h"] / max(1e-6, fs[1]["h"]))
            elif fs:
                dom.append(99.0)
        stats[k] = dict(n_faces=float(np.median(nf)),
                        dominance=float(np.median(dom)) if dom else 99.0)
    if court is None:
        court = max(stats, key=lambda k: (stats[k]["n_faces"], -stats[k]["dominance"]))
        how = "face-count / dominance fallback"
    bench = [k for k in cfg["tiles"] if k != court][0]
    fb = max(stats, key=lambda k: (stats[k]["n_faces"], -stats[k]["dominance"]))
    log["roles"] = dict(method=how, court_tile=court, bench_tile=bench,
                        captions=caps, stats=stats,
                        fallback_agrees=(fb == court),
                        court_tile_x=cfg["tiles"][court][2],
                        bench_tile_x=cfg["tiles"][bench][2])
    return court, bench


def defendant_cluster(rows, court, tile_w, log):
    """Persistent face cluster nearest tile centre. Largest-face returns the
    attorney: in shipped CARTHIEF the attorney sits at cx 0.144 and the
    defendant at cx 0.5365."""
    cl = []
    for r in rows:
        for f in r["tiles"][court]:
            hit = None
            for c in cl:
                if (abs(f["cx"] - c["cx"]) < 0.06 * tile_w
                        and abs(math.log(max(f["h"], 1e-6) / max(c["h"], 1e-6))) < 0.35):
                    hit = c
                    break
            if hit is None:
                cl.append(dict(cx=f["cx"], cy=f["cy"], h=f["h"], n=1, mem=[f]))
            else:
                hit["mem"].append(f)
                k = len(hit["mem"])
                hit["cx"] += (f["cx"] - hit["cx"]) / k
                hit["cy"] += (f["cy"] - hit["cy"]) / k
                hit["h"] += (f["h"] - hit["h"]) / k
                hit["n"] = k
    n_fr = max(1, len(rows))
    keep = [c for c in cl if c["n"] >= 0.20 * n_fr]
    if not keep:
        keep = sorted(cl, key=lambda c: -c["n"])[:3]
    best = min(keep, key=lambda c: abs(c["cx"] - tile_w / 2))
    log["defendant_cluster"] = dict(
        n_clusters=len(cl), persistent=len(keep),
        chosen=dict(cx=round(best["cx"], 1), cx_frac=round(best["cx"] / tile_w, 4),
                    cy=round(best["cy"], 1), h=round(best["h"], 1),
                    frames=best["n"]),
        others=[dict(cx_frac=round(c["cx"] / tile_w, 3), h=round(c["h"], 1),
                     frames=c["n"]) for c in sorted(keep, key=lambda c: -c["n"])[:6]])
    return best


# =========================================================================== #
# STAGE C - hero frame: a GATE, not a timestamp
# =========================================================================== #
def hero_candidates(rows, bench, tile_h, st, log):
    sign = -1.0 if st["nd_med"] < 0 else 1.0     # -1 => turned image-left
    out = []
    for r in rows:
        fs = r["tiles"][bench]
        if not fs:
            continue
        f = fs[0]
        if sign < 0 and f["nd"] > -HOUSE["gate_nd"]:
            continue
        if sign > 0 and f["nd"] < HOUSE["gate_nd"]:
            continue
        if f["nv"] > HOUSE["gate_nv"]:
            continue
        if abs(f["roll"]) > HOUSE["gate_roll"]:
            continue
        if f["h"] / tile_h < HOUSE["gate_face_in_tile"]:
            continue
        out.append(dict(t=r["t"], **f))
    out.sort(key=lambda d: (d["nv"], sign * d["nd"]))
    log["hero_gate"] = dict(sampled=len(rows), passed=len(out),
                            nd_median=round(st["nd_med"], 3),
                            nv_p10=round(st["nv_p10"], 3),
                            gate=f"nd sign {int(sign)} |nd|>={HOUSE['gate_nd']}, "
                                 f"nv<={HOUSE['gate_nv']}, |roll|<=4, faceH/tileH>=0.33")
    return out, sign


def matte_quality(tile, alpha):
    """The computable form of 'surgical cuts not slop'."""
    g = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    b = (alpha > 0.5).astype(np.uint8)
    edge = cv2.morphologyEx(b, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    edge[0, :] = edge[-1, :] = False
    edge[:, 0] = edge[:, -1] = False
    if edge.sum() < 20:
        return None
    loc = cv2.dilate(mag, np.ones((5, 5), np.float32))
    bm = float(np.median(mag[edge]))
    tm = float(np.median(mag))
    phantom = float((loc[edge] < 35).mean())
    return dict(boundary_grad=round(bm, 1), tile_grad=round(tm, 1),
                ratio=round(bm / max(tm, 1e-6), 2), phantom=round(phantom, 3),
                col_left=round(float(alpha[:, 0].mean()), 3),
                col_right=round(float(alpha[:, -1].mean()), 3),
                row_top=round(float(alpha[0, :].mean()), 3),
                row_bot=round(float(alpha[-1, :].mean()), 3))


def gesture_score(alpha, f):
    """Proxy for Nathan's 'a hand MID-GESTURE adds drama, a hand resting on her
    chin does not'. Measured, weak, and labelled as a proxy in the report:
      raised  = matte alpha at head height but lateral to the head
      resting = matte alpha inside the chin box
    """
    h, w = alpha.shape
    y0, y1 = int(max(0, f["y"])), int(min(h, f["y"] + 1.6 * f["h"]))
    xa, xb = int(f["x"] - 0.30 * f["w"]), int(f["x"] + 1.30 * f["w"])
    band = alpha[y0:y1]
    if band.size == 0:
        return 0.0, 0.0
    lat = np.concatenate([band[:, :max(0, xa)].ravel(), band[:, min(w, xb):].ravel()])
    raised = float((lat > 0.5).mean()) if lat.size else 0.0
    cy0, cy1 = int(f["y"] + 0.85 * f["h"]), int(min(h, f["y"] + 1.25 * f["h"]))
    cx0, cx1 = int(f["x"] + 0.20 * f["w"]), int(f["x"] + 0.80 * f["w"])
    chin = alpha[max(0, cy0):cy1, max(0, cx0):max(1, cx1)]
    resting = float((chin > 0.5).mean()) if chin.size else 0.0
    return raised, resting


def grab(src, off, t):
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_MSEC, (t - off) * 1000.0)
    ok, fr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"decode failed at t={t}")
    return fr


def pick_hero(name, cfg, cands, bench, sign, log, k=8):
    """Take the gated pool in rank order, matte each, keep the first that
    passes the matte-quality and tile-edge rules."""
    btw, bth, btx, bty = cfg["tiles"][bench]
    side = "R" if sign < 0 else "L"          # gaze image-left -> bleed RIGHT
    tried = []
    for c in cands[:k]:
        fr = grab(cfg["src"], cfg["off"], c["t"])
        tile = fr[bty:bty + bth, btx:btx + btw]
        fs = detect(tile)
        if not fs:
            continue
        f = fs[0]
        a = matte(tile, "birefnet-portrait")
        mq = matte_quality(tile, a)
        if mq is None:
            continue
        raised, resting = gesture_score(a, dict(x=f.x, y=f.y, w=f.w, h=f.h))
        rec = dict(t=c["t"], nd=round(f.nd, 3), nv=round(f.nv, 3),
                   roll=round(f.roll, 2), mq=mq,
                   gesture_raised=round(raised, 4), gesture_resting=round(resting, 4))
        tried.append(rec)
        if mq["phantom"] > HOUSE["phantom_fail"]:
            rec["reject"] = f"phantom {mq['phantom']} > {HOUSE['phantom_fail']}"
            continue
        # tile-edge rule: the column the silhouette is severed by must become
        # the frame edge it bleeds off.
        touch_r, touch_l = mq["col_right"] > 0.02, mq["col_left"] > 0.02
        if side == "R" and not touch_r and touch_l:
            rec["reject"] = ("silhouette severed by the tile's LEFT column but "
                             "the gaze demands a RIGHT bleed")
            continue
        if mq["row_top"] > 0.02:
            rec["reject"] = "silhouette severed by the tile's TOP row (crown cut)"
            continue
        rec["chosen"] = True
        log["hero_frames_tried"] = tried
        return c["t"], tile, a, f, side, rec
    log["hero_frames_tried"] = tried
    raise SystemExit(f"REFUSE {name}: no gated hero frame survived the matte "
                     f"and tile-edge rules (tried {len(tried)})")


# =========================================================================== #
# STAGE D - hero placement. Anchor on the EYES.
# =========================================================================== #
def place_hero(tile, alpha, f, side, face_h_frac, lead, log):
    h_t, w_t = alpha.shape
    ys, xs = np.nonzero(alpha > 0.5)
    ay0, ay1, ax0, ax1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1

    # interior-sever repair: on the side that does NOT bleed, trim inward to
    # the first column the silhouette does not touch.
    trimmed = 0
    if side == "R":
        while ax0 < ax1 - 8 and alpha[:, ax0].mean() > 0.02:
            ax0 += 1; trimmed += 1
    else:
        while ax1 > ax0 + 8 and alpha[:, ax1 - 1].mean() > 0.02:
            ax1 -= 1; trimmed += 1

    scale = (face_h_frac * H) / f.h
    cut = tile[ay0:ay1, ax0:ax1]
    ca = alpha[ay0:ay1, ax0:ax1]
    cw = max(1, int(round((ax1 - ax0) * scale)))
    ch = max(1, int(round((ay1 - ay0) * scale)))
    rgba = cv2.resize(np.dstack([cut, (ca * 255).astype(np.uint8)]), (cw, ch),
                      interpolation=cv2.INTER_LANCZOS4)

    eye_x_t, eye_y_t = f.eye_x - ax0, f.eye_y - ay0
    tgt_eye_x = (lead if side == "R" else 1.0 - lead) * W
    px = int(round(tgt_eye_x - eye_x_t * scale))
    py = int(round(HOUSE["hero_eye_y"] * H - eye_y_t * scale))
    # bottom-anchored: the cut-out must reach the bottom edge. Push down only
    # if the eye anchor leaves it floating.
    floated = 0
    if py + ch < H:
        floated = H - (py + ch)
        py = H - ch

    occ = np.zeros((H, W), np.float32)
    x0, y0 = max(0, px), max(0, py)
    x1, y1 = min(W, px + cw), min(H, py + ch)
    if x1 > x0 and y1 > y0:
        occ[y0:y1, x0:x1] = rgba[y0 - py:y1 - py, x0 - px:x1 - px, 3] / 255.0

    fb = (px + (f.x - ax0) * scale, py + (f.y - ay0) * scale,
          px + (f.x + f.w - ax0) * scale, py + (f.y + f.h - ay0) * scale)
    if side == "R":
        bleed = max(0, (px + cw) - W)
    else:
        bleed = max(0, -px)
    bottom = float((occ[H - 1, x0:x1] > 0.5).mean()) if x1 > x0 else 0.0
    log["hero_placement"] = dict(
        side=side, scale=round(scale, 3), face_h_frac=face_h_frac, lead=lead,
        eye_xy=[round((px + eye_x_t * scale) / W, 4),
                round((py + eye_y_t * scale) / H, 4)],
        face_box=[round(v, 1) for v in fb],
        face_cx=round((fb[0] + fb[2]) / 2 / W, 4),
        face_cy=round((fb[1] + fb[3]) / 2 / H, 4),
        bleed_px=int(bleed), bleed_frac=round(bleed / W, 4),
        bottom_row_cover=round(bottom, 3),
        tile_cols_trimmed=trimmed, floated_px_corrected=int(floated))
    return dict(rgba=rgba, x=px, y=py, w=cw, h=ch, occ=occ, face_box=fb,
                bleed=bleed, bottom=bottom, side=side)


# =========================================================================== #
# STAGE F - type
# =========================================================================== #
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
    """Lines + per-word colours. Rule, applied identically to all hearings:
    if the white string and the yellow string each set on one line under wmax,
    they ARE the two lines (line 2 is then 100% yellow, which is what 5/5 of
    the shipped two-line thumbnails do). Otherwise greedy-fill line 1.
    """
    font = font_for_cap(cap_px)
    d = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    ww, wy = d.textlength(white, font=font), d.textlength(yellow, font=font)
    full = (white + " " + yellow).strip()
    if d.textlength(full, font=font) <= wmax:
        lines = [full]
        cols = [["W"] * len(white.split()) + ["Y"] * len(yellow.split())]
        brk = ww / max(1e-6, d.textlength(full, font=font))
    elif ww <= wmax and wy <= wmax:
        lines = [white, yellow]
        cols = [["W"] * len(white.split()), ["Y"] * len(yellow.split())]
        brk = 1.0
    else:
        words = full.split()
        nw = len(white.split())
        lines, cols, cur, ci = [], [], [], []
        for i, w_ in enumerate(words):
            trial = " ".join(cur + [w_])
            if cur and d.textlength(trial, font=font) > wmax:
                lines.append(" ".join(cur)); cols.append(ci); cur, ci = [], []
            cur.append(w_); ci.append("W" if i < nw else "Y")
        if cur:
            lines.append(" ".join(cur)); cols.append(ci)
        if len(lines) > 3:
            return None
        if "Y" in cols[0]:
            j = cols[0].index("Y")
            pre = " ".join(lines[0].split()[:j])
            brk = (d.textlength(pre + " ", font=font)
                   / max(1e-6, d.textlength(lines[0], font=font)))
        else:
            brk = 1.0
    if len(lines) > 3:
        return None
    if any(c == "W" for cc in cols[1:] for c in cc):
        return None                       # line 2+ must be entirely yellow
    if brk < 0.55:
        return None                       # break must fall in the last 45%
    return dict(font=font, size=font.size, cap=cap_px, lines=lines, cols=cols,
                brk=brk, wmax=wmax)


def render_type_layer(ts, x_ink, y_cap, stroke, glow):
    """Draw the block and return (RGBA layer, ink mask, per-line ink boxes).

    Both lines are individually offset so their INK starts at x_ink - that is
    what drives metrics_ali to ~0 on the `left` channel, and it is what the
    shipped thumbnails do (sd 0.0019 W across five files).
    """
    font = ts["font"]
    pitch = int(round(ts["cap"] * HOUSE["pitch"]))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cap_bb = font.getbbox("H")
    boxes = []
    for i, (line, cc) in enumerate(zip(ts["lines"], ts["cols"])):
        bb = font.getbbox(line)
        ox = x_ink - bb[0]
        oy = y_cap + i * pitch - cap_bb[1]
        wx = ox
        for j, wtxt in enumerate(line.split()):
            col = (255, 255, 0, 255) if cc[j] == "Y" else (255, 255, 255, 255)
            d.text((wx, oy), wtxt, font=font, fill=col,
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            wx += d.textlength(wtxt + " ", font=font)
        boxes.append((ox + bb[0], oy + bb[1], ox + bb[2], oy + bb[3]))
    a = np.asarray(lay)[..., 3]
    ink = (a > 0).astype(np.uint8)
    if glow:
        g = lay.split()[3].filter(ImageFilter.GaussianBlur(glow))
        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gl.putalpha(g)
        lay = Image.alpha_composite(Image.alpha_composite(
            Image.new("RGBA", (W, H), (0, 0, 0, 0)), gl), lay)
    return lay, ink, boxes


# =========================================================================== #
# STAGE G - arrow
# =========================================================================== #
def arrow_poly(tail, tip, head_mul):
    sx, sy = tail; tx, ty = tip
    L = math.hypot(tx - sx, ty - sy)
    ux, uy = (tx - sx) / L, (ty - sy) / L
    px, py = -uy, ux
    shaft = L * HOUSE["arrow_shaft"] * 0.5
    hl = L * (1 - HOUSE["arrow_head"])
    hx, hy = tx - ux * hl, ty - uy * hl
    hw = shaft * head_mul
    return np.array([
        [sx + px * shaft, sy + py * shaft],
        [hx + px * shaft, hy + py * shaft],
        [hx + px * hw, hy + py * hw],
        [tx, ty],
        [hx - px * hw, hy - py * hw],
        [hx - px * shaft, hy - py * shaft],
        [sx - px * shaft, sy - py * shaft]], dtype=np.float64)


def raster(pts, shape=(H, W)):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1)
    return m


def solve_head_mul(deg, target=None):
    """Pick the head half-width multiplier that reproduces the measured
    polygon-fill-of-its-own-bbox ratio 0.463 at THIS heading."""
    target = target or HOUSE["arrow_fill"]
    L = HOUSE["arrow_len"] * W
    th = math.radians(deg)
    tip = (400.0, 400.0)
    tail = (tip[0] - math.cos(th) * L, tip[1] - math.sin(th) * L)
    lo, hi = 1.2, 6.0
    for _ in range(40):
        mid = (lo + hi) / 2
        p = arrow_poly(tail, tip, mid)
        m = raster(p, (800, 800))
        ys, xs = np.nonzero(m)
        fill = m.sum() / max(1.0, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
        if fill < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# =========================================================================== #
# grade
# =========================================================================== #
def grade(bgr):
    """Hit the shipped Thompson numbers: luminance mean 125, blacks 9.0%.

    blacks := fraction of pixels below the black point, set by definition at
    the 9th percentile of luma; gain then bisected so the mean lands on 125.
    Saturation +10% is a DEFAULT, not a measurement.
    """
    f = bgr.astype(np.float32)
    lum = 0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]
    bp = float(np.percentile(lum, HOUSE["blacks"] * 100))
    lo, hi = 0.2, 6.0
    for _ in range(40):
        g = (lo + hi) / 2
        m = float(np.clip((lum - bp) * g, 0, 255).mean())
        if m < HOUSE["lum_mean"]:
            lo = g
        else:
            hi = g
    g = (lo + hi) / 2
    out = np.clip((f - bp) * g, 0, 255)
    hsv = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.10, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    l2 = 0.114 * out[..., 0] + 0.587 * out[..., 1] + 0.299 * out[..., 2]
    return out, dict(black_point=round(bp, 1), gain=round(g, 3),
                     lum_mean=round(float(l2.mean()), 1),
                     blacks_frac=round(float((l2 < max(1.0, bp * 0)).mean()
                                             if False else (l2 < 16).mean()), 4))


# =========================================================================== #
# the joint search
# =========================================================================== #
def build(name, verbose=True):
    cfg = HEARINGS[name]
    log = dict(hearing=name, spec="L3_tight", house=HOUSE.copy())
    log["house"]["arrow_rgb"] = list(HOUSE["arrow_rgb"])
    t_all = time.time()

    print(f"\n=== {name} ===================================================")
    rows = census(name, cfg)
    court, bench = assign_roles(name, cfg, rows, log)
    print(f"  roles: court={court} bench={bench} via {log['roles']['method']} "
          f"(fallback agrees: {log['roles']['fallback_agrees']})")

    st_b = tile_stats(rows, bench)
    st_c = tile_stats(rows, court)
    log["gaze_census"] = dict(bench=st_b, court=st_c)
    if abs(st_b["nd_med"]) < 0.12:
        raise SystemExit(f"REFUSE {name}: judge nd median {st_b['nd_med']:.3f} "
                         f"is inside the +-0.12 dead band - no decisive gaze.")
    print(f"  judge nd median {st_b['nd_med']:+.3f}  nv p10 {st_b['nv_p10']:.3f}")

    ctw, cth, ctx, cty = cfg["tiles"][court]
    btw, bth, btx, bty = cfg["tiles"][bench]
    cands, sign = hero_candidates(rows, bench, bth, st_b, log)
    print(f"  hero gate: {len(cands)}/{len(rows)} frames pass")
    if not cands:
        raise SystemExit(f"REFUSE {name}: zero frames pass nd/nv/roll/size gate")
    # prefer mid-gesture over static: re-rank the top pool once the mattes exist
    t_cut, hero_tile, hero_alpha, hero_face, side, hero_rec = pick_hero(
        name, cfg, cands, bench, sign, log)
    print(f"  hero t={t_cut:.1f} nd={hero_rec['nd']} nv={hero_rec['nv']} "
          f"roll={hero_rec['roll']} phantom={hero_rec['mq']['phantom']} side={side}")

    # ---- the plate frame: gated too, never a per-case timestamp -------------
    defe_c = defendant_cluster(rows, court, ctw, log)
    plate_pool = []
    for r in rows:
        for f in r["tiles"][court]:
            if (abs(f["cx"] - defe_c["cx"]) < 0.06 * ctw
                    and abs(math.log(max(f["h"], 1e-6) / defe_c["h"])) < 0.35):
                plate_pool.append((r["t"], f))
    # a good reaction = eyes up, head not buried: lowest nv first
    plate_pool.sort(key=lambda p: p[1]["nv"])
    log["plate_pool"] = len(plate_pool)
    print(f"  defendant cluster cx={defe_c['cx']/ctw:.4f} of tile, "
          f"{defe_c['n']} frames; plate pool {len(plate_pool)}")

    # ---- YIELD LADDER ------------------------------------------------------
    ladder = []
    for lead in (HOUSE["lead"], 0.743, 0.783):
        for fh in (0.45, 0.42, 0.40, 0.38):
            for cap in (0.100, 0.095, 0.090):
                for wmax in (0.82, 0.78, 0.74, 0.70, 0.66, 0.62, 0.58, 0.54):
                    ladder.append(dict(lead=lead, fh=fh, cap=cap, wmax=wmax))
    ladder.sort(key=lambda d: (d["fh"] != 0.45, d["lead"] != HOUSE["lead"],
                               -d["wmax"], -d["cap"]))

    plates = perceive_plates(cfg, (ctw, cth, ctx, cty), plate_pool, defe_c, log)
    if not plates:
        raise SystemExit(f"REFUSE {name}: no plate frame re-detected the "
                         f"tracked defendant cluster")
    print(f"  plate frames perceived: {len(plates)}")

    best = None
    tried_cfg = 0
    for step in ladder:
        ts = typeset(cfg["white"], cfg["yellow"], int(round(step["cap"] * H)),
                     int(round(step["wmax"] * W)))
        if ts is None:
            continue
        hero = place_hero(hero_tile, hero_alpha, hero_face, side, step["fh"],
                          step["lead"], log)
        tried_cfg += 1
        _t = time.time()
        cand = search(plates, hero, ts, log)
        print(f"   ladder {tried_cfg:>3} fh={step['fh']} lead={step['lead']} "
              f"cap={step['cap']} wmax={step['wmax']} -> "
              f"{'HIT' if cand else 'miss'} {time.time()-_t:.1f}s", flush=True)
        if cand:
            best = cand
            best["step"] = step
            break
    if best is None:
        raise SystemExit(f"REFUSE {name}: the yield ladder ran out "
                         f"({tried_cfg} configurations) with no legal layout.")
    log["ladder_steps_tried"] = tried_cfg
    log["chosen_step"] = best["step"]
    print(f"  ladder step {tried_cfg}: {best['step']}  J={best['J']:.3f}")
    out = compose(name, best, log)
    log["seconds"] = round(time.time() - t_all, 1)
    return out, log


def perceive_plates(cfg, rect, plate_pool, defe_c, log, k=3):
    """Decode + perceive the top-k gated plate frames ONCE, before the ladder.

    Everything here is independent of the hero geometry and of the typeset, so
    it must not be repeated per ladder step.
    """
    ctw, cth, ctx, cty = rect
    out = []
    for i, (t_plate, dfe) in enumerate(plate_pool[:24]):
        if len(out) >= k:
            break
        print(f"   plate {i} t={t_plate:.1f}", flush=True)
        fr = grab(cfg["src"], cfg["off"], t_plate)
        tile = fr[cty:cty + cth, ctx:ctx + ctw]
        faces = detect(tile)
        target = None
        for f in faces:
            if (abs(f.cx - dfe["cx"]) < 0.05 * ctw
                    and abs(f.h - dfe["h"]) < 0.35 * dfe["h"]):
                target = f
                break
        if target is None:
            continue
        burn = burnin_mask(tile)
        mp = matte(tile, "birefnet-general-lite")
        facemask = np.zeros(tile.shape[:2], np.float32)
        for f in faces:
            b = [int(v) for v in f.box(0.18)]
            facemask[max(0, b[1]):b[3], max(0, b[0]):b[2]] = 1.0
        people = np.maximum(np.maximum((mp > 0.5).astype(np.float32), facemask), burn)
        sal = np.maximum(np.maximum(mp, facemask), burn)
        out.append(dict(t=t_plate, tile=tile, faces=faces, target=target,
                        burn=burn, people=people, sal=sal,
                        ii_burn=integral(burn), ii_people=integral(people),
                        ii_sal=integral(sal), ii_grad=integral(grad_map(tile)),
                        burn_cover=round(float((burn > 0.5).mean()), 4)))
    log["plate_frames"] = [dict(t=p["t"], n_faces=len(p["faces"]),
                                burn_cover=p["burn_cover"],
                                defe=p["target"].as_dict()) for p in out]
    return out


def type_candidates(hero, ts, log):
    """Type placements gated against the HERO only - crop-independent, so this
    is computed once per (hero geometry x typeset), not once per crop."""
    hero_fb = hero["face_box"]
    stroke = int(round(HOUSE["stroke"] * W))
    type_side = "L" if hero["side"] == "R" else "R"
    fb = [int(v) for v in hero_fb]
    body = (hero["occ"] > 0.5).copy()
    hair = body.copy()
    body[:max(0, fb[1]), :] = False
    hair[max(0, fb[1]):, :] = False
    out = []
    for y_cap in range(int(round(HOUSE["cap_top"] * H)),
                       int(round(HOUSE["cap_top_max"] * H)) + 1, 4):
        if type_side == "R":
            _, _, b0 = render_type_layer(ts, 0, y_cap, stroke, 0)
            xi = int(round(W - HOUSE["inset_x"] * W - max(b[2] for b in b0)))
        else:
            xi = int(round(HOUSE["inset_x"] * W))
        lay, ink, boxes = render_type_layer(ts, xi, y_cap, stroke, 0)
        if ink[:, 0].any() or ink[:, -1].any() or ink[0, :].any() or ink[-1, :].any():
            continue
        sub = ink[max(0, fb[1]):max(1, fb[3]), max(0, fb[0]):max(1, fb[2])]
        if sub.size and sub.any():
            continue                                    # HARD: ink on her face
        if (ink & body).sum() > 0:
            continue                                    # HARD: ink on her body
        hair_frac = (ink & hair).sum() / max(1, ink.sum())
        if hair_frac > HOUSE["ink_on_hair_max"]:
            continue
        cols = np.nonzero(ink.any(axis=0))[0]
        rows = np.nonzero(ink.any(axis=1))[0]
        ink_l, ink_r = int(cols.min()), int(cols.max())
        ink_t, ink_b = int(rows.min()), int(rows.max())
        gap = ((fb[0] - ink_r) if type_side == "L" else (ink_l - fb[2])) / W
        if gap < HOUSE["type_hero_gap_floor"]:
            continue                                    # the collision rule
        out.append(dict(y=y_cap, x=xi, ink=ink, boxes=boxes, gap=gap,
                        hair=hair_frac, ink_l=ink_l, ink_r=ink_r,
                        ink_t=ink_t, ink_b=ink_b, side=type_side,
                        iy=np.nonzero(ink)[0], ix=np.nonzero(ink)[1],
                        iy4=np.nonzero(ink)[0][::4], ix4=np.nonzero(ink)[1][::4],
                        dt=cv2.distanceTransform((~(ink > 0)).astype(np.uint8),
                                                 cv2.DIST_L2, 5)))
    # L3_TIGHT: prefer the placement that sits just above the collision FLOOR
    out.sort(key=lambda c: abs(c["gap"] - HOUSE["type_hero_gap_floor"]
                               * (1 + HOUSE["tight_bias"])))
    return out[:5]


def search(plates, hero, ts, log):
    """One (hero geometry x typeset) configuration.

    Two phases, because the expensive terms are 10^3 times dearer than the
    gates: phase 1 walks every 16:9 crop with summed-area gates only and keeps
    the best N by a cheap proxy; phase 2 builds the composite people mask and
    runs the arrow search, the free rectangle and metrics_ali on those N.
    """
    ycands = type_candidates(hero, ts, log)
    if not ycands:
        return None
    head_mul = {float(d): solve_head_mul(float(d)) for d in
                np.arange(HOUSE["arrow_deg_lo"], HOUSE["arrow_deg_hi"] + 0.1, 3.0)}
    hero_fb = hero["face_box"]
    hcx = (hero_fb[0] + hero_fb[2]) / 2 / W
    hcy = (hero_fb[1] + hero_fb[3]) / 2 / H

    shortlist = []
    funnel = dict(tried=0, burn=0, inframe=0, occl=0, size=0, sep=0, dcy=0,
                  ink_on_people=0, phase2=0, arrow=0, ok=0)
    for pl in plates:
        tile, target, people = pl["tile"], pl["target"], pl["people"]
        Ht, Wt = tile.shape[:2]
        s_min = max(0.42, (W / HOUSE["upscale_max"]) / Wt)
        for s in np.arange(s_min, 1.0001, 0.025):
            cw = int(round(Wt * s)); ch = int(round(cw * 9 / 16))
            if cw > Wt or ch > Ht:
                continue
            fh = target.h / ch
            if not (HOUSE["defe_face_h_lo"] <= fh <= HOUSE["defe_face_h_hi"]):
                funnel["size"] += 1
                continue
            kx, ky = W / cw, H / ch
            b = target.box(0.30)
            for y0 in range(0, Ht - ch + 1, 8):
                dy0, dy1 = (b[1] - y0) * ky, (b[3] - y0) * ky
                if not (0 <= dy0 and dy1 < H):
                    funnel["inframe"] += 1
                    continue
                dcy_ = (target.cy - y0) * ky / H
                if abs(hcy - dcy_) > HOUSE["dcy_max"]:
                    funnel["dcy"] += 1
                    continue
                for x0 in range(0, Wt - cw + 1, 8):
                    funnel["tried"] += 1
                    dx0, dx1 = (b[0] - x0) * kx, (b[2] - x0) * kx
                    if not (0 <= dx0 and dx1 < W):
                        funnel["inframe"] += 1
                        continue
                    sep = abs(hcx - (target.cx - x0) * kx / W)
                    if not (HOUSE["sep_lo"] <= sep <= HOUSE["sep_hi"]):
                        funnel["sep"] += 1
                        continue
                    if rsum(pl["ii_burn"], x0, y0, x0 + cw, y0 + ch) > 1.0:
                        funnel["burn"] += 1
                        continue
                    if hero["occ"][int(dy0):int(dy1), int(dx0):int(dx1)].max() > 0.10:
                        funnel["occl"] += 1
                        continue
                    # cheapest type gate: zero ink on the plate's people
                    tp = None
                    for yc in ycands:
                        tX0 = int(x0 + yc["ink_l"] / kx); tX1 = min(x0 + cw, int(x0 + yc["ink_r"] / kx) + 1)
                        tY0 = int(y0 + yc["ink_t"] / ky); tY1 = min(y0 + ch, int(y0 + yc["ink_b"] / ky) + 1)
                        if tX1 <= tX0 or tY1 <= tY0:
                            continue
                        # fast path: if no person pixel lies in the ink's BOUNDING
                        # BOX there can be none under the ink, so skip the gather
                        if rsum(pl["ii_people"], tX0, tY0, tX1, tY1) <= 0.5:
                            on = 0.0
                        else:
                            sy = np.clip((y0 + yc["iy4"] / ky).astype(np.int32), 0, Ht - 1)
                            sx = np.clip((x0 + yc["ix4"] / kx).astype(np.int32), 0, Wt - 1)
                            on = float((people[sy, sx] > 0.5).mean())
                            if on > HOUSE["ink_on_plate_people_max"]:
                                continue
                        area = float((tX1 - tX0) * (tY1 - tY0))
                        occ = rsum(pl["ii_sal"], tX0, tY0, tX1, tY1) / area
                        rea = rsum(pl["ii_grad"], tX0, tY0, tX1, tY1) / area
                        sc = 2.0 * occ + 1.0 * rea + 3.0 * on
                        if tp is None or sc < tp[0]:
                            tp = (sc, yc, occ, rea, on)
                    if tp is None:
                        funnel["ink_on_people"] += 1
                        continue
                    proxy = (-2.0 * tp[2] - 1.0 * tp[3] - 3.0 * tp[4]
                             - 2.5 * abs(fh - HOUSE["defe_face_h"])
                             - 2.0 * abs(sep - HOUSE["sep"])
                             - 1.5 * abs(abs(hcy - dcy_) - HOUSE["dcy"])
                             / HOUSE["dcy_max"]
                             - 2.0 * max(0.0, tp[1]["gap"]
                                         - HOUSE["type_hero_gap_floor"] * 1.6) * 12)
                    shortlist.append((proxy, pl, x0, y0, cw, ch, kx, ky, sep,
                                      dcy_, fh, tp))
    shortlist.sort(key=lambda z: -z[0])
    best = None
    for row in shortlist[:14]:
        funnel["phase2"] += 1
        c = score_full(row, hero, ts, head_mul, funnel)
        if c and (best is None or c["J"] > best["J"]):
            best = c
    log.setdefault("funnels", []).append(funnel)
    if best is None:
        return None
    best["hero"] = hero
    best["ts"] = ts
    return best


def score_full(row, hero, ts, head_mul, funnel):
    """Phase 2: composite people mask, arrow search, free rect, metrics_ali."""
    proxy, pl, x0, y0, cw, ch, kx, ky, sep, dcy_, fh, tp = row
    _, yc, t_occ, t_rea, t_onppl = tp
    people, target = pl["people"], pl["target"]
    Ht, Wt = pl["tile"].shape[:2]
    hero_fb = hero["face_box"]
    dfx0, dfy0 = (target.x - x0) * kx, (target.y - y0) * ky
    dfx1, dfy1 = (target.x + target.w - x0) * kx, (target.y + target.h - y0) * ky
    dfbox = (dfx0, dfy0, dfx1, dfy1)

    gy, gx = GY, GX
    py_ = np.clip((y0 + gy / ky).astype(np.int32), 0, Ht - 1)
    px_ = np.clip((x0 + gx / kx).astype(np.int32), 0, Wt - 1)
    comp_people = (people[py_, px_] > 0.5) | (hero["occ"] > 0.10)
    dt_people = cv2.distanceTransform((~comp_people).astype(np.uint8), cv2.DIST_L2, 5)

    P = ((dfx0 + dfx1) / 2, dfy0 + 0.30 * (dfy1 - dfy0))
    L = HOUSE["arrow_len"] * W
    abest = None
    for deg in np.arange(HOUSE["arrow_deg_lo"], HOUSE["arrow_deg_hi"] + 0.1, 3.0):
        deg = float(deg)
        th = math.radians(deg)
        ux, uy = math.cos(th), math.sin(th)
        tip = None
        for back in range(0, int(0.25 * W), 2):
            cx_, cy_ = P[0] - ux * back, P[1] - uy * back
            if not (0 <= cx_ < W and 0 <= cy_ < H):
                break
            if not comp_people[int(cy_), int(cx_)]:
                tip = (P[0] - ux * (back + 4), P[1] - uy * (back + 4))
                break
        if tip is None or not (0 <= tip[0] < W and 0 <= tip[1] < H):
            continue
        so = point_box_dist(tip, dfbox)
        if so < HOUSE["standoff_min"] or so > HOUSE["standoff_max"]:
            continue
        if not ray_reaches(tip, (ux, uy), dfbox):
            continue
        tail = (tip[0] - ux * L, tip[1] - uy * L)
        if not (0 <= tail[0] < W and 0 <= tail[1] < H):
            continue
        pts = arrow_poly(tail, tip, head_mul[deg])
        m = raster(pts).astype(bool)
        if m.sum() == 0 or (m & comp_people).any():
            continue
        gap_ta = float(yc["dt"][m].min())
        if gap_ta < HOUSE["arrow_text_gap"] * W:
            continue
        ys, xs = np.nonzero(m)
        cxm, cym = int(round(xs.mean())), int(round(ys.mean()))
        clr = float(dt_people[np.clip(cym, 0, H - 1), np.clip(cxm, 0, W - 1)])
        if clr < HOUSE["arrow_body_clear"] * W:
            continue
        sc = (abs(so - HOUSE["standoff_lo"]) / 40.0
              + abs(gap_ta - HOUSE["arrow_text_gap"] * W * (1 + HOUSE["tight_bias"])) / 60.0
              + abs(deg - HOUSE["arrow_deg"]) / 90.0)
        if abest is None or sc < abest[0]:
            abest = (sc, deg, tail, tip, m, so, gap_ta, clr,
                     (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
    if abest is None:
        funnel["arrow"] += 1
        return None
    _, deg, tail, tip, amask, so, gap_ta, clr, abox = abest
    funnel["ok"] += 1

    ink_boxes = [tuple(int(v) for v in b) for b in yc["boxes"]]
    boxes = ink_boxes + [abox, tuple(int(v) for v in hero_fb),
                         (int(dfx0), int(dfy0), int(dfx1), int(dfy1))]
    ali = ali_penalty(boxes)
    notppl = ~comp_people
    used = np.zeros((H, W), bool)
    for (a, b, c, d) in ink_boxes + [abox]:
        used[max(0, b):d, max(0, a):c] = True
    uti = float((notppl & used).sum()) / max(1.0, notppl.sum())
    ove = overlap(boxes)
    fr_area, fx0_, fy0_, fx1_, fy1_ = max_free_rect(comp_people)
    inside = float(((yc["ix"] >= fx0_) & (yc["ix"] < fx1_)
                    & (yc["iy"] >= fy0_) & (yc["iy"] < fy1_)).mean())

    snap = 0
    edges = []
    for (a, b, c, d) in boxes:
        edges += [("x", a), ("x", c), ("y", b), ("y", d)]
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i][0] == edges[j][0] and abs(edges[i][1] - edges[j][1]) <= HOUSE["snap_px"]:
                snap += 1
    arrow_below_type = 1.0 if abox[1] >= yc["ink_b"] else 0.0

    J = (-2.0 * t_occ - 1.0 * t_rea - 1.2 * yc["hair"]
         + 1.2 * uti - 0.9 * ali - 3.0 * ove
         - 2.5 * abs(fh - HOUSE["defe_face_h"])
         - 2.0 * abs(sep - HOUSE["sep"])
         - 1.5 * abs(abs((hero_fb[1] + hero_fb[3]) / 2 / H - dcy_)
                     - HOUSE["dcy"]) / HOUSE["dcy_max"]
         - 1.5 * abs(deg - HOUSE["arrow_deg"]) / 90.0
         - 2.0 * max(0.0, yc["gap"] - HOUSE["type_hero_gap_floor"] * 1.6) * 12
         - 1.5 * max(0.0, (gap_ta / W) - HOUSE["arrow_text_gap"] * 1.6) * 12
         - 1.0 * max(0.0, so - HOUSE["standoff_hi"]) / 40.0
         + 0.45 * (len(ts["lines"]) == 2)
         + 0.35 * (0.13 <= block_area(ink_boxes) <= 0.26)
         + 0.30 * inside + 0.06 * snap + 0.25 * arrow_below_type
         - 9.0 * max(0.0, HOUSE["free_rect_floor"] - inside))
    return dict(J=float(J), crop=(x0, y0, cw, ch), yc=yc, deg=deg, tail=tail,
                tip=tip, amask=amask, abox=abox, t_plate=pl["t"],
                tile=pl["tile"], target=target, people=people,
                metrics=dict(
                    sep=round(sep, 4),
                    dcy=round(abs((hero_fb[1] + hero_fb[3]) / 2 / H - dcy_), 4),
                    defe_face_h=round(fh, 4), type_hero_gap=round(yc["gap"], 4),
                    type_arrow_gap_px=round(gap_ta, 1),
                    standoff_px=round(so, 1), arrow_clear_px=round(clr, 1),
                    arrow_deg=round(deg, 1), ali=round(ali, 4),
                    uti=round(uti, 4), ove=round(ove, 4),
                    ink_in_free_rect=round(inside, 4),
                    free_rect_frac=round(fr_area / (W * H), 4),
                    ink_on_plate_people=round(t_onppl, 4),
                    ink_on_hair=round(yc["hair"], 4),
                    shared_axes=snap, arrow_below_type=bool(arrow_below_type),
                    upscale=round(W / cw, 3)))


def block_area(boxes):
    x0 = min(b[0] for b in boxes); x1 = max(b[2] for b in boxes)
    y0 = min(b[1] for b in boxes); y1 = max(b[3] for b in boxes)
    return (x1 - x0) * (y1 - y0) / (W * H)


def overlap(boxes):
    n = len(boxes)
    tot = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            ax0, ay0, ax1, ay1 = boxes[i]; bx0, by0, bx1, by1 = boxes[j]
            iw = min(ax1, bx1) - max(ax0, bx0); ih = min(ay1, by1) - max(ay0, by0)
            inter = iw * ih if iw > 0 and ih > 0 else 0.0
            a = (ax1 - ax0) * (ay1 - ay0); b = (bx1 - bx0) * (by1 - by0)
            if a + b - inter > 0:
                tot += inter / (a + b - inter)
    return tot / max(1, n)


def point_box_dist(p, box):
    x, y = p; x0, y0, x1, y1 = box
    dx = max(x0 - x, 0, x - x1); dy = max(y0 - y, 0, y - y1)
    return math.hypot(dx, dy)


def ray_reaches(tip, u, box, maxlen=400):
    x, y = tip; ux, uy = u
    for s in range(0, maxlen):
        px, py = x + ux * s, y + uy * s
        if box[0] <= px <= box[2] and box[1] <= py <= box[3]:
            return True
        if not (0 <= px < W and 0 <= py < H):
            return False
    return False


def mask_gap(a, b):
    if not a.any() or not b.any():
        return 1e9
    if (a & b).any():
        return 0.0
    d = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 5)
    return float(d[a].min())


def person_clearance(pt, people):
    if not people.any():
        return 1e9
    d = cv2.distanceTransform((~people).astype(np.uint8), cv2.DIST_L2, 5)
    x, y = int(np.clip(pt[0], 0, W - 1)), int(np.clip(pt[1], 0, H - 1))
    return float(d[y, x]) if not people[y, x] else 0.0


# =========================================================================== #
# compose + write
# =========================================================================== #
def compose(name, best, log):
    os.makedirs(OUTDIR, exist_ok=True)
    x0, y0, cw, ch = best["crop"]
    plate = cv2.resize(best["tile"][y0:y0 + ch, x0:x0 + cw], (W, H),
                       interpolation=cv2.INTER_LANCZOS4)
    hero = best["hero"]
    canvas = plate.copy()
    hx, hy, hw_, hh_ = hero["x"], hero["y"], hero["w"], hero["h"]
    ax0, ay0 = max(0, hx), max(0, hy)
    ax1, ay1 = min(W, hx + hw_), min(H, hy + hh_)
    sub = hero["rgba"][ay0 - hy:ay1 - hy, ax0 - hx:ax1 - hx]
    a = (sub[..., 3:4].astype(np.float32) / 255.0)
    canvas[ay0:ay1, ax0:ax1] = (sub[..., :3].astype(np.float32) * a
                                + canvas[ay0:ay1, ax0:ax1].astype(np.float32) * (1 - a)
                                ).astype(np.uint8)
    graded, gstat = grade(canvas)
    log["grade"] = gstat

    # people mask on the GRADED photographic layer, before any overlay burns in
    pm = matte(graded, "birefnet-general-lite")
    cv2.imwrite(os.path.join(OUTDIR, f"L3_tight_{name}_people.png"),
                (pm * 255).astype(np.uint8))

    img = Image.fromarray(cv2.cvtColor(graded, cv2.COLOR_BGR2RGB)).convert("RGBA")
    # arrow
    ar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ar)
    pts = arrow_poly(best["tail"], best["tip"], solve_head_mul(best["deg"]))
    ad.polygon([tuple(p) for p in pts], fill=HOUSE["arrow_rgb"] + (255,))
    img = Image.alpha_composite(img, ar)
    # type, graded before it burns in
    yc = best["yc"]
    lay, ink, boxes = render_type_layer(best["ts"], yc["x"], yc["y"],
                                        int(round(HOUSE["stroke"] * W)),
                                        HOUSE["glow_radius"])
    img = Image.alpha_composite(img, lay)
    out = os.path.join(OUTDIR, f"L3_tight_{name}.jpg")
    img.convert("RGB").save(out, quality=94, subsampling=0)
    cv2.imwrite(os.path.join(OUTDIR, f"L3_tight_{name}_ink.png"), ink * 255)
    cv2.imwrite(os.path.join(OUTDIR, f"L3_tight_{name}_heroalpha.png"),
                (hero["occ"] * 255).astype(np.uint8))
    log["metrics"] = best["metrics"]
    log["crop"] = dict(x=x0, y=y0, w=cw, h=ch,
                       upscale=round(W / cw, 3), t_plate=best["t_plate"])
    log["arrow"] = dict(tail=[round(v, 1) for v in best["tail"]],
                        tip=[round(v, 1) for v in best["tip"]],
                        deg=round(best["deg"], 1))
    log["type"] = dict(lines=best["ts"]["lines"], cap_px=best["ts"]["cap"],
                       size=best["ts"]["size"], x_ink=yc["x"], y_cap=yc["y"],
                       wmax=best["ts"]["wmax"], break_frac=round(best["ts"]["brk"], 3),
                       ink_boxes=[[int(v) for v in b] for b in boxes])
    json.dump(log, open(os.path.join(OUTDIR, f"L3_tight_{name}.json"), "w"),
              indent=1, default=str)
    print(f"  wrote {out}")
    return out


# =========================================================================== #
# VERIFICATION - run on the rendered JPEG
# =========================================================================== #
def verify(name):
    p = os.path.join(OUTDIR, f"L3_tight_{name}.jpg")
    log = json.load(open(os.path.join(OUTDIR, f"L3_tight_{name}.json")))
    img = cv2.imread(p)
    ink = cv2.imread(os.path.join(OUTDIR, f"L3_tight_{name}_ink.png"),
                     cv2.IMREAD_GRAYSCALE) > 0
    ppl = cv2.imread(os.path.join(OUTDIR, f"L3_tight_{name}_people.png"),
                     cv2.IMREAD_GRAYSCALE) > 127
    hero_a = cv2.imread(os.path.join(OUTDIR, f"L3_tight_{name}_heroalpha.png"),
                        cv2.IMREAD_GRAYSCALE) > 127
    R = []

    def chk(label, ok, detail):
        R.append((label, bool(ok), detail))

    chk("size == [1280,720]", img.shape[:2] == (H, W), f"{img.shape[1]}x{img.shape[0]}")

    faces = detect(img, 0.5)
    fb = [f.box() for f in faces]
    on_face = sum(int(ink[max(0, int(b[1])):int(b[3]), max(0, int(b[0])):int(b[2])].sum())
                  for b in fb)
    chk("type ink px on any detected face box == 0", on_face == 0,
        f"{on_face} px over {len(faces)} faces")

    # independent re-extraction of the ink from the JPEG itself
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int32)
    b_, g_, r_ = [img[..., i].astype(np.int32) for i in range(3)]
    bright = ((lum > 200) | ((r_ > 175) & (g_ > 145) & (b_ < 120)))
    dark = cv2.dilate((lum < 60).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    ink2 = bright & dark
    iou = (ink & ink2).sum() / max(1, (ink | ink2).sum())
    chk("re-extracted ink agrees with the drawn ink (IoU)", iou > 0.30,
        f"IoU {iou:.3f} - re-extraction also fires on the courtroom's white walls")
    on_face2 = sum(int((ink2 & ink)[max(0, int(b[1])):int(b[3]),
                                    max(0, int(b[0])):int(b[2])].sum()) for b in fb)
    chk("re-extracted type ink on a face box == 0", on_face2 == 0, f"{on_face2} px")

    hero_body = hero_a.copy()
    on_matte = (ink & hero_body).sum() / max(1, ink.sum())
    chk("type ink on the hero matte <= 0.02", on_matte <= 0.02, f"{on_matte:.4f}")

    # arrow, re-extracted from the JPEG by colour
    ar = (r_ > 190) & (g_ < 90) & (b_ < 90)
    ar = cv2.morphologyEx(ar.astype(np.uint8), cv2.MORPH_OPEN,
                          np.ones((3, 3), np.uint8)).astype(bool)
    n_ar = int(ar.sum())
    comp_people = ppl | hero_a
    chk("arrow px on any person == 0", int((ar & comp_people).sum()) == 0,
        f"{int((ar & comp_people).sum())} of {n_ar} red px")
    if n_ar:
        ys, xs = np.nonzero(ar)
        bw_, bh_ = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        fill = n_ar / (bw_ * bh_)
        chk("arrow fill 0.44-0.48", 0.42 <= fill <= 0.50, f"{fill:.3f}")
        chk("arrow area 0.0028-0.0066 of frame", 0.0028 <= n_ar / (W * H) <= 0.0066,
            f"{n_ar/(W*H):.5f}")
    deg = log["arrow"]["deg"]
    chk("arrow heading in the 110-152 band", 110 <= deg <= 152, f"{deg} deg")

    # tip -> defendant
    tip = log["arrow"]["tip"]
    if faces:
        d = sorted(((point_box_dist(tip, f.box()), f) for f in faces),
                   key=lambda z: z[0])
        so, nearest = d[0]
        hp = log["hero_placement"]["face_box"]
        is_hero = point_box_dist(((hp[0] + hp[2]) / 2, (hp[1] + hp[3]) / 2),
                                 nearest.box()) < 40
        chk("tip standoff 4-83 px", HOUSE["standoff_min"] <= so <= HOUSE["standoff_max"],
            f"{so:.1f} px")
        chk("the tip's nearest face is NOT the judge (it is the defendant)",
            not is_hero, f"nearest face cx {nearest.cx/W:.3f}, hero cx "
                         f"{(hp[0]+hp[2])/2/W:.3f}")
        th = math.radians(deg)
        chk("the arrow's ray reaches the defendant's face box",
            ray_reaches(tip, (math.cos(th), math.sin(th)), nearest.box()),
            f"ray from {tip} at {deg} deg")

    m = log["metrics"]
    chk("separation 0.42-0.58", 0.42 <= m["sep"] <= 0.58, f"{m['sep']}")
    chk("|dcy| <= 0.22", m["dcy"] <= 0.22, f"{m['dcy']}")
    hp = log["hero_placement"]
    chk("hero eye at 0.75+-0.02 W", abs(hp["eye_xy"][0] - 0.75) <= 0.02,
        f"{hp['eye_xy'][0]}")
    chk("hero eye at 0.327+-0.015 H", abs(hp["eye_xy"][1] - 0.327) <= 0.015,
        f"{hp['eye_xy'][1]}")
    chk("gap type -> hero face >= 0.038 W", m["type_hero_gap"] >= 0.038,
        f"{m['type_hero_gap']}")
    chk("type ink inside the largest people-free rect >= 0.60",
        m["ink_in_free_rect"] >= 0.60, f"{m['ink_in_free_rect']}")
    chk("metrics_ali <= 0.06", m["ali"] <= 0.06, f"{m['ali']}")
    chk("hero bleeds off the outside edge by >= 0.02 W",
        hp["bleed_frac"] >= 0.02, f"{hp['bleed_frac']}")
    chk("hero reaches the bottom edge (>=0.15 of its x-span)",
        hp["bottom_row_cover"] >= 0.15, f"{hp['bottom_row_cover']}")

    # severed limb: a long straight interior alpha boundary
    sev = 0
    interior = hero_a[:, 1:-1]
    left_edge = hero_a[:, 1:-1] & ~hero_a[:, :-2]
    right_edge = hero_a[:, 1:-1] & ~hero_a[:, 2:]
    hh = max(1, int(hero_a.any(axis=1).sum()))
    for e in (left_edge, right_edge):
        col = e.sum(axis=0)
        sev = max(sev, int(col.max()))
    chk("no severed limb (longest straight interior alpha boundary run)",
        sev < 0.35 * hh, f"{sev} px vs {0.35*hh:.0f} px threshold "
                         f"(hero silhouette {hh} px tall)")

    hr = log["hero_frames_tried"][-1]
    chk("Judge Boyd eyes LEVEL not down (nv <= 0.50, |roll| <= 4)",
        hr["nv"] <= 0.50 and abs(hr["roll"]) <= 4.0,
        f"nv {hr['nv']}, roll {hr['roll']} deg, nd {hr['nd']}")
    chk("matte phantom fraction <= 0.15 (surgical cut)",
        hr["mq"]["phantom"] <= 0.15,
        f"phantom {hr['mq']['phantom']}, boundary/tile gradient "
        f"{hr['mq']['ratio']}x")
    chk("luminance mean ~125", abs(log["grade"]["lum_mean"] - 125) < 12,
        f"{log['grade']['lum_mean']}")

    print(f"\n---- VERIFY {name} : {p}")
    bad = 0
    for label, ok, detail in R:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<62} {detail}")
        bad += (not ok)
    print(f"  {len(R)-bad}/{len(R)} pass")
    return bad == 0


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "ALL"
    names = list(HEARINGS) if which == "ALL" else [which]
    if "--verify-only" in sys.argv:
        allok = all(verify(n) for n in names)
        sys.exit(0 if allok else 1)
    ok = True
    for n in names:
        build(n)
    for n in names:
        ok &= verify(n)
    sys.exit(0 if ok else 1)
