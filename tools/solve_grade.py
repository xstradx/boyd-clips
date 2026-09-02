# -*- coding: utf-8 -*-
"""Solve a short's ffmpeg grade so its skin matches the thumbnail standard.

Nathan, 2026-08-31: *"that short was made off the old rules or whatever and
should be made with our new ones"*.

He is right and it is measurable. `tools/make_short.py` carries two hardcoded
filters - `eq=brightness=-0.149:contrast=1.10:saturation=1.45` on the top tile
and `-0.0201:1.06:1.16` on the bottom - written once and never checked against
an output. Measured on OFFERUP_SHORT_FINAL.mp4 at t=8/20/32s:

    skin L* 176.6 / 173.4 / 166.5      chroma 12.7 / 12.9 / 13.1

against the tone he chose for the thumbnails (v23): **L* 134.0, chroma 20.6**.
Bright and undersaturated - the exact "pale" defect he named in the stills,
sitting unnoticed in the video grade the whole time.

Note the trap this avoids: saturation was ALREADY set to 1.45, the highest value
in the file, and the result still measured chroma 12.7. A constant that looks
aggressive in source is not evidence of an aggressive result. Only the rendered
frame is.

So the grade is SOLVED against rendered frames rather than typed: sweep the eq
parameters, render, measure the skin, keep what lands closest.
"""
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The tone Nathan picked, from v23. Kept in ONE place so the short and the
# thumbnail cannot drift apart again.
# DERIVED FROM A SHIPPED SHORT, not from a thumbnail.
# Nathan, 2026-08-31: "in another short you normalized the colors and made it
# look hd why didn't you do that you told me that was the new floor".
#
# The earlier target here came from the THUMBNAIL floor (v23: L*134/20.6) and
# he rejected the result as over-processed - a still composite is not footage.
# These come from SANCHEZ_SHORT_FINAL.mp4, a short he shipped and likes:
#
#   SANCHEZ (shipped)   skin L*123.2  chroma 19.7  contrast sd 74.3
#   CARTHIEF V2         skin L*125.9  chroma 14.0  contrast sd 74.4
#   OFFERUP (old)       skin L*167.9  chroma 12.7  contrast sd 58.3
#
# OFFERUP is the outlier on every axis - bright, flat and undersaturated, which
# is exactly "not HD". SANCHEZ is the floor for shorts.
TARGET_L = 123.2
TARGET_CHROMA = 19.7
TARGET_CONTRAST_SD = 74.3


def skin_of(bgr):
    """(L*, chroma) of the largest face's skin, or None."""
    import thumb_pipeline as P
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(P.YUNET, "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(bgr)
    if r is None or not len(r):
        return None
    x, y, fw, fh = [int(v) for v in max(r, key=lambda q: q[3])[:4]]
    reg = bgr[max(0, y):y + fh, max(0, x):x + fw]
    if reg.size == 0:
        return None
    ycc = cv2.cvtColor(reg, cv2.COLOR_BGR2YCrCb)
    Cr, Cb = ycc[:, :, 1].astype(int), ycc[:, :, 2].astype(int)
    m = (Cr > 135) & (Cr < 180) & (Cb > 85) & (Cb < 135)
    if m.sum() < 100:
        return None
    lab = cv2.cvtColor(reg, cv2.COLOR_BGR2LAB)
    L = float(lab[:, :, 0][m].mean())
    a = float(lab[:, :, 1][m].mean()) - 128.0
    b = float(lab[:, :, 2][m].mean()) - 128.0
    return L, float(np.sqrt(a * a + b * b))


def frames(video, times):
    out = []
    with tempfile.TemporaryDirectory() as d:
        for t in times:
            p = os.path.join(d, f"f{t}.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t),
                            "-i", video, "-frames:v", "1", p], capture_output=True)
            im = cv2.imread(p)
            if im is not None:
                out.append(im)
    return out


def apply_eq(bgr, brightness, contrast, saturation):
    """The same maths ffmpeg's eq filter applies, done in numpy so a sweep does
    not cost one video encode per candidate."""
    f = bgr.astype(np.float32) / 255.0
    f = (f - 0.5) * contrast + 0.5 + brightness
    f = np.clip(f, 0, 1)
    g = f.mean(axis=2, keepdims=True)
    f = np.clip(g + (f - g) * saturation, 0, 1)
    return (f * 255).astype(np.uint8)


def solve(video, times=(8, 20, 32), verbose=True):
    """Search eq parameters that land skin on the target across sample frames."""
    fr = frames(video, times)
    if not fr:
        raise SystemExit("no frames")
    best = None
    for br in np.arange(-0.28, 0.03, 0.02):
        for ct in (1.00, 1.06, 1.12, 1.18, 1.24):
            for sa in np.arange(1.2, 2.61, 0.1):
                Ls, Cs = [], []
                for im in fr:
                    s = skin_of(apply_eq(im, float(br), float(ct), float(sa)))
                    if s:
                        Ls.append(s[0]); Cs.append(s[1])
                if not Ls:
                    continue
                dl = abs(np.mean(Ls) - TARGET_L)
                dc = abs(np.mean(Cs) - TARGET_CHROMA)
                # chroma weighted higher: "pale" is the defect being fixed
                err = dl / 8.0 + dc / 2.0
                if best is None or err < best[0]:
                    best = (err, float(br), float(ct), float(sa),
                            float(np.mean(Ls)), float(np.mean(Cs)))
    if not best:
        raise SystemExit("no face found in any sampled frame")
    err, br, ct, sa, L, C = best
    if verbose:
        print(f"  solved eq=brightness={br:.3f}:contrast={ct:.2f}:saturation={sa:.2f}")
        print(f"  predicted skin L*={L:.1f} chroma={C:.1f}   "
              f"(target {TARGET_L} / {TARGET_CHROMA})")
    return dict(brightness=round(br, 3), contrast=round(ct, 2),
                saturation=round(sa, 2), pred_L=round(L, 1), pred_chroma=round(C, 1))


def selftest():
    """The solver must move a known-pale input TOWARD the target, and must not
    claim success on a frame with no face."""
    ok = True
    v = "D:/Boyd Clips/READY-TO-POST/OFFERUP_SHORT_FINAL.mp4"
    if not os.path.exists(v):
        print("  SELFTEST_SKIP control video missing")
        return 0
    fr = frames(v, (8, 20, 32))
    before = [skin_of(im) for im in fr]
    before = [b for b in before if b]
    r = solve(v, verbose=True)
    after_L, after_C = r["pred_L"], r["pred_chroma"]
    b_L = float(np.mean([b[0] for b in before])); b_C = float(np.mean([b[1] for b in before]))
    print(f"  before  L*={b_L:.1f} chroma={b_C:.1f}")
    print(f"  after   L*={after_L:.1f} chroma={after_C:.1f}")
    if not (abs(after_C - TARGET_CHROMA) < abs(b_C - TARGET_CHROMA)):
        print("  FAIL chroma did not move toward the target"); ok = False
    if not (abs(after_L - TARGET_L) < abs(b_L - TARGET_L)):
        print("  FAIL luminance did not move toward the target"); ok = False
    blank = np.zeros((400, 400, 3), np.uint8)
    if skin_of(blank) is not None:
        print("  FAIL claimed skin on a blank frame"); ok = False
    print("SELFTEST_PASS solve_grade" if ok else "SELFTEST_FAIL solve_grade")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 2:
        print("usage: solve_grade.py VIDEO | --selftest")
        sys.exit(2)
    solve(sys.argv[1])
