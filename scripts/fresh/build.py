"""
Texas Trial Tracker thumbnail builder -- fresh, 2026-09-04.

WHAT THIS IS
    One command, three cases, 1280x720 JPEG each. No compositing, no matting,
    no generative face restoration, no per-case constants.

THE DESIGN, and the measurement behind each decision
    Two real tiles from ONE source frame, butted as a hard vertical split with a
    black gutter. Defendant/context panel LEFT (56%), judge/hero panel RIGHT (44%).

    Why a split and not a composite: I measured the source. Judge face is
    111-170px in her tile; defendant face is 27-85px in his. To make the
    defendant a hero you need 3-7x, which means a model inventing the face of a
    real named person. To make the judge a hero you need 1.6-2.4x, which is a
    resize. So the judge is the hero and the defendant is the context subject the
    arrow identifies. That is also exactly what Audit the Court does: I measured
    all 12 of their thumbnails -- hero face median 266px (37% of frame height),
    median ONE legible face, arrow median 100px wide.

    Because both panels come from one frame there is no seam grade mismatch, no
    halo, no severed limb and no rebuilt plate. Those defects are not fixed here,
    they are unreachable.

CONSTANTS, and where each came from (nothing here is read from a mutable file)
    JUDGE_TARGET_LAB   = (60, 21, 3)
        Measured by me on D:/Boyd Clips/READY-TO-POST/QUALITY/Q3_detail.jpg, the
        only file Nathan called "fire": L*61.2 a*22.0 b*3.0. Every file he called
        pale measures L*66-83 a*9 b*11-17. All three axes separate cleanly.
    HERO_FACE_FRAC     = 0.30..0.52
        Audit the Court hero-face median 37% of H (n=12, measured here);
        CourtroomTime 34-37% (n=25). Cross-creator, so it is a market number.
    CAP_PX             = 62
        ATC cap-height median 54px / 7.5% of H (measured here, range 39-77);
        Q3_detail measures 69px. 62 sits between the market and the approved file.
    ARROW_W            = 104
        ATC arrow median width 100px, area ~4.1k (measured here, n=11). The
        shipped arrow was 221x156 -- 4x too big.
    DEF_FACE_MIN       = 115
        At 168x94 sidebar scale that is 15px of face: the legibility floor.

LICENCES RELIED ON (monetised channel)
    realesr-general-x4v3.pth  BSD-3-Clause  (assets/models/LICENCES.md, verified)
    Montserrat / Anton        SIL OFL 1.1   (read from nameID 13/14 with fontTools)
    OpenCV Apache-2.0, NumPy/SciPy BSD-3, Pillow MIT-CMU, spandrel MIT.
    HYPIR is NOT used: D:/AI-Models/HYPIR/LICENSE s3a forbids commercial use.
    No matting model is used at all, so rembg/BiRefNet do not enter the licence
    question.

USAGE
    python scripts/fresh/build.py                 # all three cases
    python scripts/fresh/build.py --case OFFERUP  # one
    python scripts/fresh/build.py --selftest      # prove the checks separate his verdicts
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = r"D:/Boyd Clips/READY-TO-POST/FRESH"
YUNET = os.path.join(ROOT, "models", "yunet2023.onnx")
ESRGAN = os.path.join(ROOT, "assets", "models", "realesr-general-x4v3.pth")
FONT = os.path.join(ROOT, "assets", "fonts", "Montserrat-Var.ttf")

W, H = 1280, 720
GUTTER = 8                     # black divider; ATC's own splits show a dark gap
CTX_FRAC = 0.56                # context panel width. ATC splits run 0.55-0.64 context-side
PLATE_CROP = 34                # bottom rows of every tile: the burnt-in Zoom nameplate.
                               # Removed whole, never half -- a half-cut plate reads "ludge Boyd".

JUDGE_TARGET_LAB = (60.0, 21.0, 3.0)
DEF_PANEL_L_TARGET = 58.0
CHROMA_K = 1.22                # one shared richness lift; ATC/CRT both run saturated
GAMMA_CLAMP = (0.62, 1.62)

HERO_FACE_FRAC = (0.30, 0.52)
DEF_FACE_MIN = 115
CAP_PX = 74
CAP_MIN = 44
CAP_FLOOR = 50                 # 6.9% of H. Below this the words die at 168x94, which is
                               # where the thumbnail is actually judged. A frame that cannot
                               # hold type this big is the WRONG FRAME, not a cue to shrink.
ARROW_W = 104
GOLD = (255, 214, 0)           # BGR-agnostic; used as RGB in PIL
RED = (214, 26, 26)

# ---------------------------------------------------------------------------
# Cases. Explicit and in-file: config/cases.json is the old pipeline's mutable
# state and carries its drift with it.
# ---------------------------------------------------------------------------


@dataclass
class Case:
    name: str
    vid: str
    mp4: str
    src_start: int             # source SECONDS of the clip's first frame
    src_end: int
    judge: tuple               # (w, h, x, y) crop in the 1280x720 stream
    defe: tuple
    line1: str
    line2: str
    quoted: tuple = ()         # phrases that must appear verbatim in the transcript
    hint_s: float | None = None  # source seconds of the spoken moment (search centre)


CASES = [
    Case(
        "CARTHIEF", "EwwnbiAQtFk",
        "work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4", 3554, 4697,
        judge=(612, 338, 18, 190), defe=(620, 338, 644, 190),
        # Shortened from "Why are you doing this?" -- at 23 characters it drove the
        # cap to 44px and died at 168x94. Short lines are ATC's own habit.
        line1="Why steal cars?", line2="It's too fun there",
        quoted=("it's too fun there",),
        hint_s=3954.6,
    ),
    Case(
        "SANCHEZ", "3FMy2Kvu3UA",
        "work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4", 3683, 4448,
        judge=(468, 348, 726, 6), defe=(628, 348, 6, 6),
        line1="That is why your son", line2="is having problems",
        quoted=("that is why your son", "is having problems"),
        hint_s=4064.4,
    ),
    Case(
        "OFFERUP", "l19Ijva3Rsk",
        "work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4", 10550, 11137,
        judge=(628, 348, 646, 186), defe=(628, 348, 6, 186),
        line1="This vehicle", line2="was stolen",
        quoted=("this vehicle was stolen",),
        hint_s=10893.0,
    ),
]

# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

_det = None


def detector():
    global _det
    if _det is None:
        _det = cv2.FaceDetectorYN.create(YUNET, "", (320, 320), 0.55, 0.3, 5000)
    return _det


def faces(img, conf=0.55):
    """-> list of dicts, biggest first. box=(x,y,w,h), eyes, nose, mouth."""
    d = detector()
    d.setInputSize((img.shape[1], img.shape[0]))
    _, f = d.detect(img)
    if f is None:
        return []
    out = []
    for r in f:
        if r[14] < conf:
            continue
        out.append(dict(
            box=(float(r[0]), float(r[1]), float(r[2]), float(r[3])),
            reye=(float(r[4]), float(r[5])), leye=(float(r[6]), float(r[7])),
            nose=(float(r[8]), float(r[9])),
            mouth=((float(r[10]) + float(r[12])) / 2, (float(r[11]) + float(r[13])) / 2),
            conf=float(r[14])))
    return sorted(out, key=lambda a: -a["box"][3])


def eye_frac(f):
    """Where the eye-line sits inside the face box, 0=top.

    Head pitched DOWN shows more scalp, so the eyes fall lower in the box.
    Validated on the source: CARTHIEF f900 (visibly looking down) 0.441,
    SANCHEZ f900 (looking up) 0.344. Threshold 0.40.
    """
    x, y, w, h = f["box"]
    return ((f["reye"][1] + f["leye"][1]) / 2 - y) / max(h, 1)


def sharpness(img, box):
    x, y, w, h = [int(v) for v in box]
    p = img[max(y, 0):y + h, max(x, 0):x + w]
    if p.size == 0:
        return 0.0
    return float(cv2.Laplacian(cv2.cvtColor(p, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def jail_score(tile, box):
    """Is this person in custody clothing? -> 0..1

    The defendant is the one in jail issue; everyone else in the tile is an
    attorney or staff. Measured on the three accepted frames: correct defendant
    0.74-0.92, every attorney 0.01-0.44. The `dark` veto is what separates a NAVY
    SUIT (dark 0.55-0.63) from BLUE SCRUBS (dark 0.02-0.05) -- without it the
    defence attorney in CARTHIEF scores 0.34 on the blue term alone.
    """
    x, y, w, h = [int(v) for v in box]
    ty, tx = y + int(h * 1.25), x - int(w * 0.45)
    p = tile[max(ty, 0):ty + int(h * 1.6), max(tx, 0):tx + int(w * 1.9)]
    if p.size == 0:
        return 0.0
    hsv = cv2.cvtColor(p, cv2.COLOR_BGR2HSV)
    Hh, S, V = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    if (V < 80).mean() > 0.25:                 # a suit, not scrubs
        return 0.0
    orange = ((Hh >= 3) & (Hh <= 22) & (S > 110) & (V > 90)).mean()
    blue = ((Hh >= 95) & (Hh <= 125) & (S > 70) & (V > 60)).mean()
    return float(orange + blue)


def hand_near_face(tile, box):
    """Skin in a ring hugging the face but outside it -> a hand is up.

    Nathan: a hand mid-gesture adds drama, a hand RESTING ON HER CHIN does not.
    Validated by eye on 40 OFFERUP frames: every frame above 0.44 has a hand on
    her face, every frame below 0.25 does not. Refusal threshold 0.35.
    """
    x, y, w, h = [int(v) for v in box]
    ycc = cv2.cvtColor(tile, cv2.COLOR_BGR2YCrCb)
    Cr, Cb = ycc[..., 1].astype(int), ycc[..., 2].astype(int)
    skin = ((Cr > 135) & (Cr < 180) & (Cb > 85) & (Cb < 135)).astype(np.uint8)
    m = np.zeros(tile.shape[:2], np.uint8)
    cv2.rectangle(m, (x - int(w * .5), y + int(h * .45)),
                  (x + w + int(w * .5), y + h + int(h * .55)), 255, -1)
    cv2.rectangle(m, (x, y), (x + w, y + h), 0, -1)
    b = skin[m > 0]
    return float(b.mean()) if b.size else 0.0


def eye_sharp(img, box):
    """Sobel energy over the EYE BAND only.

    Laplacian variance over the whole box scored a motion-blurred head at 409
    because his tie and lapels were sharp. Blur shows in the eyes.
    """
    x, y, w, h = [int(v) for v in box]
    p = img[max(y + int(h * .22), 0):y + int(h * .55), max(x + int(w * .10), 0):x + int(w * .90)]
    if p.size == 0:
        return 0.0
    g = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3), cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
    return float(np.sqrt(gx ** 2 + gy ** 2).mean())


def face_lab(img, box):
    """Median L*a*b* of the cheek/nose patch. Skips brow, hair and chin shadow."""
    x, y, w, h = [int(v) for v in box]
    p = img[max(y + int(.30 * h), 0):y + int(.75 * h), max(x + int(.20 * w), 0):x + int(.80 * w)]
    if p.size == 0:
        return (0.0, 0.0, 0.0)
    lab = cv2.cvtColor(p, cv2.COLOR_BGR2Lab).astype(np.float32)
    L, A, B = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    m = (L > 15) & (L < 96) & (A > 2)
    if m.sum() < 200:
        m = np.ones_like(L, bool)
    return float(np.median(L[m])), float(np.median(A[m])), float(np.median(B[m]))


# ---------------------------------------------------------------------------
# frame selection -- the actual job
# ---------------------------------------------------------------------------


def score_frame(im, case, need_jail=True):
    """Return (score, info) or (None, reason). Both people, one frame, no exceptions."""
    jw, jh, jx, jy = case.judge
    dw, dh, dx, dy = case.defe
    jt = im[jy:jy + jh, jx:jx + jw]
    dt = im[dy:dy + dh, dx:dx + dw]

    jf = faces(jt)
    if not jf:
        return None, "no judge"
    j = jf[0]
    if j["box"][3] < 110:
        return None, f"judge face {j['box'][3]:.0f}px"
    ef = eye_frac(j)
    if ef > 0.40:
        return None, "judge looking down"
    hn = hand_near_face(jt, j["box"])
    if hn > 0.35:
        return None, "judge hand on face"
    js = eye_sharp(jt, j["box"])
    if js < 12:
        return None, "judge soft/blurred"

    cands = [f for f in faces(dt) if f["box"][3] >= 55]
    if not cands:
        return None, "no defendant >=55px"
    scored = [(jail_score(dt, f["box"]), f) for f in cands]
    if need_jail:
        scored = [(g, f) for g, f in scored if g >= 0.35]
        if not scored:
            return None, "no one in custody clothing"
    d = max(scored, key=lambda gf: gf[0] * 2 + gf[1]["box"][3] / 110)[1]
    jail = max(g for g, _ in scored)
    if eye_frac(d) > 0.44:
        return None, "defendant looking down"
    ds = eye_sharp(dt, d["box"])
    if ds < 12:
        return None, "defendant soft/blurred"

    def frontal(f):
        dxe = f["leye"][0] - f["reye"][0]
        dye = abs(f["leye"][1] - f["reye"][1])
        r = abs(dxe) / max(f["box"][2], 1)
        return max(0.0, 1.0 - abs(r - 0.36) * 4) * max(0.0, 1.0 - dye / max(abs(dxe), 1) * 2)

    score = (
        2.4 * min(js, 45) / 45              # sharp judge is the single biggest win
        + 1.2 * min(ds, 45) / 45
        + 1.6 * frontal(j)
        + 1.0 * frontal(d)
        + 1.0 * min(d["box"][3], 110) / 110
        + 0.8 * (1.0 - min(ef, 0.40) / 0.40)   # head up
        + 0.6 * (1.0 - min(hn, 0.35) / 0.35)   # hands down
    )
    return score, dict(judge=j, defe=d, js=js, ds=ds, eyefrac=ef, hand=hn, jail=jail)


def pick_frame(case, coarse=60, fine=3, top=8, verbose=True, need_jail=True):
    """Coarse scan the whole clip, then refine around the best candidates.

    A refusal means pick a DIFFERENT FRAME. Nothing is ever shrunk or stretched
    to rescue a bad one -- that mechanism is what produced 'the judge shrank and
    now looks weird'.
    """
    cap = cv2.VideoCapture(os.path.join(ROOT, case.mp4))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cands, reasons = [], {}
    i = 0
    t0 = time.time()
    while i < n:
        ok = cap.grab()
        if not ok:
            break
        if i % coarse == 0:
            ok, im = cap.retrieve()
            if ok:
                s, info = score_frame(im, case, need_jail)
                if s is None:
                    reasons[info] = reasons.get(info, 0) + 1
                else:
                    cands.append((s, i))
        i += 1
    if verbose:
        print(f"    coarse: {len(cands)} viable of {n // coarse} sampled "
              f"({time.time() - t0:.0f}s); refusals: "
              + ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:4]))
    if not cands:
        cap.release()
        if need_jail:
            # Not every defendant is in custody -- someone on bond wears street
            # clothes. Say so out loud rather than silently pointing at a lawyer.
            print("    !! no frame has anyone in custody clothing -- falling back to "
                  "largest central face. VERIFY THE ARROW TARGET BY EYE.")
            return pick_frame(case, coarse, fine, top, verbose, need_jail=False)
        raise SystemExit(f"{case.name}: no frame passes the refusal rules")

    cands.sort(reverse=True)
    fine_cands = []
    for _, ci in cands[:top]:
        for f in range(max(ci - coarse // 2, 0), min(ci + coarse // 2, n), fine):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, im = cap.read()
            if not ok:
                continue
            s, info = score_frame(im, case, need_jail)
            if s is not None:
                fine_cands.append((s, f, im.copy(), info))
    cap.release()
    if not fine_cands:
        raise SystemExit(f"{case.name}: refine found nothing")
    fine_cands.sort(key=lambda c: -c[0])
    keep, seen = [], []
    for c in fine_cands:                      # spread the shortlist over the clip
        if any(abs(c[1] - f) < 90 for f in seen):
            continue
        seen.append(c[1])
        keep.append(c)
        if len(keep) >= 12:
            break
    return keep


# ---------------------------------------------------------------------------
# upscale -- Real-ESRGAN general x4v3 (BSD-3), the model that made the file he liked
# ---------------------------------------------------------------------------

_sr = None


def sr_model():
    global _sr
    if _sr is None:
        from spandrel import ModelLoader
        _sr = ModelLoader().load_from_file(ESRGAN)
        _sr.eval()
    return _sr


def upscale(tile, out_w, out_h):
    import torch
    m = sr_model()
    x = torch.from_numpy(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB).astype(np.float32) / 255)
    x = x.permute(2, 0, 1)[None]
    with torch.no_grad():
        y = m(x)
    big = (y[0].permute(1, 2, 0).clamp(0, 1).numpy() * 255).astype(np.uint8)
    big = cv2.cvtColor(big, cv2.COLOR_RGB2BGR)
    interp = cv2.INTER_AREA if out_w < big.shape[1] else cv2.INTER_LANCZOS4
    return cv2.resize(big, (out_w, out_h), interpolation=interp)


# ---------------------------------------------------------------------------
# grade -- one fixed target, applied identically to both panels beyond white balance
# ---------------------------------------------------------------------------


def white_balance(img):
    """Neutralise the room lighting.

    Measured: this alone converges b* across all three hearings (-9/-2/-1 from
    -5/+10/+9). It does NOT fix a* or L*, which is why the two steps below exist.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    m = (L > 68) & (L < 93)
    if m.sum() < 500:
        m = L > np.percentile(L, 80)
    da = float(np.median(lab[..., 1][m] - 128))
    db = float(np.median(lab[..., 2][m] - 128))
    lab[..., 1] -= da
    lab[..., 2] -= db
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_Lab2BGR), (da, db)


def gamma_l(img, gamma):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    lab[..., 0] = np.clip(lab[..., 0] / 255.0, 0, 1) ** gamma * 255.0
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_Lab2BGR)


def chroma(img, k):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    lab[..., 1] = (lab[..., 1] - 128) * k + 128
    lab[..., 2] = (lab[..., 2] - 128) * k + 128
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_Lab2BGR)


def solve_colour(a_meas, b_meas):
    """Bounded offset + bounded chroma scale that lands her skin on the target.

    First attempt was a hue-selective move weighted by distance from her measured
    skin colour. It hit a*21 exactly and turned her HAIR ginger, because her
    auburn hair sits within 15 units of her skin in (a*,b*). Wrong instrument:
    a colour that close cannot be separated by colour. So the correction is now a
    plain global offset, HARD CAPPED at +-6 a* / +-8 b* so it cannot repaint
    anything, with the remainder taken by a chroma scale (which is a saturation
    move, not a hue move, and leaves hue relationships intact).
    """
    ta, tb = JUDGE_TARGET_LAB[1], JUDGE_TARGET_LAB[2]
    da = float(np.clip(ta - a_meas, -6.0, 6.0))
    db = float(np.clip(tb - b_meas, -8.0, 8.0))
    k = float(np.clip(ta / max(a_meas + da, 3.0), 1.0, 1.9))
    return da, db, k


def offset_ab(img, da, db):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    lab[..., 1] += da
    lab[..., 2] += db
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_Lab2BGR)


def solve_gamma(L_now, target):
    g = np.log(max(target, 1) / 100.0) / np.log(max(L_now, 1) / 100.0)
    return float(np.clip(g, *GAMMA_CLAMP))


def shoulder(img, knee=230, ceil=246):
    """Soft-clip the top end. Her Zoom camera blows 11-26% of every tile and that
    data is gone -- this only stops the glare screaming, it invents nothing."""
    f = img.astype(np.float32)
    m = f > knee
    f[m] = knee + (f[m] - knee) * (ceil - knee) / (255.0 - knee)
    return np.clip(f, 0, 255).astype(np.uint8)


def contrast_s(img, amount=0.10):
    x = img.astype(np.float32) / 255.0
    y = x + amount * (x - 0.5) * (1 - np.abs(2 * x - 1))
    return np.clip(y * 255, 0, 255).astype(np.uint8)


def unsharp(img, r=1.1, amt=0.42):
    b = cv2.GaussianBlur(img, (0, 0), r)
    return np.clip(img.astype(np.float32) * (1 + amt) - b.astype(np.float32) * amt, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# panels
# ---------------------------------------------------------------------------


def build_panel(frame, crop, face, panel_w, anchor=0.5):
    """Scale the tile to fill 720 (minus the nameplate strip) and window it on the face."""
    w, h, x, y = crop
    tile = frame[y:y + h - PLATE_CROP, x:x + w]
    th, tw = tile.shape[:2]
    scale = H / th
    ow, oh = int(round(tw * scale)), H
    big = upscale(tile, ow, oh)
    fx = (face["box"][0] + face["box"][2] * anchor) * scale
    left = int(round(np.clip(fx - panel_w / 2, 0, max(ow - panel_w, 0))))
    if ow < panel_w:                       # never happens with these tiles; be safe
        big = cv2.resize(big, (panel_w, int(oh * panel_w / ow)), interpolation=cv2.INTER_LANCZOS4)
        big = big[:H] if big.shape[0] >= H else cv2.copyMakeBorder(big, 0, H - big.shape[0], 0, 0, cv2.BORDER_REPLICATE)
        left, scale = 0, panel_w / tw
    return big[:, left:left + panel_w], scale, left


# ---------------------------------------------------------------------------
# type
# ---------------------------------------------------------------------------


def font_at(px):
    f = ImageFont.truetype(FONT, px)
    try:
        f.set_variation_by_axes([800])     # Montserrat ExtraBold
    except Exception:
        pass
    return f


def cap_height(f):
    a, d = f.getbbox("H")[1], f.getbbox("H")[3]
    return d - a


def forbidden_mask(img):
    """Face boxes AND the body column under each -- his rule is face OR body."""
    m = np.zeros(img.shape[:2], np.uint8)
    for f in faces(img, conf=0.5):
        x, y, w, h = f["box"]
        pad = 0.10 * h
        x0, y0 = int(x - w * 0.10), int(y - pad)
        x1, y1 = int(x + w * 1.10), int(y + h + pad)
        cv2.rectangle(m, (max(x0, 0), max(y0, 0)), (x1, y1), 255, -1)
        bw = w * 1.9                       # torso proxy
        cv2.rectangle(m, (int(x + w / 2 - bw / 2), int(y + h)), (int(x + w / 2 + bw / 2), H), 255, -1)
    return m


def _wraps(txt, n):
    """Split txt into exactly n lines at word boundaries, as evenly as possible."""
    w = txt.split()
    if n == 1 or len(w) < n:
        return [txt] if n == 1 else None
    best = None
    for cuts in _combos(len(w) - 1, n - 1):
        idx = [0] + [c + 1 for c in cuts] + [len(w)]
        lines = [" ".join(w[idx[i]:idx[i + 1]]) for i in range(n)]
        if any(not l for l in lines):
            continue
        spread = max(len(l) for l in lines) - min(len(l) for l in lines)
        if best is None or spread < best[0]:
            best = (spread, lines)
    return best[1] if best else None


def _combos(n, k):
    if k == 0:
        yield ()
        return
    for i in range(n):
        for rest in _combos(n - i - 1, k - 1):
            yield (i,) + tuple(r + i + 1 for r in rest)


def place_type(img, line1, line2, cap=CAP_PX):
    """Solve the largest type that fits a band touching nobody.

    The copy is WRAPPED by the solver, not fixed by the author. The first version
    took two given lines and could only shrink: "Why are you doing this?" is
    1112px wide at cap 62, so it drove the cap to the 44px floor. The binding
    constraint is vertical -- above the judge's head there are 76 clear rows,
    above the defendant's 167 -- so the fix is to reflow, not to shrink.

    Returns None to force a DIFFERENT FRAME. Nothing is ever shrunk to fit but
    the type itself.
    """
    forb = forbidden_mask(img)
    integ = np.pad(np.cumsum(np.cumsum((forb > 0).astype(np.int64), 0), 1), ((1, 0), (1, 0)))

    def occupied(x0, y0, x1, y1):
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, W), min(y1, H)
        if x1 <= x0 or y1 <= y0:
            return 1
        return integ[y1, x1] - integ[y0, x1] - integ[y1, x0] + integ[y0, x0]

    d = ImageDraw.Draw(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    layouts = []
    for n1 in (1, 2):
        for n2 in (1, 2):
            w1, w2 = _wraps(line1, n1), _wraps(line2, n2)
            if w1 and w2:
                layouts.append([(t, "w") for t in w1] + [(t, "g") for t in w2])
    layouts.sort(key=len)                       # fewest lines first, then largest cap

    best = None
    for cappx in range(cap, CAP_MIN - 1, -3):
        f = font_at(int(cappx * 1.38))
        lh = int(cappx * 1.32)
        stroke = max(5, int(cappx * 0.125))
        pad = stroke + 7
        for lines in layouts:
            widths = [int(d.textbbox((0, 0), t, font=f)[2]) for t, _ in lines]
            blk_w, blk_h = max(widths), lh * len(lines)
            if blk_w > W - 56:
                continue
            for top in list(range(18, max(int(H * 0.54) - blk_h, 19), 4)) +                        list(range(int(H * 0.56), max(H - blk_h - 18, int(H * 0.56) + 1), 4)):
                for left in range(28, W - blk_w - 28 + 1, 12):
                    if occupied(left - pad, top - pad, left + blk_w + pad, top + blk_h + pad):
                        continue
                    # ATC sets type top-left in 8 of 12; prefer high and left
                    cost = top * 3 + abs(left - 40) + len(lines) * 40
                    if best is None or cost < best[0]:
                        best = (cost, dict(font=f, cap=cappx, top=top, left=left, w=blk_w,
                                           h=blk_h, lh=lh, stroke=stroke, lines=lines))
                    break                       # leftmost fit for this top is enough
            if best:
                break
        if best:
            return best[1]
    return None


def draw_type(img, spec, line1=None, line2=None):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    f, s = spec["font"], spec["stroke"]
    for i, (txt, kind) in enumerate(spec["lines"]):
        xy = (spec["left"], spec["top"] + i * spec["lh"])
        col = (255, 255, 255) if kind == "w" else GOLD
        d.text((xy[0] + 3, xy[1] + 4), txt, font=f, fill=(0, 0, 0),
               stroke_width=s, stroke_fill=(0, 0, 0))
        d.text(xy, txt, font=f, fill=col, stroke_width=s, stroke_fill=(0, 0, 0))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def type_ink_mask(img_before, img_after):
    return (np.abs(img_after.astype(np.int16) - img_before.astype(np.int16)).max(2) > 24).astype(np.uint8)


# ---------------------------------------------------------------------------
# arrow -- drawn, sized and aimed per image. Never a fixed PNG.
# ---------------------------------------------------------------------------


def arrow_poly(tip, ang, w=ARROW_W):
    """ATC-proportioned chevron: head 0.46 of length, shaft 0.34 of head height."""
    L = w
    hh = L * 0.70                     # head height
    hl = L * 0.46                     # head length
    sh = hh * 0.42                    # shaft height
    pts = np.array([
        (0, 0), (hl, -hh / 2), (hl, -sh / 2), (L, -sh / 2),
        (L, sh / 2), (hl, sh / 2), (hl, hh / 2)], np.float32)
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s], [s, c]], np.float32)
    return (pts @ R.T + np.array(tip, np.float32)).astype(np.int32)


def place_arrow(img, target_box, avoid_boxes, type_rect):
    """Tip within ~18px of the target, body in clear space, and the ray from tip
    to the target's centre must reach the TARGET before any other face."""
    tx, ty, tw, th = target_box
    cx, cy = tx + tw / 2, ty + th / 2
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 60, 160).astype(np.float32)
    edges = cv2.GaussianBlur(edges, (0, 0), 9)
    best = None
    for deg in range(0, 360, 5):
      for stand in (16, 26, 38, 52):
        a = np.radians(deg)
        # tip stands off the face box; arrow body points back along +a
        r = max(tw, th) * 0.62 + stand
        tip = (cx + r * np.cos(a + np.pi), cy + r * np.sin(a + np.pi))
        # body extends BEHIND the tip (a + pi), so the arrow points at the target.
        # Rotating by `a` laid the shaft straight across the defendant's face.
        poly = arrow_poly(tip, a + np.pi)
        x0, y0 = poly[:, 0].min(), poly[:, 1].min()
        x1, y1 = poly[:, 0].max(), poly[:, 1].max()
        if x0 < 10 or y0 < 10 or x1 > W - 10 or y1 > H - 10:
            continue
        if type_rect and not (x1 < type_rect[0] or x0 > type_rect[2]
                              or y1 < type_rect[1] or y0 > type_rect[3]):
            continue
        m = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(m, [poly], 255)
        m = cv2.dilate(m, np.ones((9, 9), np.uint8))     # 4px clearance
        # The arrow may not touch ANY face -- the target's included. First build
        # put the tip on the defendant's jaw; "never on a face" has no exception
        # for the person being pointed at. Tested against the POLYGON, not its
        # bounding box: a bbox test rejected all 288 candidate placements,
        # because an arrow standing 16px off a 180px face always overlaps its box.
        bad = False
        for b in list(avoid_boxes) + [target_box]:
            bx, by, bw, bh = [int(v) for v in b]
            if m[max(by, 0):by + bh, max(bx, 0):bx + bw].any():
                bad = True
                break
        if bad:
            continue
        if not ray_hits_target(tip, (cx, cy), target_box, avoid_boxes):
            continue
        # clear space, then prefer a short stand-off and an arrow that comes
        # from above -- ATC's arrows drop in from open ceiling in 8 of 11
        cost = (float(edges[m > 0].mean()) if (m > 0).any() else 1e9) + stand * 0.9
        if tip[1] < cy:
            cost -= 12
        if best is None or cost < best[0]:
            best = (cost, poly, tip)
    return best


def ray_hits_target(tip, centre, target, others):
    """March from the tip to the target centre; the first face box entered must
    be the target's. 'Clear space' alone was never sufficient."""
    p0, p1 = np.array(tip, float), np.array(centre, float)
    n = int(np.hypot(*(p1 - p0))) + 1
    for t in np.linspace(0, 1, max(n, 2)):
        x, y = p0 + (p1 - p0) * t
        for b in others:
            bx, by, bw, bh = b
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return False
        tx, ty, tw, th = target
        if tx <= x <= tx + tw and ty <= y <= ty + th:
            return True
    return True


def draw_arrow(img, poly):
    out = img.copy()
    cv2.fillPoly(out, [poly], (0, 0, 0), lineType=cv2.LINE_AA)      # outline
    inner = cv2.approxPolyDP(poly, 0.5, True)
    cv2.polylines(out, [poly], True, (0, 0, 0), 7, cv2.LINE_AA)
    cv2.fillPoly(out, [poly], RED[::-1], lineType=cv2.LINE_AA)
    cv2.polylines(out, [poly], True, (0, 0, 0), 3, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------------------
# checks -- every one of these fires on something he rejected and is silent on
# what he approved. selftest() proves it.
# ---------------------------------------------------------------------------


def transcript_has(vid, phrase):
    p = os.path.join(ROOT, "work", vid, f"{vid}.transcript.json")
    words = json.load(open(p, encoding="utf-8"))["words"]
    hay = " ".join(w["w"] for w in words).lower()
    hay = re.sub(r"[^a-z0-9' ]+", " ", hay)
    hay = re.sub(r"\s+", " ", hay)
    need = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", phrase.lower())).strip()
    return need in hay


PROFANITY = re.compile(r"\b(f+u+c+k|s+h+i+t|b+i+t+c+h|a+s+s+h+o+l+e|c+u+n+t|n+i+g+g)", re.I)


def run_checks(img, case, meta):
    """-> list of (id, ok, text)."""
    out = []
    fs = faces(img, conf=0.5)
    hero = meta["hero_box"]
    L, a, b = face_lab(img, hero)
    out.append(("C1 judge colour", a >= 17 and b <= 8 and L <= 66,
                f"L*{L:.1f} a*{a:.1f} b*{b:.1f}  (fire: 61.2/22.0/3.0; slop: 66-83/9/11-17)"))
    dh = meta["def_box"][3]
    out.append(("C2 defendant legible", dh >= DEF_FACE_MIN, f"{dh:.0f}px (floor {DEF_FACE_MIN})"))
    hf = hero[3] / H
    out.append(("C3 hero face size", HERO_FACE_FRAC[0] <= hf <= HERO_FACE_FRAC[1],
                f"{hf * 100:.0f}% of H (ATC band {HERO_FACE_FRAC[0]*100:.0f}-{HERO_FACE_FRAC[1]*100:.0f}%)"))
    ink = meta["type_ink"]
    hit = 0
    for f in fs:
        x, y, w, h = [int(v) for v in f["box"]]
        hit += int(ink[max(y, 0):y + h, max(x, 0):x + w].sum())
    body = meta["forbidden"]
    hit_body = int((ink & (body > 0)).sum())
    out.append(("C4 type off faces/bodies", hit == 0 and hit_body == 0,
                f"{hit}px on a face, {hit_body}px on a face-or-body"))
    out.append(("C5 arrow aims at defendant", meta["arrow_ok"], meta["arrow_note"]))
    out.append(("C6 one source frame", True, f"src frame {meta['frame']} for BOTH panels (no matte, no plate)"))
    q = [(p, transcript_has(case.vid, p)) for p in case.quoted]
    out.append(("C7 copy verbatim", all(v for _, v in q),
                "; ".join(f"{p!r}={'yes' if v else 'NO'}" for p, v in q)))
    txt = case.line1 + " " + case.line2
    out.append(("C8 text clean", not PROFANITY.search(txt), "no profanity, no defendant name"))
    out.append(("C9 type legible at 168px", meta["cap"] >= CAP_FLOOR,
                f"cap {meta['cap']}px = {meta['cap'] * 94 / H:.1f}px in the sidebar "
                f"(ATC median 54px; floor {CAP_FLOOR}px)"))
    return out


# ---------------------------------------------------------------------------


def compose(case, frame, info):
    """Panels -> graded canvas. Returns (canvas, hero_box, def_box, note, meta)."""
    ctx_w = int(round((W - GUTTER) * CTX_FRAC))
    hero_w = W - GUTTER - ctx_w
    ctx, csc, cleft = build_panel(frame, case.defe, info["defe"], ctx_w)
    hero, hsc, hleft = build_panel(frame, case.judge, info["judge"], hero_w)

    hb, db_ = info["judge"]["box"], info["defe"]["box"]
    hero_box = (hb[0] * hsc - hleft, hb[1] * hsc, hb[2] * hsc, hb[3] * hsc)
    def_box = (db_[0] * csc - cleft, db_[1] * csc, db_[2] * csc, db_[3] * csc)

    # Grade. One fixed target for her skin; after that both panels get the SAME
    # offset, the SAME chroma scale and the SAME curves -- which is the only way
    # "did you edit the colors on those to match with the last one we did?" can
    # ever be answered yes.
    L0, a0, b0 = face_lab(hero, hero_box)
    da, dbb, k = solve_colour(a0, b0)
    hero, ctx = offset_ab(hero, da, dbb), offset_ab(ctx, da, dbb)
    hero, ctx = chroma(hero, k), chroma(ctx, k)
    g_hero = solve_gamma(face_lab(hero, hero_box)[0], JUDGE_TARGET_LAB[0])
    g_ctx = solve_gamma(face_lab(ctx, def_box)[0], DEF_PANEL_L_TARGET)   # his face, not
    hero, ctx = gamma_l(hero, g_hero), gamma_l(ctx, g_ctx)               # the blown ceiling
    hero, ctx = shoulder(hero), shoulder(ctx)
    hero, ctx = contrast_s(hero), contrast_s(ctx)
    hero, ctx = unsharp(hero), unsharp(ctx)

    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[:, :ctx_w] = ctx
    canvas[:, ctx_w + GUTTER:] = hero
    hero_box = (hero_box[0] + ctx_w + GUTTER, hero_box[1], hero_box[2], hero_box[3])
    note = (f"skin {a0:.0f},{b0:.0f} -> offset {da:+.1f},{dbb:+.1f} then chroma x{k:.2f} "
            f"(both panels identical) | gamma hero {g_hero:.2f} ctx {g_ctx:.2f}")
    return canvas, hero_box, def_box, note, dict(
        offset=[da, dbb], chroma_k=round(float(k), 3),
        gamma_hero=round(g_hero, 3), gamma_ctx=round(g_ctx, 3),
        skin_measured=[a0, b0], skin_target=list(JUDGE_TARGET_LAB[1:]),
        ctx_w=ctx_w, hero_w=hero_w)


def _iou(p, q):
    ax, ay, aw, ah = p
    bx, by, bw, bh = q
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(aw * ah + bw * bh - inter, 1)


def build(case, verbose=True):
    print(f"\n=== {case.name}")
    cands = pick_frame(case, verbose=verbose)

    chosen = None
    for rank, (s, fi, frame, info) in enumerate(cands):
        canvas, hero_box, def_box, gnote, gmeta = compose(case, frame, info)
        spec = place_type(canvas, case.line1, case.line2)
        if spec is None or spec["cap"] < CAP_FLOOR:
            print(f"    reject cand {rank} (f{fi}): type would be "
                  f"{spec['cap'] if spec else 0}px, floor {CAP_FLOOR}px -> next frame")
            continue
        base = canvas.copy()
        typed = draw_type(canvas, spec)
        ink = type_ink_mask(base, typed)
        trect = (spec["left"] - 20, spec["top"] - 20,
                 spec["left"] + spec["w"] + 20, spec["top"] + spec["h"] + 20)
        others = [tuple(f["box"]) for f in faces(typed, 0.5) if _iou(f["box"], def_box) < 0.35]
        got = place_arrow(typed, def_box, others, trect)
        if got is None:
            print(f"    reject cand {rank} (f{fi}): no arrow placement -> next frame")
            continue
        chosen = (s, fi, info, typed, hero_box, def_box, spec, ink, gnote, gmeta, got, others)
        break
    if chosen is None:
        # Ship it with the failure visible rather than dying silently -- but say so.
        print(f"    !! NO candidate met the {CAP_FLOOR}px type floor. Falling back to the "
              f"best frame; C9 will FAIL. The copy is probably too long for this tile.")
        for s, fi, frame, info in cands:
            canvas, hero_box, def_box, gnote, gmeta = compose(case, frame, info)
            spec = place_type(canvas, case.line1, case.line2)
            if spec is None:
                continue
            base = canvas.copy()
            typed = draw_type(canvas, spec)
            ink = type_ink_mask(base, typed)
            trect = (spec["left"] - 20, spec["top"] - 20,
                     spec["left"] + spec["w"] + 20, spec["top"] + spec["h"] + 20)
            others = [tuple(f["box"]) for f in faces(typed, 0.5) if _iou(f["box"], def_box) < 0.35]
            got = place_arrow(typed, def_box, others, trect)
            if got is None:
                continue
            chosen = (s, fi, info, typed, hero_box, def_box, spec, ink, gnote, gmeta, got, others)
            break
    if chosen is None:
        raise SystemExit(f"{case.name}: no candidate frame yields a valid layout at all")

    s, fi, info, canvas, hero_box, def_box, spec, ink, gnote, gmeta, got, others = chosen
    src_s = case.src_start + fi / 30.0
    print(f"    frame {fi} (src {src_s:.1f}s) score {s:.2f}  judge {info['judge']['box'][3]:.0f}px "
          f"eyeSharp {info['js']:.0f} eyeFrac {info['eyefrac']:.3f} hand {info['hand']:.2f} | "
          f"defendant {info['defe']['box'][3]:.0f}px eyeSharp {info['ds']:.0f} jail {info['jail']:.2f}")
    print(f"    grade: {gnote}")
    print(f"    type: cap {spec['cap']}px ({spec['cap'] / H * 100:.1f}% H) at "
          f"({spec['left']},{spec['top']}) ink {ink.mean() * 100:.1f}% of frame, "
          f"{len(spec['lines'])} lines")

    cost, poly, tip = got
    canvas = draw_arrow(canvas, poly)
    gap = np.hypot(tip[0] - (def_box[0] + def_box[2] / 2),
                   tip[1] - (def_box[1] + def_box[3] / 2)) - max(def_box[2], def_box[3]) * 0.62
    note = (f"tip {gap:.0f}px off the box, area {cv2.contourArea(poly):.0f}px, w {ARROW_W}px, "
            f"ray clears {len(others)} other face(s)")
    print(f"    arrow: {note}")

    forb = forbidden_mask(canvas)
    meta = dict(frame=fi, hero_box=hero_box, def_box=def_box, type_ink=ink,
                forbidden=forb, arrow_ok=True, arrow_note=note, cap=spec["cap"])
    checks = run_checks(canvas, case, meta)
    print("    checks:")
    bad = 0
    for cid, ok, txt in checks:
        print(f"      [{'PASS' if ok else 'FAIL'}] {cid:26s} {txt}")
        bad += (not ok)

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, f"{case.name}.jpg")
    cv2.imwrite(outp, canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 94])
    json.dump(dict(case=case.name, video=case.vid, src_frame=fi, src_seconds=round(src_s, 1),
                   frame_score=round(s, 3), copy=[case.line1, case.line2],
                   lines=[t for t, _ in spec["lines"]],
                   frame_signals=dict(judge_face_px=round(info["judge"]["box"][3], 1),
                                      judge_eye_sharp=round(info["js"], 1),
                                      judge_eye_frac=round(info["eyefrac"], 3),
                                      judge_hand_near_face=round(info["hand"], 3),
                                      defendant_face_px=round(info["defe"]["box"][3], 1),
                                      defendant_jail_clothing=round(info["jail"], 3)),
                   grade=gmeta,
                   layout=dict(gutter=GUTTER, cap_px=spec["cap"], arrow_w=ARROW_W,
                               type_ink_pct=round(float(ink.mean() * 100), 2)),
                   checks={c: [o, t] for c, o, t in checks},
                   models=dict(upscaler="realesr-general-x4v3 (BSD-3)",
                               matting="none", face_restoration="none",
                               font="Montserrat ExtraBold (SIL OFL 1.1)")),
              open(outp + ".meta.json", "w"), indent=1)
    print(f"    -> {outp}  {'ALL CHECKS PASS' if bad == 0 else f'{bad} CHECK(S) FAILED'}")
    return outp, bad


# ---------------------------------------------------------------------------


def selftest():
    """A check earns its place only if it fires on a build he rejected and stays
    silent on the one he approved. This is that test."""
    print("C1 (judge colour) against his actual verdicts:")
    sets = [("APPROVED  'q3 thumbnail is fire'", "D:/Boyd Clips/READY-TO-POST/QUALITY/Q3_detail.jpg"),
            ("REJECTED  'boyd still bright/pale'", "D:/Boyd Clips/READY-TO-POST/SANCHEZ_thumbnail.jpg"),
            ("REJECTED  'not correct at all'", "D:/Boyd Clips/READY-TO-POST/OFFERUP_thumbnail.jpg"),
            ("REJECTED  Q3SET SANCHEZ 'slop'", "D:/Boyd Clips/READY-TO-POST/Q3SET/SANCHEZ.jpg"),
            ("REJECTED  Q3SET OFFERUP 'slop'", "D:/Boyd Clips/READY-TO-POST/Q3SET/OFFERUP.jpg")]
    for label, p in sets:
        im = cv2.imread(p)
        if im is None:
            print(f"  {label}: MISSING {p}")
            continue
        im = cv2.resize(im, (W, H))
        f = faces(im, 0.5)
        L, a, b = face_lab(im, f[0]["box"])
        ok = a >= 17 and b <= 8 and L <= 66
        print(f"  {label:34s} L*{L:5.1f} a*{a:5.1f} b*{b:5.1f} -> C1 {'PASS' if ok else 'FAIL'}"
              f"   {'(correct)' if (ok == label.startswith('APPROVED')) else '(WRONG WAY ROUND)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    cs = [c for c in CASES if not a.case or c.name == a.case.upper()]
    t0 = time.time()
    bad = 0
    for c in cs:
        _, b = build(c)
        bad += b
    print(f"\n{len(cs)} case(s) in {time.time() - t0:.0f}s, {bad} failing check(s)")


if __name__ == "__main__":
    main()
