#!/usr/bin/env python
"""
build_alt.py - Texas Trial Tracker thumbnail, alternative construction.

    python scripts/fresh/build_alt.py            # all three cases
    python scripts/fresh/build_alt.py CARTHIEF   # one

Output: READY-TO-POST/FRESH_ALT/<CASE>.jpg  (1280x720 JPEG)

--------------------------------------------------------------------------
WHY THIS IS BUILT THE WAY IT IS  (every number below is measured, not tuned)
--------------------------------------------------------------------------
The old pipeline mattes two people out of two Zoom tiles and composites them
onto a rebuilt plate.  This does not.  It takes ONE real video frame, crops the
two adjacent Zoom tiles out of it, and butts them together as two panels of
unequal width.  No matte, no plate, no per-build envelope.

1. ASYMMETRIC, NOT 50/50.  Of the 12 Audit the Court references, 10 have no
   divider at all; the 2 that do put it at x=465 (36.3% of width) and x=825
   (64.5%).  Zero sit at 50%.  Panels here are 0.36 / 0.64.

2. ONE SCALE, TAKEN FROM THE SOURCE.  scale = 720 / tile_height, applied to
   BOTH tiles.  Because both tiles are the same height in all three cases,
   the judge:defendant face-size ratio in the output is exactly the ratio in
   the raw frame.  Measured native ratio 139/82 = 1.70.  Measured in
   Q3_detail.jpg, the only file Nathan called fire: 274/161 = 1.70.  The old
   solver forced that ratio to 1.0 (head_top_delta 0-2 px in all 7 builds) and
   that is the "two mugshots pasted on a wall" look he rejected five times.
   There is no solver here and no available_px.  The framing has one degree of
   freedom (horizontal position) and it is set by the face centre.

3. SAME TIMESTAMP BY CONSTRUCTION.  Both panels are crops of one decoded frame,
   so a seam grade mismatch, a halo, a severed limb and a scale lie are all
   unreachable states, not gated states.

4. HOOK FIRST, THEN FRAME.  The headline is chosen from the transcript first,
   and the frame is then searched within +/-25 s of it.  The picture therefore
   shows the moment the headline comes from, and the arrow points at a man
   reacting to it.

5. COLOUR IS A FIXED CONSTANT, NEVER A MEASURED ENVELOPE.  Judge face target
   L* 56, a* 21, b* 1.  Those are the measured values of Q3_detail.jpg.
   Measured on four rejected builds: b* 9.7 / 10.7 / 12.3 / 21.9 against 0.7
   approved - zero overlap, and b* separates better than a*.  L* does not
   separate at all (56.2 approved vs 55.2-57.0 rejected) so nothing here keys
   on luma.  A constant target is the point: a target read out of a mutable
   file is why PERKINS built against L=137.8 and CLAYTON against 107.2, and why
   "did you edit the colors on those to match with the last one we did?" could
   not be answered yes.

6. TYPE SITS ON DEAD PIXELS.  Pixels >245 are 13.5-16.2% of every judge tile
   and 9.3-11.9% of every defendant tile, and they cluster at the top of the
   tile (courtroom ceiling, blown by her Zoom camera).  That data is clipped
   and unrecoverable, so it is used as the title bed.  The band is sized to
   stop 12 px above the highest face in the frame - it is not a constant, and
   if the type will not fit above the faces the FRAME is rejected and another
   is searched.  Nobody is ever shrunk to make room for words.

LICENCES RELIED ON (monetised channel, all permit commercial use):
  realesr-general-x4v3 .... BSD-3-Clause (xinntao/Real-ESRGAN)
  YuNet face detector ..... MIT (OpenCV Zoo)
  Anton-Regular.ttf ....... SIL OFL 1.1 (verified in the repo's licence audit)
  OpenCV .................. Apache-2.0     NumPy/SciPy ... BSD-3
  Pillow .................. MIT-CMU
No matting model is used.  HYPIR is not used: its LICENSE section 3(a) forbids
commercial use, and at 2.07-2.13x no diffusion model is needed anyway.
"""
from __future__ import annotations
import sys, os, json, re, math, argparse, collections
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import esrgan

W, H          = 1280, 720
NARROW_FRAC   = 0.36          # ATC's two measured dividers: 0.363 and 0.645
YUNET         = os.path.join(ROOT, "models", "yunet2023.onnx")
ESR_W         = os.path.join(ROOT, "assets", "models", "realesr-general-x4v3.pth")
FONT          = os.path.join(ROOT, "assets", "fonts", "Anton-Regular.ttf")
_DDRIVE       = "D:" + os.sep + "Boyd Clips"
OUTDIR = os.path.join(_DDRIVE if os.path.isdir(_DDRIVE) else ROOT,
                      "READY-TO-POST", "FRESH_ALT")

# judge-face colour target = measured off Q3_detail.jpg, the approved file
TGT_L, TGT_A, TGT_B = 56.0, 21.0, 1.0
CAP_FRAC      = 0.074         # 53 px cap height = Q3_detail's measured cap
CAP_MIN_FRAC  = 0.061         # floor; ATC's own median is 0.060
ARROW_W       = 106           # ATC arrow width median (n=12); area median 4036
GOLD          = (60, 214, 255)   # BGR
INK           = (255, 255, 255)

CASES = {
  "CARTHIEF": dict(vid="work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
                   tx="work/EwwnbiAQtFk/EwwnbiAQtFk.transcript.json",
                   t0=3554.0, judge=(612, 338, 18, 190), defe=(620, 338, 644, 190)),
  "SANCHEZ":  dict(vid="work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
                   tx="work/3FMy2Kvu3UA/3FMy2Kvu3UA.transcript.json",
                   t0=3683.0, judge=(468, 348, 726, 6), defe=(628, 348, 6, 6)),
  "OFFERUP":  dict(vid="work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
                   tx="work/l19Ijva3Rsk/l19Ijva3Rsk.transcript.json",
                   t0=10550.0, judge=(628, 348, 646, 186), defe=(628, 348, 6, 186)),
}

# ----------------------------------------------------------------- detection
_DET = {}
def faces(img, conf=0.6):
    h, w = img.shape[:2]
    if (w, h) not in _DET:
        _DET[(w, h)] = cv2.FaceDetectorYN.create(YUNET, "", (w, h), conf, 0.3, 5000)
    d = _DET[(w, h)]
    d.setInputSize((w, h))
    n, f = d.detect(img)
    return [] if f is None else sorted(list(f), key=lambda r: -r[3])


def face_quality(tile, r):
    """0..1.  Penalises looking down, closed eyes, extreme yaw and motion blur.

    YuNet landmarks are (r_eye, l_eye, nose, r_mouth, l_mouth) at r[4:14].
    Nathan's stated frame rules: Boyd looking DOWN is rejected, the defendant
    needs 'a good reaction'.  Head pitch is read off the geometry - when a head
    tips down the eye-line rises inside the box and the eye-to-mouth distance
    collapses relative to the eye separation."""
    x, y, w, h = r[:4]
    if w <= 4 or h <= 4:
        return 0.0
    lm = np.array(r[4:14], np.float32).reshape(5, 2)
    eye = (lm[0] + lm[1]) / 2.0
    eyesep = float(np.linalg.norm(lm[0] - lm[1])) + 1e-6
    mouth = (lm[3] + lm[4]) / 2.0

    # PITCH.  Calibrated by eye against a 20-frame strip of the CARTHIEF judge
    # tile (alt_meas/judgeframes.jpg): frames where she is reading DOWN measure
    # nose/eyesep 0.59-0.76 and mouth/eyesep 0.99-1.24; frames where her head is
    # up and she is speaking measure 0.85-1.18 and 1.45-2.19.  The first version
    # of this function saturated at mouth/eyesep 1.30 and therefore scored a
    # downcast frame 0.92, which is how the first CARTHIEF build shipped with
    # her reading her screen.  Both bands are now placed on the measured gap.
    nose_v = (lm[2][1] - eye[1]) / eyesep
    vert = (mouth[1] - eye[1]) / eyesep
    pitch = float(np.clip((nose_v - 0.72) / 0.24, 0, 1))
    tilt = float(np.clip((vert - 1.18) / 0.45, 0, 1))
    yaw_off = abs(lm[2][0] - eye[0]) / eyesep
    yaw = float(np.clip(1.0 - (yaw_off - 0.10) / 0.55, 0, 1))

    g = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)

    def eye_open(p):
        rr = max(3, int(eyesep * 0.22))
        a = g[max(0, int(p[1]) - rr):int(p[1]) + rr, max(0, int(p[0]) - rr):int(p[0]) + rr]
        if a.size < 9:
            return 0.0
        return float(np.clip((float(a.max()) - float(a.min())) / 70.0, 0, 1))

    eyes = (eye_open(lm[0]) + eye_open(lm[1])) / 2.0

    # mouth open = mid-speech or mid-reaction.  "a hand mid-gesture adds drama,
    # a hand resting on her chin does not" - the same idea, read off the face.
    mw = max(4, int(eyesep * 0.55))
    mh = max(3, int(eyesep * 0.40))
    ma = g[max(0, int(mouth[1]) - mh):int(mouth[1]) + mh,
           max(0, int(mouth[0]) - mw):int(mouth[0]) + mw]
    react = float(np.clip((float(ma.std()) - 12.0) / 26.0, 0, 1)) if ma.size > 20 else 0.0

    fx, fy = max(0, int(x)), max(0, int(y))
    patch = g[fy:fy + int(h), fx:fx + int(w)]
    sharp = float(np.clip(cv2.Laplacian(patch, cv2.CV_64F).var() / 90.0, 0, 1)) if patch.size > 100 else 0.0
    conf = float(np.clip(r[-1], 0, 1))
    return float(pitch * 0.30 + tilt * 0.20 + yaw * 0.13 + eyes * 0.13
                 + react * 0.10 + sharp * 0.08 + conf * 0.06)


def garment_score(tile, r):
    """Which of the faces in the defendant tile IS the defendant.

    Not the biggest face - in OFFERUP the attorney's face is larger (74-85 px
    against 66-71) and in CARTHIEF they are within 6 px, so a size rule points
    the arrow at the lawyer.  The first CARTHIEF build did exactly that.

    An inmate wears a single-colour scrub or jumpsuit: saturated, one hue, and
    smooth.  A suit is dark and low-saturation, a shirt-and-tie is textured, and
    a gallery bystander is small and busy.  saturation x hue-coherence x
    smoothness, measured on the torso strip under each face:

        CARTHIEF  defendant 0.85  attorney 0.22
        OFFERUP   defendant 0.77  attorney 0.02
        SANCHEZ   defendant 0.20  attorney 0.06   (blue scrubs, not orange -
                                                   an orange-only rule fails here)

    Every case separates by more than 3x, so the defendant is the argmax and no
    threshold has to be invented."""
    x, y, w, h = [int(v) for v in r[:4]]
    p = tile[max(0, int(y + h * 1.25)):min(tile.shape[0], int(y + h * 2.9)),
             max(0, int(x - w * 0.35)):min(tile.shape[1], int(x + w * 1.35))]
    if p.size < 600:
        return 0.0
    hsv = cv2.cvtColor(p, cv2.COLOR_BGR2HSV).astype(np.float32)
    Hh, S = hsv[:, :, 0], hsv[:, :, 1]
    ang = Hh * 2 * np.pi / 180.0
    wgt = S / 255.0
    tot = max(float(wgt.sum()), 1.0)
    coh = float(np.hypot((np.cos(ang) * wgt).sum() / tot, (np.sin(ang) * wgt).sum() / tot))
    tex = float(cv2.Laplacian(cv2.cvtColor(p, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    return float(S.mean() / 255.0) * coh * float(np.clip(1.0 - tex / 900.0, 0.15, 1.0))


def face_sharpness(tile, r):
    """Laplacian variance over the face patch, normalised by face height so a
    big soft face cannot beat a small crisp one.

    This is the check that separates a defendant from a bailiff walking through
    shot.  Measured in the SANCHEZ tile: the real defendant scores 106-254, and
    the motion-blurred bailiff who hijacked the first SANCHEZ build - she scored
    a HIGHER garment score than the defendant, 0.221 against 0.196, so no
    clothing rule was ever going to catch her - scores 14.8.  A 7x gap."""
    x, y, w, h = [max(0, int(v)) for v in r[:4]]
    p = tile[y:y + h, x:x + w]
    if p.size < 200:
        return 0.0
    g = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var()) / max(h, 1) * 10.0


MIN_SHARP = 60.0


def pick_defendant(tile, fs):
    """argmax garment score over the faces in the defendant tile, among the
    faces that are actually in focus."""
    best, bs = None, -1.0
    for r in fs[:4]:
        if r[3] < 22:
            continue
        if face_sharpness(tile, r) < MIN_SHARP:
            continue
        s = garment_score(tile, r)
        if s > bs:
            best, bs = r, s
    return best, bs


# A clip can contain several consecutive hearings.  The SANCHEZ clip runs 765 s
# and holds at least three: the first SANCHEZ build took its headline from the
# THIRD one ("Dreamer, if you'll come forward, please." at +524 s) and its
# picture from a moment when no inmate was at the podium at all.  Everything -
# hook and frame - is confined to the first hearing, whose end is the next time
# the court calls somebody up.
NEXT_CASE = re.compile(r"court is calling|state versus|if you'?ll come forward|"
                       r"who'?s here on|can i see the (follow|next)", re.I)


def first_hearing_span(words, t0, t1):
    marks = []
    joined, idx = [], []
    for x in words:
        joined.append(x["w"])
        idx.append(x["t"])
    flat = " ".join(joined).lower()
    # walk a sliding window of 8 words so multi-word markers are seen
    for i in range(len(joined) - 7):
        seg = " ".join(joined[i:i + 8])
        if NEXT_CASE.search(seg):
            marks.append(idx[i])
    marks = [m for m in marks if t0 <= m <= t1]
    if not marks:
        return t0, t1
    start = marks[0]
    later = [m for m in marks if m > start + 60]
    return start, (later[0] if later else t1)


# -------------------------------------------------------------------- copy
BOILER = re.compile(r"range of punishment|do you understand|jury trial|your honor|"
                    r"court is calling|state of texas|cause number|waive the reading|"
                    r"have you received|hearing date|counsel|council|discovery|"
                    r"admonishment|indictment", re.I)
PROFANE = {"fuck", "fucking", "shit", "bitch", "ass", "damn", "hell",
           "bastard", "piss", "dick", "cunt"}
KEEPCAP = {"i", "i'm", "i've", "i'll", "texas", "challenger", "cadillac", "cadillacs"}


def censor(w):
    lw = re.sub(r"[^a-z]", "", w.lower())
    return (w[0] + "*" * (len(w) - 1)) if lw in PROFANE else w


VOCATIVE = re.compile(r"if you'?ll|come forward|please\.?$|thank you|good morning|"
                      r"have a seat|step (up|forward|back)", re.I)


def pick_hook(cases_txt, case, t0, t1, t0h=None, t1h=None):
    """Score every sentence.  Rare vocabulary beats common docket vocabulary, so
    'Do you want a jury trial?' - verbatim, but present in every hearing - loses
    to something only this case says.  Hooks are never taken from the first 90 s:
    in all three transcripts that stretch is pure docket procedure."""
    df = collections.Counter()
    for k, ws in cases_txt.items():
        df.update(ws["vocab"])
    lo = t0h if t0h is not None else t0
    hi = t1h if t1h is not None else t1
    words = [x for x in cases_txt[case]["words"] if lo <= x["t"] <= hi]
    sents, cur = [], []
    for x in words:
        cur.append(x)
        if x["w"].endswith((".", "?", "!")):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    best = []
    for s in sents:
        raw = " ".join(x["w"] for x in s)
        txt = re.sub(r"^[>\s]+", "", raw).strip()
        rel = s[0]["t"] - lo
        if rel < 90:                                    # docket procedure
            continue
        if not (14 <= len(txt) <= 40):
            continue
        if BOILER.search(txt) or VOCATIVE.search(txt):
            continue
        if re.search(r"\d", txt):                       # cause numbers, dates
            continue
        toks = re.sub(r"[^a-z' ]", "", txt.lower()).split()
        if not (3 <= len(toks) <= 8):
            continue
        if any(w[:1].isupper() and w.lower().strip(".,?!") not in KEEPCAP
               for w in txt.split()[1:]):               # proper names out
            continue
        rarity = sum(1.0 / df[w] for w in set(toks) if len(w) > 3)
        sc = rarity * 3.0
        sc += 1.4 if txt.endswith("?") else 0.0
        sc += 0.9 if txt.lower().startswith(("why", "then why", "what", "how", "so,")) else 0.0
        sc -= abs(len(txt) - 27) * 0.035
        sc += 0.5 if len(toks) <= 6 else 0.0
        best.append((sc, s[0]["t"], " ".join(censor(w) for w in txt.split())))
    best.sort(key=lambda t: -t[0])
    return best[:12]


# ------------------------------------------------------------------- grade
def face_lab(img, box):
    x, y, w, h = [max(0, int(v)) for v in box]
    p = img[y:y + h, x:x + w]
    if p.size < 300:
        return None
    L = cv2.cvtColor(p, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    m = (L[:, 0] > 60) & (L[:, 0] < 235)
    if m.sum() < 60:
        return None
    return (float(L[m, 0].mean() * 100 / 255),
            float(L[m, 1].mean() - 128),
            float(L[m, 2].mean() - 128))


def deveil(img):
    """Remove the achromatic veil.  The 'pale' defect enters at the SOURCE -
    measured on raw tiles across whole clips, judge face a* 13.6 (the approved
    case) against 7.5 and 8.8 (both rejected cases), b* -3.3 against +7.0 and
    +5.2.  Her Zoom camera white-balances differently on different hearing days
    and lifts the black end, which is what kills the red.  No grading stage
    downstream of a composite was ever going to tune this out, because it is not
    a grading defect.

    The black point is a SINGLE scalar for all three channels.  A per-channel
    lift is a white balance in disguise and it moved CARTHIEF's judge from
    b* -3.5 to +6.1 - it made the one case that did not need help worse.  All
    colour work belongs in the explicit Lab step below, where it can be
    measured against the target."""
    out = img.astype(np.float32)
    lo = min(min(float(np.percentile(out[:, :, c], 0.5)) for c in range(3)), 34.0)
    return np.clip((out - lo) * (255.0 / (255.0 - lo)), 0, 255).astype(np.uint8)


# Chroma roll-off for the saturation recovery.  A flat global a*-gain is what
# turned an orange jumpsuit fire-engine red and the judge's skin magenta in the
# first OFFERUP and SANCHEZ builds (they needed 2.15x and 2.9x).  The veil lives
# in the LOW-chroma pixels, so the gain is applied there and rolled off to 1.0
# by the time a pixel is already saturated: her skin at C~11 gets all of it, a
# jail scrub at C~70 gets none.
C_LO, C_HI = 12.0, 55.0
A_GAIN_MAX = 2.9


def grade_to_target(img, jbox):
    """Drive the JUDGE FACE to the fixed target, then leave everything alone.
    Returns (image, peak a*-gain used) so the caller can refuse a frame whose
    source is too far gone to reach the target without wrecking the picture."""
    img = deveil(img)
    peak = 1.0
    for _ in range(4):
        m = face_lab(img, jbox)
        if m is None:
            break
        L, a, b = m
        if abs(a - TGT_A) < 0.8 and abs(b - TGT_B) < 0.8 and abs(L - TGT_L) < 1.2:
            break
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        A = lab[:, :, 1] - 128.0
        Bc = lab[:, :, 2] - 128.0
        C = np.hypot(A, Bc)
        roll = np.clip((C_HI - C) / (C_HI - C_LO), 0.0, 1.0)          # 1 low-chroma, 0 saturated
        rollb = np.clip((90.0 - C) / (90.0 - C_LO), 0.0, 1.0)
        ga = float(np.clip(TGT_A / max(a, 2.0), 0.9, A_GAIN_MAX))
        db = float(np.clip(TGT_B - b, -24.0, 8.0))
        peak = max(peak, ga)
        lab[:, :, 1] = np.clip(128.0 + A * (1.0 + (ga - 1.0) * roll), 0, 255)
        lab[:, :, 2] = np.clip(128.0 + Bc + db * rollb, 0, 255)
        gm = float(np.clip(math.log(max(TGT_L, 1) / 100.0) / math.log(max(L, 1) / 100.0), 0.80, 1.30))
        n = np.clip(lab[:, :, 0] / 255.0, 1e-4, 1)
        lab[:, :, 0] = np.clip(np.power(n, gm) * 255.0, 0, 255)
        img = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return img, peak


# -------------------------------------------------------------------- type
def fit_lines(txt, maxw, cap_px, draw):
    f = ImageFont.truetype(FONT, int(cap_px * 1.40))
    words, lines, cur = txt.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return f, lines


def draw_title(pil, txt, band_h, gold_from):
    """Full-width top band on the blown ceiling.  White with one phrase in gold
    and a heavy black stroke - the treatment in 10 of the 12 ATC references and
    in the approved build.  Returns the font actually used and the line count."""
    d = ImageDraw.Draw(pil)
    chosen = None
    for capf in (CAP_FRAC, 0.070, 0.066, CAP_MIN_FRAC):
        cap = H * capf
        f, lines = fit_lines(txt, W - 56, cap, d)
        if len(lines) <= 2 and len(lines) * cap * 1.62 + 16 <= band_h:
            chosen = (f, lines, cap)
            break
    if chosen is None:
        return None, 0
    f, lines, cap = chosen
    lh = cap * 1.62
    y = max(4.0, (band_h - len(lines) * lh) / 2.0)
    stroke = max(5, int(cap * 0.17))
    flat = " ".join(txt.split())
    gi = flat.lower().find(gold_from.lower()) if gold_from else -1
    consumed = 0
    for ln in lines:
        wpx = d.textlength(ln, font=f)
        x = (W - wpx) / 2.0
        for w in ln.split(" "):
            ww = d.textlength(w + " ", font=f)
            col = GOLD if (gi >= 0 and consumed >= gi) else INK
            d.text((x, y), w, font=f, fill=(col[2], col[1], col[0]),
                   stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += ww
            consumed += len(w) + 1
        y += lh
    return f, len(lines)


def draw_arrow(img, tip, ang_deg, w=ARROW_W):
    """Drawn, not a fixed PNG.  Sized to the ATC median (106 px wide, ~4.0 kpx)
    - the shipped asset was 221x156 = 15.8 kpx, four times the reference area
    and byte-identical in every build."""
    L = w
    hw = w * 0.29
    hl = w * 0.46
    sw = w * 0.155
    pts = np.array([[0, 0], [-hl, -hw], [-hl, -sw], [-L, -sw],
                    [-L, sw], [-hl, sw], [-hl, hw]], np.float32)
    a = math.radians(ang_deg)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]], np.float32)
    P = ((pts @ R.T) + np.array(tip, np.float32)).astype(np.int32)
    cv2.fillPoly(img, [P], (0, 0, 0), lineType=cv2.LINE_AA)
    cv2.polylines(img, [P], True, (0, 0, 0), 9, cv2.LINE_AA)
    Pi = ((pts * 0.86) @ R.T + np.array(tip, np.float32)).astype(np.int32)
    cv2.fillPoly(img, [Pi], (36, 34, 222), lineType=cv2.LINE_AA)
    return P


# -------------------------------------------------------------------- build
def load_tx(path):
    d = json.load(open(path, encoding="utf-8"))
    ws = d["words"]
    vocab = set(re.sub(r"[^a-z' ]", "", " ".join(x["w"] for x in ws).lower()).split())
    return dict(words=ws, vocab=vocab)


MIN_HEADROOM = 100    # one line of type at the minimum cap needs 87 px
MIN_DEFE_FACE = 140   # 140/720*94 = 18 px of face at the 168x94 sidebar size


def search_frame(cap, cfg, centre_f, radius_f, step=5, clamp=None):
    """Score frames on BOTH subjects at once and return the best.

    The layout constraints are applied HERE, as a filter on which frames are
    admissible, not afterwards as a verdict on a finished picture.  That is the
    whole difference between "a refusal means pick a different frame" and "a
    refusal means shrink someone until it fits".  Measured over whole clips,
    frames satisfying both constraints are 20.5% / 40.5% / 17.9% of CARTHIEF /
    SANCHEZ / OFFERUP, so the filter is selective without being empty."""
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    s = H / cfg["judge"][1]
    lo = max(0, int(centre_f - radius_f))
    hi = min(N - 1, int(centre_f + radius_f))
    if clamp:
        lo = max(lo, int(clamp[0]))
        hi = min(hi, int(clamp[1]))
    if hi <= lo:
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, lo)
    best, i = None, lo - 1
    while i < hi:
        ok, fr = cap.read()
        if not ok:
            break
        i += 1
        if (i - lo) % step:
            continue
        got = {}
        for k in ("judge", "defe"):
            w, h, x, y = cfg[k]
            t = fr[y:y + h, x:x + w]
            fs = faces(t)
            if not fs:
                got = None
                break
            if k == "defe":
                r, gsc = pick_defendant(t, fs)
                if r is None or gsc < 0.06:
                    got = None
                    break
                got[k] = (r, face_quality(t, r), float(r[3]), gsc)
            else:
                if face_sharpness(t, fs[0]) < MIN_SHARP:
                    got = None
                    break
                q = face_quality(t, fs[0])
                if q < MIN_JUDGE_Q:      # she is reading her screen; take another frame
                    got = None
                    break
                got[k] = (fs[0], q, float(fs[0][3]), 0.0)
        if not got:
            continue
        # layout feasibility, in output pixels, before anything is committed
        head = min((got[k][0][1] - got[k][0][3] * 0.28) * s for k in ("judge", "defe")) - 10
        dface = got["defe"][2] * s
        if head < MIN_HEADROOM or dface < MIN_DEFE_FACE:
            continue
        sc = (got["judge"][1] * 1.15 + got["defe"][1] * 1.25
              + min(got["defe"][2], 130.0) / 130.0 * 0.85
              + min(head, 200.0) / 200.0 * 0.35)
        if best is None or sc > best[0]:
            best = (sc, i, fr.copy(), got)
    return best


def build(name, cfg, txcorp, verbose=True):
    vid = os.path.join(ROOT, cfg["vid"])
    cap = cv2.VideoCapture(vid)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    t0, t1 = cfg["t0"], cfg["t0"] + N / fps
    rep = dict(case=name)

    # --- 1. hook first, inside the first hearing only ----------------------
    hs, he = first_hearing_span(txcorp[name]["words"], t0, t1)
    rep["hearing_span_clip_s"] = [round(hs - t0, 1), round(he - t0, 1)]
    t0h, t1h = hs, he
    cands = pick_hook(txcorp, name, t0, t1, t0h, t1h)
    if not cands:
        print("[%s] REFUSED: no non-boilerplate hook in transcript" % name)
        return None
    rep["hook_candidates"] = [(round(s, 2), round(t - t0, 1), x) for s, t, x in cands[:5]]

    # --- 2. frame search around the hook, walking candidates on refusal ----
    picked = None
    lo_f, hi_f = (t0h - t0) * fps, (t1h - t0) * fps
    for sc, ht, txt in cands[:8]:
        cf = (ht - t0) * fps
        got = None
        for rad, step in ((25 * fps, 5), (60 * fps, 6), (150 * fps, 10)):
            got = search_frame(cap, cfg, cf, rad, step=step, clamp=(lo_f, hi_f))
            if got is not None:
                break
        if got is not None:
            picked = (txt, ht, got)
            break
    if picked is None:
        print("[%s] REFUSED: no frame with both subjects near any hook" % name)
        return None
    hook, htime, (fsc, fidx, frame, got) = picked
    cap.release()
    rep.update(hook=hook, hook_src_t=round(htime, 2), hook_clip_t=round(htime - t0, 1),
               frame_idx=fidx, frame_clip_t=round(fidx / fps, 2), frame_score=round(fsc, 3),
               judge_q=round(got["judge"][1], 3), defe_q=round(got["defe"][1], 3))

    # --- 3. two tiles, one frame, one scale --------------------------------
    jw, jh, jx, jy = cfg["judge"]
    dw, dh_, dx, dy = cfg["defe"]
    jt = frame[jy:jy + jh, jx:jx + jw]
    dt = frame[dy:dy + dh_, dx:dx + dw]
    s_j, s_d = H / jh, H / dh_
    rep["scale"] = [round(s_j, 4), round(s_d, 4)]
    JW = int(round(W * NARROW_FRAC))
    DW = W - JW
    jup = esrgan.upscale(jt, ESR_W, int(round(jw * s_j)), H)
    dup = esrgan.upscale(dt, ESR_W, int(round(dw * s_d)), H)

    def subject(tile, is_defe):
        fs = faces(tile)
        if not fs:
            return None
        if is_defe:
            r, _g = pick_defendant(tile, fs)
            return r
        return fs[0]

    jr = subject(jt, False)
    dr = subject(dt, True)
    if jr is None or dr is None:
        print("[%s] REFUSED: subject lost in the chosen frame" % name)
        return None

    def window(up, r, panel_w, s):
        cx = (r[0] + r[2] / 2.0) * s
        x = int(round(np.clip(cx - panel_w / 2.0, 0, max(0, up.shape[1] - panel_w))))
        return up[:, x:x + panel_w], x

    jp, jox = window(jup, jr, JW, s_j)
    dp, dox = window(dup, dr, DW, s_d)

    judge_left = jx < dx
    canvas = np.zeros((H, W, 3), np.uint8)
    if judge_left:
        canvas[:, :JW] = jp
        canvas[:, JW:] = dp
        div = JW
        joff, doff = 0 - jox, JW - dox
    else:
        canvas[:, :DW] = dp
        canvas[:, DW:] = jp
        div = DW
        joff, doff = DW - jox, 0 - dox
    rep["judge_side"] = "left" if judge_left else "right"
    rep["divider_x"] = div
    cv2.rectangle(canvas, (div - 3, 0), (div + 2, H), (14, 14, 16), -1)
    cv2.line(canvas, (div + 3, 0), (div + 3, H), (96, 104, 116), 1)

    def canvas_box(off, r, s):
        x, y, w2, h2 = r[:4]
        return (int(x * s) + off, int(y * s), int(w2 * s), int(h2 * s))

    jbox = canvas_box(joff, jr, s_j)
    dbox = canvas_box(doff, dr, s_d)
    rep["defendant_garment"] = round(got["defe"][3], 3)
    rep["judge_face_h"] = jbox[3]
    rep["defe_face_h"] = dbox[3]
    rep["face_ratio_out"] = round(jbox[3] / max(dbox[3], 1), 3)
    rep["face_ratio_src"] = round(float(got["judge"][2]) / max(float(got["defe"][2]), 1), 3)

    for b, lbl in ((jbox, "judge"), (dbox, "defendant")):
        if b[0] < div < b[0] + b[2]:
            print("[%s] REFUSED: divider crosses the %s's face" % (name, lbl))
            return None

    # --- 4. grade to the fixed target --------------------------------------
    pre = face_lab(canvas, jbox)
    canvas, gain = grade_to_target(canvas, jbox)
    post = face_lab(canvas, jbox)
    rep["a_gain_peak"] = round(gain, 2)
    rep["judge_lab_pre"] = [round(v, 1) for v in pre] if pre else None
    rep["judge_lab_post"] = [round(v, 1) for v in post] if post else None

    # --- 5. title band, sized by the faces, never the reverse --------------
    # The band stops above the HAIR, not above the detector's face box.  YuNet's
    # box starts at the brow-line, so "clear of the face box" would still put ink
    # on a head - which is how the old code could measure 13k-41k px of kicker on
    # a body and still call the rule satisfied.  0.28 of a face height is the
    # scalp allowance, and it is subtracted before the type is even sized.
    band = int(min(jbox[1] - jbox[3] * 0.28, dbox[1] - dbox[3] * 0.28) - 10)
    rep["title_band_px"] = band
    if band < 96:
        print("[%s] REFUSED: only %dpx of clear space above the faces" % (name, band))
        return None
    pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    words = hook.rstrip("?.!").split()
    gold_from = " ".join(words[max(1, len(words) - 2):])
    before = np.asarray(pil).copy()
    f, nlines = draw_title(pil, hook, band, gold_from)
    if f is None:
        print("[%s] REFUSED: title will not fit above the faces at the minimum cap" % name)
        return None
    canvas = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    inkmask = (np.abs(np.asarray(pil).astype(np.int16) - before.astype(np.int16)).sum(2) > 24)
    rep["title_lines"] = nlines
    rep["title_cap_px"] = int(f.size / 1.40)

    # --- 6. arrow: tip on the defendant, ray must strike him first ---------
    dx0, dy0, dw0, dh0 = dbox
    tgt = (dx0 + dw0 / 2.0, dy0 + dh0 * 0.42)
    from_left = tgt[0] > W / 2
    ang = 0.0 if from_left else 180.0
    gap = 26
    tip = ((tgt[0] - dw0 / 2.0 - gap, tgt[1]) if from_left
           else (tgt[0] + dw0 / 2.0 + gap, tgt[1]))
    tip = (float(np.clip(tip[0], 8, W - 8)), float(np.clip(tip[1], band + 20, H - 70)))
    hit = "none"
    steps = int(abs(tgt[0] - tip[0])) + 1
    for k in range(steps):
        px = tip[0] + (tgt[0] - tip[0]) * k / max(steps - 1, 1)
        py = tip[1] + (tgt[1] - tip[1]) * k / max(steps - 1, 1)
        if jbox[0] <= px <= jbox[0] + jbox[2] and jbox[1] <= py <= jbox[1] + jbox[3]:
            hit = "judge"
            break
        if dx0 <= px <= dx0 + dw0 and dy0 <= py <= dy0 + dh0:
            hit = "defendant"
            break
    rep["arrow_ray_first_hit"] = hit
    rep["arrow_tip_gap_px"] = int(round(abs(tip[0] - (dx0 if from_left else dx0 + dw0))))
    if hit != "defendant":
        print("[%s] REFUSED: arrow ray strikes %s before the defendant" % (name, hit))
        return None
    P = draw_arrow(canvas, tip, ang)
    rep["arrow_wh"] = [int(P[:, 0].max() - P[:, 0].min()), int(P[:, 1].max() - P[:, 1].min())]

    # --- 7. source overlays -------------------------------------------------
    # The livestream burns "187TH DC" into the bottom-left of the defendant tile
    # and "Judge Boyd" into the bottom-left of the judge tile.  Left whole those
    # are honest source UI in a real frame and they stay.  Cut in half by the
    # panel window they read as a broken composite - the second OFFERUP build
    # shipped with "7TH DC", which is the same defect as the "ludge Boyd" in the
    # old pipeline's OFFERUP.  The tile-to-canvas mapping is known exactly, so
    # any overlay the window bisects is covered by a clean plate rather than
    # detected after the fact.
    for off, s_k, tile_w in ((joff, s_j, jw), (doff, s_d, dw)):
        ox0, ox1 = off, off + int(tile_w * s_k)
        px0, px1 = ox0, ox0 + int(190 * s_k)            # overlay sits at tile x 0..190
        py = H - int(52 * s_k)
        if px0 < 0 < px1 or (px1 > W > px0):            # bisected by a panel edge
            cv2.rectangle(canvas, (max(0, px0), py), (min(W, px1), H), (16, 16, 18), -1)
    cv2.rectangle(canvas, (0, H - 38), (132, H), (16, 16, 18), -1)
    cv2.putText(canvas, "187th DC", (11, H - 12), cv2.FONT_HERSHEY_DUPLEX,
                0.62, (235, 235, 235), 1, cv2.LINE_AA)

    # --- 8. checks ---------------------------------------------------------
    # Subject region = head (with the scalp allowance) plus the torso cone below
    # it.  It deliberately does NOT balloon upward: nothing of a person exists
    # above their own hair, and inflating the box upward is what turned this
    # check into a formality in the old code.
    subj = np.zeros((H, W), bool)
    for b in (jbox, dbox):
        x, y, w2, h2 = b
        subj[max(0, y - int(h2 * 0.30)):min(H, y + int(h2 * 3.6)),
             max(0, x - int(w2 * 0.85)):min(W, x + int(w2 * 1.85))] = True
    rep["type_ink_on_subject_px"] = int((inkmask & subj).sum())
    rep["type_ink_on_face_px"] = int(sum(
        inkmask[max(0, b[1]):b[1] + b[3], max(0, b[0]):b[0] + b[2]].sum() for b in (jbox, dbox)))
    rep["blown_pct"] = round(float((cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY) > 245).mean() * 100), 2)

    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, name + ".jpg")
    cv2.imwrite(out, canvas, [cv2.IMWRITE_JPEG_QUALITY, 94])
    rep["out"] = out

    # CHECK 7 and CHECK 8 exist because the first SANCHEZ build passed all six
    # of the checks above and was obviously slop: a motion-blurred bailiff stood
    # in for the defendant and the judge was reading her screen.  A check earns
    # its place only by firing on something that actually shipped wrong.
    jsharp = face_sharpness(jt, jr)
    dsharp = face_sharpness(dt, dr)
    rep["face_sharpness"] = [round(jsharp, 1), round(dsharp, 1)]
    rep["judge_head_up"] = round(got["judge"][1], 3)
    checks = [
        ("judge a* >= 19", rep["judge_lab_post"][1], rep["judge_lab_post"][1] >= 19.0),
        ("judge b* <= 4", rep["judge_lab_post"][2], rep["judge_lab_post"][2] <= 4.0),
        ("defendant face >= 140px", rep["defe_face_h"], rep["defe_face_h"] >= 140),
        ("type ink on a subject == 0", rep["type_ink_on_subject_px"], rep["type_ink_on_subject_px"] == 0),
        ("arrow ray hits defendant first", hit, hit == "defendant"),
        ("both panels one timestamp", "frame #%d" % fidx, True),
        ("both faces in focus >= 60", "%.0f/%.0f" % (jsharp, dsharp),
         min(jsharp, dsharp) >= MIN_SHARP),
        ("judge not reading (q >= 0.60)", rep["judge_head_up"], rep["judge_head_up"] >= 0.60),
    ]
    rep["checks"] = [(n2, str(v), bool(p)) for n2, v, p in checks]
    rep["CHECKS"] = "PASS" if all(p for _, _, p in checks) else "REVIEW"
    json.dump(rep, open(out + ".json", "w"), indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))

    if verbose:
        print("\n=== %s -> %s" % (name, out))
        print('  hook      : "%s"  (src t=%.1fs, +%.0fs into clip)' % (hook, htime, htime - t0))
        print("  frame     : #%d (+%.1fs) score=%.3f judgeQ=%.3f defeQ=%.3f"
              % (fidx, fidx / fps, fsc, rep["judge_q"], rep["defe_q"]))
        print("  layout    : judge %s, divider x=%d (%.1f%%), scale %s"
              % (rep["judge_side"], div, div / W * 100, rep["scale"]))
        print("  faces     : judge %dpx (%.1f%% H)  defendant %dpx (%.1f%% H)"
              % (jbox[3], jbox[3] / H * 100, dbox[3], dbox[3] / H * 100))
        print("  ratio     : out %.2f vs source %.2f   (approved file = 1.70)"
              % (rep["face_ratio_out"], rep["face_ratio_src"]))
        print("  judge Lab : %s -> %s   target [%.0f, %.0f, %.0f]"
              % (rep["judge_lab_pre"], rep["judge_lab_post"], TGT_L, TGT_A, TGT_B))
        print("  title     : %d line(s), cap %dpx (%.1f%% H), band %dpx"
              % (nlines, rep["title_cap_px"], rep["title_cap_px"] / H * 100, band))
        print("  arrow     : %s px, ray first hit = %s, tip gap %dpx"
              % (rep["arrow_wh"], hit, rep["arrow_tip_gap_px"]))
        for i2, (n2, v, p) in enumerate(checks, 1):
            print("  CHECK %d %-32s %-12s %s" % (i2, n2, v, "PASS" if p else "FAIL"))
        print("  => %s" % rep["CHECKS"])
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", default=None)
    a = ap.parse_args()
    names = a.cases or list(CASES)
    txcorp = {k: load_tx(os.path.join(ROOT, v["tx"])) for k, v in CASES.items()}
    reps = [r for r in (build(n, CASES[n], txcorp) for n in names) if r]
    print("\n%d/%d built -> %s" % (len(reps), len(names), OUTDIR))


if __name__ == "__main__":
    main()
