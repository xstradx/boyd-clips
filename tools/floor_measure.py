# -*- coding: utf-8 -*-
"""Re-measure the thumbnail floor from the five accepted files, with the
gates' and the build's own functions, so the floor is a measurement and not a
description.

WHY THIS FILE EXISTS
Nathan, 2026-08-31: the five builds are *"the floor and minimum quality we
should put out"*. Project CLAUDE.md: *"House style is whatever
config/quality_floor.json measures on the five accepted builds - not a
description from memory"*. Until 2026-09-01 `per_case` / `envelope` in that
file came from a one-off pass whose script was never on disk, and its numbers
were not the gates' numbers (OFFERUP skin chroma 17.6/15.9 in the file vs
20.9/20.5 from `verify_build` gate I on the same JPEG). A floor nobody can
re-measure is a description from memory, and a gate tuned to a different
measurement than the floor cannot be checked against it.

WHAT IT MEASURES (definitions are also written into the file, `measured_by`)
    skin_chroma / face_blowout_pct   verify_build._face_stats(named file), the
                                     exact function gates I and J read, so the
                                     floor and the gates agree by construction.
                                     The pair is [judge, defendant], assigned by
                                     side the way gate F assigns them (face
                                     centre x >= W/2 is the judge). On MONKEY
                                     the left face is the spider monkey - YuNet
                                     detects it at 0.87 and gate J reads it too.
    subject_L / background_L         mean Lab L* (OpenCV 0-255) of
                                     <named file>.photo.jpg - the pre-graphics
                                     canvas tools/thumb.py writes beside EVERY
                                     build (the `.photo.jpg` save just before
                                     "GRAPHICS, on a finished photo") and the
                                     image its SEPARATION SOLVE measures - over
                                     subject = alpha > 0.5 and background =
                                     alpha < 0.15 with NO other exclusion:
                                     `_sm = _sa0 > 0.5; _bm = _sa0 < 0.15`, the
                                     solve's own two lines. Measured on the five
                                     `_NEW` builds, whose placed alphas match,
                                     this lands within 0.6 L* of the logged
                                     separation_solve.subject_L and within
                                     1.4 L* of its target (table below).
                                     The first version of this tool measured
                                     the finished JPEG with verify_build's
                                     _ink_mask excluded. That mask is a colour
                                     heuristic (yellow / red / white, dilated
                                     13 px) built for gate K/L edge visibility;
                                     on the floor files it also removed the
                                     defendant's orange jumpsuit (THOMPSON,
                                     73k px hit the "red" test) and the blown
                                     face highlights (MONKEY, 18k px "white") -
                                     17-40 % of the subject - and read
                                     THOMPSON's subject at 68.0 where the
                                     solve's own number is 94.2. Refuted
                                     2026-09-01; this version is the solve's.
    separation_dL                    subject_L - background_L. thumb.py's
                                     SEPARATION_DL aims for +18.6; four of the
                                     five accepted builds measure NEGATIVE
                                     (subjects darker than the plate) - the
                                     floor is what they measure, not the aim.
    contrast_sd                      std of L* over the whole named JPEG, ink
                                     included (the deliverable).
    grain_hf                         mean |L* - GaussianBlur(L*, sigma 1.0)|
                                     over the background mask of the .photo.jpg,
                                     L* units, unscaled. The photo carries the
                                     grain (thumb.py GRAIN) and no graphics, so
                                     type and arrow edges do not count as grain.

THE DEFINITION, CHECKED AGAINST THE BUILD'S OWN LOG, 2026-09-01
thumb.py logs `separation_solve` {subject_L, was, target, k} per build. On the
five builds whose placed alphas are on disk (the `_NEW` set, 08-31 12:13-12:14):

    build          log sL  log target |  measured sL  measured bL
    OFFERUP_NEW     126.5     107.9   |    126.1        107.2
    CARTHIEF_NEW    106.2      87.6   |    105.6         88.9
    SANCHEZ_NEW     117.1      98.5   |    116.7         98.6
    MONKEY_NEW      136.6     118.0   |    136.3        116.6
    THOMPSON_NEW    122.6     104.0   |    122.2        104.0

The residuals have causes: the log's subject_L is read before the grain and
the JPEG; the plate only reaches `target` away from the subject boundary,
because the solve blurs its scale map (sigma 3) so the band next to the
subject gets less than k (k > 1 leaves bL under target, k < 1 leaves it over).
The selftest re-checks this on every floor case that has its own log
(SOLVE_TOL_SUBJECT / SOLVE_TOL_BACKGROUND) and proves the v1 definition does
not pass it.

THE MASK, MEASURED 2026-09-01
The brief was "mask by verify_build._placed_alphas(work)". Measured before
trusting it: the `_placed_alpha_*.png` in four of the five work dirs were
written 12:13-12:14 on 08-31 by the `_NEW` builds (the rejected set), while the
floor files are the `_FINAL` builds from 09:09-09:37. Edge agreement between the
alpha boundary and the file's .photo.jpg (mean Sobel |grad L*| in a 7 px band
around the alpha > 0.5 boundary / mean outside it):

    matching build   OFFERUP_NEW 4.67  CARTHIEF_NEW 4.50  SANCHEZ_NEW 3.89
                     MONKEY_NEW 4.22  THOMPSON_NEW 3.52
    other build      CARTHIEF_FINAL 1.65  SANCHEZ_FINAL 1.18  MONKEY_FINAL 1.85
                     THOMPSON_FINAL 1.39
    shifted 40 px    0.94-1.49   (~1.0 = the boundary lies on nothing)

So the placed alpha is used only when it sits on the named file's own photo
(ALIGN_MIN 2.6, between the bands); otherwise the .photo.jpg is re-matted with
the pipeline's own matting model (tools/matting.py, birefnet-matting, local,
measured deterministic: repeated runs byte-identical) and the file records
which mask each case got. Re-matte the PHOTO, not the finished JPEG: on
OFFERUP, where the placed alpha exists, rematte(photo) reads 126.1 / 107.0
against the placed 126.1 / 107.2, while rematte(final) reads 122.3 / 110.1 -
the title and arrow pull the matte.

The 08-31 numbers are NOT reproducible: no simple definition (Lab L*, gray or
luma std; |L - blur| at sigma 0.7/1.0/1.6, Laplacian, over the file or its
.photo.jpg sibling) lands on their contrast_sd 75-77 or grain_hf 23-25, and
their subject/background L do not match either mask on either file.

    python tools/floor_measure.py            # measure, print the table, write
    python tools/floor_measure.py --check    # FLOOR_MEASURE_OK / _STALE <diffs>
    python tools/floor_measure.py --selftest # SELFTEST_PASS/FAIL floor_measure

Writing changes the thumbnail floor hash (tools/floor_stamp.py); a build
stamped under the old file is stale and is rebuilt before it is shown.
"""
import hashlib
import io
import json
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FLOOR = os.path.join(ROOT, "config", "quality_floor.json")
MEDIA = "D:/Boyd Clips"
TOOL = "tools/floor_measure.py"

TOL = 0.15          # JPEG decode, YuNet and the local matte are deterministic
                    # here; anything past rounding (0.05) is a different file
                    # or a different function
SUBJECT_A = 0.5     # thumb.py SEPARATION SOLVE: _sm = _sa0 > 0.5
BACKGROUND_A = 0.15 # thumb.py SEPARATION SOLVE: _bm = _sa0 < 0.15
GRAIN_SIGMA = 1.0
ALIGN_MIN = 2.6     # on the .photo.jpg: matching alphas 3.52-4.67, other
                    # builds' alphas 1.18-1.85, a 40 px shift 0.94-1.49
                    # (docstring); 2.6 sits between the bands
BAND = 7            # +-3px around the alpha boundary for the alignment score
LOG_WINDOW_S = 5.0  # _build_log.json names no output; it belongs to the named
                    # file when both were written by the same build - measured
                    # 0.002 s apart on OFFERUP, 3 h apart on the _FINAL four
SOLVE_TOL_SUBJECT = 1.0     # measured 0.3-0.6 on the five _NEW builds (docstring)
SOLVE_TOL_BACKGROUND = 2.0  # measured 0.0-1.4 on the same five

METRICS = ("subject_L", "background_L", "separation_dL", "skin_chroma",
           "face_blowout_pct", "grain_hf", "contrast_sd")
PAIRED = ("skin_chroma", "face_blowout_pct")
# the envelope keeps the file's existing key order
ENVELOPE_ORDER = ("separation_dL", "grain_hf", "contrast_sd", "subject_L",
                  "background_L", "skin_chroma", "face_blowout_pct")
DEFINITIONS = {
    "subject_L": "mean Lab L* (OpenCV 0-255) of <named file>.photo.jpg - the pre-graphics canvas thumb.py writes beside every build and the image its SEPARATION SOLVE measures - where subject alpha > 0.5, no other exclusion (the solve's own mask); reproduces the logged separation_solve.subject_L within 0.6 on every build that has a log",
    "background_L": "mean Lab L* of the same .photo.jpg where subject alpha < 0.15 (the solve's own plate mask); within 1.4 of the logged separation_solve.target on every build that has a log",
    "separation_dL": "subject_L - background_L (positive = subjects brighter than the plate; thumb.py SEPARATION_DL aims for +18.6, four of the five accepted builds measure negative)",
    "skin_chroma": "[judge, defendant] verify_build._face_stats chroma on the named JPEG: mean sqrt(a*^2+b*^2) over YCrCb skin pixels of each of the two largest YuNet faces; judge = face centre x >= W/2 (gate F's rule); on MONKEY the defendant-side face is the spider monkey",
    "face_blowout_pct": "[judge, defendant] verify_build._face_stats blowout on the named JPEG: percent of face-box pixels with L* > 210",
    "grain_hf": "mean |L* - GaussianBlur(L*, sigma=1.0)| over the background mask (alpha < 0.15) of the .photo.jpg, L* units, unscaled; the photo carries the grain and no graphics, so type and arrow edges do not count",
    "contrast_sd": "standard deviation of L* over the whole named JPEG, ink included (the deliverable)",
    "alpha_align": "mean Sobel |grad L*| of the .photo.jpg in a 7px band around the alpha > 0.5 boundary / mean outside it; >= 2.6 means the mask sits on that photo's own edges (matching builds 3.5-4.7, other builds 1.2-1.9, a 40px shift 0.9-1.5)",
    "mask_source": "placed_alpha = verify_build._placed_alphas(work) (the build's own mattes, used when alpha_align.placed >= 2.6); rematte(photo) = tools/matting.py over the .photo.jpg with thumb_pipeline's ALPHA_FLOOR/CEIL stretch, used when the work dir's alphas belong to another build",
    "solve_log": "the work dir's _build_log.json separation_solve {subject_L, target}, only when that log was written by the same build as the named file (mtime within 5 s); null = the log belongs to a later build. Where present, measured subject_L / background_L must land within 1.0 / 2.0 of it (selftest)",
}


class PhotoMissing(FileNotFoundError):
    """The named file has no .photo.jpg beside it - the solve's image."""


def _load(path=FLOOR):
    return json.load(io.open(path, encoding="utf-8"))


def _r1(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 1)


def _r2(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 2)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:12]


def _lab_L(im):
    return cv2.cvtColor(im, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)


def photo_path(out_jpg):
    """thumb.py: `os.path.splitext(out_path)[0] + ".photo.jpg"` - written for
    every build, at the deliverable's JPEG quality, before any graphics."""
    return os.path.splitext(out_jpg)[0] + ".photo.jpg"


def build_log_for(out_jpg, window_s=LOG_WINDOW_S):
    """The work dir's _build_log.json, only when the same build wrote it and
    the named file (the log names no output; mtime within window_s is the
    link). None when the log belongs to a later build."""
    p = os.path.join(os.path.dirname(out_jpg), "_build_log.json")
    if not os.path.isfile(p):
        return None
    if abs(os.path.getmtime(p) - os.path.getmtime(out_jpg)) > window_s:
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return None


def reference_build(work, window_s=LOG_WINDOW_S):
    """The build in `work` that its _build_log.json describes - the JPEG
    written within window_s of the log that also has its .photo.jpg and the
    placed alphas beside it - or None. Whatever the floor names, this is a
    build whose own logged separation_solve can be re-measured, so the
    selftest's proof that the definition is thumb.py's does not depend on a
    floor file still being the last build in its dir."""
    log_p = os.path.join(work, "_build_log.json")
    if not os.path.isfile(log_p):
        return None
    t = os.path.getmtime(log_p)
    cands = []
    for n in os.listdir(work):
        if not n.lower().endswith(".jpg") or n.lower().endswith(".photo.jpg"):
            continue
        p = os.path.join(work, n)
        if abs(os.path.getmtime(p) - t) <= window_s and os.path.isfile(photo_path(p)):
            cands.append((abs(os.path.getmtime(p) - t), p))
    if not cands:
        return None
    p = min(cands)[1]
    log = build_log_for(p, window_s)
    ss = (log or {}).get("separation_solve") or {}
    if "subject_L" not in ss or "target" not in ss:
        return None
    pim = cv2.imread(photo_path(p))
    if pim is None or placed_subject_alpha(work, pim.shape) is None:
        return None
    return {"jpg": p, "photo": photo_path(p), "subject_L": ss["subject_L"], "target": ss["target"]}


# --------------------------------------------------------------- the mask --
def alpha_alignment(L, alpha):
    """Does this alpha's boundary sit on the image's own edges? ~1.0 = no."""
    core = (alpha > SUBJECT_A).astype(np.uint8)
    k = np.ones((BAND, BAND), np.uint8)
    band = (cv2.dilate(core, k) - cv2.erode(core, k)).astype(bool)
    if band.sum() < 100 or (~band).sum() < 100:
        return 0.0
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1)
    g = np.sqrt(gx * gx + gy * gy)
    return float(g[band].mean() / max(g[~band].mean(), 1e-6))


def placed_subject_alpha(work, shape):
    """max(judge, defendant) of the build's placed alphas, 0..1, as thumb.py
    forms _subject_alpha - or None when the work dir has none / wrong size."""
    import verify_build as VB
    al = VB._placed_alphas(work)
    if not al:
        return None
    a = None
    for v in al.values():
        if v.shape[:2] != shape[:2]:
            return None
        v = v.astype(np.float32) / 255.0
        a = v if a is None else np.maximum(a, v)
    return a


def rematte(im):
    """The pipeline's own matting model over an image, with the same gentle
    alpha stretch thumb_pipeline.matte applies (ALPHA_FLOOR/CEIL)."""
    import matting
    if not matting.available():
        return None
    import thumb_pipeline as P
    a = matting.alpha(im).astype(np.float32)
    a = np.clip((a - P.ALPHA_FLOOR) * (255.0 / (P.ALPHA_CEIL - P.ALPHA_FLOOR)), 0, 255)
    return a / 255.0


def subject_alpha(work, photo_im, photo_L):
    """(alpha 0..1 or None, provenance dict). The placed alpha when it sits
    on this photo's edges; otherwise the photo re-matted."""
    prov = {"mask_source": None, "align_placed": None, "align_used": None}
    placed = placed_subject_alpha(work, photo_im.shape)
    if placed is not None:
        prov["align_placed"] = _r2(alpha_alignment(photo_L, placed))
        if prov["align_placed"] >= ALIGN_MIN:
            prov["mask_source"] = "placed_alpha"
            prov["align_used"] = prov["align_placed"]
            return placed, prov
    a = rematte(photo_im)
    if a is None:
        prov["mask_source"] = "none (placed alpha misaligned or absent; matting model absent)"
        return None, prov
    prov["align_used"] = _r2(alpha_alignment(photo_L, a))
    prov["mask_source"] = "rematte(photo)" if prov["align_used"] >= ALIGN_MIN else "rematte(photo) (UNALIGNED)"
    return a, prov


ALIGNED_SOURCES = ("placed_alpha", "rematte(photo)")


# ------------------------------------------------------------- the faces --
def face_pair(out_jpg, im):
    """[judge, defendant] pairs of (chroma, blowout) from verify_build's own
    _face_stats. It returns the two largest faces in size order without their
    boxes, so the same detector call (same YuNet, same 0.6/0.3/5000) is made
    again here to learn which of the two is on which side."""
    import verify_build as VB
    import thumb_pipeline as P
    st = VB._face_stats(out_jpg)
    if not st:
        return None
    h, w = im.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(im)
    rows = sorted(r, key=lambda q: -q[3])[:2] if r is not None else []
    sides = ["judge" if (b[0] + b[2] / 2) >= w / 2 else "defendant" for b in rows]
    out = {}
    for who, (ch, bl) in zip(sides, st):
        out.setdefault(who, (ch, bl))
    if "judge" not in out or "defendant" not in out:
        return None   # both subjects on one side: not a two-up
    return out


# ------------------------------------------------------------ one case --
def solve_numbers(photo_L, alpha):
    """subject_L / background_L / separation_dL / grain_hf exactly as the
    SEPARATION SOLVE forms its masks, on the photo it measures. None when a
    mask is under thumb.py's own 500 px minimum."""
    sm = alpha > SUBJECT_A
    bm = alpha < BACKGROUND_A
    if sm.sum() <= 500 or bm.sum() <= 500:
        return None
    sL, bL = float(photo_L[sm].mean()), float(photo_L[bm].mean())
    hf = np.abs(photo_L - cv2.GaussianBlur(photo_L, (0, 0), GRAIN_SIGMA))
    return {"subject_L": _r1(sL), "background_L": _r1(bL),
            "separation_dL": _r1(_r1(sL) - _r1(bL)), "grain_hf": _r2(hf[bm].mean())}


def measure_case(case, out_jpg):
    """Every metric for one accepted file. Raises FileNotFoundError (the
    named file) or PhotoMissing (its .photo.jpg) - both are reported by the
    caller, never skipped."""
    if not os.path.isfile(out_jpg):
        raise FileNotFoundError(out_jpg)
    photo = photo_path(out_jpg)
    if not os.path.isfile(photo):
        raise PhotoMissing(photo)
    im = cv2.imread(out_jpg)
    if im is None:
        raise FileNotFoundError(f"unreadable: {out_jpg}")
    pim = cv2.imread(photo)
    if pim is None or pim.shape[:2] != im.shape[:2]:
        raise PhotoMissing(f"unreadable or not the named file's size: {photo}")
    work = os.path.dirname(out_jpg)
    L, pL = _lab_L(im), _lab_L(pim)
    alpha, prov = subject_alpha(work, pim, pL)
    m = {"subject_L": None, "background_L": None, "separation_dL": None,
         "grain_hf": None}
    if alpha is not None and prov["mask_source"] in ALIGNED_SOURCES:
        m.update(solve_numbers(pL, alpha) or {})
    faces = face_pair(out_jpg, im)
    if faces:
        m["skin_chroma"] = [_r1(faces["judge"][0]), _r1(faces["defendant"][0])]
        m["face_blowout_pct"] = [_r1(faces["judge"][1]), _r1(faces["defendant"][1])]
    else:
        m["skin_chroma"] = None
        m["face_blowout_pct"] = None
    m["contrast_sd"] = _r1(L.std())
    ordered = {k: m[k] for k in METRICS}
    ss = (build_log_for(out_jpg) or {}).get("separation_solve") or {}
    prov["solve_log"] = ({"subject_L": ss["subject_L"], "target": ss["target"]}
                         if "subject_L" in ss and "target" in ss else None)
    prov["file_sha256"] = _sha(out_jpg)
    prov["photo_sha256"] = _sha(photo)
    return ordered, prov


def measure_all(floor, verbose=True):
    """(per_case, provenance, problems). A case whose file or .photo.jpg is
    not on disk is a problem line, not a skipped row."""
    files = floor.get("files") or {}
    per_case, prov, problems = {}, {}, []
    for case in floor.get("approved", []):
        rel = files.get(case)
        if not rel:
            problems.append(f"NO FILE      {case}: approved but quality_floor.json['files'] does not name its file")
            continue
        out = os.path.join(MEDIA, rel)
        try:
            per_case[case], prov[case] = measure_case(case, out)
        except PhotoMissing as e:
            problems.append(f"NO PHOTO     {case}: {e} - thumb.py writes it beside every build; the solve is measured on it")
        except FileNotFoundError as e:
            problems.append(f"MISSING      {case}: {e} is not on disk")
    if verbose:
        print_table(per_case, prov)
        for p in problems:
            print("  " + p)
    return per_case, prov, problems


def print_table(per_case, prov):
    print(f"  {'case':9} {'subjL':>6} {'bgL':>6} {'dL':>6} {'chroma J/D':>11} "
          f"{'blowout J/D':>11} {'grain':>6} {'sd':>5}  mask (align)  solve log sL/target")
    for c, m in per_case.items():
        def f(v, w=6, nd=1):
            return f"{'-':>{w}}" if v is None else f"{v:{w}.{nd}f}"
        pair = lambda p: "-" if not p else "/".join("-" if v is None else f"{v:.1f}" for v in p)
        p = prov.get(c, {})
        sl = p.get("solve_log")
        sl = "-" if not sl else f"{sl['subject_L']:.1f}/{sl['target']:.1f}"
        print(f"  {c:9} {f(m['subject_L'])} {f(m['background_L'])} {f(m['separation_dL'])} "
              f"{pair(m['skin_chroma']):>11} {pair(m['face_blowout_pct']):>11} "
              f"{f(m['grain_hf'], 6, 2)} {f(m['contrast_sd'], 5)}  "
              f"{p.get('mask_source')} ({p.get('align_used')}; placed {p.get('align_placed')})  {sl}")


# ------------------------------------------------------------- envelope --
def envelope(per_case):
    """min / median / max of every metric over the cases. Paired metrics pool
    both faces (10 values) - the max is what the gates are tuned against."""
    env = {}
    for k in ENVELOPE_ORDER:
        vals = []
        for m in per_case.values():
            v = m.get(k)
            if k in PAIRED:
                vals += [x for x in (v or []) if x is not None]
            elif v is not None:
                vals.append(v)
        if not vals:
            env[k] = {"min": None, "median": None, "max": None}
            continue
        nd = 2 if k == "grain_hf" else 1
        env[k] = {"min": round(min(vals), nd),
                  "median": round(float(np.median(vals)), nd),
                  "max": round(max(vals), nd)}
    return env


# -------------------------------------------------------------- compare --
def _diff(a, b):
    if a is None and b is None:
        return None
    if a is None or b is None:
        return f"{a} vs {b}"
    return None if abs(float(a) - float(b)) <= TOL else f"{b} -> {a}"


def compare(measured, floor, problems=()):
    """Metric-level diffs between a fresh measurement and the file's per_case
    and envelope. Empty list = FLOOR_MEASURE_OK."""
    diffs = list(problems)
    got_pc = floor.get("per_case") or {}
    for case in floor.get("approved", []):
        if case not in measured:
            continue   # already a MISSING / NO FILE / NO PHOTO problem
        have = got_pc.get(case)
        if not have:
            diffs.append(f"{case}: not in per_case")
            continue
        for k in METRICS:
            a, b = measured[case].get(k), have.get(k)
            if k in PAIRED:
                a = a or [None, None]
                b = b or [None, None]
                for i, who in enumerate(("judge", "defendant")):
                    d = _diff(a[i], b[i] if i < len(b) else None)
                    if d:
                        diffs.append(f"{case}.{k}[{who}] {d}")
            else:
                d = _diff(a, b)
                if d:
                    diffs.append(f"{case}.{k} {d}")
    for case in got_pc:
        if case not in floor.get("approved", []):
            diffs.append(f"{case}: in per_case but not approved")
    env_now, env_file = envelope(measured), floor.get("envelope") or {}
    for k, stats in env_now.items():
        for s, v in stats.items():
            d = _diff(v, (env_file.get(k) or {}).get(s))
            if d:
                diffs.append(f"envelope.{k}.{s} {d}")
    return diffs


def solve_log_diffs(per_case, prov):
    """Where a floor case carries its own build log, the measured pair must
    reproduce the logged solve. Returns (checked cases, diff lines)."""
    checked, diffs = [], []
    for c, p in prov.items():
        sl = p.get("solve_log")
        m = per_case.get(c) or {}
        if not sl or m.get("subject_L") is None:
            continue
        checked.append(c)
        ds = abs(m["subject_L"] - sl["subject_L"])
        db = abs(m["background_L"] - sl["target"])
        if ds > SOLVE_TOL_SUBJECT:
            diffs.append(f"{c}.subject_L {m['subject_L']} vs logged solve {sl['subject_L']} (> {SOLVE_TOL_SUBJECT})")
        if db > SOLVE_TOL_BACKGROUND:
            diffs.append(f"{c}.background_L {m['background_L']} vs logged target {sl['target']} (> {SOLVE_TOL_BACKGROUND})")
    return checked, diffs


def measured_by(prov):
    return {
        "tool": TOOL,
        "date": time.strftime("%Y-%m-%d"),
        "definitions": dict(DEFINITIONS),
        "mask_source": {c: p["mask_source"] for c, p in prov.items()},
        "alpha_align": {c: {"placed": p["align_placed"], "used": p["align_used"]}
                        for c, p in prov.items()},
        "solve_log": {c: p.get("solve_log") for c, p in prov.items()},
        "file_sha256": {c: p["file_sha256"] for c, p in prov.items()},
        "photo_sha256": {c: p["photo_sha256"] for c, p in prov.items()},
    }


NOTE = ("per_case / envelope re-measured by tools/floor_measure.py (measured_by "
        "names the date, the definitions, the mask each case got and the build "
        "log each was checked against). Replaces the 2026-08-31 one-off pass, "
        "whose script was never on disk and whose numbers are not reproducible "
        "from any file in thumbwork: its skin_chroma / face_blowout were not "
        "verify_build's (OFFERUP 17.6/15.9 vs 20.9/20.5 from gate I on the same "
        "JPEG), and no simple definition lands on its contrast_sd 75-77 or "
        "grain_hf 23-25. skin_chroma and face_blowout_pct are now "
        "verify_build._face_stats itself, so gate I (ceiling 25.5) and gate J "
        "(12.0) are tuned to these same functions - the floor and the gates agree "
        "by construction; tools/check_floor_gates.py checks the gates against the "
        "same files. subject_L / background_L / separation_dL / grain_hf are "
        "thumb.py's SEPARATION SOLVE measurement: mean L* of <file>.photo.jpg (the "
        "pre-graphics canvas thumb.py writes beside every build) over alpha > 0.5 / "
        "alpha < 0.15 with no other exclusion - on OFFERUP, whose _build_log.json "
        "is its own, this reproduces the logged solve (126.5 / 107.9) to 0.4 / 0.7. "
        "The 2026-09-01 first version of this tool measured the finished JPEG with "
        "verify_build._ink_mask excluded, which also removed jumpsuit and face "
        "highlights (17-40 % of the subject) and read THOMPSON's subject at 68.0; "
        "refuted the same day, see the tool's docstring. The placed alpha is used "
        "only where it sits on the named file's photo (OFFERUP); the other four work "
        "dirs hold the _NEW builds' alphas, so their _FINAL photos are re-matted with "
        "tools/matting.py (see mask_source). Four of the five accepted builds have "
        "the plate BRIGHTER than the subjects (separation_dL negative); thumb.py "
        "SEPARATION_DL = +18.6 describes OFFERUP only. Rewriting this file moves the "
        "thumbnail floor hash (tools/floor_stamp.py).")


def write(floor, per_case, prov, path=FLOOR, force=False):
    """Assign only the owned keys; every other key and its order is preserved
    byte-for-byte (json round-trips the file identically)."""
    new_env = envelope(per_case)
    new_mb = measured_by(prov)
    if not force:
        old_mb = dict(floor.get("measured_by") or {})
        same = (floor.get("per_case") == per_case and floor.get("envelope") == new_env
                and floor.get("measurement_note") == NOTE
                and {k: v for k, v in old_mb.items() if k != "date"}
                == {k: v for k, v in new_mb.items() if k != "date"})
        if same:
            print("  unchanged - not rewritten (the floor hash stays put)")
            return False
    floor["per_case"] = per_case
    floor["envelope"] = new_env
    floor["measurement_note"] = NOTE
    floor["measured_by"] = new_mb
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(floor, indent=1, ensure_ascii=False) + "\n")
    return True


def check(measured=None, prov=None, problems=None, floor=None, verbose=True):
    floor = floor or _load()
    if measured is None:
        measured, prov, problems = measure_all(floor, verbose=verbose)
    diffs = compare(measured, floor, problems or [])
    diffs += solve_log_diffs(measured, prov or {})[1]
    if verbose:
        print("FLOOR_MEASURE_OK" if not diffs else "FLOOR_MEASURE_STALE " + "; ".join(diffs))
    return (not diffs), diffs


# -------------------------------------------------------------- selftest --
def selftest():
    """Measures the five ONCE and reuses the result. Proves: --check passes on
    a freshly written copy and on the real file; fails on a tampered copy (one
    number moved by 3.0, in a plain metric and inside a pair); a missing,
    unnamed or photo-less floor file is reported, not skipped; the alignment
    score can fail (a 40px shift of a real alpha); the measured pair reproduces
    the build's own logged solve where a log exists, and the v1 definition
    (finished JPEG, ink excluded) does not; the envelope gives a known answer."""
    import copy
    import shutil
    import tempfile
    ok = True

    def chk(label, got, want, why=""):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:56} -> {got} (want {want})")
        if not hit and why:
            print(f"        {why}")

    # 1. the envelope, known answer, before anything real is read
    fake = {"A": {"subject_L": 1.0, "background_L": 3.0, "separation_dL": -2.0,
                  "skin_chroma": [10.0, 20.0], "face_blowout_pct": [0.0, 5.0],
                  "grain_hf": 1.11, "contrast_sd": 70.0},
            "B": {"subject_L": 2.0, "background_L": 1.0, "separation_dL": 1.0,
                  "skin_chroma": [15.0, 30.0], "face_blowout_pct": [1.0, 2.0],
                  "grain_hf": 2.22, "contrast_sd": 72.0},
            "C": {"subject_L": 9.0, "background_L": 2.0, "separation_dL": 7.0,
                  "skin_chroma": [12.0, 25.0], "face_blowout_pct": [3.0, 4.0],
                  "grain_hf": 3.33, "contrast_sd": 71.0}}
    env = envelope(fake)
    chk("envelope subject_L min/median/max", (env["subject_L"]["min"], env["subject_L"]["median"], env["subject_L"]["max"]), (1.0, 2.0, 9.0))
    chk("envelope pools both faces for skin_chroma", (env["skin_chroma"]["min"], env["skin_chroma"]["median"], env["skin_chroma"]["max"]), (10.0, 17.5, 30.0))
    chk("envelope key order is the file's", tuple(env), ENVELOPE_ORDER)

    # 2. a missing floor file is reported, not skipped; so is an unnamed one
    ghost = {"approved": ["GHOST", "NONAME"], "files": {"GHOST": "thumbwork/GHOST/GHOST_FINAL.jpg"}}
    pc, pv, probs = measure_all(ghost, verbose=False)
    chk("missing floor file is a MISSING problem", any(p.startswith("MISSING") and "GHOST" in p for p in probs), True, "; ".join(probs))
    chk("approved case without a file is a NO FILE problem", any(p.startswith("NO FILE") and "NONAME" in p for p in probs), True, "; ".join(probs))
    chk("  ...and neither produced a row", pc, {})
    good, diffs = check(pc, pv, probs, floor=dict(ghost, per_case={}, envelope={}), verbose=False)
    chk("  ...and --check is STALE, not OK", good, False, "; ".join(diffs))

    # 3. the real measurement, once
    real = _load()
    t0 = time.time()
    per_case, prov, problems = measure_all(real, verbose=True)
    print(f"  measured {len(per_case)} case(s) in {time.time() - t0:.1f}s")
    chk("every approved file measured", sorted(per_case), sorted(real.get("approved", [])), "; ".join(problems))
    chk("every case got an aligned mask", all(p["mask_source"] in ALIGNED_SOURCES for p in prov.values()), True,
        str({c: p["mask_source"] for c, p in prov.items()}))
    chk("every case has a [judge, defendant] chroma pair", all(m["skin_chroma"] and len(m["skin_chroma"]) == 2 for m in per_case.values()), True)

    # 3b. a floor file with no .photo.jpg beside it is a NO PHOTO problem: the
    #     named JPEG alone cannot give the solve's numbers. A copy of a real
    #     floor file in a temp dir, without its sibling. os.path.join(MEDIA,
    #     <absolute path>) is that absolute path, so 'files' can point at it.
    tmp = tempfile.mkdtemp(prefix="floor_measure_")
    try:
        some_real = os.path.join(MEDIA, real["files"][next(iter(per_case))])
        lone = os.path.join(tmp, "LONE.jpg")
        shutil.copy(some_real, lone)
        pc2, pv2, probs2 = measure_all({"approved": ["LONE"], "files": {"LONE": lone}}, verbose=False)
        chk("floor file without its .photo.jpg is a NO PHOTO problem", any(p.startswith("NO PHOTO") and "LONE" in p for p in probs2), True, "; ".join(probs2))
        chk("  ...and produced no row", pc2, {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4. the alignment score can fail: shift a real placed alpha by 40px (on
    #    the photo, where the score is taken)
    some = next((c for c, p in prov.items() if p["align_placed"] is not None), None)
    if some:
        out = os.path.join(MEDIA, real["files"][some])
        pim = cv2.imread(photo_path(out))
        pL = _lab_L(pim)
        a = placed_subject_alpha(os.path.dirname(out), pim.shape)
        shifted = np.roll(a, 40, axis=1)
        chk(f"alignment of {some}'s own alpha is >= {ALIGN_MIN}", alpha_alignment(pL, a) >= ALIGN_MIN, True, f"{alpha_alignment(pL, a):.2f}")
        chk("  ...and the same alpha shifted 40px is not", alpha_alignment(pL, shifted) < ALIGN_MIN, True, f"{alpha_alignment(pL, shifted):.2f}")
    else:
        chk("alignment control: some case has a placed alpha", False, True)

    # 5. the definition is thumb.py's own. Proved on a build whose logged
    #    separation_solve can be re-measured (the last build in any approved
    #    work dir that has its log, its .photo.jpg and its placed alphas -
    #    whichever build that is today): solve_numbers() must land within
    #    SOLVE_TOL_* of the log, and the v1 definition (finished JPEG,
    #    verify_build._ink_mask excluded) must NOT, or the check is vacuous.
    ref = next((r for r in (reference_build(os.path.join(MEDIA, "thumbwork", c)) for c in real.get("approved", [])) if r), None)
    chk("some approved work dir holds a build with its own solve log", bool(ref), True,
        "no _build_log.json sits beside the JPEG + .photo.jpg + placed alphas it describes")
    if ref:
        pim = cv2.imread(ref["photo"])
        pL = _lab_L(pim)
        a = placed_subject_alpha(os.path.dirname(ref["jpg"]), pim.shape)
        got = solve_numbers(pL, a)
        ds, db = abs(got["subject_L"] - ref["subject_L"]), abs(got["background_L"] - ref["target"])
        chk(f"  {os.path.basename(ref['jpg'])}: subject_L within {SOLVE_TOL_SUBJECT} of the logged solve", ds <= SOLVE_TOL_SUBJECT, True,
            f"measured {got['subject_L']} vs logged {ref['subject_L']}")
        chk(f"  ...and background_L within {SOLVE_TOL_BACKGROUND} of the logged target", db <= SOLVE_TOL_BACKGROUND, True,
            f"measured {got['background_L']} vs logged target {ref['target']}")
        import verify_build as VB
        im = cv2.imread(ref["jpg"])
        old = float(_lab_L(im)[(a > SUBJECT_A) & ~VB._ink_mask(im)].mean())
        chk("  ...and v1's ink-excluded finished-JPEG subject_L does not", abs(old - ref["subject_L"]) > SOLVE_TOL_SUBJECT, True,
            f"v1 {old:.1f} vs logged {ref['subject_L']}")
    #    and where a FLOOR case carries its own log (OFFERUP today), --check
    #    holds its pair to the log too; a pair 3.0 off must fail that.
    checked, sdiffs = solve_log_diffs(per_case, prov)
    chk(f"floor cases with their own solve log reproduce it ({len(checked)} checked)", sdiffs, [], "; ".join(sdiffs))
    if checked:
        wrong = copy.deepcopy(per_case)
        wrong[checked[0]]["subject_L"] = round(wrong[checked[0]]["subject_L"] + 3.0, 1)
        chk("  ...and a pair 3.0 off the log fails the solve-log check", bool(solve_log_diffs(wrong, prov)[1]), True)

    # 6. fresh copy passes; tampered copies fail and name the metric
    tmp = tempfile.mkdtemp(prefix="floor_measure_")
    try:
        fresh = os.path.join(tmp, "quality_floor.json")
        shutil.copy(FLOOR, fresh)
        fl = _load(fresh)
        write(fl, copy.deepcopy(per_case), prov, path=fresh, force=True)
        fl = _load(fresh)
        good, diffs = check(per_case, prov, problems, floor=fl, verbose=False)
        chk("--check passes on the freshly written copy", good, True, "; ".join(diffs))
        keep = [k for k in real if k not in ("per_case", "envelope", "measurement_note", "measured_by")]
        chk("  ...and the other keys are byte-identical", {k: fl[k] for k in keep} == {k: real[k] for k in keep}, True,
            f"differ: {[k for k in keep if fl.get(k) != real.get(k)]}")
        chk("  ...in the same order", [k for k in fl][:len(keep)], keep)
        case0 = next(iter(per_case))
        bad = copy.deepcopy(fl)
        bad["per_case"][case0]["subject_L"] = round(bad["per_case"][case0]["subject_L"] + 3.0, 1)
        good, diffs = check(per_case, prov, problems, floor=bad, verbose=False)
        chk("tampered subject_L (+3.0) is STALE", good, False)
        chk("  ...and names the case and metric", any(d.startswith(f"{case0}.subject_L") for d in diffs), True, "; ".join(diffs))
        bad = copy.deepcopy(fl)
        bad["per_case"][case0]["skin_chroma"][1] = round(bad["per_case"][case0]["skin_chroma"][1] + 3.0, 1)
        good, diffs = check(per_case, prov, problems, floor=bad, verbose=False)
        chk("tampered defendant skin_chroma (+3.0) is STALE", good, False)
        chk("  ...and names the face", any(f"{case0}.skin_chroma[defendant]" in d for d in diffs), True, "; ".join(diffs))
        bad = copy.deepcopy(fl)
        bad["envelope"]["contrast_sd"]["max"] = round(bad["envelope"]["contrast_sd"]["max"] + 3.0, 1)
        good, diffs = check(per_case, prov, problems, floor=bad, verbose=False)
        chk("tampered envelope is STALE", good, False)
        # a rewrite with nothing new must not touch the file (floor hash)
        before = _sha(fresh)
        wrote = write(_load(fresh), copy.deepcopy(per_case), prov, path=fresh)
        chk("rewrite with identical numbers is a no-op", (wrote, _sha(fresh) == before), (False, True))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 7. the real file. Stale here means: run `python tools/floor_measure.py`.
    good, diffs = check(per_case, prov, problems, floor=real, verbose=False)
    chk("config/quality_floor.json matches a fresh measurement", good, True,
        "run `python tools/floor_measure.py` to re-measure: " + "; ".join(diffs))
    mb = real.get("measured_by") or {}
    chk("  ...and names this tool and its definitions", (mb.get("tool"), sorted(mb.get("definitions") or {}) == sorted(DEFINITIONS)), (TOOL, True))

    print("SELFTEST_PASS floor_measure" if ok else "SELFTEST_FAIL floor_measure")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    if "--check" in a:
        sys.exit(0 if check()[0] else 1)
    floor = _load()
    per_case, prov, problems = measure_all(floor)
    if problems or len(per_case) != len(floor.get("approved", [])):
        print("FLOOR_MEASURE_INCOMPLETE - not written: " + "; ".join(problems))
        sys.exit(1)
    unaligned = [c for c, p in prov.items() if p["mask_source"] not in ALIGNED_SOURCES]
    if unaligned:
        print("FLOOR_MEASURE_INCOMPLETE - no aligned mask for " + ", ".join(unaligned) + " - not written")
        sys.exit(1)
    checked, sdiffs = solve_log_diffs(per_case, prov)
    if sdiffs:
        print("FLOOR_MEASURE_INCOMPLETE - the measurement does not reproduce the build's own solve log: " + "; ".join(sdiffs) + " - not written")
        sys.exit(1)
    if write(floor, per_case, prov, force="--force" in a):
        print(f"  wrote {os.path.relpath(FLOOR, ROOT)} - the thumbnail floor hash moved (tools/floor_stamp.py)")
    sys.exit(0)
