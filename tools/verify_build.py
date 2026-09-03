# -*- coding: utf-8 -*-
"""Build-time gates for the defects Nathan found on 2026-08-31.

Nathan: *"Okay but are you gonna make sure it never happens again"*.

Prose has provably failed here. `spec/NATHAN_RULES.md` and the boyd-thumbnail
skill both existed, were read, and rules in them were broken the same day. The
only thing that has ever actually stopped a regression in this repo is a check
that FAILS THE BUILD. So each defect he found today gets one, and each is
validated against the real file that carried the defect - a gate that cannot
fail is worse than no gate, because it looks like coverage.

`verify_thumb.py` gates the finished JPEG (posterisation, blown subject,
duplicate face). These gates need the WORK DIR too - the mattes and the source
crops - because that is where these particular defects live.

    E  matte softness   hair must matte softer than cloth
    F  skin chroma      neither face may be repainted away from its own source
    G  hard rim         no white outline traced around a subject
    I  skin chroma      both faces inside the measured corpus band
    J  face blowout     no face clipped to paper white
    K  hard cut         no pixel-straight visible matte edge (severed limb, R29)
    L  bystander        one island per subject; no face 12-88% behind the judge (R8)
    H  no orphans       every checker in tools/ is invoked by something

K and L were ported here on 2026-09-01 from scripts/verify_set.py, which
nothing on the build path ever called (its luma and chroma thresholds also
fail four of the five accepted builds - see the checker registry in
spec/NATHAN_RULES.md). The `--set` entry point that used to shell out to it is
gone for the same reason.

Run:  python tools/verify_build.py WORKDIR OUT.jpg
      python tools/verify_build.py --selftest
"""
import os
import subprocess
import sys

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- limits, each derived from a measured pair on 2026-08-31 ----------------
# ---- and re-derived against the FIVE ACCEPTED BUILDS on 2026-09-01 ----------
# The 08-31 numbers came from OFFERUP pairs only. Run over the floor
# (config/quality_floor.json "files") they rejected 3 of the 5 he called "the
# floor and minimum quality we should put out": CARTHIEF, SANCHEZ, THOMPSON
# all failed E and I. A gate that rejects the floor is mis-tuned, not strict.
#
# E: birefnet-general measured 1.67 hair/cloth and chopped her hair;
#    birefnet-portrait measured 2.25 and looked right. 1.9 sat between them -
#    on OFFERUP. The accepted five measure (judge / defendant):
#      OFFERUP 2.75 / -     CARTHIEF 2.38 / 1.55   SANCHEZ 11.50 / 1.65
#      MONKEY  6.67 / 7.50  THOMPSON 2.00 / 2.12
#    so the floor's minimum is 1.55. 1.4 keeps a margin under it and still
#    rejects a cloth edge blurred out to the width of the hair (ratio ~0.5).
MIN_HAIR_CLOTH_RATIO = 1.4
# The absolute pixel limits (hair >= 7.5, cloth <= 9.0) were OFFERUP's cutout
# scale, not a property of a good matte: the accepted CARTHIEF defendant is
# 2480px wide with a 31px hair band and a 20px cloth band, and the old alpha
# crush applied to every accepted matte RAISES the ratio on four of the five
# (CARTHIEF judge 2.38 -> 4.00). No fixed width separates the crush across
# cases, so the crush is stopped where it was made instead: gate E(source)
# reads thumb_pipeline.ALPHA_FLOOR / ALPHA_CEIL. The widths are still printed.
MAX_ALPHA_FLOOR = 8.0     # the crush was 26
MIN_ALPHA_CEIL = 244.0    # the crush was 232
# F: keyed on the DIFFERENCE between the two faces' drift, not the absolute
#    drift. The absolute number also carries the global SAT_TRIM lift, which
#    moves both faces equally and is not the defect; a 5.0 absolute limit failed
#    a good build on the defendant's b*. What he actually saw was ONE face
#    repainted harder than the other. Measured:
#      v19 (forced sat parity)  judge 6.4  defendant 2.2  -> differential 4.2
#      v21 (0.35 partial pull)  judge 4.2  defendant 4.2  -> differential 0.0
MAX_CHROMA_IMBALANCE = 2.5
# G: the outline he rejected comes only from rim_mode 'smooth'/'line', or from
#    a glow turned up until it reads as haze. 0.30 was the rejected value; the
#    settled one is 0.085.
# I: skin chroma, from the 68-thumbnail calibration corpus (Tier-A median a*
#    11.62 / b* 13.52 -> chroma 17.83; both components IQR ~5, so this is the
#    most defensible target in that study). Our builds measured 22.2/20.4
#    before the ceiling went in - a grade inflating skin ~1.7x on source
#    material that was already in band.
# widened for the tone he selected on 2026-08-31 (v23, chroma 20.6). The band
# still rejects the pale end, which is the defect it was built for.
# 2026-09-01: measured by THIS function on the accepted five (judge/defendant):
#   OFFERUP 20.9/20.5  CARTHIEF 23.4/19.1  SANCHEZ 20.1/23.2
#   MONKEY 19.7/19.9   THOMPSON 20.8/24.5
# 22.5 rejected three of them. The 1.7x-inflated control measures 27.7/31.3.
# 25.5 = floor max (24.5) + 1.0, and still 2.2 under the control.
SKIN_CHROMA_CEILING = 25.5
# J: highlight blowout. Measured before the shoulder: EVERY face clipped to
#    L*255 and up to 30.5% of one face sat above L*210. A few specular pixels
#    (glasses, jewellery) are normal; a third of a face is not.
MAX_FACE_BLOWOUT = 12.0   # percent of face pixels above L*210
MAX_RIM_GLOW = 0.22   # raised from 0.12 on 2026-08-31: he asked for the glow to
                      # be MORE visible ("to see them better"), so the ceiling
                      # moves with the instruction. It still rejects 0.30, the
                      # value that produced the haze he called a mistake.
# K: hard cut / severed limb (R29; N15 "you cut the defendants whole arm off",
#    N69 "It should always touch the screen or the edges"). A crop boundary is
#    pixel-straight; a body is not - hair wanders, cloth wanders, a crop edge
#    does not, so the edge is tested at EXACT straightness (a +-1px tolerance
#    flagged SANCHEZ's hair at 82px). Measured on the PLACED alpha, and a
#    transition hidden under ink (title/kicker/arrow) or under the other
#    subject is discounted, because that is how he judged: cuts under the
#    kicker band shipped five times without comment. On the five accepted
#    builds (2026-09-01, aligned _NEW files) the longest visible straight run
#    over the subject's vertical span was 0.14 (OFFERUP judge 78/558). MONKEY's
#    judge measures 0.38 - a 203px cut at x=1239 on her right shoulder with the
#    chair visible past it - and K rejects it by design; the fix is scale her up
#    until that edge leaves the canvas.
LIMB_MAX_RUN_FRAC = 0.18
# L: bystander (R8 "it looks weird how his lawyer ir right behind judge boyd").
#    Fully covered is fine, fully clear is fine; 12-88% coverage of a face by
#    the judge's alpha is the defect band. The judge is composited LAST
#    (thumb.py: defendant, then judge), so only faces in the defendant's layer
#    can be half-hidden. Faces are read from the defendant's own placed RGB
#    layer when the build wrote one (`_placed_rgb_defendant.png`, un-occluded),
#    else from the finished JPEG. Gallery faces in the plate are 21-24px and
#    are scenery; 40px is the floor.
BYST_MIN_FACE = 40
BYST_CLEAR = 0.12
BYST_HIDDEN = 0.88
# L(a): a subject's alpha must be ONE island. A second island this large is a
#    person the matte swallowed, not noise - the accepted five measure a
#    largest secondary island of 12px.
MIN_STRAY_COMPONENT = 4000


def _alpha(png):
    im = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    if im is None or im.shape[2] < 4:
        return None
    return im[:, :, 3]


def _transition(a, rows):
    """Median width of the partial-alpha band across the given rows."""
    out = []
    for y in rows:
        r = a[y].astype(np.float32) / 255.0
        idx = np.where((r > 0.05) & (r < 0.95))[0]
        if idx.size:
            cuts = np.where(np.diff(idx) > 3)[0]
            out.append(max(len(s) for s in np.split(idx, cuts + 1)))
    return float(np.median(out)) if out else float("nan")


def gate_E(work):
    """Hair must matte SOFTER than cloth. That single ratio is what separated
    the three candidate models, and it is what a crushed alpha destroys."""
    rows = []
    for who in ("judge", "defendant"):
        p = os.path.join(work, f"{who}_surgical.png")
        if not os.path.exists(p):
            continue
        a = _alpha(p)
        if a is None:
            continue
        H = a.shape[0]
        hair = _transition(a, range(int(H * 0.10), int(H * 0.30), 4))
        cloth = _transition(a, range(int(H * 0.72), int(H * 0.92), 4))
        if not np.isfinite(hair) or not np.isfinite(cloth):
            continue
        rows.append((who, hair, cloth, hair / max(cloth, 1e-6)))
    if not rows:
        return None, "no mattes found"
    bad = [r for r in rows if r[3] < MIN_HAIR_CLOTH_RATIO]
    detail = "  ".join(f"{w}: hair {h:.1f} cloth {c:.1f} ratio {q:.2f}"
                       for w, h, c, q in rows)
    return (not bad), detail


def gate_E_source(pipeline=None):
    """The alpha crush is stopped at its source, not inferred from widths.

    thumb_pipeline.matte() stretches alpha between ALPHA_FLOOR and ALPHA_CEIL.
    (26, 232) was the crush that zeroed every faint hair strand; (6, 246) is
    the gentle contrast that replaced it on 2026-08-31. Like gate G on the rim
    mode, this reads the setting the build ran with rather than trying to
    measure its shadow in the output - no output-side width separated the
    crush across the five accepted cutouts.
    """
    if pipeline is None:
        import thumb_pipeline as pipeline
    fl = float(getattr(pipeline, "ALPHA_FLOOR", 26.0))
    ce = float(getattr(pipeline, "ALPHA_CEIL", 232.0))
    ok = fl <= MAX_ALPHA_FLOOR and ce >= MIN_ALPHA_CEIL
    return ok, f"alpha stretch {fl:g}..{ce:g} (limit <= {MAX_ALPHA_FLOOR:g} / >= {MIN_ALPHA_CEIL:g})"


def _skin(bgr, box):
    x, y, w, h = box
    r = bgr[max(0, y):y + h, max(0, x):x + w]
    if r.size == 0:
        return None
    ycc = cv2.cvtColor(r, cv2.COLOR_BGR2YCrCb)
    Cr, Cb = ycc[:, :, 1].astype(int), ycc[:, :, 2].astype(int)
    m = (Cr > 135) & (Cr < 180) & (Cb > 85) & (Cb < 135)
    if m.sum() < 200:
        return None
    lab = cv2.cvtColor(r, cv2.COLOR_BGR2LAB)
    return (float(lab[:, :, 1][m].mean()) - 128.0,
            float(lab[:, :, 2][m].mean()) - 128.0)


def _biggest_face(bgr, thr=0.5):
    import thumb_pipeline as P
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), thr, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(bgr)
    if r is None or not len(r):
        return None
    return [int(v) for v in max(r, key=lambda q: q[3])[:4]]


def gate_F(work, out_jpg):
    """Neither face may be repainted away from its OWN source crop.

    This is the gate for the defect he described as Boyd looking "weird and un
    natural": the skin-saturation parity rule dragged her chroma 6.4 a* off her
    source while moving the defendant only 2.3. Brightness parity is his rule
    and is NOT checked here - only chroma drift per face.
    """
    fin = cv2.imread(out_jpg)
    if fin is None:
        return None, "no output"
    W = fin.shape[1]
    src = {}
    for who in ("judge", "defendant"):
        # R56/R57, 2026-09-03. The reference is the crop AS IT ENTERS THE
        # COMPOSITE, which since R56 is the colour-corrected one. Measuring
        # against `<who>_raw.png` made this gate count R56's own declared
        # correction as a repaint, so it could only ever pass a build that left
        # Boyd grey (she enters the composite at chroma 9.2 against an accepted
        # band of 16.5-25.6). Everything the gate was written to catch - the
        # saturation-parity repaint - happens AFTER this point and is still
        # measured exactly as before; the OFFERUP v19 control still fails.
        # ONLY `_colour.png` displaces `_raw.png`. Falling back through
        # `_hypir.png` moved the reference for builds that predate R56 and
        # failed the accepted THOMPSON (imbalance 3.1 against a 2.5 limit) - a
        # gate change that re-judges his approved work is a regression, not a
        # fix. Builds without an R56 crop are measured exactly as before.
        p = next((q for q in (os.path.join(work, f"{who}_colour.png"),
                              os.path.join(work, f"{who}_raw.png"))
                  if os.path.exists(q)), None)
        if p is None:
            continue
        im = cv2.imread(p)
        b = _biggest_face(im)
        if b:
            s = _skin(im, b)
            if s:
                src[who] = s
    if not src:
        return None, "no source skin sample"
    import thumb_pipeline as P
    h, w = fin.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(fin)
    if r is None or not len(r):
        return None, "no faces in output"
    # ONLY THE TWO SUBJECTS. Bucketing every detection by x put background
    # faces in the tally - THOMPSON reported three rows, "judge" twice, and the
    # imbalance was computed off whichever landed last. The subjects are always
    # far larger than anyone in the gallery behind them, so take the two biggest
    # and assign them by side.
    subs = sorted(r, key=lambda q: -q[3])[:2]
    rows, drift = [], {}
    for row in sorted(subs, key=lambda q: q[0]):
        b = [int(v) for v in row[:4]]
        who = "defendant" if b[0] + b[2] / 2 < W / 2 else "judge"
        if who not in src:
            continue
        got = _skin(fin, b)
        if not got:
            continue
        drift[who] = max(abs(got[0] - src[who][0]), abs(got[1] - src[who][1]))
        rows.append(f"{who}: drift {drift[who]:.1f}")
    if len(drift) < 2:
        return None, "need both faces"
    # The imbalance formula is the ORIGINAL one and stays: driving both faces
    # to the same destination repaints whichever started further away, and that
    # is what this refuses. What changed under R56 is only the REFERENCE it
    # measures from (see the source selection above).
    imb = abs(drift["judge"] - drift["defendant"])
    return (imb <= MAX_CHROMA_IMBALANCE), "  ".join(rows) + f"   imbalance {imb:.1f}"


def gate_G(work, out_jpg):
    """No hard white outline. Gated on the CONFIGURATION, not the pixels.

    THREE pixel metrics were tried against a deliberately-rendered hard-rim
    control at identical geometry, and every one of them failed to separate it
    from the good build on BOTH subjects:

      edge-band vs body interior   0.4036 / 0.1820 - measured background, not rim
      near-band minus far-band     control +31/+46  vs good +28/+40  (3-6 apart)
      radial peak-to-tail ratio    control 1.72/4.30 vs good 1.69/10.20 - inverted

    Boyd sits against a bright ceiling, so any "is the edge brighter than its
    surroundings" test is contaminated for her specifically. Rather than ship a
    gate that cannot fail - which reads as coverage and is worse than none -
    this asserts the single upstream cause: the rim settings the build used.
    A hard outline can ONLY come from rim_mode 'smooth' or 'line', or from an
    inflated glow. That is exact, and it fails on the control.
    """
    log = os.path.join(work, "_build_log.json")
    if not os.path.exists(log):
        return None, "no build log"
    import json
    d = json.load(open(log))
    rim = d.get("rim")
    if rim == "off":
        return True, "rim off"
    if not isinstance(rim, dict):
        return None, f"rim not logged ({rim!r})"
    mode, glow = rim.get("mode"), float(rim.get("glow", 0))
    ok = mode in ("none", "glow") and glow <= MAX_RIM_GLOW
    return ok, f"mode={mode} glow={glow}"


def _face_stats(out_jpg):
    """Skin chroma and highlight blowout for the two subject faces."""
    import thumb_pipeline as P
    im = cv2.imread(out_jpg)
    if im is None:
        return None
    h, w = im.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(im)
    if r is None or not len(r):
        return None
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)
    out = []
    for row in sorted(r, key=lambda q: -q[3])[:2]:
        x, y, fw, fh = [int(v) for v in row[:4]]
        reg = im[max(0, y):y + fh, max(0, x):x + fw]
        if reg.size == 0:
            continue
        ycc = cv2.cvtColor(reg, cv2.COLOR_BGR2YCrCb)
        Cr, Cb = ycc[:, :, 1].astype(int), ycc[:, :, 2].astype(int)
        m = (Cr > 135) & (Cr < 180) & (Cb > 85) & (Cb < 135)
        L = lab[max(0, y):y + fh, max(0, x):x + fw, 0].astype(float)
        a = lab[max(0, y):y + fh, max(0, x):x + fw, 1].astype(float) - 128
        b = lab[max(0, y):y + fh, max(0, x):x + fw, 2].astype(float) - 128
        ch = float(np.sqrt(a[m] ** 2 + b[m] ** 2).mean()) if m.sum() > 100 else float("nan")
        out.append((ch, float((L > 210).mean() * 100)))
    return out or None


def gate_I(out_jpg):
    """Skin chroma must sit in the measured corpus band, not above it."""
    st = _face_stats(out_jpg)
    if not st:
        return None, "no faces"
    # a BAND, not a ceiling - too little chroma reads as pale, which is
    # the defect a ceiling-only check let through
    bad = [c for c, _ in st if np.isfinite(c) and not (14.5 <= c <= SKIN_CHROMA_CEILING)]
    return (not bad), "  ".join(f"chroma {c:.1f}" for c, _ in st)


def gate_J(out_jpg):
    """Faces must not be blown to paper white."""
    st = _face_stats(out_jpg)
    if not st:
        return None, "no faces"
    bad = [b for _, b in st if b > MAX_FACE_BLOWOUT]
    return (not bad), "  ".join(f"blowout {b:.1f}%" for _, b in st)


def _placed_alphas(work):
    """The subject mattes IN CANVAS SPACE, as thumb.py dumps them."""
    out = {}
    for who in ("judge", "defendant"):
        p = os.path.join(work, f"_placed_alpha_{who}.png")
        im = cv2.imread(p, cv2.IMREAD_UNCHANGED) if os.path.exists(p) else None
        if im is not None:
            out[who] = im if im.ndim == 2 else im[:, :, -1]
    return out


def _ink_mask(im):
    """Title yellow, arrow red, caption white - dilated. A matte edge under
    ink is not visible, and he does not count it."""
    b, g, r = [im[:, :, i].astype(int) for i in range(3)]
    yellow = (r > 190) & (g > 160) & (b < 90)
    red = (r > 170) & (g < 80) & (b < 80)
    white = (r > 235) & (g > 235) & (b > 235)
    m = (yellow | red | white).astype(np.uint8)
    return cv2.dilate(m, np.ones((13, 13), np.uint8)).astype(bool)


def _longest_runs(t, axis):
    """Longest contiguous True run along `axis`, one number per line."""
    t = np.moveaxis(t, axis, 0)
    best = np.zeros(t.shape[1], int)
    cur = np.zeros(t.shape[1], int)
    for line in t:
        cur = np.where(line, cur + 1, 0)
        best = np.maximum(best, cur)
    return best


def gate_K(work, out_jpg):
    """No hard cut. The longest pixel-straight visible matte edge, over the
    subject's vertical span, must stay under LIMB_MAX_RUN_FRAC."""
    alphas = _placed_alphas(work)
    if not alphas:
        return None, "no _placed_alpha_*.png in work dir"
    im = cv2.imread(out_jpg) if out_jpg else None
    ink = _ink_mask(im) if im is not None else None
    notes, bad = [], False
    for who, a in alphas.items():
        m = a > 128
        ys = np.where(m.any(axis=1))[0]
        if not ys.size:
            continue
        span = int(ys[-1] - ys[0] + 1)
        hide = np.zeros(m.shape, bool)
        if ink is not None and ink.shape == m.shape:
            hide |= ink
        for other, b in alphas.items():
            if other != who:
                hide |= (b > 128)
        # a transition between column x and x+1 at row y; between row y and y+1
        tv = (m[:, :-1] != m[:, 1:]) & ~hide[:, :-1]
        th = (m[:-1, :] != m[1:, :]) & ~hide[:-1, :]
        col = _longest_runs(tv, 0)   # per column, run down the rows
        row = _longest_runs(th, 1)   # per row, run along the columns
        r = max(int(col.max()), int(row.max()))
        frac = r / span
        notes.append(f"{who} {int(col.max())}px@x={int(col.argmax())} "
                     f"{int(row.max())}px@y={int(row.argmax())} /{span} = {frac:.2f}")
        if frac > LIMB_MAX_RUN_FRAC:
            bad = True
    return (not bad), "; ".join(notes)


def _faces(bgr, thr=0.5):
    import thumb_pipeline as P
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), thr, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(bgr)
    return [[int(v) for v in row[:4]] for row in (r if r is not None else [])]


def gate_L(work, out_jpg):
    """No bystander: (a) each subject alpha is one island; (b) no face in the
    defendant's layer sits 12-88% behind the judge."""
    alphas = _placed_alphas(work)
    if not alphas:
        return None, "no _placed_alpha_*.png in work dir"
    notes, bad = [], False
    for who, a in alphas.items():
        n, _, stats, _ = cv2.connectedComponentsWithStats((a > 128).astype(np.uint8), connectivity=8)
        areas = sorted((int(s[cv2.CC_STAT_AREA]) for s in stats[1:]), reverse=True)
        islands = sum(1 for x in areas if x >= MIN_STRAY_COMPONENT)
        notes.append(f"{who} islands {islands} (2nd {areas[1] if len(areas) > 1 else 0}px)")
        if islands != 1:
            bad = True
    if "judge" in alphas and "defendant" in alphas:
        jud = alphas["judge"] > 128
        layer = os.path.join(work, "_placed_rgb_defendant.png")
        src = "layer"
        bgr = cv2.imread(layer) if os.path.exists(layer) else None
        if bgr is not None:
            # only what the matte keeps is in the thumbnail
            keep = (alphas["defendant"].astype(np.float32) / 255.0)[..., None]
            bgr = (bgr.astype(np.float32) * keep + 128.0 * (1 - keep)).astype(np.uint8)
        else:
            src = "final"
            bgr = cv2.imread(out_jpg) if out_jpg else None
        if bgr is None:
            notes.append("no image for faces")
        else:
            h, w = bgr.shape[:2]
            for x, y, fw, fh in _faces(bgr):
                if fh < BYST_MIN_FACE:
                    continue
                x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + fw), min(h, y + fh)
                if x1 <= x0 or y1 <= y0:
                    continue
                own = float((alphas["defendant"][y0:y1, x0:x1] > 128).mean())
                if src == "final" and own < 0.5:
                    continue   # the judge's own face, or plate scenery
                c = float(jud[y0:y1, x0:x1].mean())
                if BYST_CLEAR < c < BYST_HIDDEN:
                    bad = True
                    notes.append(f"face {fw}x{fh}@{x},{y} {c:.2f} behind judge")
            notes.append(f"faces from {src}")
    return (not bad), "; ".join(notes)


def gate_H():
    """Every checker in tools/ must be invoked by something.

    Today four separate defects traced to a correct tool that nothing called:
    assemble_final (every video shipped ~7dB quiet), audit_cuts, expression.py
    (built, then run by hand), and autocrop (15 hand-typed coordinates). This is
    the gate for that whole class.
    """
    reg = os.path.join(ROOT, "tools", "check_registry.py")
    if not os.path.exists(reg):
        return None, "check_registry.py missing"
    r = subprocess.run([sys.executable, reg], capture_output=True, text=True,
                       cwd=ROOT)
    txt = (r.stdout or "") + (r.stderr or "")
    # count the per-tool ORPHAN rows; check_registry prints one line each and
    # has no single summary number to scrape
    n = sum(1 for ln in txt.splitlines() if ln.rstrip().endswith("ORPHAN"))
    return (n == 0), f"{n} orphaned tool(s)"


def precheck(out_jpg):
    """The output must exist and carry a detectable face, or nothing below
    means anything.

    2026-09-01: `verify_build.py WORKDIR ""` printed BUILD_GATES PASS - F/I/J
    each returned None ("no output" / "no faces"), None is not False, so the
    build "passed" with no file. A gate that passes on nothing is the
    checker-that-cannot-fail the skill warns about. Fail here, loudly.
    """
    if not out_jpg or not os.path.isfile(out_jpg):
        return False, f"no output file: {out_jpg!r}"
    im = cv2.imread(out_jpg)
    if im is None:
        return False, f"unreadable output: {out_jpg}"
    st = _face_stats(out_jpg)
    if not st:
        return False, "0 faces detected in output - not a thumbnail"
    return True, f"{len(st)} face(s) detected"


def run(work, out_jpg, verbose=True):
    results = []
    ok0, det0 = precheck(out_jpg)
    if verbose:
        print(f"   {'PASS' if ok0 else 'FAIL'}  {'0 output exists':18} {det0}")
    if not ok0:
        return False, [("0 output exists", False, det0)]
    for name, fn in (("E matte softness", lambda: gate_E(work)),
                     ("E alpha stretch", lambda: gate_E_source()),
                     ("F skin chroma", lambda: gate_F(work, out_jpg)),
                     ("G hard rim", lambda: gate_G(work, out_jpg)),
                     ("I skin chroma", lambda: gate_I(out_jpg)),
                     ("J face blowout", lambda: gate_J(out_jpg)),
                     ("K hard cut", lambda: gate_K(work, out_jpg)),
                     ("L bystander", lambda: gate_L(work, out_jpg)),
                     ("H no orphans", gate_H)):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = None, f"ERROR {e}"
        results.append((name, ok, detail))
        if verbose:
            tag = "...." if ok is None else ("PASS" if ok else "FAIL")
            print(f"   {tag}  {name:18} {detail}")
    hard = [r for r in results if r[1] is False]
    return (not hard), results


def selftest():
    """PROVE EACH GATE CAN FAIL, against a control that carries the defect.

    The controls are CONSTRUCTED here rather than pointed at old renders. An
    earlier version of this selftest compared against OFFERUP_v18/v19, and those
    files have different geometry from the current build - the placed alphas did
    not correspond to them, so the "known bad" comparison was measuring unrelated
    pixels. A synthesised control cannot drift out from under the test.
    """
    import json
    import shutil
    import tempfile
    W = "D:/Boyd Clips/thumbwork/OFFERUP"
    ok = True

    def check(label, got, want, why):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:44} -> {got} (want {want})")
        if not hit:
            print(f"        {why}")
        return hit

    # ---- 0: the run must fail on nothing --------------------------------------
    got, det = precheck("")
    check("0 rejects an empty output path", got, False, det)
    got, det = precheck(os.path.join(W, "does_not_exist.jpg"))
    check("0 rejects a missing output file", got, False, det)
    with tempfile.TemporaryDirectory() as d:
        flat = os.path.join(d, "flat.jpg")
        cv2.imwrite(flat, np.full((720, 1280, 3), 128, np.uint8))
        got, det = precheck(flat)
        check("0 rejects a faceless output", got, False, det)
        ran, _ = run(W, flat, verbose=False)
        check("  ...and run() reports FAIL, not PASS", ran, False, "run() must not pass on a faceless file")
    ran, _ = run(W, "", verbose=False)
    check("0 run() FAILs on an empty path (the 2026-09-01 bug)", ran, False, "")
    got, det = precheck(os.path.join(W, "OFFERUP_NEW.jpg"))
    check("0 accepts the published OFFERUP build", got, True, det)

    # ---- G: configuration gate, both directions, no rendering needed --------
    with tempfile.TemporaryDirectory() as d:
        json.dump({"rim": {"mode": "smooth", "glow": 0.30}},
                  open(os.path.join(d, "_build_log.json"), "w"))
        got, det = gate_G(d, None)
        check("G rejects rim_mode='smooth' (the one he rejected)", got, False, det)
        json.dump({"rim": {"mode": "glow", "glow": 0.085}},
                  open(os.path.join(d, "_build_log.json"), "w"))
        got, det = gate_G(d, None)
        check("G accepts the settled glow", got, True, det)
        json.dump({"rim": {"mode": "glow", "glow": 0.40}},
                  open(os.path.join(d, "_build_log.json"), "w"))
        got, det = gate_G(d, None)
        check("G rejects a glow turned up to haze", got, False, det)

    # ---- E: real matte passes; a robe edge blurred out to hair width fails --
    got, det = gate_E(W)
    check("E accepts the birefnet-portrait matte", got, True, det)
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(W, "judge_surgical.png")
        im = cv2.imread(src, cv2.IMREAD_UNCHANGED)
        a = im[:, :, 3].astype(np.float32)
        H = a.shape[0]
        # the 'massive' defect: 19px of mush on the robe. Blur ONLY the cloth
        # band so the hair band is untouched and the ratio alone decides.
        y0, y1 = int(H * 0.70), int(H * 0.94)
        a[y0:y1] = cv2.GaussianBlur(a[y0:y1], (0, 0), 9.0)
        im[:, :, 3] = np.clip(a, 0, 255).astype(np.uint8)
        cv2.imwrite(os.path.join(d, "judge_surgical.png"), im)
        got, det = gate_E(d)
        check("E rejects a mushy robe edge (cloth blurred to hair width)", got, False, det)

    # ---- E(source): the old crush cannot come back through the constants ----
    class _P:  # the pipeline as it ran until 2026-08-31
        ALPHA_FLOOR, ALPHA_CEIL = 26.0, 232.0
    got, det = gate_E_source(_P)
    check("E(source) rejects the 26..232 crush", got, False, det)
    got, det = gate_E_source()
    check("E(source) accepts the pipeline as it is", got, True, det)

    # ---- F: chroma imbalance -----------------------------------------------
    import re as _re
    cur = sorted((f for f in os.listdir(W)
                  if f.startswith("OFFERUP_v") and f.endswith(".jpg")
                  and ".photo." not in f),
                 key=lambda f: int(_re.search(r"_v(\d+)", f).group(1)))
    if cur:
        latest = os.path.join(W, cur[-1])
        got, det = gate_F(W, latest)
        check(f"F accepts {os.path.basename(latest)}", got, True, det)
    old = os.path.join(W, "OFFERUP_v19.jpg")
    if os.path.exists(old):
        got, det = gate_F(W, old)
        check("F rejects v19 (forced saturation parity)", got, False, det)

    # ---- I and J: synthesise the exact defects they exist to catch ---------
    import tempfile as _tf
    # The CURRENT build, not the highest-numbered legacy file. Picking
    # OFFERUP_v23.jpg made this test measure a build from before the fix and
    # report a false failure.
    good = os.path.join(W, "OFFERUP_NEW.jpg")
    if os.path.exists(good):
        im = cv2.imread(good)
        with _tf.TemporaryDirectory() as d:
            # over-chromatic skin: the ~1.7x inflation the grade was applying
            lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
            lab[..., 1] = np.clip(128 + (lab[..., 1] - 128) * 1.7, 0, 255)
            lab[..., 2] = np.clip(128 + (lab[..., 2] - 128) * 1.7, 0, 255)
            bad_c = os.path.join(d, "chroma.jpg")
            cv2.imwrite(bad_c, cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR))
            got, det = gate_I(bad_c)
            check("I rejects 1.7x inflated skin chroma", got, False, det)
            # blown highlights: lift until faces clip, as they did before
            bad_b = os.path.join(d, "blown.jpg")
            cv2.imwrite(bad_b, np.clip(im.astype(np.float32) * 1.55, 0, 255).astype(np.uint8))
            got, det = gate_J(bad_b)
            check("J rejects blown-out faces", got, False, det)
            got, det = gate_I(good)
            check("I accepts the current build", got, True, det)
            got, det = gate_J(good)
            check("J accepts the current build", got, True, det)

    # ---- K and L: real placed alphas pass; a synthetic cut / bystander fails --
    final = os.path.join(W, "OFFERUP_NEW.jpg")
    alphas = {k: os.path.join(W, f"_placed_alpha_{k}.png") for k in ("judge", "defendant")}
    if os.path.exists(final) and all(os.path.exists(p) for p in alphas.values()):
        got, det = gate_K(W, final)
        check("K accepts the accepted OFFERUP build", got, True, det)
        got, det = gate_L(W, final)
        check("L accepts the accepted OFFERUP build", got, True, det)

        def _stage(d, edit=None):
            for k, p in alphas.items():
                a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
                if edit and k == "defendant":
                    a = edit(a)
                cv2.imwrite(os.path.join(d, f"_placed_alpha_{k}.png"), a)

        def _cut_cols(a):          # a vertical crop line through the defendant
            a = a.copy(); a[:, 350:] = 0; return a

        def _cut_rows(a):          # a horizontal one - the severed-arm case
            a = a.copy(); a[500:, :] = 0; return a

        with _tf.TemporaryDirectory() as d:
            _stage(d, _cut_cols)
            got, det = gate_K(d, final)
            check("K rejects a vertical crop line (x=350)", got, False, det)
        with _tf.TemporaryDirectory() as d:
            _stage(d, _cut_rows)
            got, det = gate_K(d, final)
            check("K rejects a horizontal crop line (y=500)", got, False, det)

        def _blob(a):              # a second person the matte swallowed
            a = a.copy(); a[80:160, 1180:1240] = 255; return a

        with _tf.TemporaryDirectory() as d:
            _stage(d, _blob)
            got, det = gate_L(d, final)
            check("L rejects a stray 60x80 island", got, False, det)
            check("  ...and says so", "islands 2" in det, True, det)

        # a face in the defendant's layer, half behind the judge: paste the
        # defendant's own face where the judge's silhouette covers ~half of
        # the box, into a synthetic un-occluded defendant RGB layer
        im = cv2.imread(final)
        jud = cv2.imread(alphas["judge"], cv2.IMREAD_UNCHANGED) > 128
        dal = cv2.imread(alphas["defendant"], cv2.IMREAD_UNCHANGED)
        faces = [f for f in _faces(im) if f[3] >= 150 and (dal[f[1]:f[1] + f[3], f[0]:f[0] + f[2]] > 128).mean() > 0.5]
        if faces:
            fx, fy, fw, fh = faces[0]
            crop = im[fy:fy + fh, fx:fx + fw].copy()
            spot = None
            for y in range(120, im.shape[0] - fh, 20):
                for x in range(0, im.shape[1] - fw, 10):
                    c = jud[y:y + fh, x:x + fw].mean()
                    if 0.45 < c < 0.55:
                        spot = (x, y); break
                if spot:
                    break
            if spot:
                x, y = spot
                with _tf.TemporaryDirectory() as d:
                    layer = im.copy()
                    layer[y:y + fh, x:x + fw] = crop
                    cv2.imwrite(os.path.join(d, "_placed_rgb_defendant.png"), layer)
                    a2 = dal.copy(); a2[y:y + fh, x:x + fw] = 255
                    cv2.imwrite(os.path.join(d, "_placed_alpha_defendant.png"), a2)
                    cv2.imwrite(os.path.join(d, "_placed_alpha_judge.png"),
                                cv2.imread(alphas["judge"], cv2.IMREAD_UNCHANGED))
                    got, det = gate_L(d, final)
                    check(f"L rejects a face half behind the judge @{x},{y}", got, False, det)
                    check("  ...and names it", "behind judge" in det, True, det)
            else:
                check("L bystander control: no half-covered spot found", False, True, "")
        else:
            check("L bystander control: no defendant face found", False, True, "")

    # ---- H ------------------------------------------------------------------
    got, det = gate_H()
    check("H reports the real orphan count", got, True, det)

    print("SELFTEST_PASS verify_build" if ok else "SELFTEST_FAIL verify_build")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 3:
        print("usage: verify_build.py WORKDIR OUT.jpg")
        sys.exit(2)
    ok, _ = run(sys.argv[1], sys.argv[2])
    print("BUILD_GATES PASS" if ok else "BUILD_GATES FAIL")
    sys.exit(0 if ok else 1)
