# -*- coding: utf-8 -*-
"""Build one thumbnail. Single linear pass, no compensation stages.

Obeys spec/THUMBNAIL_SPEC.md. The rule that shapes this file:

    every operation must be LOCAL to the dimension it owns

Nathan states local requirements ("the background is too dark", "she's too
small"). Every previous build turned those into global operations, so each fix
moved four dimensions and broke three. Then a stage was added to repair the
damage, and another to repair that. v3.py ended with five corrective stages,
four of which existed only to undo the previous one.

Here: layers stay separate values, each graded once to its own measured target,
and there is exactly ONE composite at the end. Nothing after the composite
touches colour.

The duplicate-person problem is solved by GEOMETRY, not by inpainting. The
background crop is chosen so her original position lands underneath her enlarged
cut-out. No paint, no mush, no ghost - and the courtroom stays real, which is the
thing that made HS_REMAKE look photographic.
"""
import os, sys, json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_type as TT      # every glyph is drawn there; presets in TT.STYLES

W, H = 1280, 720
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTS = os.path.join(ROOT, "assets", "fonts")
ARROW = None            # set from the caller's asset dir

YELLOW = (254, 251, 3)          # sampled, all 12 Audit thumbnails
GOLD = (237, 203, 9)            # sampled off ref9800's own caption - "golden yellow"
# 9800 caption, measured: fill #EDCB09, stroke pure black, cap 0.167 H, ALL CAPS,
# band x0.19-0.78 W, y0.81-0.98 H. Arrow 0.230W x 0.263H, centre y 0.524H.
KICKER_CAP = 0.167
KICKER_BAND = (0.19, 0.81)
KICKER_STROKE = 9
KICKER_MARGIN = 16
KICKER_FACE_GAP = 10   # px the kicker ink must clear the LOWEST face by
KICKER_MIN_CAP = 96    # px. Below this the kicker is unreadable at 168px sidebar
#
# THE ARROW GOES LAST. Nathan, 2026-08-31: "remove that arrow and replace once
# you fix the entire thumbnail the arrow should be last so you can always make
# sure it doesn't look sloppy".
#
# It is a PROCESS rule, and it is right: the arrow is the only element placed
# relative to everything else, so placing it before the layout is settled means
# re-solving it every time a subject moves - and it kept landing on Boyd's face
# because it was solved against positions that then changed. Build the frame,
# confirm it, add the arrow.
# THE VERTICAL BUDGET, and why "Boyd's head and body is still low" kept
# recurring. The frame is 720px and three things must fit without touching:
#     title    0 -> ~190
#     faces  190 -> 190 + hair + FACE_H
#     kicker  the remainder, and it needs ~140px to read at sidebar size
# With FACE_H=345 and her bob, her face bottom lands at ~625 and the kicker gets
# 95px - so it either sits ON her face or shrinks until it cannot be read. Both
# were shipped. The budget is the constraint; FACE_H is the variable that gives.
HEAD_GAP = 14        # px between the title's lowest ink and the top of both heads   # px the kicker ink must keep clear of the bottom edge   # 13 put flat_g_p90 at 0.352; ref9800 itself sits at 0.263
# Arrow: measured off HIS OWN repositioning, 2026-08-29. He moved it bigger,
# left and lower than the 9800's placement, so his numbers win over the reference.
# ARROW: smaller and tipped up, DEFAULT for every build since 2026-08-31.
# Nathan asked for "make arrow smaller and tip it up on the left to make it look
# like it's coming kinda from WORST EXCUSE EVER", I set it on OFFERUP's case
# config, and every other thumbnail kept the big horizontal arrow - which he
# then had to point out: "things don't have the better spaces out upgrade we
# talked about and arrow upgrade". Per-case is the wrong home for a house-style
# decision. 0.255 W -> 0.1875 W is the 326px -> 240px he approved.
ARROW_W_FRAC, ARROW_CY_FRAC = 0.1875, 0.735
ARROW_CX_FRAC = 0.505
ARROW_ROT_DEFAULT = 15.0
ARROW_DRIFT_COST = 900    # px-equivalent penalty per arrow-width moved
ARROW_GALLERY_COST = 0.25 # per arrow pixel over a padded gallery (stranger) face
ARROW_RETREAT_MAX = 220   # (unused: superseded by the 2D search)
ARROW_ON_SUBJECT_OK = 400  # a few hundred px of soft edge is not "lying on him"
SUBJECT_FACE_MIN_AREA = 20000   # px; below this a detection is background, not a subject
# 0.255 W of source lands at 0.240 W of visible red after the de-jag median.
RED = (253, 1, 1)               # sampled, the 9 with arrows
WHITE_RGB = (255, 255, 255)
LUMA_W = np.array([0.299, 0.587, 0.114], np.float32)
# GRAIN. 1.5 was "the lightest that clears the gate" - calibrated against a
# gate, not against whether anyone can SEE it. Measured in the colour study: a
# sigma-1.5 grain survives JPEG q95 as 0.284 and q85 as 0.132, i.e. it is
# destroyed by the encoder. Nathan, twice: "u still didn't add grain".
# 5.0 survives compression and unifies the composite - a cut-out and a plate
# come from different sources, and a shared grain is what stops the join
# reading as pasted.
# 5.0 was visible but it landed ON the faces as haze - face "detail" measured
# 1383 against 1011 on the version he preferred, which is noise inflating the
# metric while the face itself got flatter. 3.0 still survives JPEG (a sigma-1.5
# grain does not) without frosting skin.
GRAIN = 1.8    # light pass on the PHOTO, before type
FINAL_GRAIN = 3.4  # the real layer, over the whole finished frame
# BG_DARKEN retired 2026-08-31. Measured redundant: at BG_TARGET=70, moving
# darken 0.08 -> 0.20 took the composite background 69 -> 64, identical in kind
# to lowering BG_TARGET by ~13. Two knobs fighting over one dimension.
BG_DARKEN = 0.0
BG_BLUR_DEFAULT = 1.1  # sigma. The 1.6 ceiling is the mush he rejected.
# SAT_TRIM 1.13 -> 1.00. Measured 2026-08-31 against a 68-thumbnail corpus
# rebuilt under a declared quality rule: our skin a* runs 14.4-20.6 where the
# corpus q1-q3 is 8.5-13.7 and OUR OWN SOURCE PLATES are 6.8-13.6. The pipeline
# was multiplying skin chroma ~1.7x on material that started correct.
# The sweep also showed this alone CANNOT fix it (at 0.85 CARTHIEF is still
# 13.1), which is why the clamp below exists.
SAT_TRIM = 1.00
ARROW_NUDGE_X = 0    # superseded: the arrow now targets his measured centre
RIM_PX = 2           # crisp white outline, then a soft glow OUTSIDE it.
# ---------------------------------------------------------------- SIMPLE --
# 2026-09-02, after five rejected builds and five invented metrics:
# "the engine that actually picks what faces to use and the engine to edit
#  the people probably needs to be redone ... or idk maybe we're over
#  complicating everything pls just fix".
#
# The subjects pass through ten stages that each move colour: per-layer luma
# and saturation grade, skin-saturation balance, face-brightness midpoint,
# skin-chroma lift, rim glow, dodge/burn, then a global LOOK. He looked at a
# raw restored crop and said it was good, then at the composite and said the
# people were ruined. BOYD_SIMPLE=1 turns the colour surgery OFF and keeps
# only geometry, matte, and the plate darkening that gives separation - the
# people keep their own pixels. Compare the two on the vs_accepted sheet.
SIMPLE = os.environ.get('BOYD_SIMPLE', '') == '1'
RIM_MODE = 'glow'    # 'line' | 'smooth' | 'glow' | 'none'
# 2026-08-29 he picked 'smooth' (hard white outline + wide glow) from four
# options. 2026-08-31 he called that a defect: "Surgically fix all the mistakes
# you make with the white blur and outline around the people" - and then, when I
# removed it entirely, corrected me again: "I wanted you to do the slight glow
# around the people but professionally and surgically".
#
# So the settled reading is: NO hard outline, but KEEP a slight separation glow.
# 'glow' mode draws no line at all; RIM_GLOW dropped 0.30 -> 0.085 and the
# spread 14 -> 9, because 14px read as haze rather than separation.
# He picked 'smooth' 2026-08-29 after seeing all four at full size. The outline
# is gated by local curvature: it stays where the boundary is smooth (jaw,
# shoulder, cheek) and fades where it is ragged (hair). A hard line traces every
# bump of a hair silhouette - that is not a polish problem, it is what a hard
# line DOES on hair, which is why cleaning the contour alone never fixed it.
RIM_STRENGTH = 0.85  # 4px bloomed into a blob in the hair; 2px + the
                     # (1-alpha) term keeps it a line, not a halo.
# SEPARATION GLOW. Nathan, 2026-08-31: "surgically have the white glow around
# the main subjects to see them better kinda like the slight outline but
# professionally do it, no shortcuts".
#
# A single blur is the shortcut, and it is what made the earlier versions read
# as either a hard line or a haze. A separation glow the way it is actually
# built: TWO layers. A tight bright core that hugs the silhouette and does the
# separating, plus a wide low falloff that seats the subject against the plate.
# Neither alone looks right - the core alone is an outline, the falloff alone is
# fog.
RIM_GLOW = 0.16      # overall strength
RIM_CORE_SIGMA = 3.5  # the tight lift that separates
RIM_WIDE_SIGMA = 16.0  # the soft seat behind it
RIM_CORE_MIX = 0.62   # how much of the total is core vs falloff
RIM_SPREAD = 9       # kept for configs that set it explicitly
SKIN_SAT_PULL = 0.35 # fraction of the way to the shared skin-saturation midpoint
# FACE LUMINANCE: partial pull, same principle as the saturation one.
# Nathan, 2026-08-31: "Apply the surgical lighting fix that we did in the other
# thumbnails and make sure u always use that when making thumbnails".
#
# The fix only existed as HAND-TYPED numbers on one case - OFFERUP carried
# face_l_bias {defendant +7.5, boyd -4.08}, which I derived by rendering twice
# and solving each face's slope by hand. That is the loop the skill warns
# against, and it is why four of five cases never got the fix at all.
#
# Forcing both faces to an identical measured L* was the original over-
# correction ("defendant's face is still dark" then "Boyd slightly looks overly
# bright" in consecutive messages) - equal L* is not equal PERCEIVED brightness
# when one face is lit and the other is in shadow. Pulling each PART of the way
# closes a real mismatch without repainting either face, and needs no per-case
# constant, so every build gets it.
FACE_L_PULL = 0.60
# SKIN CHROMA CEILING, Lab sqrt(a^2+b^2). Tier-A corpus median a* 11.62 /
# b* 13.52 -> chroma 17.83, and both components pass the variance rule
# (IQR 5.23 and 5.45) - the most defensible target in the calibration study.
# Clamped LOCALLY on skin, instead of trimming global saturation, so the room
# and the orange jumpsuits keep their colour.
# SKIN TARGET, both directions. A CEILING alone made skin pale: it pushed
# chroma down and nothing ever pulled it back, so the finished faces measured
# L*150-158 with chroma 15.3-17.3 against a corpus median of L*~145 / 17.8 -
# brighter than the corpus AND less colourful than it, which is the definition
# of pallid. Nathan: "Their skin is bright but now it's pale".
# Targeted, with a dead-band so a face already in range is left alone.
# HIS PICK, and it beats the corpus. Nathan, 2026-08-31: "I like the skin tone
# in v23 better and the background of the very latest". Measured on v23:
# L*134.2 / chroma 20.6, against the then-current 148.3 / 17.7 - deeper and
# richer. Note 20.6 sits ABOVE the 68-thumbnail corpus median of 17.8: the
# corpus is evidence, his eye is the decision, and where they disagree he wins.
# SUPERSEDES the corpus-derived 17.8/146.
SKIN_CHROMA_TARGET = 20.6
SKIN_CHROMA_BAND = 1.2
SKIN_L_TARGET = 134.0     # uint8 Lab, measured off v23, the tone he chose
SKIN_L_BAND = 5.0
# HIGHLIGHT SHOULDER ON SUBJECTS. Nathan: "There's still harsh white lighting on
# faces". Measured: EVERY face clipped to L*255, up to 30.5% of Boyd's face
# above L*210 on SANCHEZ. A shoulder identical to this already existed - applied
# to the BACKGROUND layer only, never to the subjects. One-of-two again.
# Knee and strength set from the measurement, not taste: at 186/0.45 one face
# still had 20.3% of its pixels above L*210. 168/0.30 brings the worst case
# under the 12% gate while leaving normal speculars alone.
# Style-2 corpus median subject-minus-background separation, from the 68
# thumbnail calibration (IQR +11.5 to +29.9 in L*).
SEPARATION_DL = 18.6
DB_DODGE = 0.26   # centre lift
DB_BURN = 0.22    # perimeter deepen
# A DODGE MAY NOT CLIP A FACE. The lift is a MULTIPLY (canvas * (1 + amt)), so
# a T-zone pixel already at 200 comes out at 252 - paper white, flat, with the
# hard edge of the ellipse around it. That is exactly the defect verify_build
# gate J exists to catch, and it is what refused CLAYTON: Boyd's own layer
# measured 3.0% of her face over L*210 with p95 205, and the build turned that
# into 18-23% - a hard-edged white patch across her cheek and nose - while
# face_l_bias, the documented brightness lever, moved it only 0.43 %/unit
# (23.3% at bias 0, 18.2% at -12: ~34 units to fix, which would have made her
# a silhouette). Clipped pixels do not scale back. So the dodge is limited per
# pixel to the headroom under this luma: a pixel already at or above it gets
# no lift, and no pixel is lifted past it. 205 sRGB luma is just under the
# L*210 the gate measures (L* 210/2.55 = 82.4 -> ~207 sRGB).
DB_DODGE_CEILING = 205.0
# Knee raised back to 178. At 158 it was compressing most of a LIT FACE, not
# just blown highlights, and measured face contrast fell 62.2 -> 57.3 - the
# "they look super processed / flat" defect. Brightness is now handled by the
# skin L target instead, so the shoulder only has to catch real clipping.
SUBJ_SHOULDER = 178.0
SUBJ_SHOULDER_K = 0.30
# WHITE BALANCE: TRIED AND REVERTED, 2026-08-31. It found the brightest
# low-chroma cloth in each subject and pulled it to neutral. On THOMPSON that
# cloth is Boyd's PINK COLLAR - genuinely pink, not grey - so "correcting" it
# dragged both subjects blue. Nathan: "the defendant and judge look blue".
#
# The gate said it worked (her chroma drift went 11.3 -> 1.5) while the picture
# got worse, which is the whole lesson: a metric that improves is not evidence
# the image improved. Do not reinstate this without a guaranteed neutral
# reference - a colour chart, or a surface known to be white - and never infer
# one from "brightest and least saturated".
TYPE_SHADOW = dict(dx=5, dy=6, blur=7, alpha=0.72)
KICKER_EMPHASIS = 0.85       # strength of the coloured glow behind the 2nd run
KICKER_EMPHASIS_BLUR = 13.0  # px sigma

# --- targets, every one measured off a file Nathan approved -------------------
# BACKGROUND TARGET. Nathan, 2026-08-31: "The subjects don't pop and grab
# attention subconsciously like a viral thumbnail does".
#
# MEASURED, and it was backwards. With L=120 the background came out BRIGHTER
# than the people standing in front of it:
#     OFFERUP   subject L*104.7   background L*118.4    dL -13.7
#     CARTHIEF  subject L* 93.0   background L*128.2    dL -35.2
#     THOMPSON  subject L* 95.5   background L*135.8    dL -40.3
# The eye goes to the brightest, most contrasted region, so it went to the room.
# No amount of rim glow fixes that - the glow was compensating for a tonal
# relationship that was inverted at source.
#
# Subjects land around L*95-105, so the plate is targeted well below them and
# desaturated, which is what actually makes a cut-out read as foreground.
# INTERIM, NOT DERIVED. L=120 gave no subject/background separation ("the
# subjects don't pop"); L=78 gave "colors are way off". The answer is bracketed
# between two of his complaints, so this sits between them AS A PLACEHOLDER
# until the calibration measurement lands. Do not treat it as measured - that
# is exactly the invented-threshold failure this repo keeps repeating.
# DERIVED, no longer a placeholder. The calibration solved each case's plate
# for the style-2 corpus median separation of dL +18.6 (OFFERUP 100.7,
# THOMPSON 81.7, CARTHIEF 76.2) -> median 81.7. At the interim 100 the measured
# separation was NEGATIVE again (median dL -10.2, background brighter than the
# people) - "the subjects don't pop", measurably back.
# S is deliberately left near the corpus q1 floor of 41 rather than targeted:
# background saturation IQR is 41-146, too variable to aim at.
BG_TARGET = dict(L=82.0, S=42.0)
FACE_L_TARGET = 120.0                   # HS_REMAKE 121, WORKING 118 (median L*)
SUBJECT_S_TARGET = 86.0                 # the plate's own skin/scrubs saturation
LOOK = dict(luma=113.5, sd=73.8, definition=0.28)
if SIMPLE:
    # No shared destinations, no lifts, no rim. Dead-bands so wide the skin
    # stages can never fire, and the pull to a shared saturation is zero.
    RIM_MODE = 'none'
    # The highlight shoulder is the airbrush. Every subject pixel over L178
    # is crushed to 178 + 0.30*(L-178), so a face whose specular lives at
    # 190-230 comes out flat paste - measured 2026-09-02 against the restored
    # crop, which still had real pores and beard detail at 1:1 while the
    # composite face was waxy. Off in SIMPLE; gate C still catches a face
    # that is genuinely blown.
    SUBJ_SHOULDER = 255.0
    SUBJ_SHOULDER_K = 1.0
    DB_BURN = 0.0
    SKIN_SAT_PULL = 0.0
    SKIN_CHROMA_BAND = 999.0
    SKIN_L_BAND = 999.0
    print('  thumb: BOYD_SIMPLE=1 - subject colour surgery OFF '
          '(rim, skin balance, chroma lift, skin L all disabled)')
# LOOK measured off Nathan's own regrade of the 2026-08-29 build: he took luma
# 119.9->109.7, contrast 59.5->69.3, definition +24%. Applied ONCE, at the end,
# as a look - not as a stage repairing another stage.
FACE_H = 345   # bumped from 300 on 2026-08-30: "make them all a little bigger over all"                            # parity: both subjects identical.
# Was raised to 340 only to make the two cut-outs big enough to bury the attorney
# standing behind Boyd. A clean harvested plate has nobody to bury, so it goes
# back - and the room shows through instead.
DEF_C, JUD_C = (300, 392), (990, 392)   # defendant LEFT, Boyd RIGHT. Also pulled
                                        # back in from the edges for the same
                                        # reason - the room is worth seeing now.


# ---------------------------------------------------------------- primitives
def sat_scale(f, k):
    """Saturation in float RGB, luminance preserved. Never HSV round trips - six
    of them posterised both faces while every gate reported PASS."""
    g = (f * LUMA_W).sum(axis=2, keepdims=True)
    return g + (f - g) * k


def measure(f, mask=None):
    u = np.clip(f, 0, 255).astype(np.uint8)
    sel = np.ones(u.shape[:2], bool) if mask is None else mask
    g = cv2.cvtColor(u, cv2.COLOR_RGB2GRAY)
    s = cv2.cvtColor(u, cv2.COLOR_RGB2HSV)[..., 1]
    return float(g[sel].mean()), float(s[sel].mean())


def grade_to(f, L_target, S_target, mask=None, iters=30):
    """Bring ONE layer to ONE target. Owns luma and saturation for that layer and
    returns nothing else - it cannot move geometry, sharpness or any other layer."""
    for _ in range(iters):
        L, S = measure(f, mask)
        if abs(L - L_target) < 0.8 and abs(S - S_target) < 0.8:
            break
        f = f * (L_target / max(L, 1e-3)) ** 0.55
        L2, S2 = measure(f, mask)
        k = float(np.clip(1.0 + (S_target - S2) / 170.0, 0.86, 1.16))
        f = sat_scale(f, k)
    return f


# ------------------------------------------------------ cut edges (R29) --
# A source-boundary edge (the Zoom tile ending at her chest / shoulder) shows
# up on a cutout as a run of consecutive rows whose silhouette ENDS on the same
# column. Gate K rejects it when it lands inside the canvas (longest straight
# run > CUT_EDGE_RUN_FRAC of the subject's span). Nathan's fix, verbatim: "what
# you really could have done was expanded her to make her bigger ... It should
# always touch the screen or the edges, and it should not show any hard cuts."
# So cut() SCALES the layer until every such edge is at or past the canvas
# edge - the same loop that already grows a layer until its bottom leaves the
# frame. MONKEY, 2026-09-01: the judge's crop ran 21 px past her tile, the
# matte ended in a 494-row cliff at cutout x=1279, every build failed K at
# canvas x=1239. A mirrored strip was tried first and removed the same day:
# R29 says scale, never a stretched, mirrored or cloned extension.
CUT_EDGE_RUN_FRAC = 0.18   # == verify_build.LIMB_MAX_RUN_FRAC, the signature gate K rejects


def _longest_run(v):
    """Longest run of True in a 1-D bool array."""
    v = np.concatenate(([False], np.asarray(v, bool), [False])).astype(np.int8)
    d = np.diff(v)
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    return int((ends - starts).max()) if starts.size else 0


def find_cliff(a, side="right", frac=CUT_EDGE_RUN_FRAC):
    """The seam signature on a cutout alpha: the longest run of consecutive
    rows whose silhouette ends on the SAME column, on `side`. Returns
    (column, rows_mask, run, span) when run/span > frac, else None. A row
    counts only where that column is its last subject pixel - a sleeve edge
    with more body beyond it is not a cliff."""
    m = np.asarray(a) > 128
    H_, W_ = m.shape
    has = m.any(axis=1)
    ys = np.where(has)[0]
    if not ys.size:
        return None
    span = int(ys[-1] - ys[0] + 1)
    if side == "right":
        last = W_ - 1 - np.argmax(m[:, ::-1], axis=1)
    else:
        last = np.argmax(m, axis=1)
    counts = np.bincount(last[has], minlength=W_)
    best = (0, None)
    for c in np.where(counts > max(8, frac * span))[0]:
        run = _longest_run(has & (last == c))
        if run > best[0]:
            best = (run, int(c))
    run, c = best
    if c is None or run <= frac * span:
        return None
    return c, (has & (last == c)), run, span


def resize_rgba(im, size):
    """RGB and ALPHA resized separately. Pillow flattens colour wherever alpha is
    not solid, which lands on the semi-transparent hair band."""
    a = np.asarray(im)
    rgb = np.asarray(Image.fromarray(a[..., :3]).resize(size, Image.LANCZOS))
    alp = np.asarray(Image.fromarray(a[..., 3]).resize(size, Image.LANCZOS))
    return Image.fromarray(np.dstack([rgb, alp]))


def ink_vs_subjects(tmask, kmask, jal, dal, face_boxes):
    """R1, measured honestly. Returns
        title_on_subject_px  - title ink over EITHER subject's alpha (> 0.4).
                               Asserted 0 since the beginning.
        kicker_on_face_px    - kicker ink inside any face box (x, y, w, h in
                               canvas space). Asserted 0 since 2026-09-01: the
                               kicker solver pushed itself below the faces from
                               2026-08-31 but nothing ever MEASURED the result.
        kicker_on_subject_px - kicker ink over either subject's alpha. LOGGED,
                               not asserted: the kicker band is the bottom of
                               the frame and both bodies live there. Measured
                               2026-09-01 on the five accepted builds: judge
                               17.7k-30.8k px, defendant 13.3k-41.0k px on
                               every one. He accepted all five. So 'type never
                               on a body' is satisfied by the TITLE only, and
                               the log used to hide that behind one number
                               (`type_on_subject_px`) that counted the title
                               alone while the skill said it covered both.
    `type_on_subject_px` stays in the log for its readers and now equals
    title_on_subject_px + kicker_on_face_px - the two that must be zero."""
    subj = (jal > 0.4) | (dal > 0.4)
    tmask = tmask.astype(bool)
    kmask = kmask.astype(bool)
    fmask = np.zeros(kmask.shape, bool)
    for b in face_boxes or ():
        if not b:
            continue
        x, y, w, h = (int(v) for v in b[:4])
        fmask[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = True
    t_sub = int((tmask & subj).sum())
    k_face = int((kmask & fmask).sum())
    k_sub = int((kmask & subj).sum())
    return dict(title_on_subject_px=t_sub, kicker_on_face_px=k_face,
                kicker_on_subject_px=k_sub, type_on_subject_px=t_sub + k_face)


def faces_in(rgb):
    bgr = rgb[:, :, ::-1].copy()
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(os.path.join(ROOT, "models", "yunet2023.onnx"),
                                  "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, raw = d.detect(bgr)
    out = []
    if raw is None:
        return out
    for r in sorted(raw, key=lambda r: -r[3]):
        x, y, fw, fh = [max(0, int(v)) for v in r[:4]]
        if fw > 24 and fh > 24:
            out.append((x, y, fw, fh))
    return out


# ---------------------------------------------------------------- the build
class Thumb:
    # tunables a caller may vary to generate options. Each is ONE dimension.
    bg_blur = BG_BLUR_DEFAULT  # sigma, background layer only - DEFAULT, not opt-in
    face_h = None          # override FACE_H per build (parity is kept: ONE value)
    def_c = None           # override DEF_C
    jud_c = None           # override JUD_C
    bg_plate = None        # a CLEAN harvested courtroom plate (nobody standing).
                           # When set there is nothing to hide, so the crop is a
                           # straight centre framing instead of a contorted one.
    arrow_on = True        # the arrow is optional per build
    # 22 deg read as tilted away from the caption. Nathan, 2026-08-31: "fix the
    # arrow a little bit less off the captions" - so flatten it and drop the
    # whole arrow nearer the kicker, which is where he wanted it to appear to
    # come FROM in the first place.
    arrow_rot = 15.0       # degrees, POSITIVE tips the pointing end UP
    arrow_want = None      # width in px; None = ARROW_W_FRAC * W
    defendant_nudge = (0, 0)   # (dx, dy) applied to the solved position
    solo = False           # one subject + the prop, instead of the two-up
    face_l_target = None   # override FACE_L_TARGET; "brighten his face up a bit"
    # DEFAULT ON since 2026-08-31. It was opt-in and only OFFERUP set it, so the
    # other four cases used a fixed FACE_H and the kicker got squeezed to fit
    # whatever room was left - CARTHIEF rendered "HE LAUGHED..." at size 69 in
    # the bottom-left corner instead of full width. Deriving face_h from the
    # vertical budget is right for every build, not just the one that asked.
    # Set "solve_face_h": false on a case to opt OUT.
    solve_face_h = True    # derive face_h from the vertical budget, never typed
    judge_head_dy = 0      # raise/lower Boyd relative to heads-level (R38)
    face_l_bias = None     # {"boyd": -6, "defendant": +8} L* trim around the midpoint
    yellow = YELLOW        # title accent
    title_frac = 0.965     # share of frame width the title spans
    type_style = "house"   # TT.STYLES key: the type treatment for title AND kicker.
                           # "house" is the accepted 2026-08-31 look byte for byte;
                           # anything else is an option Nathan picks (P36, 0025)

    def __init__(self, plate_png, judge_png, plate_face, judge_face, texts, arrow_png):
        self.plate = np.asarray(Image.open(plate_png).convert("RGB"))
        self.plate_a = np.asarray(Image.open(plate_png).split()[-1]) \
            if Image.open(plate_png).mode == "RGBA" else None
        self.judge_src = judge_png
        self.plate_face = plate_face          # her face IN THE PLATE - used only to
                                              # solve a crop that hides her original
        self.defendant_face = plate_face      # her face INSIDE her own layer image;
                                              # differs once she is regenerated from
                                              # her own crop. Two different frames of
                                              # reference - conflating them made the
                                              # crop solver unsolvable.
        self.judge_face = judge_face
        self.white, self.yellow = texts
        self.yellow_rgb = YELLOW
        self.kicker_text = None
        # TWO-COLOUR KICKER. Nathan, 2026-08-31, for the monkey build: "put
        # 'YOUR OWNER HATES YOU' and your owner is white and hates you is red".
        # The TITLE has had a two-colour split since the beginning; the kicker
        # was single-GOLD only - the same title/kicker asymmetry that has now
        # produced four separate defects in one day. `kicker_split` is the
        # leading run, `kicker_colors` the two fills.
        self.kicker_split = None
        self.kicker_colors = None
        self.arrow_png = arrow_png
        self.cover_masks = {}   # {name: HxW bool in PLATE coords} - things the
                                # background must not show: the defendant's own
                                # original position, and the attorney
        self.log = {}

    # -- geometry: solve the crop against the ACTUAL mattes ------------------
    def solve_crop(self, cover_masks, subject_cover):
        if self.bg_plate is not None:
            ph, pw = self.bg_plate.shape[:2]
            crop_h = min(ph, pw / (W / H))
            crop_w = crop_h * (W / H)
            x0 = (pw - crop_w) / 2.0
            y0 = (ph - crop_h) / 2.0
            self.log["crop"] = [int(x0), int(y0), int(x0 + crop_w), int(y0 + crop_h)]
            self.log["crop_scale"] = round(W / crop_w, 4)
            self.log["crop_source"] = "clean harvested plate"
            self.log["exposed_px_quarter_res"] = 0
            g = cv2.cvtColor(cv2.resize(
                self.bg_plate[int(y0):int(y0 + crop_h), int(x0):int(x0 + crop_w)],
                (W, H)), cv2.COLOR_RGB2GRAY)
            self.log["crop_detail"] = round(float(cv2.Laplacian(g, cv2.CV_64F).var()), 1)
            return

        """His fix: make the subjects bigger, scoot her left, slide the whole
        background RIGHT. Everything the plate must not show - her original
        position and the attorney - then travels right until the two cut-outs sit
        on top of it. No inpainting anywhere.

        Search is done at 1/4 resolution on the masks alone. Testing a full-plate
        resize per candidate was 260k image ops; this is the same answer in ~2s.
        """
        import thumb_metrics as TM
        ph, pw = self.plate.shape[:2]
        Q = 4
        cov_q = cv2.resize(subject_cover.astype(np.uint8), (W // Q, H // Q),
                           interpolation=cv2.INTER_NEAREST) > 0
        masks_q = {k: cv2.resize(v.astype(np.uint8), (pw // Q, ph // Q),
                                 interpolation=cv2.INTER_NEAREST) > 0
                   for k, v in cover_masks.items()}
        cands = []
        for crop_w in range(1300, min(pw, 2600) + 1, 50):
            crop_h = crop_w / (W / H)
            if crop_h > ph:
                continue
            for x0 in range(0, int(pw - crop_w) + 1, 40):
                for y0 in range(0, int(ph - crop_h) + 1, 40):
                    exposed = 0
                    for m in masks_q.values():
                        sub = m[int(y0 / Q):int((y0 + crop_h) / Q),
                                int(x0 / Q):int((x0 + crop_w) / Q)]
                        if not sub.any():
                            continue
                        r = cv2.resize(sub.astype(np.uint8), (W // Q, H // Q),
                                       interpolation=cv2.INTER_NEAREST) > 0
                        exposed += int((r & ~cov_q).sum())
                    cands.append((exposed, x0, y0, crop_w, crop_h))
        # Two-stage, and the order matters: FIRST keep every framing that hides
        # what must be hidden, THEN among those pick the one with the most real
        # courtroom in it. Ranking by exposure alone picked a blank ceiling.
        cands.sort(key=lambda t: t[0])
        floor = cands[0][0]
        viable = [c for c in cands if c[0] <= floor + 200][:220]
        best = None
        for exposed, x0, y0, crop_w, crop_h in viable:
            cand = np.asarray(Image.fromarray(self.plate).crop(
                (int(x0), int(y0), int(x0 + crop_w), int(y0 + crop_h))
            ).resize((W, H), Image.LANCZOS))
            pfa = TM.poster_fa(cand)
            # Keep the ROOM. Hiding the attorney by zooming into blank ceiling
            # technically satisfies every constraint and throws away the courtroom,
            # which is the thing that makes these read as real. Reward real texture.
            g = cv2.cvtColor(cand, cv2.COLOR_RGB2GRAY)
            detail = float(cv2.Laplacian(g, cv2.CV_64F).var())
            score = -detail + pfa * 200.0 + exposed / 40.0
            if best is None or score < best[0]:
                best = (score, x0, y0, crop_w, crop_h, pfa, exposed)
        score, x0, y0, crop_w, crop_h, pfa, exposed = best
        self.log["crop"] = [int(x0), int(y0), int(x0 + crop_w), int(y0 + crop_h)]
        self.log["crop_scale"] = round(W / crop_w, 4)
        self.log["crop_poster_fa"] = round(float(pfa), 4)
        self.log["exposed_px_quarter_res"] = int(exposed)
        self.log["crop_detail"] = round(float(cv2.Laplacian(cv2.cvtColor(np.asarray(Image.fromarray(self.plate).crop((int(x0), int(y0), int(x0 + crop_w), int(y0 + crop_h))).resize((W, H), Image.LANCZOS)), cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()), 1)

    def background(self):
        x0, y0, x1, y1 = self.log["crop"]
        src = self.bg_plate if self.bg_plate is not None else self.plate
        im = Image.fromarray(src).crop((x0, y0, x1, y1)).resize((W, H), Image.LANCZOS)
        f = np.asarray(im).astype(np.float32)
        # ONE local operation: tame the clipped courtroom lights. LUMINANCE only.
        # Compressing per-channel pulls bright pixels toward a common value and
        # flattens their chroma - measured, it took the ceiling's poster_fa from
        # 0.000 in the crop to 0.046 in the render, which is the gate's whole
        # complaint. Scaling RGB by the luma ratio preserves the colour spread.
        g = (f * LUMA_W).sum(axis=2, keepdims=True)
        tamed = np.where(g > 186.0, 186.0 + (g - 186.0) * 0.5, g)
        f = f * (tamed / np.maximum(g, 1e-3))
        if True:
            # depth only: the subjects are composited on top afterwards, so this
            # separates them from the room without touching either of them.
            f = cv2.GaussianBlur(f, (0, 0), self.bg_blur)
        # DARKEN THE PLATE so the lit subjects sit forward. Nathan, 2026-08-31:
        # "slightly blur and darken the back". This was never applied at all -
        # `bg_blur` existed as a per-case value set on exactly ONE case, and
        # there was no darkening anywhere. Both are house style, so both are
        # defaults now.
        f = grade_to(f, BG_TARGET["L"], BG_TARGET["S"])
        # AFTER the grade, not before. Applied first, grade_to() normalised the
        # plate straight back to its target and the darkening did nothing at all
        # - measured bg L*=120.0 on every case with BG_DARKEN already set.
        if BG_DARKEN:
            f = f * (1.0 - BG_DARKEN)
        L, S = measure(f)
        self.log["background"] = dict(L=round(L, 1), S=round(S, 1))
        return f

    def _kicker_runs(self):
        """The kicker as (text, fill, emphasised) runs - the split form when
        `kicker_split` is a prefix, else the single GOLD run."""
        if self.kicker_split and self.kicker_text.startswith(self.kicker_split):
            c1, c2 = (self.kicker_colors or (WHITE_RGB, RED))
            head = self.kicker_split
            return [(head, tuple(c1), False), (self.kicker_text[len(head):], tuple(c2), True)]
        return [(self.kicker_text, GOLD, False)]

    def _kicker_ink_height(self):
        """Ink height of the kicker AT FULL SIZE. The budget must be reserved
        for the kicker the house style wants, not for whatever it shrank to."""
        if not self.kicker_text:
            return 0
        spec = TT.resolve(self.type_style, "kicker")
        cap = int(KICKER_CAP * H)
        lay = TT.fit(spec, self._kicker_runs(), cap, W * 0.62, 240)
        bb = lay.ink_bbox(spec["ink_stroke"])
        return int(bb[3] - bb[1]) + TT.extra_below(spec, TT.cap_height(lay.base))

    def _hair_ratio(self, png, face):
        """Silhouette height ABOVE the face box, as a multiple of face height.

        This is the number that made Boyd sit low: her bob carries far more
        silhouette above her eyes than his head does, so a shared face_h puts
        her FACE lower in the frame even when their heads are level. Measured
        per subject from their own cut-out rather than assumed.
        """
        src = Image.open(png)
        a = np.asarray(src.split()[-1]) > 8
        ys, xs = np.where(a)
        if not ys.size:
            return 0.0
        fx, fy, fw, fh = face
        top = int(ys.min())
        return max(0.0, (fy - top) / float(max(fh, 1)))

    def cut(self, png, face, want_h, cx, cy, label, top_y=None):
        """Place a subject.

        `cy` centres the FACE BOX. `top_y`, when given, instead lands the TOP OF
        THE SILHOUETTE (the top of the head) on that row and overrides cy.

        Nathan, 2026-08-30: "you kept making this choice to put the defendant so
        low ... their head should be level with Boyd's head."

        Measured, this is not an eye-line problem - the eye lines were already
        level to within 1-4px (CARTHIEF 400.6 vs 401.8, SANCHEZ 372.3 vs 376.3).
        It is a HEAD EXTENT problem: Boyd's bob puts her silhouette top far above
        the defendant's, so with faces aligned she still reads as sitting higher.
        Aligning the heads means aligning the tops of the heads.
        """
        src = Image.open(png)
        a = np.asarray(src.split()[-1]) > 8
        ys, xs = np.where(a)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        crop = src.crop(box)
        fx, fy, fw, fh = face
        s = want_h / fh
        s0 = s
        # CUT EDGES (R29). A tile-seam cliff on either side of this cutout, in
        # crop coordinates; the loop below grows the layer until each one is
        # at or past the canvas edge, exactly as it already does for the
        # bottom. A cliff on the NEAR side of the face centre cannot be pushed
        # out by growing (growing pulls it inward) - it is logged and left for
        # gate K to refuse, not hidden.
        _fcx_crop = fx + fw / 2 - box[0]
        _ca = np.asarray(crop.split()[-1])
        cliffs, stuck = [], []
        for _side in ("right", "left"):
            _hit = find_cliff(_ca, _side)
            if _hit is None:
                continue
            _c = _hit[0]
            _far = (_c > _fcx_crop) if _side == "right" else (_c < _fcx_crop)
            (cliffs if _far else stuck).append(
                dict(side=_side, column=int(_c), run=int(_hit[2]), span=int(_hit[3])))
        for _ in range(40):
            r = resize_rgba(crop, (max(1, int(crop.width * s)), max(1, int(crop.height * s))))
            x0 = int(cx - (fx + fw / 2 - box[0]) * s)
            _al = np.asarray(r.split()[-1])
            m = _al > 12
            # HEAD TOP KEYS ON THE SOLID SILHOUETTE, NOT THE FAINTEST STRAND.
            # `m` (>12) is the layer's full extent and is right for the bottom /
            # cut-edge test. It is WRONG for head placement: after the matte was
            # softened on 2026-08-31 so hair stopped being chopped, a single
            # wisp counted as the top of the head and moved head_top by 3px -
            # enough to trip the heads-level assert on CARTHIEF (192 vs 189,
            # tolerance 2). A wisp is not the top of a head; a person levelling
            # these by eye uses the solid mass.
            msolid = _al > 128
            if not msolid.any():
                msolid = m
            yy, xx = np.where(m)
            if top_y is not None:
                # The top of THIS SUBJECT'S head, not the topmost pixel in the
                # layer. CARTHIEF's cut-out also contains the attorney standing
                # behind him; anchoring on the layer's global minimum put the
                # ATTORNEY's head at the target row and pushed the defendant out
                # of frame, so the thumbnail showed the wrong man - while the
                # heads-level assert happily reported delta 0.
                fcx = (fx + fw / 2 - box[0]) * s
                lo = max(0, int(fcx - fw * s * 0.9))
                hi = min(r.width, int(fcx + fw * s * 0.9))
                band = msolid[:, lo:hi]
                by = np.where(band.any(axis=1))[0]
                head = int(by.min()) if by.size else int(np.where(msolid.any(axis=1))[0].min())
                y0 = int(top_y - head)
            else:
                y0 = int(cy - (fy + fh / 2 - box[1]) * s)
            _side_in = False
            for _cl in cliffs:
                _xc = x0 + _cl["column"] * s
                if _cl["side"] == "right" and _xc < W - 1:
                    _side_in = True
                if _cl["side"] == "left" and _xc > 0:
                    _side_in = True
            if y0 + int(yy.max()) >= H and not _side_in:   # no cut edge inside the frame
                break
            s *= 1.03
        if s != s0 or stuck:
            # the growth is a decision, so it is in the log where he can see it
            self.log.setdefault("cut_edge", {})[label] = dict(
                grew=round(s / s0, 3), face_h=int(round(fh * s)), want_h=int(want_h),
                cliffs=cliffs, unresolvable=stuck)
            for _cl in cliffs:
                print(f"  cut-edge  {label:9} {_cl['side']} cliff {_cl['run']}/{_cl['span']} rows"
                      f" -> layer grown x{s / s0:.3f} (face {int(want_h)} -> {int(round(fh * s))} px)"
                      f" so the cut leaves the canvas")
            for _cl in stuck:
                print(f"  cut-edge  {label:9} {_cl['side']} cliff {_cl['run']}/{_cl['span']} rows"
                      f" on the NEAR side of the face - growing cannot push it out; gate K decides")
        # OVERFLOW CLAMP - REMOVED 2026-08-31, it was my regression.
        #
        # The problem it targeted is real: cut() scales a layer so the FACE is
        # want_h px, so a narrow source crop can produce a layer wider than the
        # frame and push a head off the edge. But the fix was wrong twice over.
        # It forced x0 >= 0, and a subject legitimately cropped by the left edge
        # NEEDS a negative x0 - and moving x0 shifts the column band that
        # build() samples to find each head top, which broke the heads-level
        # assert (R38) on a build that had passed minutes earlier.
        #
        # The correct fix is upstream: choose the source CROP so the scaled
        # layer fits, rather than repositioning a layer that is already too big.
        # Left undone deliberately rather than left half-done.
        mask = np.zeros((H, W), np.uint8)
        mh, mw = r.height, r.width
        sy0, sx0 = max(0, y0), max(0, x0)
        sy1, sx1 = min(H, y0 + mh), min(W, x0 + mw)
        al = np.asarray(r.split()[-1])[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        mask[sy0:sy1, sx0:sx1] = al
        rgb = np.zeros((H, W, 3), np.float32)
        rgb[sy0:sy1, sx0:sx1] = np.asarray(r)[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0, :3]
        _sy = np.where((np.asarray(r.split()[-1]) > 128).any(axis=1))[0]
        self.log[label] = dict(face_h=round(fh * s), cx=cx,
                               head_top=int(y0 + int(_sy.min() if _sy.size else yy.min())),
                               bottom=int(y0 + int(yy.max())))
        return rgb, mask.astype(np.float32) / 255.0

    def rim(self, canvas, alpha):
        """A surgical outline: constant width, and it never sits on top of hair.

        The bug this replaces: the ring was built as dilate(alpha) - alpha with a
        SOFT alpha. Dilating soft values blooms, so the rim grew thick exactly
        where the matte is most delicate - the hair - and read as a white blob.

        Two rules make it surgical:
          1. Build the ring from a HARDENED silhouette (alpha > 0.5), so its width
             is the same everywhere regardless of how soft the matte is there.
          2. Multiply the ring by (1 - alpha). Where the subject is partially
             present - every hair strand - the outline fades out instead of
             painting over it.
        """
        a = alpha.astype(np.float32)

        # CLEAN THE SILHOUETTE BEFORE TRACING IT. The rim follows the matte
        # exactly, so every stray hair strand, speck and pinhole becomes a squiggle
        # in the outline - which reads as "scribbled randomly". A person drawing
        # this by hand would trace ONE smooth closed contour, not the noise.
        core8 = (a > 0.5).astype(np.uint8)
        rk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        core8 = cv2.morphologyEx(core8, cv2.MORPH_OPEN, rk)      # drop specks
        core8 = cv2.morphologyEx(core8, cv2.MORPH_CLOSE, rk)     # fill pinholes
        n_, lab_, st_, _ = cv2.connectedComponentsWithStats(core8, 8)
        if n_ > 1:                                               # one body, no fragments
            keep_i = 1 + int(np.argmax(st_[1:, cv2.CC_STAT_AREA]))
            core8 = (lab_ == keep_i).astype(np.uint8)
        from scipy.ndimage import binary_fill_holes
        core8 = binary_fill_holes(core8).astype(np.uint8)
        core8 = cv2.medianBlur(core8 * 255, 9)                   # smooth the contour
        core = (core8 > 127).astype(np.float32)
        self.log.setdefault("rim_cleanup", []).append(
            dict(raw_px=int((a > 0.5).sum()), clean_px=int(core.sum())))
        S = 2
        big = cv2.resize(core, (W * S, H * S), interpolation=cv2.INTER_NEAREST)
        k = np.ones((RIM_PX * S * 2 + 1,) * 2, np.float32)
        ring = cv2.resize(np.clip(cv2.dilate(big, k) - big, 0, 1), (W, H),
                          interpolation=cv2.INTER_AREA)
        ring = cv2.GaussianBlur(ring, (0, 0), 0.6)
        ring = ring * (1.0 - a)                 # never over hair
        _mode = getattr(self, "rim_mode", RIM_MODE)
        if _mode == "none":
            ring = ring * 0.0
        elif _mode == "glow":
            # no hard line at all: only the soft outer lift. Hair has an
            # irregular silhouette and any hard line traces every bump of it.
            ring = ring * 0.0
        elif _mode == "smooth":
            # gate the line by local curvature: keep it where the boundary is
            # smooth (jaw, shoulder, cheek), fade it out where it is ragged (hair)
            cur = cv2.GaussianBlur(core, (0, 0), 9) - core
            rough = np.clip(np.abs(cur) * 3.2, 0, 1)
            rough = cv2.GaussianBlur(rough, (0, 0), 5)
            ring = ring * (1.0 - rough)
        mode = getattr(self, "rim_mode", RIM_MODE)
        glow_amt = getattr(self, "rim_glow", RIM_GLOW)
        ring = np.clip(ring * RIM_STRENGTH, 0, 1)
        canvas = canvas * (1 - ring[..., None]) + 246.0 * ring[..., None]
        # "none" HAS TO MEAN NONE. It used to zero the outline and then apply the
        # outer glow anyway at full RIM_GLOW - so the white halo survived the one
        # setting whose whole purpose was to remove it. Same asymmetry as the
        # title/kicker shadow: the switch covered one of the two things it named.
        if mode == "none" or glow_amt <= 0:
            self.log["rim"] = "off"
            return canvas
        base = np.clip(a + ring, 0, 1)
        core = np.clip(cv2.GaussianBlur(base, (0, 0), RIM_CORE_SIGMA) - base, 0, 1)
        wide = np.clip(cv2.GaussianBlur(base, (0, 0), RIM_WIDE_SIGMA) - base, 0, 1)
        core = core / max(core.max(), 1e-6)
        wide = wide / max(wide.max(), 1e-6)
        outer = (RIM_CORE_MIX * core + (1.0 - RIM_CORE_MIX) * wide)
        outer = np.clip(outer, 0, 1) * (glow_amt * (2.2 if mode == "glow" else 1.0))
        self.log["rim"] = dict(mode=mode, glow=glow_amt,
                               core_sigma=RIM_CORE_SIGMA, wide_sigma=RIM_WIDE_SIGMA,
                               core_mix=RIM_CORE_MIX)
        return 255.0 - (255.0 - canvas) * (255.0 - 250.0 * outer[..., None]) / 255.0

    def glow(self, alpha, spread=13, amount=0.72):
        ring = np.clip(cv2.GaussianBlur(alpha, (0, 0), spread) - alpha, 0, 1)
        return (ring / max(ring.max(), 1e-6)) * amount

    def type_layer(self, base):
        # He asked for it BIGGER - starting near the left edge and almost
        # touching the right. So the width is the driver, not the cap height.
        # The drawing itself lives in thumb_type (2026-09-01): the title and
        # the kicker were two copies of the same code and the type could only
        # change by editing both. `type_style` names the treatment.
        spec = TT.resolve(self.type_style, "title")
        cap = int(0.125 * H)
        x, y = 20, 26
        runs = [(self.white + " ", WHITE_RGB, False), (self.yellow, tuple(self.yellow_rgb), True)]
        lay = TT.fit(spec, runs, cap, W * self.title_frac, 190, x=x, y=y)
        rgba, ink = TT.render_runs(lay, spec, W, H, TT.cap_height(lay.base))
        self.log["type"] = dict(size=lay.size, cap=cap, top=y, lines=1)
        self.log["type_style"] = self.type_style if isinstance(self.type_style, str) else "custom"
        self.log["type_treatment"] = TT.describe(self.type_style)
        return np.asarray(rgba).astype(np.float32), np.asarray(ink) > 40

    def kicker(self, canvas):
        """The 9800's own caption treatment, measured off that file: ALL CAPS,
        golden fill #EDCB09, pure black stroke, cap 0.167 H, sitting low.

        The caps break the Audit sentence-case pattern on purpose - he asked for
        this one in the 9800's exact style, and the 9800 is his own winner.

        Drawn by thumb_type under `type_style`, like the title. The two-colour
        split (Nathan 2026-08-31: "your owner is white and hates you is red")
        is the emphasised run; what the style adds to it (glow, underline,
        panel) is ink here, so the face-clear solve, the bottom clamp and R1
        all see it.
        """
        if not self.kicker_text:
            return np.zeros((H, W, 4), np.float32), np.zeros((H, W), bool)
        spec = TT.resolve(self.type_style, "kicker")
        cap = int(KICKER_CAP * H)
        runs = self._kicker_runs()
        x = int(KICKER_BAND[0] * W)
        lay = TT.fit(spec, runs, cap, W * 0.62, 240, x=x, y=0)
        size = lay.size

        def ink_extent(lay_):
            # (top offset, height) of everything the treatment inks, rel. y
            bb = lay_.ink_bbox(spec["ink_stroke"])
            return bb[1], (bb[3] - bb[1]) + TT.extra_below(spec, TT.cap_height(lay_.base))

        y = int(KICKER_BAND[1] * H) - int(size * 0.18)

        # THE KICKER MUST CLEAR EVERY FACE.
        #
        # Nathan, 2026-08-31: "judge Boyd's head and body is still low with the
        # captions over her face. I've mentioned this fix so many times for
        # different thumbnails but everytime you make one you have the same
        # problems."
        #
        # He is right, and the reason it kept coming back is exact: the TITLE
        # has had an assert since the beginning - `type_on_subject_px == 0`,
        # R1 - and the KICKER never had one. kmask existed only to tell the
        # ARROW where not to go. So one text element was protected by code and
        # the other by him noticing, every single time. (2026-09-01: and the
        # solve below was never measured afterwards either - `ink_vs_subjects`
        # now asserts kicker_on_face_px == 0 at the end of build().)
        #
        # Measured on OFFERUP_v9 before this went in: Boyd's face box overlapped
        # the kicker band by 13,206px - the text sat 62px up into her face.
        #
        # Solved, not just failed: push the kicker below the lowest face, and if
        # that will not fit above the bottom margin, SHRINK it until it does.
        # Failing the build would just move the manual work somewhere else.
        _fb = getattr(self, "_face_bottoms", None)
        if _fb:
            _need = max(_fb) + KICKER_FACE_GAP
            for _ in range(60):
                _h2 = ink_extent(lay)[1]
                if _need + _h2 + KICKER_MARGIN <= H or size <= 30:
                    break
                size -= 2
                lay = TT.Layout(spec, runs, size, x, 0)
            if _need > y:
                self.log["kicker_pushed_below_face"] = dict(
                    from_y=int(y), to_y=int(_need), lowest_face=int(max(_fb)),
                    size=size)
                y = int(_need)
        # CLAMP so the ink - stroke included - cannot run off the bottom edge.
        # Measured 2026-08-29 on CARTHIEF: y=558 with size 139 put 475 gold
        # pixels on the very last row, bottom margin 0. `y` is the TOP of the
        # text box, so a band position alone does not bound the descender.
        # Nathan sees this instantly; the band is a target, the edge is a limit.
        _top, _ink_h = ink_extent(lay)
        _max_y = H - KICKER_MARGIN - _ink_h - _top
        if y > _max_y:
            self.log["kicker_clamped_from"] = y
            y = int(_max_y)
        lay = TT.Layout(spec, runs, size, x, y)
        rgba, ink = TT.render_runs(lay, spec, W, H, TT.cap_height(lay.base))
        if len(runs) == 2:
            self.log["kicker_split"] = dict(head=runs[0][0], tail=runs[1][0],
                                            colors=[list(runs[0][1]), list(runs[1][1])])
        self.log["kicker"] = dict(text=self.kicker_text, size=size, x=x, y=y)
        return np.asarray(rgba).astype(np.float32), np.asarray(ink) > 40

    def arrow_at(self, cx, cy, faces, want=None):
        """Put the arrow exactly at (cx, cy). Warn if it lands on a face; never
        silently move it - he chose this position."""
        ar = self._arrow_img(want)
        aw, ah = ar.width, ar.height
        amask = np.asarray(ar.split()[-1]) > 30
        x0, y0 = int(cx - aw / 2), int(cy - ah / 2)

        # PLACEMENT IS A 2D SEARCH, not a 1D retreat.
        # The retreat version backed off along the pointing axis with a fixed
        # budget, and on three of five builds there was simply no clear spot on
        # that line - it stopped at its budget still sitting on a subject
        # (CARTHIEF 4188px, THOMPSON 5037px). Nathan: "The arrows messed up in
        # every single one."
        #
        # An arrow has two jobs: point at the right thing, and touch nothing.
        # Both are satisfiable almost anywhere in the gap between the subjects,
        # so search that gap in 2D and score candidates instead of walking one
        # line. Ties break toward the requested position, so a hand-placed
        # arrow_xy still wins when it is clear.
        subj = getattr(self, "_subject_alpha", None)
        avoid = getattr(self, "_arrow_avoid", None)
        blocked = None
        if subj is not None:
            blocked = subj > 0.45
        if avoid is not None:
            blocked = avoid if blocked is None else (blocked | avoid)
        # GALLERY FACES ARE A SOFT COST, not a block. A plate full of court
        # strangers is normal (SANCHEZ shipped on 9-12 of them) and blocking
        # them would leave no clear spot; but an arrow whose tip sits on a
        # stranger's head points at HIM. Measured 2026-09-02 on TORRES: the tip
        # landed on the man seated at counsel table between the two subjects.
        # Every small face (below SUBJECT_FACE_MIN_AREA, outside the subject
        # alpha), padded by half its size, costs ARROW_GALLERY_COST per pixel
        # in the search - enough to slide off when a clear spot exists nearby,
        # never enough to push the arrow onto a subject or the type.
        gallery = np.zeros((H, W), bool)
        for (fx, fy, fw, fh) in faces:
            if fw * fh >= SUBJECT_FACE_MIN_AREA:
                continue
            if subj is not None and fh > 0 and fw > 0 and \
                    (subj[fy:fy + fh, fx:fx + fw] > 0.45).mean() > 0.5:
                continue        # a detection on a subject's layer is not gallery
            _px, _py = fw // 2, fh // 2
            gallery[max(0, fy - _py):min(H, fy + fh + _py),
                    max(0, fx - _px):min(W, fx + fw + _px)] = True
        if blocked is not None:
            want_x, want_y = x0, y0
            best = None
            for ty in range(int(H * 0.18), int(H * 0.78), 10):
                for tx in range(int(W * 0.20), int(W * 0.72), 10):
                    if tx + aw > W or ty + ah > H:
                        continue
                    ov = int((amask & blocked[ty:ty + ah, tx:tx + aw]).sum())
                    og = int((amask & gallery[ty:ty + ah, tx:tx + aw]).sum())
                    # distance from where it was asked to go, in arrow-widths
                    d = ((tx - want_x) ** 2 + (ty - want_y) ** 2) ** 0.5 / max(aw, 1)
                    score = ov + og * ARROW_GALLERY_COST + d * ARROW_DRIFT_COST
                    if best is None or score < best[0]:
                        best = (score, tx, ty, ov, d)
            if best:
                _, x0, y0, ov, d = best
                og = int((amask & gallery[y0:y0 + ah, x0:x0 + aw]).sum())
                self.log["arrow_placed"] = dict(on_blocked_px=ov, on_gallery_px=og,
                                                gallery_faces=int(gallery.any()),
                                                drift_arrow_widths=round(d, 2))
        x0 = max(0, min(W - aw, x0))
        y0 = max(0, min(H - ah, y0))
        am = np.zeros((H, W), bool)
        am[y0:y0 + ah, x0:x0 + aw] = amask
        # Count overlap against the SUBJECT faces only. Counting every YuNet hit
        # made this unusable: a blurred background plate yields small spurious
        # detections (a 34x39 blob on MONKEY) and gallery faces, so the number
        # never reached zero no matter where the arrow went. Foreground subject
        # faces are an order of magnitude larger - Boyd 198x264, defendant
        # 190x251, versus 43x46 for the monkey and 34x39 for the artefact.
        on_face = on_any = 0
        for (fx, fy, fw, fh) in faces:
            hit = int(am[max(0, fy):fy + fh, max(0, fx):fx + fw].sum())
            on_any += hit
            if fw * fh >= SUBJECT_FACE_MIN_AREA:
                on_face += hit
        self.log["arrow"] = dict(x=x0, y=y0, w=aw, h=ah,
                                 on_face_px=on_face, on_any_face_px=on_any)
        if on_face:
            print(f"   WARNING arrow covers {on_face}px of a face at his chosen position")
        lay = np.zeros((H, W, 4), np.float32)
        lay[y0:y0 + ah, x0:x0 + aw] = np.asarray(ar).astype(np.float32)
        return lay

    def _arrow_img(self, want=None):
        """De-jag ONLY a low-res source.

        The original asset was 334px with a hard, stair-stepped alpha, so it
        needed supersampling and a median. A high-res asset does not: it is
        already clean (1.1% soft edge at 815px), and running the same median over
        it would round its corners and soften the outline - destroying the very
        crispness that makes it look professional. Downscaling alone antialiases.
        """
        ar = Image.open(self.arrow_png)
        want = want or int(ARROW_W_FRAC * W)
        if ar.width < want * 1.5:
            aa = np.asarray(ar)
            big = cv2.resize(aa, (ar.width * 3, ar.height * 3), interpolation=cv2.INTER_CUBIC)
            alp = cv2.GaussianBlur(cv2.medianBlur(big[..., 3], 5), (0, 0), 2.2)
            ar = Image.fromarray(np.dstack([big[..., :3], alp]))
            self.log["arrow_dejag"] = True
        else:
            self.log["arrow_dejag"] = False
        ar = resize_rgba(ar, (want, int(ar.height * want / ar.width)))
        # Nathan, 2026-08-31: "tip it up on the left to make it look like it's
        # coming kinda from WORST EXCUSE EVER". The arrow points LEFT, so
        # raising its tip is a CLOCKWISE turn; PIL rotates counter-clockwise, so
        # the sign is negated here and `arrow_rot` stays readable in the config
        # as "positive = tip up". BICUBIC with expand keeps the alpha clean -
        # the asset is high-res, and _arrow_img deliberately does not median it.
        if self.arrow_rot:
            ar = ar.rotate(-float(self.arrow_rot), resample=Image.BICUBIC,
                           expand=True)
            self.log["arrow_rot"] = float(self.arrow_rot)
        return ar

    def arrow(self, occupied, faces, target, want=None):
        ar = Image.open(self.arrow_png)
        want = want or int(ARROW_W_FRAC * W)   # 0.230 W, the 9800's own scale
        # De-jag. The extracted asset has a hard alpha (max gradient 181, 34% of
        # it sitting in the top histogram bin), so scaling it straight keeps every
        # stair-step. Supersample 3x, median out the jaggies, feather by half a
        # pixel, then land on the target size.
        aa = np.asarray(ar)
        big = cv2.resize(aa, (ar.width * 3, ar.height * 3), interpolation=cv2.INTER_CUBIC)
        alp = cv2.medianBlur(big[..., 3], 5)
        alp = cv2.GaussianBlur(alp, (0, 0), 2.2)
        ar = Image.fromarray(np.dstack([big[..., :3], alp]))
        ar = resize_rgba(ar, (want, int(ar.height * want / ar.width)))
        # DO NOT recolour it. The asset carries 4,387 distinct colours in its red
        # (R 69-255, std 34.1) with a dark bevelled edge band at (81,10,8) against
        # a (232,6,4) core, and 34% of it is soft antialias. Flattening that to a
        # single RGB is what made it read as dead, cheap and pasted-on. Its red is
        # already the right red - it just also has shading, and the shading is the
        # thing that makes it look real.
        am = cv2.dilate((np.asarray(ar.split()[-1]) > 30).astype(np.float32),
                        np.ones((9, 9), np.float32))
        ov = cv2.matchTemplate(occupied.astype(np.float32), am, cv2.TM_CCORR) / max(am.sum(), 1)
        fm = np.zeros((H, W), np.float32)
        for (x, y, fw, fh) in faces:
            fm[max(0, y):y + fh, max(0, x):x + fw] = 1
        fo = cv2.matchTemplate(fm, am, cv2.TM_CCORR)
        ys, xs = np.mgrid[0:ov.shape[0], 0:ov.shape[1]]
        cost = np.hypot(xs + ar.width * 0.10 - target[0], ys + ar.height * 0.5 - target[1]) + ov * 5000
        cost[ov > 0.02] = 1e9
        cost[fo > 0] = 1e9
        cost[:, :8] = 1e9
        cost[:8, :] = 1e9
        iy, ix = np.unravel_index(np.argmin(cost), cost.shape)
        if cost[iy, ix] > 1e8:
            self.log["arrow"] = "no clear placement"
            return np.zeros((H, W, 4), np.float32)
        lay = np.zeros((H, W, 4), np.float32)
        aw, ah = ar.width, ar.height
        lay[iy:iy + ah, ix:ix + aw] = np.asarray(ar).astype(np.float32)
        self.log["arrow"] = dict(x=int(ix), y=int(iy), w=aw, overlap=round(float(ov[iy, ix]), 4))
        return lay

    def _final_grain(self, canvas):
        """The whole-frame grain layer, applied on BOTH exits of build().

        Nathan: "I meant a layer of grain over the entire thumbnail". It lived
        inline after the arrow paste, and `if not self.arrow_on:` returns
        BEFORE that - so every --no-arrow build saved ungrained. That is the
        iterate-without-the-arrow workflow the skill prescribes, and MONKEY,
        which ships arrowless on purpose, was shipped without it. Measured
        2026-09-02 on CLAYTON: the arrowless build logged no `final_grain`,
        the house-style checklist printed "MISSING grain layer over the whole
        frame", and gate A read flat_g_p90 0.3934 against a 0.30 limit -
        i.e. the preview being judged was a different image from the one that
        would ship. One method, called from both exits, so the two cannot
        drift apart again.
        """
        if FINAL_GRAIN <= 0:
            return canvas
        _rng = np.random.default_rng(11)
        _n = _rng.normal(0.0, FINAL_GRAIN, canvas.shape[:2]).astype(np.float32)
        _y = (canvas * LUMA_W).sum(axis=2) / 255.0
        # midtone-weighted with a floor, so flat black type and paper-white
        # highlights still receive some - a completely ungrained region is
        # the tell this exists to remove
        _w = 0.45 + 0.55 * (4.0 * _y * (1.0 - _y)).clip(0, 1)
        canvas = canvas + (_n * _w)[..., None]
        self.log["final_grain"] = FINAL_GRAIN
        return canvas

    def build(self, out_path):
        # The title is sized by WIDTH (he wants it near edge to edge), so its
        # height is an OUTPUT, not a constant. Subject placement therefore derives
        # from it - a taller title pushes the heads down, it does not overlap them.
        probe = np.zeros((H, W, 3), np.float32)
        _, tmask_probe = self.type_layer(probe)
        ys = np.where(tmask_probe.any(axis=1))[0]
        title_bottom = int(ys.max()) if ys.size else 120
        self.log["title_bottom"] = title_bottom

        # HEADS LEVEL. Both silhouette tops land on the same row, HEAD_GAP
        # below the title. This replaces an 8-pass nudge loop that only pushed
        # subjects down until the HIGHER of the two cleared the title - which
        # left the other one sitting lower by however much their hair differed.
        # R38 / spec 12.10.
        fh_ = self.face_h or FACE_H          # ONE value for both: parity is a rule

        # ---- SOLVE face_h FROM THE VERTICAL BUDGET -------------------------
        # Nathan, 2026-08-31: "go in surgically remove what's causing root
        # problems the correct structural way".
        #
        # THE ROOT PROBLEM, stated exactly. The layout was ~20 independent
        # hand-tuned constants that interact. On this one thumbnail alone I
        # hand-tuned face_h three times (345 -> 296 -> 252), bg_blur three times
        # (1.6 -> 0.8 -> 0.45), def_c/jud_c five times, both crops and the
        # plate - each change breaking something the previous one had fixed.
        # Every "same problem again" this session traces to that: a constant
        # typed by hand where a value should have been derived.
        #
        # face_h is NOT a preference. Three things share 720px and may not
        # touch: the title, the two faces, and the kicker. So:
        #
        #     available = kicker_ink_top - title_bottom - HEAD_GAP
        #     face_h    = available / (1 + tallest_hair_ratio)
        #
        # where hair_ratio is how much silhouette each subject carries ABOVE
        # their face box, measured from their own cut-out - which is exactly
        # why Boyd kept ending up low: her bob is tall, so at a shared face_h
        # her FACE sits lower than his even with their heads level.
        #
        # Opt-in per case so approved builds do not silently change.
        if self.solve_face_h:
            _kick_h = self._kicker_ink_height()
            _avail = (H - KICKER_MARGIN - _kick_h - KICKER_FACE_GAP) \
                - (title_bottom + HEAD_GAP)
            _hair = []
            for _png, _fb in ((self.judge_src, self.judge_face),
                              (self.defendant_png, self.defendant_face)):
                _hair.append(self._hair_ratio(_png, _fb))
            _solved = int(_avail / (1.0 + max(_hair)))
            self.log["face_h_solved"] = dict(
                available_px=int(_avail), kicker_ink=int(_kick_h),
                hair_ratios=[round(h, 3) for h in _hair],
                solved=_solved, was=int(fh_))
            fh_ = max(180, min(fh_, _solved))
        dc = self.def_c or DEF_C
        jc = self.jud_c or JUD_C
        head_top = title_bottom + HEAD_GAP
        # R38 (heads level) RELAXED BY AN EXPLICIT OFFSET, not deleted.
        # Nathan asked for Boyd higher three separate times on 2026-08-31, and
        # R38 - also his rule - pins her head top to the defendant's. Newest
        # instruction wins, but the older rule is superseded VISIBLY: the offset
        # is a number in the config and the assert below still holds to within
        # it, so an accidental 400px drift is still caught.
        jrgb, jal = self.cut(self.judge_src, self.judge_face, fh_,
                             jc[0], jc[1], "boyd",
                             top_y=head_top + self.judge_head_dy)
        # Nathan, 2026-08-31: "bring up and scoot back the defendant just a tad".
        # UP is negative y, BACK is away from centre - he sits on the left, so
        # back is negative x. Applied to the SOLVED position rather than
        # replacing the solver, so heads-level (R38) still holds within its
        # tolerance and the nudge is visibly a nudge.
        _ddx, _ddy = getattr(self, "defendant_nudge", (0, 0))
        # DEFENDANT SCALE. cut() sizes a layer so its detected FACE becomes
        # fh_, which keeps two people at parity - correct for two people, wrong
        # for a substituted prop. MONKEY replaces the defendant with a cut-out
        # spider monkey whose face is a much larger share of its silhouette, so
        # face-parity renders the whole animal small. Nathan: "make the monkey
        # bigger". A per-case multiplier, applied only where a substitution is
        # in play.
        _dsc = float(getattr(self, "defendant_scale", 1.0))
        drgb, dal = self.cut(self.defendant_png, self.defendant_face,
                             int(fh_ * _dsc),
                             dc[0] + _ddx, dc[1] + _ddy, "defendant",
                             top_y=head_top + _ddy)
        if _dsc != 1.0:
            self.log["defendant_scale"] = _dsc
        if _ddx or _ddy:
            self.log["defendant_nudge"] = dict(dx=_ddx, dy=_ddy)
        tops = {}
        for al, k, ctr in ((jal, "boyd", jc[0]), (dal, "defendant", dc[0])):
            band = (al > 0.4)[:, max(0, ctr - 150):min(W, ctr + 150)]
            r = np.where(band.any(axis=1))[0]
            tops[k] = int(r.min()) if r.size else -1
        self.log["head_tops"] = tops
        self.log["head_top_delta"] = abs(tops["boyd"] - tops["defendant"])
        # SOLO. Nathan, 2026-08-31: "now it looks just a like but too cluttered".
        #
        # Both complaints have one cause and one fix. "Looks alike" is the
        # measured template problem - every thumbnail on this channel is
        # defendant-left / Boyd-right, and our own set scores 0.32 layout
        # self-similarity against the competitor set's 0.09. "Cluttered" is five
        # elements competing: two faces, the prop, its circle, and the headline.
        #
        # Dropping one subject fixes both at once. It is the only change here
        # that alters the LAYOUT rather than the parameters, and parameters were
        # not what he was objecting to.
        #
        # R38 (heads level) is not violated - it is INAPPLICABLE with one head,
        # so the assert is skipped rather than weakened.
        if getattr(self, "solo", False):
            dal = np.zeros_like(dal)
            self.log["solo"] = "defendant layer dropped - single subject layout"
        else:
            assert self.log["head_top_delta"] <= 2 + abs(self.judge_head_dy), (
                f"heads not level: {tops} - he has asked for this explicitly")

        # Now that both cut-outs exist, solve a crop that hides everything the
        # plate must not show underneath them.
        subject_cover = (jal > 0.4) | (dal > 0.4)
        self.solve_crop(self.cover_masks, subject_cover)
        bg = self.background()

        # each subject graded ONCE, to a face target, on its own pixels only
        # Balance the two subjects to the MIDPOINT of their own skin saturation.
        # "boyd is a little too colorful and defendant is a little too washed -
        # make the colors meet in the middle." Measured on the FACE, because that
        # is what the eye judges; a whole-silhouette mean is dominated by a black
        # robe and a set of scrubs and says nothing about skin.
        def face_sat(rgb, al, fbox):
            u = np.clip(rgb, 0, 255).astype(np.uint8)
            x, y, fw, fh = fbox
            m = np.zeros(al.shape, bool)
            m[max(0, y):y + fh, max(0, x):x + fw] = True
            m &= (al > 0.5)
            if m.sum() < 300:
                m = al > 0.5
            return float(cv2.cvtColor(u, cv2.COLOR_RGB2HSV)[..., 1][m].mean()), m

        # DETECT the face in each layer. Estimating a box from the matte put
        # Boyd's "face" on her black robe and reported her skin at S 33.9 when it
        # is really 88.1 - which inverted the balance and washed the defendant
        # further instead of meeting in the middle.
        boxes = {}
        for rgb, al, key in ((jrgb, jal, "boyd"), (drgb, dal, "defendant")):
            # In solo mode the defendant alpha is all zeros, so np.where finds
            # nothing and xs_.mean() is NaN. Skip him rather than fabricate a box.
            if not (al > 0.5).any():
                continue
            u = np.clip(rgb, 0, 255).astype(np.uint8)
            u = (u * (al[..., None] > 0.5)).astype(np.uint8)
            det = faces_in(u)
            if det:
                boxes[key] = max(det, key=lambda t: t[2] * t[3])
            else:
                ys_, xs_ = np.where(al > 0.5)
                boxes[key] = (int(xs_.mean()) - 110, int(ys_.min()) + 40, 220, 240)
            self.log.setdefault(key, {})["face_box"] = list(boxes[key])
            # this layer's OWN skin chroma before any grade touches it - the
            # reference the final skin stage keeps each face's offset from
            # (see SKIN_CHROMA_TARGET: a shared LIFT, not a shared destination)
            _sx, _sy, _sw, _sh = boxes[key]
            _fu = np.clip(rgb, 0, 255).astype(np.uint8)[max(0, _sy):_sy + _sh, max(0, _sx):_sx + _sw]
            if _fu.size:
                _fy = cv2.cvtColor(_fu, cv2.COLOR_RGB2YCrCb)
                _fm = ((_fy[..., 1] > 135) & (_fy[..., 1] < 180)
                       & (_fy[..., 2] > 85) & (_fy[..., 2] < 135))
                if _fm.sum() >= 300:
                    _fl = cv2.cvtColor(_fu, cv2.COLOR_RGB2LAB).astype(np.float32)
                    _src_chroma = getattr(self, "_src_chroma", {})
                    _src_chroma[key] = float(np.sqrt((_fl[..., 1][_fm] - 128.0) ** 2
                                                     + (_fl[..., 2][_fm] - 128.0) ** 2).mean())
                    self._src_chroma = _src_chroma

        # Skin balance needs TWO faces to find a midpoint between. With one
        # subject there is nothing to balance against, so the stage is skipped
        # rather than run against a fabricated second face.
        if "defendant" in boxes:
            s_j, mj = face_sat(jrgb, jal, boxes["boyd"])
            s_d, md = face_sat(drgb, dal, boxes["defendant"])
            # PARTIAL PULL, not parity. Measured on OFFERUP v19: forcing both
            # faces onto one saturation midpoint dragged Boyd from S 44.5 up to
            # 57.0 and the defendant from 69.5 down to 57.0. Against her own
            # source crop that pushed her skin a* from +9.5 to +15.9 while his
            # moved only +9.1 -> +11.4, which is the "weird and un natural"
            # colour he pointed at - she was reddened almost 3x as hard as him.
            #
            # Equal BRIGHTNESS between the two is his standing rule and stays.
            # Equal SATURATION is not the same thing and was never asked for:
            # two different people under different light genuinely have
            # different skin chroma, and forcing them equal repaints one of
            # them. Pull each only part of the way, so a real mismatch still
            # closes most of the way without either face leaving its own tone.
            mid_true = (s_j + s_d) / 2.0
            mid = None  # set per face below
            self.log["skin_sat_pull"] = SKIN_SAT_PULL
            sat_goal = {"boyd": s_j + (mid_true - s_j) * SKIN_SAT_PULL,
                        "defendant": s_d + (mid_true - s_d) * SKIN_SAT_PULL}
            self.log["skin_balance"] = dict(boyd=round(s_j, 1), defendant=round(s_d, 1),
                                            midpoint=round(mid_true, 1),
                                            pull=SKIN_SAT_PULL,
                                            goal={k: round(v, 1) for k, v in sat_goal.items()})
        else:
            s_j, mj = face_sat(jrgb, jal, boxes["boyd"])
            s_d, md = s_j, None
            sat_goal = {"boyd": s_j, "defendant": s_j}
            self.log["skin_balance"] = "solo - single subject, nothing to balance"

        # ---- FACE BRIGHTNESS: match them to each other, not to a constant ----
        # His rule, stated 2026-08-29: "you're supposed to have the defendant as
        # bright as the judge." A fixed FACE_L_TARGET cannot deliver that - the
        # two layers arrive at different exposures, and a partial (0.45) pull
        # toward a constant leaves whatever gap it started with. Measured on
        # MONKEY: Grant 141 vs Boyd 117 one way, then 94 vs 116 the other.
        # So: measure BOTH faces, take the midpoint, and bring both fully to it,
        # exactly as the saturation balance already does.
        #
        # LUMINANCE ONLY. An RGB multiply for brightness once took her skin from
        # S 86.3 to 16.6 (spec 8.4), so this scales L* in Lab and leaves a*/b*.
        face_L = {}
        for rgb, al, m, key in ((jrgb, jal, mj, "boyd"), (drgb, dal, md, "defendant")):
            lm = m if m.sum() > 300 else (al > 0.5)
            u = np.clip(rgb, 0, 255).astype(np.uint8)
            face_L[key] = float(np.median(cv2.cvtColor(u, cv2.COLOR_RGB2LAB)[..., 0][lm]))
        # Nathan, 2026-08-31: "Brighten his face up a bit make it look more
        # natural". The midpoint rule stays - both faces still land on the SAME
        # value, because "as bright as the judge" is his older and still-standing
        # rule - but the window that midpoint is clipped into can be raised per
        # build. Raising only the defendant would re-open the parity defect this
        # code was written to close.
        _tgt = float(self.face_l_target or FACE_L_TARGET)
        midL = float(np.clip((face_L["boyd"] + face_L["defendant"]) / 2.0,
                             _tgt - 18, _tgt + 18))
        # PER-FACE TRIM around the shared midpoint. Nathan, 2026-08-31, in two
        # consecutive messages: "defendants face is still dark, or toned down"
        # and "Boyd slightly looks overly bright".
        #
        # Both are true at once, and that is the parity rule overcorrecting.
        # Forcing both faces to the SAME measured L* was written to fix him
        # rendering darker than her - but equal L* is not equal PERCEIVED
        # brightness when one face is lit and the other is in shadow. So the
        # midpoint stays (they remain balanced against each other, which is the
        # older standing rule) and each face gets an explicit trim off it.
        _bias = self.face_l_bias or {}
        self.log["face_L_balance"] = dict(boyd=round(face_L["boyd"], 1),
                                          defendant=round(face_L["defendant"], 1),
                                          midpoint=round(midL, 1),
                                          pull=FACE_L_PULL, bias=_bias)

        for rgb, al, m, key in ((jrgb, jal, mj, "boyd"), (drgb, dal, md, "defendant")):
            sel = al > 0.5
            if sel.sum() > 500:
                lm = m if m.sum() > 300 else sel
                _cur0 = face_L[key]
                _goal = (_cur0 + (midL - _cur0) * FACE_L_PULL
                         + float(_bias.get(key, 0.0)))
                for _ in range(12):
                    u = np.clip(rgb, 0, 255).astype(np.uint8)
                    lab = cv2.cvtColor(u, cv2.COLOR_RGB2LAB).astype(np.float32)
                    cur = float(np.median(lab[..., 0][lm]))
                    if abs(cur - _goal) < 0.8:
                        break
                    lab[..., 0] = np.clip(lab[..., 0] * (_goal / max(cur, 1e-3)), 0, 255)
                    rgb[:] = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32)
                for _ in range(14):
                    u = np.clip(rgb, 0, 255).astype(np.uint8)
                    S = float(cv2.cvtColor(u, cv2.COLOR_RGB2HSV)[..., 1][m].mean())
                    _sg = sat_goal.get(key, S)
                    if abs(S - _sg) < 1.0:
                        break
                    k = float(np.clip(1.0 + (_sg - S) / 150.0, 0.90, 1.12))
                    rgb[:] = sat_scale(rgb, k)
                self.log[key]["L_before"] = round(face_L[key], 1)
                self.log[key]["skin_S"] = round(S, 1)

        # ---- PHOTO layers only ------------------------------------------------
        canvas = bg.copy()
        for rgb, al in ((drgb, dal), (jrgb, jal)):
            canvas = self.rim(canvas, al)
            canvas = canvas * (1 - al[..., None]) + rgb * al[..., None]
        # Dump each subject's alpha IN CANVAS SPACE. verify_build's rim gate
        # needs the edge where the subject actually sits; its first version
        # rescaled the layer-space matte onto the canvas, which put the "edge
        # band" over unrelated pixels and read ~0.20 on a good build and a bad
        # one alike. Cheap to write, and it makes that gate exact.
        # The arrow needs to know where the SUBJECTS are, not just their faces.
        self._subject_alpha = np.maximum(np.clip(dal, 0, 1), np.clip(jal, 0, 1))
        # kept SEPARATELY too: a correction pooled across both subjects clamps
        # their MEAN, so a hot face hides behind a cool one and stays over the
        # ceiling (SANCHEZ: pooled mean landed at 18.0 while one face sat at
        # 21.1). Anything per-person has to be computed per-person.
        self._alpha_by = dict(defendant=np.clip(dal, 0, 1), boyd=np.clip(jal, 0, 1))
        _dbg = getattr(self, "debug_dir", None)
        if _dbg:
            for _al, _k in ((dal, "defendant"), (jal, "judge")):
                Image.fromarray((np.clip(_al, 0, 1) * 255).astype(np.uint8)).save(
                    os.path.join(_dbg, f"_placed_alpha_{_k}.png"))
            # the defendant's RGB layer BEFORE the judge covers it, so gate L
            # (bystander behind the judge) reads the un-occluded layer instead
            # of the final JPEG - a bystander hidden by Boyd is still in the
            # matte and still ships when the layout moves.
            cv2.imwrite(os.path.join(_dbg, "_placed_rgb_defendant.png"),
                        cv2.cvtColor(np.clip(drgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))

        # ---- FRAMING REPORT: where each subject actually sits -------------------
        # No gate measured this, which is how Boyd rendered at 453px instead of
        # 300 and both heads left the frame while gates A, C and D all passed.
        # A head cropped by the top edge is the single most obvious "slop" tell.
        fr = {}
        for al, key in ((dal, "defendant"), (jal, "boyd")):
            ys, xs = np.where(al > 0.4)
            if not ys.size:
                continue
            fr[key] = dict(top=int(ys.min()), bottom=int(ys.max()),
                           left=int(xs.min()), right=int(xs.max()),
                           touches_top=bool(ys.min() <= 1),
                           head_px_above_frame=0)
            # how much of the head would sit above y=0 if it were not clipped:
            # a silhouette that starts hard at row 0 with a wide run is cropped.
            if ys.min() <= 1:
                width_at_top = int((al[0] > 0.4).sum())
                fr[key]["head_px_above_frame"] = width_at_top
        self.log["framing"] = fr
        clipped = [k for k, v in fr.items() if v["touches_top"]]
        self.log["heads_clipped_by_top_edge"] = clipped

        # ---- optional THIRD element (a prop, not a person) ---------------------
        # MONKEY, 2026-08-29: "Cut out the monkey put him in the thumbnail and
        # point the arrow at him." The subject of that hearing is an animal, so
        # the object the judge is asking about belongs in the frame. It is
        # composited HERE, with the photo layers, so it takes the same look pass
        # and grain - a prop pasted after finishing reads as a sticker.
        # It gets the same rim so it separates from the plate like a subject.
        self.extra_alpha = None
        if getattr(self, "extra", None):
            e = self.extra
            src = Image.open(e["png"]).convert("RGBA")
            eh = int(e.get("h", 300))
            ew = max(1, int(src.size[0] * eh / src.size[1]))
            ex = np.asarray(resize_rgba(src, (ew, eh)))   # RGB and alpha SEPARATELY
            erg = ex[..., :3].astype(np.float32)
            eal = ex[..., 3].astype(np.float32) / 255.0
            cx, cy = int(e.get("cx", W // 2)), int(e.get("cy", H // 2))
            x0, y0 = cx - ew // 2, cy - eh // 2
            lrgb = np.zeros((H, W, 3), np.float32)
            lal = np.zeros((H, W), np.float32)
            sx0, sy0 = max(0, x0), max(0, y0)
            sx1, sy1 = min(W, x0 + ew), min(H, y0 + eh)
            if sx1 > sx0 and sy1 > sy0:
                lrgb[sy0:sy1, sx0:sx1] = erg[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
                lal[sy0:sy1, sx0:sx1] = eal[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
            # GLOW. "make the spider monkey more seen ... more noticeable and
            # attention grabbing in a professional thumbnail style". A prop
            # sitting between two large faces loses the eye; a soft halo behind
            # it separates it from the plate without touching the subjects.
            # SPOTLIGHT. A light halo cannot separate a prop from a bright
            # courtroom - white on white reads as nothing. Darkening the plate
            # locally around it does, and it is the house rule already: "darker"
            # always means LOCAL, around the subjects (spec 4.1). Dark pool
            # behind, lit subject in front - that is the separation.
            sp = e.get("spotlight", 0)
            if sp:
                yy0, xx0 = np.mgrid[0:H, 0:W]
                d2 = ((xx0 - cx) / float(sp)) ** 2 + ((yy0 - cy) / float(sp * 0.78)) ** 2
                pool = np.exp(-d2 * 1.6).astype(np.float32)
                pool *= e.get("spotlight_strength", 0.55)
                pool *= (1 - lal)                      # never darken the prop
                canvas = canvas * (1 - pool[..., None] * 0.85)
                self.log.setdefault("extra_spotlight", {}).update(
                    radius=sp, strength=e.get("spotlight_strength", 0.55))
            g = e.get("glow", 0)
            if g:
                k = int(g) | 1
                halo = cv2.GaussianBlur((lal * 255).astype(np.uint8), (k, k), 0)
                halo = np.clip(halo.astype(np.float32) / 255.0 * e.get("glow_gain", 1.9), 0, 1)
                halo *= (1 - lal)          # only outside the prop itself
                gc = np.array(e.get("glow_rgb", (255, 244, 214)), np.float32)
                canvas = canvas * (1 - halo[..., None]) + gc * halo[..., None]
                self.log.setdefault("extra_glow", {}).update(
                    radius=k, gain=e.get("glow_gain", 1.9), px=int((halo > 0.05).sum()))
            if e.get("rim", True):
                canvas = self.rim(canvas, lal)
            canvas = canvas * (1 - lal[..., None]) + lrgb * lal[..., None]
            self.extra_alpha = lal
            self.log["extra"] = dict(png=os.path.basename(e["png"]), h=eh, w=ew,
                                     cx=cx, cy=cy, px=int((lal > 0.4).sum()))

        # ---- photo finishing: look pass, then grain. GRAPHICS ARE NOT HERE ----
        # Previously the type, kicker and arrow were composited BEFORE this, so the
        # unsharp mask was sharpening antialiased letterforms into crunchy edges and
        # the grain was speckling the glyphs. That is the "processed / heavy / not
        # HD" type and a good part of the jagged arrow. Photo gets finished; vector
        # goes on top of a finished photo, clean.
        blur = cv2.GaussianBlur(canvas, (0, 0), 1.5)
        canvas = canvas + (canvas - blur) * LOOK["definition"]
        for _ in range(20):
            u = np.clip(canvas, 0, 255).astype(np.uint8)
            gg = cv2.cvtColor(u, cv2.COLOR_RGB2GRAY)
            mu, sd = float(gg.mean()), float(gg.std())
            if abs(mu - LOOK["luma"]) < 0.8 and abs(sd - LOOK["sd"]) < 0.8:
                break
            k = float(np.clip((LOOK["sd"] / max(sd, 1e-3)) ** 0.6, 0.94, 1.08))
            canvas = (canvas - mu) * k + mu
            u = np.clip(canvas, 0, 255).astype(np.uint8)
            canvas *= (LOOK["luma"] / max(cv2.cvtColor(u, cv2.COLOR_RGB2GRAY).mean(), 1e-3)) ** 0.55
        canvas = sat_scale(canvas, SAT_TRIM)
        g2 = cv2.cvtColor(np.clip(canvas, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        self.log["look"] = dict(luma=round(float(g2.mean()), 1), sd=round(float(g2.std()), 1))

        # ---- DODGE & BURN, the move that actually makes a face pop ----------
        # Every practitioner source in the 2026 craft study named this
        # independently, and we had none of it. Their paint map, applied here
        # with landmarks instead of a brush:
        #   DODGE  nose bridge, centre forehead, cheekbones, under-eyes, chin
        #   BURN   sides of the face, jawline, temples, edge of the hair
        # Their stated purpose - "pull the attention towards the middle" - is
        # exactly what "the subjects don't pop" was asking for. Kept gentle;
        # every source finishes by pulling the layer back to ~65-70% opacity.
        try:
            import expression as _X
            _u8 = np.clip(canvas, 0, 255).astype(np.uint8)
            _clipped = 0.0
            for _f in _X.blendshapes(cv2.cvtColor(_u8, cv2.COLOR_RGB2BGR)):
                _bx, _by, _bw, _bh = [int(v) for v in _f["box"]]
                if _bw * _bh < 12000:
                    continue                      # background faces stay alone
                _cx, _cy = _bx + _bw / 2.0, _by + _bh / 2.0
                _yy, _xx = np.mgrid[0:H, 0:W]
                # centre-weighted ellipse over the face: >0 lifts, <0 deepens
                _r = (((_xx - _cx) / (_bw * 0.42)) ** 2 +
                      ((_yy - _cy) / (_bh * 0.50)) ** 2)
                _core = np.clip(1.0 - _r, 0, 1)                 # T-zone
                _edge = np.clip(_r - 1.0, 0, 1) * np.clip(2.0 - _r, 0, 1)
                _dodge = _core * DB_DODGE
                _burn = _edge * DB_BURN
                _m = (getattr(self, "_subject_alpha", np.ones((H, W))) > 0.5)
                _amt = np.where(_m, _dodge - _burn, 0.0).astype(np.float32)
                _amt = cv2.GaussianBlur(_amt, (0, 0), max(_bw, _bh) * 0.06)
                # headroom limit - see DB_DODGE_CEILING. Only the POSITIVE
                # (dodge) side is limited; the burn is unbounded downward and
                # cannot clip to white. The limit is a smooth function of the
                # luma already under the brush, so it does not put an edge
                # back into the blurred map.
                _yl = (canvas * LUMA_W).sum(axis=2)
                _head = np.clip(DB_DODGE_CEILING / np.maximum(_yl, 1.0) - 1.0,
                                0.0, None).astype(np.float32)
                _clipped = float((_amt > _head).mean())
                _amt = np.where(_amt > 0, np.minimum(_amt, _head), _amt)
                canvas = canvas * (1.0 + _amt[..., None])
            self.log["dodge_burn"] = dict(dodge=DB_DODGE, burn=DB_BURN,
                                          ceiling=DB_DODGE_CEILING,
                                          limited_px_frac=round(_clipped, 4))
        except Exception as _e:
            self.log["dodge_burn"] = f"skipped: {_e}"

        # ---- SUBJECT FINISH: runs AFTER the look grade, deliberately --------
        # ROOT CAUSE OF A WHOLE CLASS OF BUG. Corrections were being applied to
        # the LAYERS and then silently undone by the global grade that follows.
        # Measured twice on 2026-08-31:
        #   * a white-balance pass was normalised straight back out by grade_to
        #   * a skin-chroma ceiling left the layers at 14.8/16.5, and the
        #     finished JPEG measured 22.2/20.4 - the LOOK contrast/saturation
        #     pass had reinflated it
        # So anything that must be TRUE OF THE FINISHED IMAGE has to run here,
        # after every global operation, not upstream of them.
        _sa = getattr(self, "_subject_alpha", None)
        if _sa is not None:
            _m = _sa > 0.5
            if _m.sum() > 500:
                # (a) highlight shoulder - stop faces clipping to paper white.
                # Nathan: "There's still harsh white lighting on faces".
                # Measured before this: every face clipped to L*255, up to 30.5%
                # of one face above L*210. The identical shoulder had existed on
                # the BACKGROUND layer only.
                # CLAMP FIRST. The ratio below is computed from the CLIPPED
                # gray and was applied to the UNCLIPPED float canvas, so any
                # pixel the earlier multiplies had pushed past 255 survived
                # the shoulder: gray reads 255, the ratio is 201/255 = 0.788,
                # and 0.788 of a float 320 is still 252 - paper white. That is
                # why gate J kept failing on CLAYTON with the shoulder in
                # place (16.4% of Boyd's face over L*210 while her own layer
                # was 3.0%), and why turning face_l_bias could not fix it.
                canvas = np.clip(canvas, 0, 255)
                _u = canvas.astype(np.uint8)
                _g = cv2.cvtColor(_u, cv2.COLOR_RGB2GRAY).astype(np.float32)
                _t = np.where(_g > SUBJ_SHOULDER,
                              SUBJ_SHOULDER + (_g - SUBJ_SHOULDER) * SUBJ_SHOULDER_K, _g)
                _r = np.where(_m, _t / np.maximum(_g, 1e-3), 1.0)
                canvas = canvas * _r[..., None]

                # (b) skin brought TO the corpus target, per subject, both
                # directions - lifted if dull, pulled back if hot, and left
                # alone inside the dead-band.
                # MEASURE ON THE FACE, not the whole silhouette. Measured
                # across the full subject alpha the defendant read chroma 26.6
                # (hands, neck, forearms, jumpsuit spill) while his FACE was
                # 15.5 - so the correction was solving for a region nobody
                # looks at and left the face pale. The face is what he judges.
                _fb = {}
                try:
                    _u0 = np.clip(canvas, 0, 255).astype(np.uint8)
                    _dt = cv2.FaceDetectorYN.create(os.path.join(ROOT, "models", "yunet2023.onnx"), "", (W, H), 0.6, 0.3, 5000)
                    _dt.setInputSize((W, H))
                    _, _rr = _dt.detect(cv2.cvtColor(_u0, cv2.COLOR_RGB2BGR))
                    if _rr is not None:
                        for _row in sorted(_rr, key=lambda q: -q[3])[:2]:
                            _x, _y, _w2, _h2 = [int(v) for v in _row[:4]]
                            _box = np.zeros((H, W), bool)
                            _box[max(0, _y):_y + _h2, max(0, _x):_x + _w2] = True
                            _fb[("defendant" if _x + _w2 / 2 < W / 2 else "boyd")] = _box
                except Exception:
                    _fb = {}
                # A SHARED LIFT, NOT A SHARED DESTINATION. Driving both faces
                # to the same chroma number repaints whichever started further
                # from it harder, and verify_build gate F (his "weird and un
                # natural" Boyd) refuses exactly that. Measured 2026-09-02 on
                # TORRES: sources 12.3 (Boyd) / 16.5 (defendant), both pushed
                # to 20.6 -> drift 7.5 vs 3.4, imbalance 4.1, refused; THOMPSON
                # had passed at 2.4 only because its two sources happened to
                # sit close. The two rules are jointly satisfiable: the PAIR's
                # mean lands on his target and each face keeps its own offset
                # from that mean, so both move by the same amount. Solo keeps
                # the target itself.
                _src = getattr(self, "_src_chroma", {})
                _both = [k for k in ("boyd", "defendant") if k in _src]
                _lift = (SKIN_CHROMA_TARGET - float(np.mean([_src[k] for k in _both]))
                         if len(_both) == 2 else None)
                if _lift is not None:
                    self.log["skin_chroma_lift"] = dict(
                        source={k: round(_src[k], 1) for k in _both}, lift=round(_lift, 1),
                        goal={k: round(_src[k] + _lift, 1) for k in _both})
                for _key, _pa in getattr(self, "_alpha_by", {}).items():
                    _pm = (_pa > 0.5)
                    if _key in _fb:
                        _pm = _pm & _fb[_key]
                    if _pm.sum() < 500:
                        continue
                    _goal_ch = (_src[_key] + _lift) if (_lift is not None and _key in _src) else SKIN_CHROMA_TARGET
                    _u = np.clip(canvas, 0, 255).astype(np.uint8)
                    _ycc = cv2.cvtColor(_u, cv2.COLOR_RGB2YCrCb)
                    _Cr = _ycc[..., 1].astype(np.int16); _Cb = _ycc[..., 2].astype(np.int16)
                    _skin = _pm & (_Cr > 135) & (_Cr < 180) & (_Cb > 85) & (_Cb < 135)
                    if _skin.sum() < 300:
                        continue
                    _lab = cv2.cvtColor(_u, cv2.COLOR_RGB2LAB).astype(np.float32)
                    _a = _lab[..., 1] - 128.0
                    _b = _lab[..., 2] - 128.0
                    _ch = float(np.sqrt(_a[_skin] ** 2 + _b[_skin] ** 2).mean())
                    _sl = float(_lab[..., 0][_skin].mean())
                    # measured on the face, applied to all of that subject's
                    # skin so the neck and hands do not end up a different colour
                    _paint = ((_pa > 0.5) & (_Cr > 135) & (_Cr < 180)
                              & (_Cb > 85) & (_Cb < 135))
                    _soft = cv2.GaussianBlur(_paint.astype(np.float32), (0, 0), 6.0)
                    if abs(_ch - _goal_ch) > SKIN_CHROMA_BAND:
                        _kc = float(np.clip(_goal_ch / max(_ch, 1e-3), 0.6, 1.6))
                        _w = 1.0 + (_kc - 1.0) * _soft
                        _lab[..., 1] = 128.0 + _a * _w
                        _lab[..., 2] = 128.0 + _b * _w
                    if abs(_sl - SKIN_L_TARGET) > SKIN_L_BAND:
                        _kl = float(np.clip(SKIN_L_TARGET / max(_sl, 1e-3), 0.80, 1.20))
                        _lab[..., 0] = np.clip(_lab[..., 0] * (1.0 + (_kl - 1.0) * _soft), 0, 255)
                    canvas = cv2.cvtColor(np.clip(_lab, 0, 255).astype(np.uint8),
                                          cv2.COLOR_LAB2RGB).astype(np.float32)
                    self.log.setdefault("skin_final", {})[_key] = dict(
                        L=round(_sl, 1), chroma=round(_ch, 1), chroma_goal=round(_goal_ch, 1))

        # ---- SEPARATION SOLVE: LAST, after every subject operation ----------
        # Third time this exact ordering mistake has bitten today. Placed before
        # the dodge/burn and highlight shoulder, it solved for a subject
        # luminance that those steps then changed underneath it - MONKEY went
        # +17.0 -> +1.5 because the shoulder pulled the subject highlights down
        # after the plate had already been set. Anything that must be TRUE OF
        # THE FINISHED IMAGE runs at the end.
        # A fixed BG_TARGET cannot deliver a fixed separation - the calibration
        # measured per-case solved plate values spanning 76-101, and at a single
        # constant the composite dL ran +28.7 / -5.9 / +12.8 / +17.0 / +5.7
        # across the five. Two of them still had the background BRIGHTER than
        # the people, which is the "subjects don't pop" defect.
        # So the plate is graded to whatever puts it SEPARATION_DL below the
        # subjects as actually composited. Target is the style-2 corpus median.
        _sa0 = getattr(self, "_subject_alpha", None)
        if _sa0 is not None:
            _sm = _sa0 > 0.5
            _bm = _sa0 < 0.15
            if _sm.sum() > 500 and _bm.sum() > 500:
                _u = np.clip(canvas, 0, 255).astype(np.uint8)
                _L = cv2.cvtColor(_u, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
                _sL = float(_L[_sm].mean()); _bL = float(_L[_bm].mean())
                _want = _sL - SEPARATION_DL
                if _bL > 1.0:
                    _k = float(np.clip(_want / _bL, 0.55, 1.35))
                    _sc = np.where(_bm, _k, 1.0).astype(np.float32)
                    _sc = cv2.GaussianBlur(_sc, (0, 0), 3.0)
                    canvas = canvas * _sc[..., None]
                    self.log["separation_solve"] = dict(
                        subject_L=round(_sL, 1), was=round(_bL, 1),
                        target=round(_want, 1), k=round(_k, 3))

        if GRAIN > 0:
            rng = np.random.default_rng(7)
            n = rng.normal(0.0, GRAIN, canvas.shape[:2]).astype(np.float32)
            y = (canvas * LUMA_W).sum(axis=2) / 255.0
            # Midtone-weighted, but with a floor. Pure weighting is ZERO at white,
            # which left the new crisp rim (a 252-value band) completely ungrained
            # and reading as a long flat line - flat_g_p90 0.045 -> 0.45.
            w = 0.35 + 0.65 * (4.0 * y * (1.0 - y)).clip(0, 1)
            canvas = canvas + (n * w)[..., None]
            self.log["grain"] = GRAIN

        # Gate A measures PHOTOGRAPHIC posterisation, so it is measured HERE - on
        # the finished photo, before any vector art. Type, kicker and arrow are
        # deliberately flat; grading them as though they were photo is why the
        # number jumped 0.045 -> 0.446 the moment graphics stopped being grained.
        # (Grain over the glyphs was hiding them from the metric, not fixing them.)
        # Saved as JPEG at the SAME quality and subsampling as the deliverable.
        # A PNG has no compression noise, and that noise is what breaks up flat
        # areas - measuring a PNG against JPEG-derived thresholds is the quant
        # table trap, and it reads 0.50 where the same pixels as JPEG read 0.05.
        Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).save(
            os.path.splitext(out_path)[0] + ".photo.jpg", quality=95, subsampling=0)

        # ---- GRAPHICS, on a finished photo, untouched afterwards --------------
        tl, tmask = self.type_layer(canvas)
        ta = tl[..., 3:4] / 255.0
        canvas = canvas * (1 - ta) + tl[..., :3] * ta

        # Face bottoms in CANVAS space, for the kicker to solve around. Taken
        # from the placed layer alphas rather than a re-detection, so it is the
        # face that is actually in the picture.
        self._face_bottoms = []
        for _al, _k in ((jal, "boyd"), (dal, "defendant")):
            _b = self.log.get(_k, {}).get("face_box")
            if _b:
                self._face_bottoms.append(int(_b[1] + _b[3]))
        kl, kmask = self.kicker(canvas)
        ka = kl[..., 3:4] / 255.0
        canvas = canvas * (1 - ka) + kl[..., :3] * ka
        # the masks the checkers must use: check_clutter used to REDRAW the
        # kicker from the log with the house font, which is wrong for any other
        # treatment (an underline, a panel, another face). Written next to the
        # build, read back from there.
        _dbg = getattr(self, "debug_dir", None)
        if _dbg:
            Image.fromarray((tmask * 255).astype(np.uint8)).save(os.path.join(_dbg, "title_ink.png"))
            Image.fromarray((kmask * 255).astype(np.uint8)).save(os.path.join(_dbg, "kicker_ink.png"))

        # ---- ANNOTATION CIRCLE round the third element -----------------------
        # Nathan, 2026-08-31: "Put a red circle around the monkey".
        #
        # Drawn HERE, in the graphics stage, for the same reason the arrow is:
        # after the look pass and the grain. An annotation circle put through
        # the unsharp mask comes out crunchy and speckled, which is the exact
        # "processed / not HD" look the arrow used to have.
        #
        # It is an ANNOTATION, not a prop - a hand-drawn red ring reading "look
        # here", so it deliberately does NOT take the photo rim or grain.
        ann = None
        if self.extra_alpha is not None and isinstance(self.extra, dict) \
                and self.extra.get("circle"):
            ys, xs = np.where(self.extra_alpha > 0.35)
            if len(xs):
                cx0, cx1 = int(xs.min()), int(xs.max())
                cy0, cy1 = int(ys.min()), int(ys.max())
                ccx, ccy = (cx0 + cx1) // 2, (cy0 + cy1) // 2
                pad = float(self.extra.get("circle_pad", 1.18))
                rx = int((cx1 - cx0) / 2 * pad)
                ry = int((cy1 - cy0) / 2 * pad)
                th = int(self.extra.get("circle_thickness", 11))
                col = tuple(self.extra.get("circle_rgb", RED))
                ann = np.zeros((H, W), np.float32)
                cv2.ellipse(ann, (ccx, ccy), (rx, ry), 0, 0, 360, 1.0, th,
                            lineType=cv2.LINE_AA)
                # A hairline of soft edge so it is not aliased, but nowhere near
                # enough to read as a glow - this is ink, not light.
                ann = cv2.GaussianBlur(ann, (0, 0), 0.8)
                ann = np.clip(ann, 0, 1)
                canvas = canvas * (1 - ann[..., None]) \
                    + np.array(col, np.float32) * ann[..., None]
                self.log["extra_circle"] = dict(centre=(ccx, ccy), rx=rx, ry=ry,
                                                thickness=th,
                                                px=int((ann > 0.5).sum()))

        if not self.arrow_on:
            self.log["arrow"] = "off"
            canvas = self._final_grain(canvas)
            out = np.clip(canvas, 0, 255).astype(np.uint8)
            Image.fromarray(out).save(out_path, quality=95, subsampling=0)
            self._log_ink_vs_subjects(tmask, kmask, jal, dal)
            self._log_overlay(tmask, kmask, None, ann)
            return out

        occupied = ((dal > 0.4) | (jal > 0.4) | tmask | kmask)
        # THE ARROW MUST CLEAR THE TYPE TOO, not just the subjects. Bringing it
        # nearer the caption on Nathan's instruction ("a little bit less off the
        # captions") slid it straight ONTO the kicker on four of five builds,
        # because the retreat test only knew about subject alpha. Same
        # one-of-two asymmetry as every other bug in this file: a rule was
        # written for the subjects and not for their sibling, the type.
        self._arrow_avoid = (kmask | tmask)
        # He placed this himself, so his position is the target - not a solve.
        # The solver still runs, but only to keep it off a face; it starts here.
        # PLACED, not solved. He positioned it himself - overlapping her hair on
        # purpose - and a search that "improves" on that is me overruling him.
        # The face check still runs, but as a WARNING, not a relocation.
        # arrow_xy overrides the placed default - used when the thing worth
        # pointing at is not the defendant (MONKEY: it points at the monkey).
        if getattr(self, "arrow_xy", None):
            tx, ty = int(self.arrow_xy[0]), int(self.arrow_xy[1])
        else:
            tx, ty = int(ARROW_CX_FRAC * W), int(ARROW_CY_FRAC * H)
        al_ = self.arrow_at(tx, ty, faces_in(np.clip(canvas, 0, 255).astype(np.uint8)),
                            want=getattr(self, 'arrow_want', None))
        self.log["arrow_target"] = [tx, ty]
        aa = al_[..., 3:4] / 255.0
        canvas = canvas * (1 - aa) + al_[..., :3] * aa

        # ---- FINAL GRAIN LAYER, over the ENTIRE thumbnail --------------------
        # Nathan: "I meant a layer of grain over the entire thumbnail".
        # The earlier grain went on the PHOTO ONLY, before the title, kicker and
        # arrow were drawn - so the type sat on top of it perfectly clean, which
        # is exactly what makes vector art read as pasted onto a photo. A real
        # grain pass is the last thing that happens, over everything, because
        # that is what makes the whole frame look like one captured image.
        canvas = self._final_grain(canvas)

        out = np.clip(canvas, 0, 255).astype(np.uint8)
        # 4:4:4. Pillow defaults to 4:2:0, which halves chroma resolution and makes a*
        # piecewise-constant across smooth areas - measured, that alone put
        # poster_fa at 0.032 on a composite that was 0.000 before the save.
        # HS_REMAKE, the approved reference, is 4:4:4.
        Image.fromarray(out).save(out_path, quality=95, subsampling=0)
        self._log_ink_vs_subjects(tmask, kmask, jal, dal)
        self._log_overlay(tmask, kmask, aa[..., 0], ann)
        return out

    def _log_ink_vs_subjects(self, tmask, kmask, jal, dal):
        """R1: title ink never on a subject; kicker ink never in a face box.
        Refuses the build on either. The kicker-over-body count is logged so
        the number he is shown is the number that was measured."""
        boxes = [self.log.get(k, {}).get("face_box") for k in ("boyd", "defendant")]
        m = ink_vs_subjects(tmask, kmask, jal, dal, boxes)
        self.log.update(m)
        assert m["title_on_subject_px"] == 0, "R1: title touches a subject"
        assert m["kicker_on_face_px"] == 0, (
            f"R1: kicker ink inside a face box ({m['kicker_on_face_px']} px) - "
            f"the kicker solver did not clear the faces")

    def _log_overlay(self, tmask, kmask, arrow_a, circle_a):
        """R43 - the frame has an element budget. Every graphic laid over the
        photo (title, kicker, arrow, circle) goes into ONE mask so
        tools/check_clutter.py can measure exact ink cover at feed size
        instead of guessing it back off the JPEG. Logged as log["ink"] and
        dumped as _overlay_mask.png beside the other debug layers."""
        H, W = tmask.shape[:2]
        ov = tmask.astype(bool) | kmask.astype(bool)
        if arrow_a is not None:
            ov |= arrow_a > 0.5
        if circle_a is not None:
            ov |= circle_a > 0.5
        small = cv2.resize(ov.astype(np.float32), (168, 94), interpolation=cv2.INTER_AREA)
        self.log["ink"] = dict(cover=round(float(ov.mean()), 4),
                               cover_168=round(float((small > 0.5).mean()), 4),
                               px=int(ov.sum()),
                               parts=dict(title=int(tmask.sum()), kicker=int(kmask.sum()),
                                          arrow=int((arrow_a > 0.5).sum()) if arrow_a is not None else 0,
                                          circle=int((circle_a > 0.5).sum()) if circle_a is not None else 0))
        _dbg = getattr(self, "debug_dir", None)
        if _dbg:
            cv2.imwrite(os.path.join(_dbg, "_overlay_mask.png"), (ov * 255).astype(np.uint8))
        return ov
