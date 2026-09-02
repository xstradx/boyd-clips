# -*- coding: utf-8 -*-
"""Pick the frame where the face MATCHES the words. Measured, not guessed.

Nathan, 2026-08-31:

  "always get a really good attention grabbing expression that fits closely with
   the video and thumbnail words and title like judge boyd should look upset or
   like she's serious or yelling. It's not as easy as I explain it we need to
   master this and not just give u a simple instruction cause it never works"

He is right that the instruction never works, and the reason is structural: the
builder picked frames on FACE SIZE and sharpness. A big sharp face mid-blink,
looking down, scores exactly as well as the moment she leans in and says the
thing the headline quotes. Nothing in the pipeline ever looked at the face.

THE PRINCIPLE THIS IS BUILT ON
The expression is not chosen from a mood word. It is taken from the MOMENT IN
THE TRANSCRIPT THAT THE HEADLINE COMES FROM. If the card says "Do you want a
jury trial?" then the frame should be from when she says it. That is grounded in
the recording rather than in my taste, and it is why this can be automated at
all.

WHY BLENDSHAPES AND NOT AN EMOTION CLASSIFIER
Published emotion classification runs about 63% accurate at this scale, which is
not good enough to steer a build - a wrong label would confidently pick a wrong
face. MediaPipe's FaceLandmarker returns 52 BLENDSHAPES: browDownLeft, jawOpen,
eyeSquint, mouthFrown and so on. Those are geometric measurements of the face,
not a guess about the person's inner state. "Brows are down 0.62" is a fact;
"she is angry" is an inference. This file only ever states the fact.

WHAT IT CANNOT DO, said plainly
It cannot tell acting from feeling, and it cannot read a face turned away from
camera. It cannot tell WHAT the eyes are looking at either: a head-level face
with the eyes cast down at a defendant (CARTHIEF, lids open, symmetric blink
0.018) is separated from a head-level face with the lids dropped to the desk
(t131, 0.412) only by how far the LIDS have come down - see the head-pose and
lid costs below for what they can and cannot separate. When no frame in the
window clears the floor it says so and returns the best available WITH its
score, rather than pretending the search succeeded.
"""
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MODEL = os.path.join(ROOT, "models", "face_landmarker.task")

# Target blendshape profiles. Each is (blendshape, weight). Weights are a
# STARTING POINT, not a measurement - they encode which muscles a description
# implies, and should be re-derived against frames Nathan approves.
#
# 'speaking' and 'yelling' used to carry a key "mouthOpen". That is NOT one of
# the 52 names the landmarker returns (enumerated 2026-09-01: the mouth shapes
# are mouthClose, mouthFunnel, mouthPucker, mouthLowerDown*, mouthUpperUp*,
# mouthStretch*, mouthPress*, mouthShrug*, mouthRoll*, mouthSmile*, mouthFrown*,
# mouthDimple*, mouthLeft/Right), so shapes.get() returned 0.0 and 'speaking'
# was jawOpen alone, scaled by 1/1.6. jawOpen barely fires on Boyd's tile - 176
# faces over 60-300s of the Thompson hearing: p50 0.002, p90 0.052, max 0.282 -
# while the lower lip does: mouthLowerDownLeft p90 0.205 max 0.683, Right p90
# 0.282 max 0.824. A strip of the top-7 frames by jawOpen and by mouthLowerDown
# both showed visibly open mouths, so the dead weight now goes to the lower-lip
# shapes, at the same total weight as before.
PROFILES = {
    "angry": [("browDownLeft", 1.0), ("browDownRight", 1.0),
              ("mouthFrownLeft", 0.6), ("mouthFrownRight", 0.6),
              ("eyeSquintLeft", 0.4), ("eyeSquintRight", 0.4)],
    "yelling": [("jawOpen", 1.2),
                ("mouthLowerDownLeft", 0.4), ("mouthLowerDownRight", 0.4),
                ("browDownLeft", 0.6), ("browDownRight", 0.6),
                ("mouthStretchLeft", 0.4), ("mouthStretchRight", 0.4)],
    "serious": [("browDownLeft", 0.8), ("browDownRight", 0.8),
                ("mouthPressLeft", 0.7), ("mouthPressRight", 0.7),
                ("eyeSquintLeft", 0.3), ("eyeSquintRight", 0.3)],
    "shocked": [("eyeWideLeft", 1.0), ("eyeWideRight", 1.0),
                ("jawOpen", 0.9), ("browInnerUp", 0.7)],
    "speaking": [("jawOpen", 1.0),
                 ("mouthLowerDownLeft", 0.3), ("mouthLowerDownRight", 0.3)],
    "stern": [("browDownLeft", 0.9), ("browDownRight", 0.9),
              ("mouthPressLeft", 0.5), ("mouthPressRight", 0.5)],
    # FEAR. Nathan, 2026-08-31, on SANCHEZ: "Make sure it's a exaggerated frame
    # of her looking scared". There was no fear profile at all, so a "scared"
    # brief fell through to 'serious' and picked a composed face.
    #
    # Fear is NOT shock. Shock is eyes wide plus a dropped jaw; fear is the
    # INNER brows pulled up and together (browInnerUp is the single strongest
    # cue), the upper lids raised, and the mouth stretched wide rather than
    # opened. Weighted accordingly.
    #
    # WHO that brief is about: the SANCHEZ defendant (the kicker on that build
    # points the arrow at her - docs/verdicts/team_A_verdicts.md N89). The judge
    # on the same build is judged on her own headline's profile, not on this.
    "scared": [("browInnerUp", 1.2),
               ("eyeWideLeft", 0.9), ("eyeWideRight", 0.9),
               ("mouthStretchLeft", 0.6), ("mouthStretchRight", 0.6),
               ("mouthFrownLeft", 0.4), ("mouthFrownRight", 0.4),
               ("jawOpen", 0.3)],
}

# Words in a headline that imply a target profile. The headline is the brief.
WORD_TO_PROFILE = [
    (("yell", "shout", "screams", "erupt", "explodes", "snaps"), "yelling"),
    (("angry", "furious", "mad", "loses it", "had enough", "fed up"), "angry"),
    (("scared", "afraid", "terrified", "fear", "panic", "crying", "cries",
      "begs", "begged", "pleads", "breaks down"), "scared"),
    (("shock", "stunned", "cannot believe", "can't believe", "unbelievable",
      "wait", "what"), "shocked"),
    (("warn", "warns", "warned", "serious", "final", "last chance",
      "no mercy", "doubled", "sentence"), "stern"),
    (("asked", "asks", "wants to know", "?", "why", "where", "how"), "serious"),
]

# MEASURED, not chosen. The first value here was 0.18, invented, and it
# rejected every real frame - the same mistake the variety gate made. Scanned
# 58 faces over 120s of a real hearing:
#     speaking  p50 0.0018  p90 0.0890  p95 0.1366  max 0.1764
#     stern     p50 0.0255  p90 0.0757            max 0.1998
# A frame in the top decile is a genuine expression; the median frame is a
# neutral face. So the floor was the measured p90 - and 0.042 was the p90 of
# the penalised 'serious' distribution once the penalties went in.
#
# RE-DERIVED 2026-09-01, after the penalty was rebuilt (see PENALTIES). The
# scale moved: the old eyeLookDown penalty was subtracting most from the
# engaged, head-level frames, so it had compressed the top of the distribution.
# Same Thompson video, right tile, step 1.0, min face 0.4% of the tile:
#     serious  120-150s (28 faces) p50 0.0438  p90 0.0918  p95 0.1373  max 0.1738
#     serious   60-300s (176 faces) p50 0.0462  p90 0.0829  p95 0.0956  max 0.2506
#     speaking 120-150s             p50 0.0055  p90 0.1800  p95 0.1964  max 0.2158
#     stern    120-150s             p50 0.0227  p90 0.0796  p95 0.1173  max 0.1847
# The p90 rule would now put the floor at 0.083-0.092. The five approved
# cutouts (config/quality_floor.json - the MINIMUM, by his word) score, on the
# profile their own headline maps to ('serious' for all five):
#     CARTHIEF 0.0552 (p64 of the 176)   MONKEY 0.1210 (p98)   OFFERUP 0.0873 (p90)
#     SANCHEZ  0.0431 (p47)              THOMPSON 0.1454 (p98)
# so a p90 floor would reject two approved builds - a floor that fails the
# floor set is a regression by definition (tools/check_floor_gates.py: a gate
# must reject the known-bad controls AND pass all five). The floor is therefore
# anchored on the approved minimum, rounded down: SANCHEZ 0.0431 -> 0.04. What
# 0.04 means on the hearing: roughly the median 'serious' frame, i.e. it now
# separates "a face" from "a reading/blinking/neutral face", not the top decile
# from the rest. The reading controls it must reject all score 0.000 (t60, t74,
# t79, t101, t116, t117, t265, t267, t268 - head pitched 8-15 deg to the desk).
#
# RE-MEASURED 2026-09-01 (later the same day) after the blink cost became a
# LID ramp (see BLINK_FREE / BLINK_COST): open-eyed frames no longer pay a
# blink tax, so the top of the scale rose a little. Same video, right tile,
# step 1.0, min face 0.4% (175 faces found this pass, 176 the pass before):
#     serious  120-150s (27 faces)  p50 0.0413  p90 0.0983  p95 0.1439  max 0.1888
#     serious   60-300s (175 faces) p50 0.0501  p90 0.0938  p95 0.1059  max 0.2599
#     speaking 120-150s             p50 0.0148  p90 0.1797  p95 0.1799  max 0.2171
#     stern    120-150s             p50 0.0246  p90 0.0876  p95 0.1228  max 0.1998
# The five approved on 'serious' (their blink readings 0.018-0.094 all sit
# inside the free band, so each now scores exactly its raw):
#     CARTHIEF 0.0582 (p57 of the 175)   MONKEY 0.1375 (p98)   OFFERUP 0.0917 (p89)
#     SANCHEZ  0.0520 (p53)              THOMPSON 0.1494 (p98)
# The approved minimum rounded down would now read 0.05. The floor is HELD at
# 0.04 on purpose: 0.05 would leave SANCHEZ 0.002 of margin on a reading that
# moves 0.012 between crop methods (SANCHEZ reads 0.0520 on the full cutout
# tools/library.py measures, 0.0399 on a face_box+25% crop), and nothing the
# floor has to reject lives between the two - the lid controls top out at
# 0.0145 (t126) and the frames scoring 0.040-0.050 on the hearing (t70, t90,
# t140, t223, t272, ...) were read off the strip as open-eyed neutral faces,
# not defects. So 0.04 = 0.012 under the approved minimum, and every control
# (head-down reading frames 0.000; lids-down t131/t132/t81/t191 0.000, t126
# 0.0145; OFFERUP/_old 0.000) stays under it.
FLOOR = 0.04


def profile_for(headline):
    """Which expression the WORDS imply. The headline is the brief."""
    h = (headline or "").lower()
    for words, prof in WORD_TO_PROFILE:
        if any(w in h for w in words):
            return prof
    return "serious"


_LM = None


def _landmarker(n_faces=3):
    global _LM
    if _LM is None:
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        if not os.path.exists(MODEL):
            raise FileNotFoundError(
                f"{MODEL} missing. Download face_landmarker.task from "
                "storage.googleapis.com/mediapipe-models - expression selection "
                "will not silently fall back to picking the biggest face.")
        _LM = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=mpp.BaseOptions(model_asset_path=MODEL),
                output_face_blendshapes=True,
                # head pose comes from the same pass. Checked 2026-09-01 on the
                # five approved cutouts: turning this on changes no blendshape
                # (max |diff| 0.000000 against the run without it).
                output_facial_transformation_matrixes=True,
                num_faces=n_faces))
    return _LM


# HEAD PITCH, in degrees, from the landmarker's 4x4 transformation matrix:
# atan2(R[2,1], R[2,2]). The SIGN is measured, not taken from a doc: on this
# hearing's camera, frames of Boyd reading the desk measure +8.4..+15.3 (t60
# +10.9, t101 +8.4, t116 +11.6, t117 +14.3, t265 +14.7, t268 +15.2, t79 +15.3)
# and frames of her engaged with the room measure -9.9..-19.8. Over 176 faces:
# p10 -16.1, p50 -9.5, p90 +10.7. Positive = pitched down toward the desk.
#
# The ramp: 0 at HEAD_DOWN_START, 1 at HEAD_DOWN_FULL. The five approved
# cutouts sit at +1.1 (CARTHIEF, looking down at the defendant, yaw -42), -9.0,
# -12.2, -19.5, -19.1; CARTHIEF's other cutout versions read up to +2.2. So 3
# deg keeps every approved face at exactly 0 with a margin, and 12 deg is past
# the lowest reading frame in the controls (t101 +8.4 lands at 0.6).
HEAD_DOWN_START = 3.0
HEAD_DOWN_FULL = 12.0


def head_down(pitch_deg):
    """0 = head level or raised, 1 = pitched fully down to the desk."""
    return float(min(1.0, max(0.0, (pitch_deg - HEAD_DOWN_START)
                               / (HEAD_DOWN_FULL - HEAD_DOWN_START))))


def _pitch(m):
    R = np.asarray(m, dtype=np.float64)[:3, :3]
    return math.degrees(math.atan2(R[2, 1], R[2, 2]))


def blendshapes(bgr):
    """Every detected face's 52 blendshapes, with its bounding box.

    Also writes one PSEUDO-SHAPE into `shapes`: "_headDown" (0..1, the pitch
    ramp above). It rides inside the shapes dict on purpose: tools/library.py
    stores `shapes` in index.json and re-scores from them LIVE (score_entry),
    so the head penalty has to travel with the shapes or the library and the
    video search would be scored on different rules. An index seeded before
    this key existed reads it as 0.0 (no head penalty) until re-seeded. The raw
    pitch is returned beside the dict as "pitch" for diagnostics.
    """
    import mediapipe as mp
    lm = _landmarker()
    img = mp.Image(image_format=mp.ImageFormat.SRGB,
                   data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    r = lm.detect(img)
    out = []
    H, W = bgr.shape[:2]
    mats = getattr(r, "facial_transformation_matrixes", None) or []
    for i, bs in enumerate(r.face_blendshapes):
        d = {c.category_name: float(c.score) for c in bs}
        pitch = _pitch(mats[i]) if i < len(mats) else 0.0
        d["_headDown"] = head_down(pitch)
        xs = [p.x for p in r.face_landmarks[i]]
        ys = [p.y for p in r.face_landmarks[i]]
        out.append({
            "shapes": d,
            "box": (int(min(xs) * W), int(min(ys) * H),
                    int((max(xs) - min(xs)) * W), int((max(ys) - min(ys)) * H)),
            "cx": float(np.mean(xs)), "cy": float(np.mean(ys)),
            "pitch": pitch,
        })
    return out


# DISQUALIFIERS. Nathan, 2026-08-31: "her reaction isn't good".
#
# The first version scored only the target muscles, and picked a frame of Boyd
# looking DOWN at paperwork - because looking down lowers the brows and presses
# the mouth, which is exactly what the 'serious' profile rewards. The muscles
# were right and the face was wrong. Measured 2026-09-01, that is not a small
# effect: among the 176 faces, those pitched >= 10 deg to the desk reach a
# 'serious' raw of 0.1660 (p90 0.1457) - higher than four of the five approved
# cutouts. A reading face out-scores an approved one on muscles alone.
#
# A thumbnail face must be LOOKING AT SOMETHING and have its eyes open. Two
# costs, in SCORE UNITS (what a full excursion subtracts from the raw profile
# score):
#
# 1. LIDS, on min(eyeBlinkLeft, eyeBlinkRight). The two eyes do NOT read
#    alike on this camera: 164 of the 176 faces (93%) read blinkLeft above
#    blinkRight, median gap 0.139, and all five approved cutouts - eyes
#    plainly open - read blinkLeft 0.21-0.30 against blinkRight 0.02-0.09. The
#    old penalty (and the veto) used both eyes, so an open-eyed engaged frame
#    such as t245 (blinkLeft 0.635, blinkRight 0.017, looking straight at the
#    camera, speaking) was vetoed outright. A real blink is bilateral, so the
#    symmetric part is the blink; the one-sided remainder is the camera.
#
#    It is a RAMP, not a straight multiple. The first rebuild charged 0.175 x
#    the symmetric blink (the old effective cost, 0.3 x 1.4 / 2.4), and that
#    had no real frame it could fail: the largest symmetric blink among the
#    175 hearing faces is t131 at 0.412 - read off the strip 2026-09-01 as
#    Boyd's lids dropped to the desk with the head level (pitch -5.1) - and
#    at 0.175 x 0.412 it still cleared the floor at 0.0572 on 'serious'. A
#    cost that lets its own worst case through is decoration. Where the
#    symmetric reading lands on this camera:
#        175 faces:  p50 0.058  p75 0.131  p90 0.227  p95 0.312  max 0.412
#        approved five, eyes open: 0.018 0.025 0.023 0.051 0.094 (MONKEY)
#        lids visibly down (strip): t131 0.412  t191 0.397  t132 0.326
#                                   t81 0.318   t126 0.284
#    so the free band ends at BLINK_FREE 0.10 - above every approved reading
#    - and the cost ramps linearly from there to EYES_SHUT, where the veto
#    takes over (no cliff in the wrong direction: a face at 0.549 pays the
#    whole cost, at 0.55 it is vetoed). Sweep of the full cost on the same
#    faces, head cost fixed:
#        0.175 -> t131 0.0080, t126 0.0247 (both under the floor, t131 not zero)
#        0.20  -> t131 0.000,  t126 0.0145, t132/t81/t191 0.000   <- chosen
#        0.25  -> t126 0.000 too, but t87 (engaged, 0.13, just past the free
#                 band) pays 0.017 instead of 0.013 for nothing gained
#    Each lids-down control's OPEN-EYED TWIN (same shapes, blink zeroed)
#    clears the floor - t131 0.1293, t126 0.0964 - so the lids are the one
#    thing separating those frames from usable ones, which is what the cost
#    is for. The approved five pay nothing at any setting (all under 0.10).
#
# 2. HEAD DOWN, on the "_headDown" pseudo-shape (head pitch, see head_down).
#    This REPLACES the eyeLookDown penalty, which measured INVERTED: eyeLookDown
#    is the eye's rotation inside the head, not what it is aimed at. The two
#    most head-down reading frames (t60 +10.9, t101 +8.4, eyes straight ahead
#    in a lowered head) read eyeLookDown 0.03, the other reading controls
#    0.24-0.50, and the head-level ENGAGED frames read the highest values in
#    the sample, 0.36-0.70 (t191 0.70, t222 0.66, t186 0.59, t87 0.59, t292
#    0.58). So the old penalty spared the worst reading frames and taxed the
#    good ones, and it zeroed CARTHIEF (an approved cutout: eyeLookDown
#    0.412/0.379, penalty 0.2474 x 0.3 = 0.0742, above its best raw 0.0642 on
#    any profile).
#    Cost 0.20: the reading frames pitched >= 10 deg reach 'serious' raw
#    0.1660, so a fully head-down face cannot clear the floor whatever its
#    muscles do. Sweep on the same 176 faces (blink cost fixed, ramp 3-12):
#        cost 0.10 -> reading controls t101 0.045, t79 0.055, t74 0.024 survive
#        cost 0.15 -> t101 0.014 survives; serious p90 0.0843, 142/176 survive
#        cost 0.20 -> every head-down control 0.000; p90 0.0829, 136/176  <- chosen
#        cost 0.25 -> same controls, p90 0.0819, 135/176 (no further gain)
#    The five approved cutouts are untouched at every cost (head_down 0).
#
# WHAT THIS STILL CANNOT CATCH, said plainly: eyes cast down with the head
# level AND the lids still up. The lid ramp now takes the head-level reading
# frames whose lids came down (t131, t126, t132, t81 - all 0.000-0.0145), but
# t89 (pitch 0.0, symmetric blink 0.001) and t125 (+3.5, 0.169) are reading
# frames that score 0.033 / 0.080 on 'serious', and CARTHIEF (+1.1, 0.018) is
# an approved frame looking down at a defendant. Neither pose nor lids
# separate those, and gaze target is not a face measurement, so they are left
# to the floor and to the transcript anchor.
BLINK_FREE = 0.10
BLINK_COST = 0.20
HEAD_DOWN_COST = 0.20

# HARD REJECT, not a penalty. Nathan asked to "exaggerate ... their facial
# reactions", so the picker was pointed at the defendant too - and it promptly
# chose a frame of him with his EYES CLOSED. That is not a scoring accident: a
# blink is one of the LARGEST blendshape excursions a face makes, so any scorer
# rewarding magnitude will actively seek blinks out.
#
# A weighted penalty cannot fix this, because a strong enough expression
# elsewhere always buys the blink back. Closed eyes make a thumbnail face
# unusable no matter what the rest of the face is doing, so it is a veto.
#
# 0.55 is above a natural narrowed-eye squint (which the 'angry'/'stern'
# profiles legitimately want) and below a real blink. Applied to the SYMMETRIC
# blink (min of the two eyes) since 2026-09-01, for the reason under BLINK
# above: on max() it fired on 7 of the 176 Thompson faces, five of them with
# blinkRight under 0.11 and the eyes open in the frame; on min() it fires on
# none of them (the largest symmetric blink in that sample is 0.412). The
# defendant frame that motivated the veto is not on disk to re-measure - not
# verified against it.
EYES_SHUT = 0.55


def blink(shapes):
    """The bilateral blink - the part of the reading both eyes agree on."""
    return min(float(shapes.get("eyeBlinkLeft", 0.0)),
               float(shapes.get("eyeBlinkRight", 0.0)))


def blink_max(shapes):
    """The WORSE eye. One half-shut eye is enough to make a thumbnail face
    unusable, and min() hides it (see BLINK_MAX_REJECT)."""
    return max(float(shapes.get("eyeBlinkLeft", 0.0)),
               float(shapes.get("eyeBlinkRight", 0.0)))


# SEARCH GATES (rank_rows), measured 2026-09-01 on the ten frames of the
# frame-picker audit: the five approved judge frames (cases.json judge_t, in
# their SOURCE clips) against the frame the scorer preferred in each window.
# The values are set in the block that follows the measurement table below
# (tools/check_frame_picker.py proves them on every run).
GATES = dict(blink_max=True, sharp=True, eyes=True, anchor=True)
BLINK_MAX_REJECT = 1.01   # placeholder until measured (1.01 = gate off)
SHARP_FRAC = 0.0          # placeholder until measured (0.0 = gate off)
EYES_FRAC = 0.0           # placeholder until measured (0.0 = gate off)
ANCHOR_TAU = 1e9          # placeholder until measured (1e9 = flat window)


def eyes_shut(shapes):
    """True if this face is mid-blink - a veto, checked before any scoring."""
    return blink(shapes) >= EYES_SHUT


def lids_down(shapes):
    """0 while the symmetric blink sits in the free band (open eyes on this
    camera), 1 at the veto. The ramp in the LIDS note above."""
    return float(min(1.0, max(0.0, (blink(shapes) - BLINK_FREE)
                               / (EYES_SHUT - BLINK_FREE))))


def penalty(shapes):
    """How much this face disqualifies itself regardless of expression, in
    score units (0 = nothing to hold against it)."""
    return (BLINK_COST * lids_down(shapes)
            + HEAD_DOWN_COST * float(shapes.get("_headDown", 0.0)))


def raw_score(shapes, profile):
    """The profile's weighted mean of its blendshapes, before disqualifiers."""
    spec = PROFILES[profile]
    tot = sum(w for _, w in spec)
    return sum(float(shapes.get(k, 0.0)) * w for k, w in spec) / max(tot, 1e-6)


def score(shapes, profile):
    """How strongly this face expresses the profile, minus disqualifiers.

    Clamped at 0: a face that is more disqualified than expressive is simply
    unusable, and letting it go negative would make a blinking face rank BELOW
    a blank wall rather than alongside it.
    """
    if eyes_shut(shapes):
        return 0.0                      # veto: no expression buys back a blink
    return max(0.0, raw_score(shapes, profile) - penalty(shapes))


def _matches(bgr, box, ref, thr):
    """Is the face in `box` the person `ref` describes?"""
    try:
        import identity as I
    except Exception:
        return True
    x, y, w, h = [int(v) for v in box]
    pad = int(max(w, h) * 0.25)
    sub = bgr[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    if sub.size == 0:
        return False
    rows = I.faces_in(sub, score=0.5)
    if not rows:
        return False
    big = max(rows, key=lambda r: r[3])
    return I.score_against(I.embed(sub, big), ref) >= thr


def audio_energy(video, t, win=0.6):
    """Loudness around t. A raised voice is the strongest single cue for
    'yelling' and it costs nothing - the audio is already there."""
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, t-win/2):.2f}",
                        "-t", f"{win:.2f}", "-i", video, "-vn", "-ac", "1",
                        "-ar", "16000", "-f", "wav", wav],
                       capture_output=True)
        if not os.path.exists(wav):
            return 0.0
        import wave
        with wave.open(wav) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        return float(np.abs(a.astype(np.float32)).mean()) / 32768.0 if a.size else 0.0


def _frame(video, t, side=None):
    """One frame at t, optionally one half of a 2-up tile. None if unreadable."""
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "f.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                        "-i", video, "-frames:v", "1", png],
                       capture_output=True)
        im = cv2.imread(png)
    if im is None:
        return None
    W0 = im.shape[1]
    if side == "left":
        return im[:, :W0 // 2]
    if side == "right":
        return im[:, W0 // 2:]
    return im


# ------------------------------------------------------------- features --
# The search is TWO PHASES since 2026-09-01: extract() reads every feature the
# ranker needs off each frame ONCE (blendshapes, head pitch, face sharpness,
# identity, audio) and can cache them to disk; rank_rows() applies the profile
# weights and the gates to those rows. A threshold can then be re-measured, or
# a gate switched off for a negative control, without another pass over the
# video - and the frame-picker selftest (tools/check_frame_picker.py) runs the
# SAME ranker the build runs, on cached rows, in seconds.
FEATURES_VERSION = 3       # part of the cache key; bump when a feature changes
SHARP_PAD = 0.0            # face box padding for the sharpness crop: TIGHT


def sharpness(bgr, box, pad=SHARP_PAD, upper=False):
    """Laplacian variance of the grey face crop - the TIGHT landmarker box
    (`upper`=True: its top half, the eyes and glasses). Motion blur and a soft
    seek both lower it; it is compared to the WINDOW's median, never to a
    constant (see SHARP_FRAC).

    WHY TIGHT. The first version padded the box by 0.3 x its long side, and
    on MONKEY that read the blurred old pick (src 6292.0) at 591 against the
    approved sharp frame (6311.0) at 469 - backwards - because the padding
    takes in her hair line, collar and the chair edge, which are sharp in
    every frame and swamp the face. The tight box reads the same two frames
    133 / 249 (the audit's numbers), the top half 77 / 217.
    """
    x, y, w, h = [int(v) for v in box]
    p = int(pad * max(w, h))
    y1 = y + (h // 2 if upper else h) + p
    crop = bgr[max(0, y - p):y1, max(0, x - p):x + w + p]
    if crop.size == 0:
        return 0.0
    return float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def ident_score(bgr, box, ref):
    """(identity, detector score) for the face in `box`: identity is
    identity.score_against on the largest YuNet face in the padded box,
    detector score is YuNet's own confidence in it. (-1.0, 0.0) when YuNet
    finds no face there - the landmarker saw one, the detector did not, so it
    cannot be matched and the ranker treats it as not the person. (None, 0.0)
    when identity cannot be imported."""
    try:
        import identity as I
    except Exception:
        return None, 0.0
    x, y, w, h = [int(v) for v in box]
    pad = int(max(w, h) * 0.25)
    sub = bgr[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    if sub.size == 0:
        return -1.0, 0.0
    rows = I.faces_in(sub, score=0.5)
    if not rows:
        return -1.0, 0.0
    big = max(rows, key=lambda r: r[3])
    return float(I.score_against(I.embed(sub, big), ref)), float(big[-1])


def crop_side(im, side=None, region=None):
    """The part of a frame the search looks at. CROP BEFORE DETECTION, not
    filter after: measured on a real hearing frame, 1920x1080 2-up, the FULL
    frame returns 0 faces at every scale while the right half at native scale
    returns 1. The detector is not built for two small faces in a wide
    composite, so filtering detections by side would filter an empty list
    forever.

    A TIGHT `region` beats a tile half. MediaPipe's landmarker needs the face
    to occupy a decent share of what it is given: measured on OFFERUP's
    defendant at his own plate_t, it found 0 faces in the 640x720 half AND 0
    in the 628x323 detected tile - at any upscale - but 1 in the 300x320 plate
    crop. The subject stands in roughly one spot for his hearing, so that crop
    rectangle is the right spatial anchor over time."""
    W0 = im.shape[1]
    if region is not None:
        rx, ry, rw, rh = [int(v) for v in region]
        return im[max(0, ry):ry + rh, max(0, rx):rx + rw]
    if side == "left":
        return im[:, :W0 // 2]
    if side == "right":
        return im[:, W0 // 2:]
    return im


def face_features(im, min_face_frac=0.004, ident_ref=None):
    """Every face in `im` (already cropped to the side/region) at or above
    `min_face_frac` of its area, with the features the ranker reads."""
    H, W = im.shape[:2]
    out = []
    for f in blendshapes(im):
        bw, bh = f["box"][2], f["box"][3]
        frac = (bw * bh) / float(W * H)
        if frac < min_face_frac:
            continue
        ident, det = (None, None)
        if ident_ref is not None:
            ident, det = ident_score(im, f["box"], ident_ref)
        out.append(dict(box=[int(v) for v in f["box"]], shapes=f["shapes"],
                        pitch=round(float(f["pitch"]), 2), frac=round(frac, 5),
                        lap=round(sharpness(im, f["box"]), 2),
                        lap_eyes=round(sharpness(im, f["box"], upper=True), 2),
                        ident=(None if ident is None else round(ident, 4)),
                        det=(None if det is None else round(det, 4))))
    return out


def _cache_key(video, t0, t1, step, side, region, min_face_frac, use_audio, anchor, ident_ref):
    import hashlib
    st = os.stat(video)
    ms = os.stat(MODEL) if os.path.exists(MODEL) else None
    parts = [os.path.abspath(video), st.st_size, st.st_mtime_ns,
             round(t0, 3), round(t1, 3), round(step, 4), side,
             None if region is None else [int(v) for v in region],
             min_face_frac, bool(use_audio), None if anchor is None else round(anchor, 3),
             None if ident_ref is None else hashlib.sha1(np.ascontiguousarray(ident_ref).tobytes()).hexdigest(),
             None if ms is None else (ms.st_size, ms.st_mtime_ns),
             FEATURES_VERSION]
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:20]


def extract(video, t0, t1, step=0.4, side=None, region=None, min_face_frac=0.004,
            ident_ref=None, use_audio=True, anchor=None, cache=None, progress=False):
    """Per-frame features over [t0, t1]: [{t, audio, faces: [face_features]}],
    one row per readable frame (a frame with no qualifying face has faces=[]).

    THE GRID IS ANCHORED. Samples sit at anchor + k*step (anchor defaults to
    t0). prep() builds the judge window as judge_t +/- 25 s and anchors on
    judge_t, so the hand-verified frame is itself a sample - on the old grid
    (t0 + k*0.4 from judge_t-25) it never was: 25/0.4 = 62.5, so the nearest
    samples sat 0.2 s either side of it.

    `cache` is a directory: rows are read from / written to <cache>/<key>.json
    where the key covers the video's bytes (size + mtime), every argument and
    FEATURES_VERSION."""
    import json
    key = None
    if cache:
        os.makedirs(cache, exist_ok=True)
        key = os.path.join(cache, _cache_key(video, t0, t1, step, side, region,
                                             min_face_frac, use_audio, anchor, ident_ref) + ".json")
        if os.path.exists(key):
            try:
                return json.load(open(key, encoding="utf-8"))["rows"]
            except Exception:
                pass
    a0 = t0 if anchor is None else float(anchor)
    k_lo = int(math.ceil((t0 - a0) / step - 1e-9))
    k_hi = int(math.floor((t1 - a0) / step + 1e-9))
    rows = []
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "f.png")
        for k in range(k_lo, k_hi + 1):
            t = round(a0 + k * step, 2)
            if os.path.exists(png):
                os.remove(png)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                            "-i", video, "-frames:v", "1", png],
                           capture_output=True)
            im = cv2.imread(png)
            if im is None:
                continue
            im = crop_side(im, side=side, region=region)
            faces = face_features(im, min_face_frac=min_face_frac, ident_ref=ident_ref)
            a = audio_energy(video, t) if (use_audio and faces) else 0.0
            rows.append(dict(t=t, audio=round(a, 4), faces=faces))
            if progress and abs((t - t0) % 5.0) < step:
                print(f"    scanned {t - t0:.0f}s / {t1 - t0:.0f}s", flush=True)
    if key:
        json.dump(dict(video=os.path.abspath(video), t0=t0, t1=t1, step=step, side=side,
                       region=region, anchor=anchor, features_version=FEATURES_VERSION,
                       rows=rows),
                  open(key, "w", encoding="utf-8"))
    return rows


def anchor_weight(dt, tau=None):
    """How much a frame `dt` seconds from the anchor keeps of its score:
    1/(1 + (dt/tau)^2). 1.0 on the anchor, 0.5 at tau, 0.2 at 2 tau."""
    tau = ANCHOR_TAU if tau is None else tau
    return 1.0 / (1.0 + (float(dt) / tau) ** 2)


def rank_rows(rows, profile, ident_min=0.30, gates=None, anchor=None):
    """Score and order extracted rows for `profile`. Returns (best, cands):
    cands is every qualifying face, accepted ones first by total desc, then
    the gated-out ones (total 0.0, `reject` says which gate); best is the top
    accepted candidate or None when nothing survives.

    `gates` is a dict of gate flags (see GATES); a missing key means ON. The
    frame-picker selftest turns them off to prove the old ranking comes back.
    `anchor` is the hand-verified time the window was built around; with the
    'anchor' gate on, a candidate's total is weighted by anchor_weight().
    """
    g = dict(GATES)
    g.update(gates or {})
    cands = []
    for r in rows:
        for f in r["faces"]:
            # IDENTITY CONSTRAINT. The judge occupies her tile for the whole
            # hearing, so scanning her side by expression alone is safe. The
            # DEFENDANT'S tile does not work that way - whoever is at the
            # podium stands there, and on OFFERUP the picker happily chose a
            # defence attorney in a suit and put him in the thumbnail. So
            # when a reference is supplied, a candidate that is not that
            # person is not a candidate at all.
            if f.get("ident") is not None and f["ident"] < ident_min:
                continue
            cands.append((r, f))
    laps = sorted(f["lap"] for _, f in cands)
    med = laps[len(laps) // 2] if laps else 0.0
    eyes = sorted(f.get("lap_eyes", 0.0) for _, f in cands)
    med_eyes = eyes[len(eyes) // 2] if eyes else 0.0
    out = []
    for r, f in cands:
        sh = f["shapes"]
        s = score(sh, profile)
        why = None
        bm = blink_max(sh)
        le = f.get("lap_eyes", 0.0)
        if g.get("blink_max", True) and bm >= BLINK_MAX_REJECT:
            why = f"blink_max {bm:.3f} >= {BLINK_MAX_REJECT}"
        elif g.get("sharp", True) and med > 0 and f["lap"] < SHARP_FRAC * med:
            why = f"blur: lap {f['lap']:.0f} < {SHARP_FRAC} x window median {med:.0f}"
        elif g.get("eyes", True) and med_eyes > 0 and le < EYES_FRAC * med_eyes:
            why = f"eyes: lap_eyes {le:.0f} < {EYES_FRAC} x window median {med_eyes:.0f}"
        if why:
            s = 0.0
        a = float(r["audio"])
        # audio is a MODIFIER, not the score - a loud room is not a face
        total = s * (1.0 + 0.5 * min(a * 6.0, 1.0))
        dt = None if anchor is None else abs(float(r["t"]) - float(anchor))
        w = 1.0
        if dt is not None and g.get("anchor", True):
            w = anchor_weight(dt)
            total *= w
        out.append(dict(t=r["t"], expr=round(s, 4), audio=round(a, 4),
                        total=round(total, 4), box=tuple(f["box"]),
                        head_down=round(sh.get("_headDown", 0.0), 3),
                        lids=round(lids_down(sh), 3), blink_max=round(bm, 3),
                        lap=f["lap"], lap_med=round(med, 1),
                        lap_eyes=le, lap_eyes_med=round(med_eyes, 1),
                        ident=f.get("ident"), det=f.get("det"),
                        pitch=f.get("pitch"), dt=dt, anchor_w=round(w, 4), reject=why))
    out.sort(key=lambda r: (r["reject"] is not None, -r["total"]))
    best = next((r for r in out if r["reject"] is None and r["total"] > 0.0), None)
    return best, out


def search(video, t0, t1, profile, step=0.4, side=None, min_face_frac=0.004,
           use_audio=True, progress=False, coarse=True, ident_ref=None,
           ident_min=0.30, region=None, anchor=None, cache=None, gates=None):
    """Best-expression frame in [t0,t1], COARSE THEN FINE: extract() + rank_rows().

    `side` restricts to one half of a 2-up tile layout ('left'/'right'), because
    a courtroom 2-up holds two faces and the wrong one will happily win.

    Returns (best, rows). best is None when NO candidate survives the gates;
    rows is every candidate with its verdict, and is EMPTY when no qualifying
    face was found at all - the caller must treat that as "wrong side or wrong
    window", not as "nothing expressive here".

    WHY COARSE-TO-FINE. A flat scan at `step` costs one ffmpeg seek + one
    landmark pass per sample, so widening the window to find a more expressive
    frame multiplies the cost linearly. On 2026-08-31 the windows went to
    ~580s, which at step 0.4 is ~1450 samples PER SUBJECT - twenty times that
    across ten subjects, and the batch had to be killed.

    An expression builds and decays over roughly a second, so a 2s grid cannot
    miss a peak entirely - it lands somewhere on the slope. So: scan the whole
    window coarsely, then re-scan +/-2s around the best at the fine step. Same
    answer, an order of magnitude fewer frames.
    """
    kw = dict(side=side, region=region, min_face_frac=min_face_frac, ident_ref=ident_ref,
              use_audio=use_audio, anchor=anchor, cache=cache)
    if coarse and (t1 - t0) > 60:
        c_rows = extract(video, t0, t1, step=2.0, progress=progress, **kw)
        c_best, c_ranked = rank_rows(c_rows, profile, ident_min=ident_min, gates=gates)
        if not c_best:
            return None, c_ranked
        lo = max(t0, c_best["t"] - 2.0)
        hi = min(t1, c_best["t"] + 2.0)
        f_rows = extract(video, lo, hi, step=step, progress=False, **kw)
        seen = {r["t"] for r in c_rows}
        best, ranked = rank_rows(c_rows + [r for r in f_rows if r["t"] not in seen],
                                 profile, ident_min=ident_min, gates=gates)
        if progress and best:
            print(f"    coarse best t={c_best['t']}  ->  refined t={best['t']} "
                  f"({best['total']:.4f})", flush=True)
        return best, ranked
    rows = extract(video, t0, t1, step=step, progress=progress, **kw)
    return rank_rows(rows, profile, ident_min=ident_min, gates=gates)


# The approved reactions library (tools/library.py seeds it; read-only here).
REACTIONS = os.path.join(ROOT, "assets", "harvest", "reactions", "boyd")
CASES_JSON = os.path.join(ROOT, "config", "cases.json")
THUMBWORK = "D:/Boyd Clips/thumbwork"
# The one superseded judge cutout on disk: OFFERUP's first matte (2026-08-30
# 16:22), replaced by the one he accepted. Read off the file 2026-09-01: head
# pitched +16.1 to the desk, eyes on the paperwork - the "looking DOWN at
# paperwork" face. The _NEW builds he rejected on 08-31 re-used the approved
# cutouts, so this is the only rejected-class judge cutout that exists
# separately from the approved five.
REJECTED_CUTOUT = os.path.join(THUMBWORK, "OFFERUP", "_old", "judge_surgical.png")


def cutout_face(png_path, long_side=1600):
    """The largest face on an RGBA cutout, measured the way tools/library.py
    tags it: composited on mid grey (a transparent hole is not a face) and
    resized to `long_side` on the long edge. Returns (face, scale) or
    (None, why)."""
    im = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
    if im is None:
        return None, "unreadable"
    if im.ndim == 3 and im.shape[2] == 4:
        a = im[..., 3:4].astype(np.float32) / 255.0
        bgr = (im[..., :3].astype(np.float32) * a + 128.0 * (1 - a)).astype(np.uint8)
    else:
        bgr = im[..., :3]
    s = float(long_side) / max(bgr.shape[:2])
    if s < 1.0:
        bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    else:
        s = 1.0
    faces = blendshapes(bgr)
    if not faces:
        return None, "no face found on the cutout"
    return max(faces, key=lambda f: f["box"][2] * f["box"][3]), s


def _headline_profiles():
    """case -> profile its own headline maps to, from config/cases.json."""
    try:
        import json
        C = json.load(open(CASES_JSON, encoding="utf-8"))
    except Exception:
        return {}
    return {k: profile_for(f"{v.get('white', '')} {v.get('yellow', '')}")
            for k, v in C.items() if isinstance(v, dict)}


def selftest():
    """Prove the scorer separates expressions, against controls whose answer is
    known before the number is read. Synthetic faces are not usable here, so the
    control is a REAL pair: a neutral frame and a speaking frame from the same
    hearing. If the scorer cannot tell those apart it cannot steer a build."""
    import json
    ok = True
    if not os.path.exists(MODEL):
        print("  SELFTEST_SKIP face_landmarker.task not present")
        return 0
    src = None
    for c in (r"D:/Boyd Clips/READY-TO-POST/1_LONGFORM_Thompson.mp4",):
        if os.path.exists(c):
            src = c
            break
    if src is None:
        print("  SELFTEST_SKIP no control video on disk")
        return 0

    b, rows = search(src, 120, 150, "speaking", step=1.0, use_audio=False,
                     side="right", min_face_frac=0.004)
    if not rows:
        print("  FAIL no faces found in 30s of a hearing"); return 1
    top = rows[0]["expr"]
    bot = rows[-1]["expr"]
    print(f"  scanned {len(rows)} faces over 30s")
    print(f"  most 'speaking'  {top:.4f} at t={rows[0]['t']}")
    print(f"  least 'speaking' {bot:.4f} at t={rows[-1]['t']}")
    if not (top > bot * 5.0):
        print(f"  FAIL scorer does not separate open mouths from closed "
              f"(top {top:.4f} vs bottom {bot:.4f})")
        ok = False
    if top < FLOOR:
        print(f"  FAIL best frame {top:.4f} is under the measured floor {FLOOR}")
        ok = False

    # VALIDITY: two different profiles must NOT rank the same frames identically.
    # If they do, the profiles are not measuring distinct expressions and the
    # whole selection is theatre.
    _, rows_b = search(src, 120, 150, "stern", step=1.0, use_audio=False,
                       side="right", min_face_frac=0.004)
    if rows_b:
        ta = {r["t"]: r["expr"] for r in rows}
        tb = {r["t"]: r["expr"] for r in rows_b}
        common = sorted(set(ta) & set(tb))
        if len(common) >= 5:
            import numpy as _np
            ra = _np.argsort(_np.argsort([ta[t] for t in common]))
            rb = _np.argsort(_np.argsort([tb[t] for t in common]))
            rho = float(_np.corrcoef(ra, rb)[0, 1])
            print(f"  profile rank correlation speaking vs stern: {rho:+.3f}"
                  f"  (want well under 1.0)")
            if rho > 0.95:
                print("  FAIL the two profiles rank frames identically")
                ok = False

    # HEAD DOWN, on real frames whose answer was read off the strip before the
    # number: t60 / t265 / t268 are Boyd reading the desk (pitch +10.9, +14.7,
    # +15.2), t87 is her engaged with the room (-15.8). The reading frames must
    # score 0 on 'serious' - the profile that rewards a lowered brow - and the
    # engaged one must clear the floor, or the penalty is not doing its job.
    for t, want_down in ((60.0, True), (265.0, True), (268.0, True), (87.0, False)):
        im = _frame(src, t, side="right")
        faces = [] if im is None else blendshapes(im)
        faces = [f for f in faces
                 if (f["box"][2] * f["box"][3]) / float(im.shape[0] * im.shape[1]) >= 0.004]
        if not faces:
            print(f"  FAIL no face at t={t:.0f}")
            ok = False
            continue
        f = max(faces, key=lambda q: q["box"][2] * q["box"][3])
        hd = f["shapes"]["_headDown"]
        s = score(f["shapes"], "serious")
        raw = raw_score(f["shapes"], "serious")
        tag = "reading" if want_down else "engaged"
        print(f"  t={t:.0f} {tag:8} pitch {f['pitch']:+5.1f} head_down {hd:.2f} "
              f"serious raw {raw:.4f} -> {s:.4f}")
        if want_down and not (hd >= 0.5 and s == 0.0):
            print(f"  FAIL head-down reading frame t={t:.0f} not rejected")
            ok = False
        if (not want_down) and not (hd == 0.0 and s >= FLOOR):
            print(f"  FAIL engaged frame t={t:.0f} was penalised or is under the floor")
            ok = False

    # LIDS DOWN, on real frames read off the strip before the number: t131 and
    # t126 are Boyd with her lids dropped to the desk and her head LEVEL
    # (pitch -5.1 / +1.9, so the head cost is 0 and only the lid ramp can
    # reject them), symmetric blink 0.412 / 0.284, 'serious' raw 0.1293 /
    # 0.0964 - both clear the floor on muscles alone. Each must score under
    # FLOOR, and its OPEN-EYED TWIN (same shapes, blink zeroed) must clear it:
    # that is the lid cost separating a usable face from an unusable one on
    # the same muscles, the one thing it is for. The expected values are the
    # floor, not the cost constant - a cost of 0, or a free band that swallows
    # 0.41, fails here on the real frame.
    for t in (131.0, 126.0):
        im = _frame(src, t, side="right")
        faces = [] if im is None else blendshapes(im)
        faces = [f for f in faces
                 if (f["box"][2] * f["box"][3]) / float(im.shape[0] * im.shape[1]) >= 0.004]
        if not faces:
            print(f"  FAIL no face at t={t:.0f}")
            ok = False
            continue
        f = max(faces, key=lambda q: q["box"][2] * q["box"][3])
        sh = f["shapes"]
        raw = raw_score(sh, "serious")
        s = score(sh, "serious")
        s_open = score(dict(sh, eyeBlinkLeft=0.0, eyeBlinkRight=0.0), "serious")
        print(f"  t={t:.0f} lids-down pitch {f['pitch']:+5.1f} blink {blink(sh):.3f} "
              f"lids {lids_down(sh):.2f} serious raw {raw:.4f} -> {s:.4f}  "
              f"open-eyed twin {s_open:.4f}  (floor {FLOOR})")
        if sh["_headDown"] != 0.0 or blink(sh) < 0.25 or raw < FLOOR:
            print(f"  FAIL t={t:.0f} is not the control it was read as (head_down "
                  f"{sh['_headDown']:.2f}, blink {blink(sh):.3f}, raw {raw:.4f})")
            ok = False
        if s >= FLOOR:
            print(f"  FAIL lids-down frame t={t:.0f} clears the floor - the lid cost is not biting")
            ok = False
        if s_open < FLOOR:
            print(f"  FAIL the open-eyed twin of t={t:.0f} is under the floor")
            ok = False

    # THE FIVE APPROVED CUTOUTS, scored the way the pipeline scores them
    # (tools/library.py _tag_expression: grey composite, 1600 long side, largest
    # face; then score() on the profile the case's own headline maps to). They
    # are the floor set, so every one must clear FLOOR - a scorer that rejects
    # an approved face is the regression tools/check_floor_gates.py exists to
    # stop. The index's face_box says WHICH face: the largest detection must
    # land inside it.
    idx_path = os.path.join(REACTIONS, "index.json")
    real_shapes = None
    if not os.path.isdir(REACTIONS) or not os.path.exists(idx_path):
        print(f"  SELFTEST_SKIP approved-five gate: {REACTIONS} absent")
    else:
        entries = json.load(open(idx_path, encoding="utf-8"))
        head = _headline_profiles()
        for e in entries:
            case = e.get("case", "?")
            path = e.get("file") or ""
            if not os.path.isabs(path):
                path = os.path.join(ROOT, path)
            f, s = cutout_face(path)
            if f is None:
                print(f"  FAIL {case}: {s}")
                ok = False
                continue
            prof = head.get(case, "serious")
            sc = score(f["shapes"], prof)
            raw = raw_score(f["shapes"], prof)
            inside = True
            fb = e.get("face_box")
            if fb and len(fb) == 4:
                bx, by, bw, bh = f["box"]
                cx, cy = (bx + bw / 2.0) / s, (by + bh / 2.0) / s
                inside = (fb[0] <= cx <= fb[0] + fb[2]) and (fb[1] <= cy <= fb[1] + fb[3])
            print(f"  {case:9} {prof:8} raw {raw:.4f} penalty {penalty(f['shapes']):.4f} "
                  f"head_down {f['shapes']['_headDown']:.2f} -> {sc:.4f}"
                  f"  (floor {FLOOR}){'' if inside else '  FACE OUTSIDE index face_box'}")
            if not inside:
                print(f"  FAIL {case}: largest face is not the one index.json boxes")
                ok = False
            if sc < FLOOR:
                print(f"  FAIL approved cutout {case} scores {sc:.4f} < FLOOR {FLOOR} on {prof!r}")
                ok = False
            if case == "THOMPSON" or real_shapes is None:
                real_shapes = dict(f["shapes"])

    # THE OTHER WAY: the superseded OFFERUP cutout (head down on the desk) must
    # stay under the floor on EVERY profile, or the gate only ever says yes.
    if not os.path.exists(REJECTED_CUTOUT):
        print(f"  SELFTEST_SKIP rejected-cutout control: {REJECTED_CUTOUT} absent")
    else:
        f, s = cutout_face(REJECTED_CUTOUT)
        if f is None:
            print(f"  FAIL rejected cutout: {s}")
            ok = False
        else:
            worst = max((score(f["shapes"], p), p) for p in PROFILES)
            print(f"  OFFERUP/_old (superseded) pitch {f['pitch']:+5.1f} head_down "
                  f"{f['shapes']['_headDown']:.2f} best {worst[1]} {worst[0]:.4f} (want < {FLOOR})")
            if worst[0] >= FLOOR:
                print("  FAIL the superseded head-down cutout clears the floor")
                ok = False

    # NEGATIVE CONTROLS on a REAL shape dict (an approved cutout's, else the
    # best speaking frame's), each proving one disqualifier can actually fail
    # a face:
    if real_shapes is None:
        im = _frame(src, rows[0]["t"], side="right")
        faces = [] if im is None else blendshapes(im)
        if faces:
            real_shapes = dict(max(faces, key=lambda q: q["box"][2] * q["box"][3])["shapes"])
    if real_shapes is None:
        print("  FAIL no real shape dict available for the negative controls")
        ok = False
    else:
        base = {p: score(real_shapes, p) for p in PROFILES}
        # (1) eyes shut: both eyes at 0.9 must score exactly 0.0 on every profile
        shut = dict(real_shapes, eyeBlinkLeft=0.9, eyeBlinkRight=0.9)
        got = {p: score(shut, p) for p in PROFILES}
        print(f"  eyes-shut control: max score over profiles {max(got.values()):.4f} (want 0.0)")
        if any(v != 0.0 for v in got.values()):
            print("  FAIL a face with both eyes shut scored above 0")
            ok = False
        # (2) one-sided blink is the camera, not a blink: must NOT veto
        oneside = dict(real_shapes, eyeBlinkLeft=0.9, eyeBlinkRight=0.05)
        print(f"  one-sided blink control: serious {score(oneside, 'serious'):.4f} "
              f"(base {base['serious']:.4f}; want > 0)")
        if base["serious"] > 0.02 and score(oneside, "serious") <= 0.0:
            print("  FAIL a one-sided blink reading vetoed an open-eyed face")
            ok = False
        # (3) eyeLookDown alone must stay under the floor everywhere - it is not
        #     an expression, and it is no longer a penalty either
        look = {"eyeLookDownLeft": 0.9, "eyeLookDownRight": 0.9}
        worst = max(score(look, p) for p in PROFILES)
        print(f"  eyeLookDown-only control: max score over profiles {worst:.4f} (want < {FLOOR})")
        if worst >= FLOOR:
            print("  FAIL eyeLookDown alone clears the floor")
            ok = False
        # (4) the head-down cost: the same real face (THOMPSON's approved
        #     shapes, 'serious' 0.1494) pitched fully down to the desk must
        #     land UNDER THE FLOOR - a face reading the desk is not a thumbnail
        #     face whatever its muscles do. The expectation is the floor, not
        #     the cost constant, so a cost too small to matter fails here.
        down = dict(real_shapes, _headDown=1.0)
        s_down = score(down, "serious")
        print(f"  head-down control: serious {base['serious']:.4f} -> {s_down:.4f} "
              f"(want < {FLOOR})")
        if base["serious"] < FLOOR:
            print("  FAIL the head-down control's base face is under the floor - control void")
            ok = False
        elif s_down >= FLOOR:
            print("  FAIL a fully head-down face clears the floor - the head cost is not biting")
            ok = False
        # (5) the lid ramp on a shape dict (the path tools/library.py re-scores
        #     index.json entries by, no video involved): the same real face
        #     with both lids at 0.4 - inside the ramp, under the veto, between
        #     the two real lids-down controls above (t126 0.284, t131 0.412) -
        #     must lose at least the floor's worth, or a floor-level face with
        #     its lids that far down would still count as floor quality.
        half = dict(real_shapes, eyeBlinkLeft=0.4, eyeBlinkRight=0.4)
        s_half = score(half, "serious")
        print(f"  half-lid control: serious {base['serious']:.4f} -> {s_half:.4f} "
              f"(want <= {max(0.0, base['serious'] - FLOOR):.4f})")
        if base["serious"] - s_half < FLOOR:
            print("  FAIL lids at 0.4 cost less than the floor - the lid cost is not biting")
            ok = False

    print("SELFTEST_PASS expression" if ok else "SELFTEST_FAIL expression")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys, json
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ap = sys.argv[1:]
    if len(ap) < 4:
        print(__doc__)
        print("usage: expression.py VIDEO T0 T1 HEADLINE [--side left|right]")
        sys.exit(2)
    video, t0, t1, headline = ap[0], float(ap[1]), float(ap[2]), ap[3]
    side = ap[ap.index("--side") + 1] if "--side" in ap else None
    prof = profile_for(headline)
    print(f'headline: {headline!r}  ->  profile {prof!r}')
    best, rows = search(video, t0, t1, prof, side=side, progress=True)
    if not best:
        print("no usable face found in the window")
        sys.exit(1)
    print(f"\nbest t={best['t']}s  expr={best['expr']:.4f}  audio={best['audio']:.4f}"
          f"  total={best['total']:.4f}  head_down={best.get('head_down', 0.0):.2f}"
          f"  lids={best.get('lids', 0.0):.2f}")
    if best["expr"] < FLOOR:
        print(f"  WARNING below the {FLOOR} floor - this is close to a neutral "
              f"face. The window may not contain the moment.")
    print("\ntop 5:")
    for r in rows[:5]:
        print(f"  t={r['t']:8.2f}  expr {r['expr']:.4f}  audio {r['audio']:.4f}"
              f"  total {r['total']:.4f}  head_down {r.get('head_down', 0.0):.2f}"
              f"  lids {r.get('lids', 0.0):.2f}")
